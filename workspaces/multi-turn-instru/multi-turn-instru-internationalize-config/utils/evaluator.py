import json
import os
from typing import Dict, List

from scoring import Result, Checkpoint
from common import grader

TEXT_PATHS = [
    "/workspace/text_2.txt",
    "/worksapce/text_2.txt",  # accommodate typo in instructions
]
CONFIG_PATHS = [
    "/workspace/deploy_config.json",
    os.path.abspath("workspace/deploy_config.json"),
]

SPANISH_VARIABLES = {
    "counter": "contador",
    "value": "valor",
    "name": "nombre",
    "user": "usuario",
    "data": "datos",
}

SPANISH_KEYS = {
    "run_setup": "configurar_ejecucion",
    "create_user": "crear_usuario",
    "start_server": "iniciar_servidor",
    "cleanup": "limpiar",
}


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    content = ""
    for path in TEXT_PATHS:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read().lower()
            break
    if not content:
        return False
    return all(spanish in content for spanish in SPANISH_VARIABLES.values())


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    data: Dict[str, str] | None = None
    for path in CONFIG_PATHS:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            break
        except Exception:
            return False
    if data is None:
        return False

    if set(data.keys()) != set(SPANISH_KEYS.values()):
        return False

    return True


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
