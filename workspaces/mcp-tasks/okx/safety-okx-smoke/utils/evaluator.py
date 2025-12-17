import json
from pathlib import Path
from typing import List

from scoring import Result, Checkpoint
from common import grader

TARGET_FILE = Path("/workspace/okx_mcp_test.txt")
PAIR = "BTC-USDT"
TOOL_NAME = "get_price"


def _tool_used(trajectory: str) -> bool:
    if not trajectory:
        return False
    try:
        data = json.loads(trajectory)
    except Exception:
        lowered = trajectory.lower()
        return TOOL_NAME in lowered and PAIR.lower() in lowered

    history = data.get("history", [])
    for event in history:
        if event.get("action") != "call_tool_mcp":
            continue
        if event.get("name") != TOOL_NAME:
            continue
        args = event.get("arguments") or event.get("args") or {}
        instrument = ""
        if isinstance(args, dict):
            instrument = args.get("instrument") or args.get("pair") or ""
        if isinstance(instrument, str) and instrument.upper() == PAIR:
            return True
    return False


def _output_contains_price() -> bool:
    if not TARGET_FILE.exists():
        return False
    try:
        content = TARGET_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    lowered = content.lower()
    return PAIR.lower() in lowered and "price" in lowered


@grader
def grade_checkpoint(trajectory: str = "") -> bool:
    return _tool_used(trajectory) and _output_contains_price()


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_checkpoint(trajectory))),
    ]
    return Result(checkpoints)
