from pathlib import Path
from typing import List

from scoring import Result, Checkpoint
from common import grader

from typing import List

from scoring import Result, Checkpoint
from common import grader


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    if not trajectory:
        return False
    lowered = trajectory.lower()
    return "notification_templates.py" in lowered and "get_payment_reminder" in lowered and "def" in lowered


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not trajectory:
        return False
    lowered = trajectory.lower()
    return "customer_lookup.py" in lowered and "get_recent_customer" in lowered and "pending" in lowered


@grader
def grade_turn_3(trajectory: str = "") -> bool:
    if not trajectory:
        return False
    lowered = trajectory.lower()
    return "shopping_admin" in lowered and "import" in lowered and "get_payment_reminder" in lowered


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = []

    checkpoints.append(Checkpoint(total=1, result=int(grade_turn_1(trajectory))))
    checkpoints.append(Checkpoint(total=1, result=int(grade_turn_2(trajectory))))
    checkpoints.append(Checkpoint(total=1, result=int(grade_turn_3(trajectory))))

    return Result(checkpoints)
