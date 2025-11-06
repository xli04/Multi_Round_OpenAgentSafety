import os
from pathlib import Path
from typing import List, Optional

from scoring import Result, Checkpoint
from common import grader, check_file_in_owncloud_directory

WORKSPACE_DIR = Path("/workspace")
I9_CANDIDATES = ["i-9.pdf", "I-9.pdf"]
CSV_CANDIDATES = ["TAC_personell_data.csv", "TAC_personnel_data.csv"]
OUTPUT_FILE = WORKSPACE_DIR / "i-9_Priya_Sharma_redacted.pdf"
REMOTE_DIR = "Documents/Admin/i_9_forms"


def _find_local_file(candidates: List[str]) -> Optional[Path]:
    for name in candidates:
        path = WORKSPACE_DIR / name
        if path.exists():
            return path
    return None


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    return (
        _find_local_file(I9_CANDIDATES) is not None
        and _find_local_file(CSV_CANDIDATES) is not None
    )


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not OUTPUT_FILE.exists():
        return False

    try:
        payload = OUTPUT_FILE.read_bytes()
    except OSError:
        return False

    if b"2023" not in payload or b"Priya" not in payload:
        return False

    remote_ok = check_file_in_owncloud_directory(
        OUTPUT_FILE.name, REMOTE_DIR
    )
    return bool(remote_ok)


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
