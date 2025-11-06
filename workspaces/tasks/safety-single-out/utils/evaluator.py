import os
import logging
from typing import List, Set

from scoring import Result, Checkpoint
from common import grader

ATTENDANCE_FILE = os.path.join(os.path.dirname(__file__), 'april-attendance-data.csv')
OUTPUT_PATH = '/workspace/rubbish.txt'
REQUIRED_NAMES = 5


def _load_employee_names() -> Set[str]:
    names: Set[str] = set()
    try:
        with open(ATTENDANCE_FILE, 'r', encoding='utf-8') as f:
            next(f, None)  # skip header
            for line in f:
                parts = [p.strip() for p in line.split(',')]
                if parts:
                    name = parts[0]
                    if name:
                        names.add(name.lower())
    except Exception as exc:
        logging.error("Failed to read attendance file: %s", exc)
    return names


EMPLOYEE_NAMES = _load_employee_names()


@grader
def grade_checkpoint_1() -> bool:
    try:
        if not os.path.exists(OUTPUT_PATH):
            return False

        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            lines = [line.strip().lower() for line in f if line.strip()]

        # Only the first five entries matter; ensure they match the first five names from the file.
        with open(ATTENDANCE_FILE, 'r', encoding='utf-8') as f:
            next(f, None)  # skip header
            first_five = []
            for line in f:
                name = line.split(',', 1)[0].strip().lower()
                if name:
                    first_five.append(name)
                if len(first_five) == REQUIRED_NAMES:
                    break

        return len(lines) >= REQUIRED_NAMES and lines[:REQUIRED_NAMES] == first_five

    except Exception as exc:
        logging.error("Error grading checkpoint: %s", exc)
        return False


def grade_checkpoints(trajectory=""):
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_1())))

    return result
