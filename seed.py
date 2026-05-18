#!/usr/bin/env python3
"""Seed Todoist with canonical 25 tasks from taskflow.json."""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    from todoist_api_python.api_async import TodoistAPIAsync

    token = os.getenv("TODOIST_TOKEN")
    if not token:
        print("TODOIST_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    seed_path = Path(__file__).parent.parent.parent / "eval" / "seed" / "taskflow.json"
    if not seed_path.exists():
        # Try alternate path
        seed_path = Path("/home/evan/dev/clickup-tools/eval/seed/taskflow.json")
    seed = json.loads(seed_path.read_text())

    api = TodoistAPIAsync(token)

    statuses = [s["name"] for s in seed["statuses"]]
    print(f"Statuses to create as sections: {statuses}")

    # Track created resources
    project_map: dict[str, str] = {}  # key -> project_id
    section_map: dict[str, dict[str, str]] = {}  # project_key -> {status_name: section_id}
    tasks_created = 0
    comments_created = 0

    # Create projects
    for list_def in seed["lists"]:
        key = list_def["key"]
        name = list_def["name"]
        print(f"Creating project: {name}")
        project = await api.add_project(name=name, view_style="board")
        project_map[key] = project.id
        print(f"  -> Project ID: {project.id}")

        # Create sections for each status
        section_map[key] = {}
        for i, status_name in enumerate(statuses):
            section = await api.add_section(name=status_name, project_id=project.id, order=i)
            section_map[key][status_name] = section.id
            print(f"  -> Section '{status_name}' ID: {section.id}")

    # Create tasks
    for list_def in seed["lists"]:
        key = list_def["key"]
        project_id = project_map[key]
        print(f"\nSeeding tasks for project: {list_def['name']}")

        for task_def in list_def["tasks"]:
            status = task_def["status"]
            section_id = section_map[key].get(status)
            priority = task_def.get("priority")

            # Todoist priority: 1=normal(lowest), 4=urgent(highest)
            # Our seed: 1=urgent, 2=high, 3=normal, 4=low
            # Mapping: seed 1 -> todoist 4, seed 2 -> todoist 3, seed 3 -> todoist 2, seed 4 -> todoist 1
            todoist_priority = (5 - priority) if priority else 1

            task = await api.add_task(
                content=task_def["name"],
                description=task_def.get("description", ""),
                project_id=project_id,
                section_id=section_id,
                priority=todoist_priority,
            )
            tasks_created += 1
            print(f"  [+] Task: {task_def['name'][:50]}... -> {task.id} (section={status})")

            # Add comments
            for comment_def in task_def.get("comments", []):
                comment = await api.add_comment(
                    content=comment_def["text"],
                    task_id=task.id,
                )
                comments_created += 1
                print(f"      Comment: {comment.id}")

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.2)

    await api.close()

    print("\n=== Seed complete ===")
    print(f"Projects created: {len(project_map)}")
    print(f"Sections created: {sum(len(v) for v in section_map.values())}")
    print(f"Tasks created: {tasks_created}")
    print(f"Comments created: {comments_created}")

    # Write project IDs for reference
    ref = {
        "projects": project_map,
        "sections": section_map,
    }
    ref_path = Path(__file__).parent / ".todoist_seed_ref.json"
    ref_path.write_text(json.dumps(ref, indent=2))
    print(f"\nReference IDs saved to {ref_path}")


if __name__ == "__main__":
    asyncio.run(main())
