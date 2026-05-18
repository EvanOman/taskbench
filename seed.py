#!/usr/bin/env python3
"""Seed Planka with the canonical 25-task TaskFlow dataset.

Usage:
    uv run python seed.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from plankapy.v2 import Planka

PLANKA_URL = "http://localhost:18920"
PLANKA_USER = "admin"
PLANKA_PASS = "Planka!Admin2025#Secure"
SEED_FILE = Path("/home/evan/dev/clickup-tools/eval/seed/taskflow.json")

STATUS_COLUMNS = ["to do", "in progress", "review", "complete"]


def main() -> None:
    seed_data = json.loads(SEED_FILE.read_text())

    planka = Planka(PLANKA_URL)
    planka.login(username=PLANKA_USER, password=PLANKA_PASS, accept_terms=True)
    me = planka.me
    print(f"Logged in as {me.name} (id={me.id})")

    # Check if project already exists
    existing = [p for p in planka.projects if p.name == seed_data["project_name"]]
    if existing:
        print(f"Project '{seed_data['project_name']}' already exists (id={existing[0].id}). Deleting...")
        existing[0].delete()

    # Create the project
    project = planka.create_project(name=seed_data["project_name"], type="private")
    print(f"Created project: {project.name} (id={project.id})")

    cards_created = 0
    comments_created = 0

    for list_spec in seed_data["lists"]:
        board = project.create_board(name=list_spec["name"], position="bottom")
        print(f"  Created board: {board.name} (id={board.id})")

        # Create status columns (Planka Lists) for each board
        planka_lists: dict[str, object] = {}
        for status_name in STATUS_COLUMNS:
            pl = board.create_list(name=status_name, position="bottom")
            planka_lists[status_name] = pl
            print(f"    Created list/column: {pl.name} (id={pl.id})")

        # Insert cards into the correct column
        for task in list_spec["tasks"]:
            status = task["status"]
            target_list = planka_lists.get(status)
            if target_list is None:
                print(f"    WARNING: Unknown status '{status}', defaulting to 'to do'")
                target_list = planka_lists["to do"]

            card = target_list.create_card(
                name=task["name"],
                description=task.get("description"),
                position="bottom",
            )
            cards_created += 1
            print(f"      Card: {card.name} (id={card.id}, status={status})")

            # Add comments
            for comment_spec in task.get("comments", []):
                card.comment(comment_spec["text"])
                comments_created += 1
                print(f"        Comment added: {comment_spec['text'][:50]}...")

    print(f"\nSeed complete: {cards_created} cards, {comments_created} comments")
    return


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
