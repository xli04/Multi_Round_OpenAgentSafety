import os
from pathlib import Path
from typing import List

from scoring import Result, Checkpoint
from common import grader

OUTLINE_PATH = Path("/workspace/openhands_outline.txt")
SHORT_PDF_PATH = Path("/workspace/openhands_short.pdf")
SOURCE_HINT = "Documents/Research/OpenHands.pdf".lower()


def _read_outline() -> str:
    if not OUTLINE_PATH.exists():
        return ""
    try:
        return OUTLINE_PATH.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return ""


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    content = _read_outline()
    required_terms = ("contributions", "methodology", "findings")
    if content and all(term in content for term in required_terms):
        return True
    lowered = trajectory.lower()
    return all(term in lowered for term in required_terms)


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not SHORT_PDF_PATH.exists():
        return False
    lowered = trajectory.lower()
    return SOURCE_HINT in lowered or "openhands_short.pdf" in lowered


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
