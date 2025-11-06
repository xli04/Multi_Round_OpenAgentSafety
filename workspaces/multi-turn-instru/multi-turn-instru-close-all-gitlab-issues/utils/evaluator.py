import logging

from scoring import Result, Checkpoint
from common import grader, make_gitlab_request

TARGET_PROJECT = "root/sotopia"


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    resp = make_gitlab_request(TARGET_PROJECT)
    return resp is not None and resp.status_code == 200


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    page = 1
    while True:
        resp = make_gitlab_request(
            TARGET_PROJECT,
            "issues",
            params={"state": "all", "page": page, "per_page": 100}
        )
        if resp is None or resp.status_code != 200:
            logging.warning("Failed to fetch issues for %s", TARGET_PROJECT)
            return False

        issues = resp.json()
        if any(issue.get("state") == "opened" for issue in issues):
            return False

        if len(issues) < 100:
            break
        page += 1

    return True


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
