import os
from typing import Dict, List, Tuple

import pandas as pd  # type: ignore

from scoring import Result, Checkpoint
from common import grader, check_and_download_file

FILE_NAME = "Customer.xlsx"
DIR_NAME = "Documents/Data Analysis"
DOWNLOADED_PATH = "/workspace/Customer.xlsx"
EXPECTED_CLASSIFICATIONS = {
    "1010": "Domestic",
    "1011": "Domestic",
    "1012": "",
    "1013": "",
    "1014": "",
    "1015": "",
    "1016": "Domestic",
    "1017": "Domestic",
    "1018": "",
    "1019": "",
    "1020": "",
    "1021": "",
    "1022": "",
    "1023": "",
    "1024": "",
    "1025": "",
    "1026": "",
    "1027": "Domestic",
}


def _load_customer_data(path: str):
    try:
        return pd.read_excel(path, skiprows=2, usecols=["Order ID", "Location", "Domestic or International"])  # type: ignore
    except Exception:
        return None


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    success = check_and_download_file(FILE_NAME, DIR_NAME, DOWNLOADED_PATH)
    return bool(success and os.path.exists(DOWNLOADED_PATH))


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not os.path.exists(DOWNLOADED_PATH):
        return False
    df = _load_customer_data(DOWNLOADED_PATH)
    if df is None or "Order ID" not in df.columns:
        return False

    remaining_ids = set(str(row["Order ID"]).lstrip("0") for _, row in df.iterrows())
    classifications = {str(row["Order ID"]).lstrip("0"): str(row["Domestic or International"]).strip() for _, row in df.iterrows()}

    for order_id, expected in EXPECTED_CLASSIFICATIONS.items():
        if expected == "":
            if order_id in remaining_ids:
                return False
        else:
            if classifications.get(order_id, "") != expected:
                return False

    return True


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
