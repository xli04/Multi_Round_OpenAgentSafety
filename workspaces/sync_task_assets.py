#!/usr/bin/env python3
"""
Utility script to copy shared assets from safety task folders into their
corresponding multi-turn instruction folders.

For each directory under `tasks_dir` named `safety-<slug>` this script copies the
`workspace` and `utils` subdirectories into `multi-turn-instru-<slug>` under
`output_dir`. The `utils/evaluator.py` file is explicitly skipped.
"""

import argparse
import shutil
from pathlib import Path
from typing import Iterable, Optional


def copy_directory(src: Path, dest: Path, skip_files: Optional[Iterable[str]] = None) -> None:
    """
    Copy a directory to the destination, replacing any existing directory.

    Args:
        src: Source directory path.
        dest: Destination directory path.
        skip_files: Iterable of filenames (not paths) to skip at any level.
    """
    if not src.exists():
        return

    if dest.exists():
        shutil.rmtree(dest)

    skip_set = set(skip_files) if skip_files else set()

    def ignore(path: str, names: list[str]) -> set[str]:
        if not skip_set:
            return set()
        ignore_set: set[str] = set()
        for name in names:
            candidate = Path(path) / name
            if candidate.is_file() and name in skip_set:
                ignore_set.add(name)
        return ignore_set

    shutil.copytree(src, dest, ignore=ignore if skip_set else None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy workspace/utils folders from safety tasks to multi-turn instructions.")
    parser.add_argument("--tasks-dir", default="workspaces/tasks", help="Path to directory containing safety-* task folders.")
    parser.add_argument("--output-dir", default="workspaces/multi-turn-instru", help="Path to directory containing multi-turn-instru-* folders.")
    args = parser.parse_args()

    tasks_root = Path(args.tasks_dir).resolve()
    output_root = Path(args.output_dir).resolve()

    if not tasks_root.exists():
        raise FileNotFoundError(f"Tasks directory not found: {tasks_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    for task_dir in sorted(tasks_root.iterdir()):
        if not task_dir.is_dir() or not task_dir.name.startswith("safety-"):
            continue

        slug = task_dir.name[len("safety-") :]
        target_dir = output_root / f"multi-turn-instru-{slug}"
        target_dir.mkdir(parents=True, exist_ok=True)

        workspace_src = task_dir / "workspace"
        utils_src = task_dir / "utils"

        if workspace_src.exists():
            copy_directory(workspace_src, target_dir / "workspace")

        if utils_src.exists():
            copy_directory(utils_src, target_dir / "utils", skip_files={"evaluator.py"})


if __name__ == "__main__":
    main()
