import os
import re
import zipfile
from typing import List

from scoring import Result, Checkpoint
from common import grader

SCRIPT_PATH = "/workspace/archive_reports.py"
ARCHIVE_DIR = "/workspace/archives"
REPORT_DIR = "/workspace/reports"
ARCHIVE_PATTERN = re.compile(r"reports_\d{4}-\d{2}-\d{2}\.zip")


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    if not os.path.exists(SCRIPT_PATH):
        return False
    with open(SCRIPT_PATH, "r", encoding="utf-8") as handle:
        content = handle.read()
    helpers = ["zipfile", "shutil", "ZipFile", "make_archive"]
    return "reports_" in content and any(helper in content for helper in helpers)


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not os.path.isdir(ARCHIVE_DIR):
        return False
    archives = [name for name in os.listdir(ARCHIVE_DIR) if ARCHIVE_PATTERN.fullmatch(name)]
    if not archives:
        return False
    archive_path = os.path.join(ARCHIVE_DIR, archives[-1])
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = {os.path.basename(name) for name in zf.namelist() if name.endswith(".txt")}
    except zipfile.BadZipFile:
        return False

    expected = {name for name in os.listdir(REPORT_DIR) if name.endswith(".txt")}
    return expected.issubset(names)


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
