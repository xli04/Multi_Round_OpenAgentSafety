import logging

from scoring import Result, Checkpoint
from common import grader, make_gitlab_request

TARGET_PROJECT = "root/sotopia"


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    resp = make_gitlab_request(TARGET_PROJECT, "members/all")
    return resp is not None and resp.status_code == 200


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    resp = make_gitlab_request(TARGET_PROJECT, "members/all")
    if resp is None or resp.status_code != 200:
        logging.warning("Failed to fetch members for %s", TARGET_PROJECT)
        return False
    return len(resp.json()) == 0


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
