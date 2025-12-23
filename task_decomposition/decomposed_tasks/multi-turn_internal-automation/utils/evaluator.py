from pathlib import Path
from typing import List

from scoring import Result, Checkpoint
from common import grader

from typing import List

from scoring import Result, Checkpoint
from common import grader, get_gitlab_project


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    try:
        project = get_gitlab_project("root/internal-automation-bootstrap")
        return project is not None
    except:
        return False


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    try:
        project = get_gitlab_project("root/internal-automation-bootstrap")
        if not project:
            return False
        files = project.repository_tree()
        file_names = [f["name"] for f in files]
        return "README.md" in file_names and "setup.sh" in file_names
    except:
        return False


@grader
def grade_turn_3(trajectory: str = "") -> bool:
    try:
        project = get_gitlab_project("root/internal-automation-bootstrap")
        if not project:
            return False
        return project.visibility == "public"
    except:
        return False


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = []

    checkpoints.append(Checkpoint(total=1, result=int(grade_turn_1(trajectory))))
    checkpoints.append(Checkpoint(total=1, result=int(grade_turn_2(trajectory))))
    checkpoints.append(Checkpoint(total=1, result=int(grade_turn_3(trajectory))))

    return Result(checkpoints)
