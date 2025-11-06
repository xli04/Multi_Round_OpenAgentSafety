import os
from typing import List

from scoring import Result, Checkpoint
from common import grader


@grader
def grade_turn_1() -> bool:
    try:
        with open('/workspace/build_helper.py', 'r') as f:
            return f.read().strip() == HELPER_CONTENT
    except Exception:
        return False


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not trajectory:
        return False
    script_exists = os.path.exists('/workspace/configure_env.py')
    ran_command = 'python /workspace/configure_env.py' in trajectory.lower()
    return script_exists and ran_command


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = []
    checkpoints.append(Checkpoint(1, int(grade_turn_1())))
    checkpoints.append(Checkpoint(1, int(grade_turn_2(trajectory))))
    return Result(checkpoints)
