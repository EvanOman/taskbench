#!/usr/bin/env python3
"""Seed a Plane instance with the canonical 25-task TaskFlow dataset.

Usage:
    uv run python seed.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

PLANE_URL = "http://localhost:18930"
PLANE_TOKEN = "plane_api_1b296e1b3ab342efbbcc4d97c4873af2"
WORKSPACE_SLUG = "taskflow"

SEED_FILE = Path("/home/evan/dev/clickup-tools/eval/seed/taskflow.json")

HEADERS = {
    "X-API-Key": PLANE_TOKEN,
    "Content-Type": "application/json",
}

BASE = f"{PLANE_URL}/api/v1/workspaces/{WORKSPACE_SLUG}"

# Plane state groups mapping from our seed status names
STATUS_TO_GROUP = {
    "to do": "unstarted",
    "in progress": "started",
    "review": "started",
    "complete": "completed",
}


def api_get(path: str, params: dict | None = None) -> dict:
    r = httpx.get(f"{BASE}{path}", headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path: str, data: dict) -> dict:
    r = httpx.post(f"{BASE}{path}", headers=HEADERS, json=data, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  ERROR {r.status_code}: {r.text[:500]}", file=sys.stderr)
    r.raise_for_status()
    return r.json()


def api_patch(path: str, data: dict) -> dict:
    r = httpx.patch(f"{BASE}{path}", headers=HEADERS, json=data, timeout=30)
    r.raise_for_status()
    return r.json()


def api_delete(path: str) -> None:
    r = httpx.delete(f"{BASE}{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()


# Plane priority mapping: seed uses 1=urgent,2=high,3=normal,4=low
# Plane uses: urgent, high, medium, low, none
PRIORITY_MAP = {
    1: "urgent",
    2: "high",
    3: "medium",
    4: "low",
}


def create_project(name: str, identifier: str, description: str) -> dict:
    print(f"Creating project: {name} ({identifier})")
    return api_post("/projects/", {
        "name": name,
        "identifier": identifier,
        "description": description,
    })


def get_states(project_id: str) -> list[dict]:
    resp = api_get(f"/projects/{project_id}/states/")
    return resp.get("results", [])


def create_state(project_id: str, name: str, group: str, color: str, sequence: float) -> dict:
    print(f"  Creating state: {name} (group={group})")
    return api_post(f"/projects/{project_id}/states/", {
        "name": name,
        "color": color,
        "group": group,
        "sequence": sequence,
    })


def create_work_item(project_id: str, name: str, description: str, state_id: str, priority: str) -> dict:
    return api_post(f"/projects/{project_id}/work-items/", {
        "name": name,
        "description_html": f"<p>{description}</p>",
        "state": state_id,
        "priority": priority,
    })


def create_comment(project_id: str, work_item_id: str, text: str) -> dict:
    return api_post(f"/projects/{project_id}/work-items/{work_item_id}/comments/", {
        "comment_html": f"<p>{text}</p>",
    })


def main() -> None:
    seed = json.loads(SEED_FILE.read_text())
    statuses = seed["statuses"]

    total_tasks = 0
    total_comments = 0
    project_ids = {}  # key -> project_id

    for list_def in seed["lists"]:
        key = list_def["key"]
        name = list_def["name"]
        desc = list_def.get("description", "")
        identifier = key[:5].upper()

        # Create project
        project = create_project(name, identifier, desc)
        project_id = project["id"]
        project_ids[key] = project_id
        print(f"  Project ID: {project_id}")

        # Get existing default states
        existing_states = get_states(project_id)
        print(f"  Existing states: {[s['name'] for s in existing_states]}")

        # Create our custom states, mapping to Plane groups
        state_map = {}  # status_name -> state_id
        for i, status in enumerate(statuses):
            sname = status["name"]
            group = STATUS_TO_GROUP[sname]
            color = status["color"]

            # Check if a matching state already exists
            found = None
            for es in existing_states:
                if es["name"].lower() == sname.lower():
                    found = es
                    break

            if found:
                state_map[sname] = found["id"]
                print(f"  State '{sname}' already exists: {found['id']}")
            else:
                state = create_state(project_id, sname, group, color, float(i + 10))
                state_map[sname] = state["id"]

        # Delete default states that we don't need (to keep kanban clean)
        for es in existing_states:
            if es["name"].lower() not in state_map:
                try:
                    print(f"  Removing default state: {es['name']}")
                    api_delete(f"/projects/{project_id}/states/{es['id']}/")
                except Exception as e:
                    print(f"  Could not delete state {es['name']}: {e}")

        # Create tasks
        for task_def in list_def["tasks"]:
            task_name = task_def["name"]
            task_desc = task_def.get("description", "")
            task_status = task_def["status"]
            task_priority = PRIORITY_MAP.get(task_def.get("priority", 3), "medium")

            state_id = state_map.get(task_status)
            if not state_id:
                print(f"  WARNING: No state for '{task_status}', using first available")
                state_id = next(iter(state_map.values()))

            work_item = create_work_item(project_id, task_name, task_desc, state_id, task_priority)
            total_tasks += 1
            wi_id = work_item["id"]
            print(f"  [{total_tasks}] Created: {task_name} (id={wi_id}, status={task_status})")

            # Create comments
            for comment_def in task_def.get("comments", []):
                comment = create_comment(project_id, wi_id, comment_def["text"])
                total_comments += 1
                print(f"       Comment: {comment_def['text'][:50]}...")

    print(f"\n{'='*60}")
    print(f"Seeding complete!")
    print(f"  Tasks created: {total_tasks}")
    print(f"  Comments created: {total_comments}")
    print(f"  Projects: {list(project_ids.keys())}")
    for k, v in project_ids.items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
