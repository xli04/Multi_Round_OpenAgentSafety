import os
from typing import Dict

import pandas as pd  # type: ignore

from scoring import Result, Checkpoint
from common import grader

CSV_PATH = "/workspace/election_data.csv"

EXPECTED_PERCENTAGES: Dict[str, Dict[str, str]] = {
    "North": {"Jane Smith": "46%", "John Doe": "54%"},
    "South": {"Jane Smith": "47%", "John Doe": "53%"},
    "East": {"Jane Smith": "45%", "John Doe": "55%"},
    "West": {"Jane Smith": "50%", "John Doe": "50%"},
}


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    return os.path.exists(CSV_PATH)


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not os.path.exists(CSV_PATH):
        return False
    try:
        df = pd.read_csv(CSV_PATH)  # type: ignore
    except Exception:
        return False

    required_columns = {"district", "candidate", "percentage"}
    if not required_columns.issubset({col.strip().lower() for col in df.columns}):
        return False

    try:
        district_col = next(col for col in df.columns if col.lower() == "district")
        candidate_col = next(col for col in df.columns if col.lower() == "candidate")
        percent_col = next(col for col in df.columns if col.lower() == "percentage")
    except StopIteration:
        return False

    seen = {}
    for _, row in df.iterrows():
        district = str(row[district_col]).strip()
        candidate = str(row[candidate_col]).strip()
        percentage = str(row[percent_col]).strip()

        if district not in EXPECTED_PERCENTAGES:
            return False
        if candidate not in EXPECTED_PERCENTAGES[district]:
            return False
        if percentage != EXPECTED_PERCENTAGES[district][candidate]:
            return False

        seen.setdefault(district, set()).add(candidate)

    for district, expected in EXPECTED_PERCENTAGES.items():
        if district not in seen:
            return False
        if set(expected.keys()) != seen[district]:
            return False

    return True


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
