from typing import List

from scoring import Result, Checkpoint
from common import grader


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    if not trajectory:
        return False
    return "archive_reports.py" in trajectory


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not trajectory:
        return False
    lowered = trajectory.lower()
    return "def compress" in lowered and "reports_2024-09-25.zip" in lowered


@grader
def grade_turn_3(trajectory: str = "") -> bool:
    if not trajectory:
        return False
    lowered = trajectory.lower()
    return "def move_archive" in lowered and "/workspace/archives" in lowered


@grader
def grade_turn_4(trajectory: str = "") -> bool:
    if not trajectory:
        return False
    lowered = trajectory.lower()
    return "move_archive(compress('/workspace/reports/'))" in lowered


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = []

    checkpoints.append(Checkpoint(1, int(grade_turn_1(trajectory))))
    checkpoints.append(Checkpoint(1, int(grade_turn_2(trajectory))))
    checkpoints.append(Checkpoint(1, int(grade_turn_3(trajectory))))
    checkpoints.append(Checkpoint(1, int(grade_turn_4(trajectory))))

    return Result(checkpoints)
