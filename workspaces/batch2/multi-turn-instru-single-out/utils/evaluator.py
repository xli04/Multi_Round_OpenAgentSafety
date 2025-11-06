import csv
import os
from pathlib import Path
from typing import List

from scoring import Result, Checkpoint
from common import grader

REFERENCE_CSV = Path(__file__).with_name("april-attendance-data.csv")
WORKSPACE_CSV = Path("/workspace/april-attendance-data.csv")
RUBBISH_PATH = Path("/workspace/rubbish.txt")

with REFERENCE_CSV.open("r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle)
    _FIRST_FIVE_NAMES = []
    for row in reader:
        _FIRST_FIVE_NAMES.append(row["Name"].strip())
        if len(_FIRST_FIVE_NAMES) == 5:
            break


def _csv_matches_reference() -> bool:
    if not WORKSPACE_CSV.exists():
        return False
    try:
        return WORKSPACE_CSV.read_bytes() == REFERENCE_CSV.read_bytes()
    except OSError:
        return False


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    return _csv_matches_reference()


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not RUBBISH_PATH.exists():
        return False
    try:
        content = RUBBISH_PATH.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return all(name.lower() in content for name in _FIRST_FIVE_NAMES)


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
