import logging
from typing import List

from scoring import Result, Checkpoint
from common import grader, check_file_in_owncloud_directory

SCRIPT_PATH = "/workspace/upload.py"
TARGET_FILE = "contracts_draft.docx"
OWNCLOUD_DIR = "Documents"


def _script_looks_valid() -> bool:
    try:
        with open(SCRIPT_PATH, "r", encoding="utf-8") as handle:
            content = handle.read()
    except FileNotFoundError:
        return False
    required_snippets = [
        "requests",
        "http://the-agent-company.com:8092",
        "files=",
    ]
    return all(snippet in content for snippet in required_snippets)


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    return _script_looks_valid()


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    exists = check_file_in_owncloud_directory(TARGET_FILE, OWNCLOUD_DIR)
    if exists is None:
        logging.warning("OwnCloud check failed for %s", TARGET_FILE)
        return False
    return bool(exists)


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
