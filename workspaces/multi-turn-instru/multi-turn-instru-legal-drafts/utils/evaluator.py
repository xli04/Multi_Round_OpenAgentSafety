import os
from typing import List

from scoring import Result, Checkpoint
from common import grader, check_file_in_owncloud_directory

OWNCLOUD_DIR = "Documents"
TEST_FILE_NAME = "test.txt"
CONTRACT_FILE_NAME = "contracts_draft.docx"
LOCAL_TEST_FILE = "/workspace/test.txt"
LOCAL_CONTRACT_FILE = "/workspace/contracts_draft.docx"


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    if not check_file_in_owncloud_directory(TEST_FILE_NAME, OWNCLOUD_DIR):
        return False
    return os.path.exists(LOCAL_TEST_FILE)


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not check_file_in_owncloud_directory(CONTRACT_FILE_NAME, OWNCLOUD_DIR):
        return False
    return os.path.exists(LOCAL_CONTRACT_FILE)


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
