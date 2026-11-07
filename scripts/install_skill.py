#!/usr/bin/env python3
"""Install the AIHub4All Agent Skill for Codex and/or Claude Code."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_SOURCE = REPO_ROOT / "skills" / "aihub-access"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=("user", "project"),
        default="user",
        help="Install into the current user's home directory or the current project.",
    )
    parser.add_argument(
        "--targets",
        default="codex,claude",
        help="Comma-separated targets: codex,claude (default: both).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing installed skill directory.",
    )
    args = parser.parse_args()

    targets = {item.strip().lower() for item in args.targets.split(",") if item.strip()}
    unknown = targets - {"codex", "claude"}
    if unknown or not targets:
        parser.error(f"Unknown or empty target selection: {', '.join(sorted(unknown))}")

    base = Path.home() if args.scope == "user" else Path.cwd()
    locations = {
        "codex": base / ".agents" / "skills",
        "claude": base / ".claude" / "skills",
    }

    for target in sorted(targets):
        destination = locations[target] / "aihub-access"
        if destination.exists():
            if not args.force:
                raise SystemExit(
                    f"{destination} already exists. Review it or rerun with --force."
                )
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SKILL_SOURCE, destination)
        print(f"Installed {target} skill: {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
