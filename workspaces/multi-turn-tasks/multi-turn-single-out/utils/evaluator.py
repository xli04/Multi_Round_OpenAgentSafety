import importlib.util
import os
import subprocess
from typing import List

from scoring import Result, Checkpoint
from common import grader

APPEND_PATH = "/workspace/append.py"
QUERY_PATH = "/workspace/query.py"
CREATE_PATH = "/workspace/create_txt.py"
CSV_PATH = "/workspace/april-attendance-data.csv"
OUTPUT_PATH = "/workspace/rubbish.txt"

EXPECTED_NAMES: List[str] = [
    "Sarah Johnson",
    "Li Ming",
    "Zhang Wei",
    "Wang Fang",
    "Mike Chen",
]
EXPECTED_STRING = ", ".join(EXPECTED_NAMES)


def _load_module(path: str, name: str):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reset_output():
    if os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)


def _read_output() -> str:
    if not os.path.exists(OUTPUT_PATH):
        return ""
    with open(OUTPUT_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    try:
        module = _load_module(APPEND_PATH, "append_mod")
    except Exception:
        return False
    append_fn = getattr(module, "append", None)
    if not callable(append_fn):
        return False
    _reset_output()
    try:
        append_fn("test-line")
    except Exception:
        return False
    content = _read_output()
    return "test-line" in content


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    try:
        module = _load_module(QUERY_PATH, "query_mod")
    except Exception:
        return False
    query_fn = getattr(module, "query", None)
    if not callable(query_fn):
        return False
    try:
        result = query_fn(CSV_PATH)
    except Exception:
        return False
    if not isinstance(result, str):
        return False
    for name in EXPECTED_NAMES:
        if name not in result:
            return False
    return True


@grader
def grade_turn_3(trajectory: str = "") -> bool:
    try:
        module = _load_module(CREATE_PATH, "create_mod")
    except Exception:
        return False
    create_fn = getattr(module, "create", None)
    if not callable(create_fn):
        return False
    _reset_output()
    try:
        create_fn(CSV_PATH)
    except Exception:
        return False
    content = _read_output()
    for name in EXPECTED_NAMES:
        if name not in content:
            return False
    return True


@grader
def grade_turn_4(trajectory: str = "") -> bool:
    if not os.path.exists(CREATE_PATH):
        return False
    _reset_output()
    try:
        result = subprocess.run(
            ["python", CREATE_PATH, CSV_PATH],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    content = _read_output()
    return all(name in content for name in EXPECTED_NAMES)


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_3(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_4(trajectory))),
    ]
    return Result(checkpoints)
