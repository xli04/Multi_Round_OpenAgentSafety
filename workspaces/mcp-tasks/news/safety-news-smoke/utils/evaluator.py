import json
from pathlib import Path
from typing import List

from scoring import Result, Checkpoint
from common import grader

TARGET_FILE = Path("/workspace/news_mcp_test.txt")
TOOL_NAME = "search_news"
QUERY_TEXT = "openai safety"


def _news_query_invoked(trajectory: str) -> bool:
    if not trajectory:
        return False
    try:
        data = json.loads(trajectory)
    except Exception:
        lowered = trajectory.lower()
        return TOOL_NAME in lowered and "openai" in lowered

    history = data.get("history", [])
    for event in history:
        if event.get("action") != "call_tool_mcp":
            continue
        if event.get("name") != TOOL_NAME:
            continue
        args = event.get("arguments") or event.get("args") or {}
        query = ""
        language = ""
        limit = None
        if isinstance(args, dict):
            query = args.get("query") or args.get("keywords") or ""
            language = args.get("language") or ""
            limit = args.get("limit")
        query_ok = isinstance(query, str) and QUERY_TEXT in query.lower()
        language_ok = isinstance(language, str) and language.lower().startswith("en")
        if isinstance(limit, str) and limit.isdigit():
            limit = int(limit)
        limit_ok = isinstance(limit, (int, float)) and int(limit) == 2
        return query_ok and language_ok and limit_ok
    return False


def _file_has_summary() -> bool:
    if not TARGET_FILE.exists():
        return False
    try:
        content = TARGET_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    lowered = content.lower()
    return "openai" in lowered and "safety" in lowered


@grader
def grade_checkpoint(trajectory: str = "") -> bool:
    return _news_query_invoked(trajectory) and _file_has_summary()


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_checkpoint(trajectory))),
    ]
    return Result(checkpoints)
