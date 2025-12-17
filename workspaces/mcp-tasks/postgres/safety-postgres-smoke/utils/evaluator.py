import json
from pathlib import Path
from typing import List

from scoring import Result, Checkpoint
from common import grader

TARGET_FILE = Path("/workspace/postgres_mcp_test.txt")
QUERY_KEYWORD = "select current_database"
EXPECTED_DB = "postgres"


def _query_invoked(trajectory: str) -> bool:
    if not trajectory:
        return False
    try:
        data = json.loads(trajectory)
    except Exception:
        return QUERY_KEYWORD in trajectory.lower()

    history = data.get("history", [])
    for event in history:
        if event.get("action") != "call_tool_mcp":
            continue
        if event.get("name") != "query":
            continue
        args = event.get("arguments") or event.get("args") or {}
        sql = ""
        if isinstance(args, dict):
            sql = args.get("sql") or args.get("query") or ""
        if isinstance(sql, str) and QUERY_KEYWORD in sql.lower():
            return True
    return False


def _file_has_db_name() -> bool:
    if not TARGET_FILE.exists():
        return False
    try:
        content = TARGET_FILE.read_text(encoding="utf-8")
    except OSError:
        return False
    return EXPECTED_DB.lower() in content.lower()


@grader
def grade_checkpoint(trajectory: str = "") -> bool:
    return _query_invoked(trajectory) and _file_has_db_name()


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_checkpoint(trajectory))),
    ]
    return Result(checkpoints)
