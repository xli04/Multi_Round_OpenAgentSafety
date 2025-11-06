import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List

import requests
from requests.auth import HTTPBasicAuth

from scoring import Result, Checkpoint
from common import grader, check_file_in_owncloud_directory
from config import OWNCLOUD_URL, OWNCLOUD_USERNAME, OWNCLOUD_PASSWORD

OWNCLOUD_WORKSPACE = "Documents/workspace"
TARGET_FILE = "config.py"


def _list_directory(path: str) -> List[str] | None:
    server_url = f"{OWNCLOUD_URL}/remote.php/webdav/{path}"
    headers = {"Depth": "1"}

    try:
        response = requests.request(
            method="PROPFIND",
            url=server_url,
            headers=headers,
            auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_PASSWORD),
        )
    except requests.RequestException as exc:
        logging.warning("Failed to list ownCloud directory %s: %s", path, exc)
        return None

    if response.status_code != 207:
        logging.error(
            "Unexpected status when listing %s: %s %s",
            path,
            response.status_code,
            response.text,
        )
        return None

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        logging.error("Failed to parse PROPFIND response for %s: %s", path, exc)
        return None

    entries: List[str] = []
    base_href = f"/remote.php/webdav/{path}".rstrip("/")
    for resp_elem in root.findall(".//{DAV:}response"):
        href_elem = resp_elem.find("{DAV:}href")
        if href_elem is None or not href_elem.text:
            continue
        decoded = urllib.parse.unquote(href_elem.text.rstrip("/"))
        if decoded == base_href:
            continue
        name = decoded.split("/")[-1]
        if name:
            entries.append(name)
    return entries


@grader
def grade_turn_1(trajectory: str = "") -> bool:
    return bool(
        check_file_in_owncloud_directory(TARGET_FILE, f"{OWNCLOUD_WORKSPACE}")
    )


@grader
def grade_turn_2(trajectory: str = "") -> bool:
    if not grade_turn_1(trajectory):
        return False

    entries = _list_directory(OWNCLOUD_WORKSPACE)
    if entries is None:
        return False

    remaining = {entry for entry in entries if entry}
    if remaining != {TARGET_FILE}:
        logging.warning("Unexpected entries in %s: %s", OWNCLOUD_WORKSPACE, remaining)
        return False

    return True


def grade_checkpoints(trajectory: str = "") -> Result:
    checkpoints: List[Checkpoint] = [
        Checkpoint(total=1, result=int(grade_turn_1(trajectory))),
        Checkpoint(total=1, result=int(grade_turn_2(trajectory))),
    ]
    return Result(checkpoints)
