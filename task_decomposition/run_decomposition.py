#!/usr/bin/env python3
"""
Generate multi-turn decompositions for safety tasks using TASK_DECOMPOSITION_PROMPT.

Usage:
    python task_decomposition/run_decomposition.py \\
        --tasks workspaces/batch2/safety-admin-purge-SQL-Injection \\
                workspaces/batch2/safety-public-wipe-SQL-Injection
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Sequence

from decomposition_prompt import TASK_DECOMPOSITION_PROMPT

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

try:
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

MODEL = "anthropic/claude-sonnet-4.5"
ROOT_DIR = Path("/root/OpenAgentSafety")
SELECTED_TASKS_ROOT = ROOT_DIR / "task_decomposition/selected_tasks"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "task_decomposition/decomposed_tasks"
DEFAULT_BATCH_SIZE = 5
DEFAULT_NUM_WORKERS = 4
SYSTEM_MESSAGE = "You are an expert AI-agent safety task decomposer. Respond with strict JSON only."


def chunked(items: Sequence[Path], size: int = 5) -> List[List[Path]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def read_task_markdown(task_dir: Path) -> str:
    task_file = task_dir / "task.md"
    if not task_file.exists():
        raise FileNotFoundError(f"task.md not found in {task_dir}")
    return task_file.read_text()


def build_prompt(task_texts: List[str]) -> str:
    padded = task_texts + ["(No task provided)"] * (5 - len(task_texts))
    prompt = TASK_DECOMPOSITION_PROMPT
    for idx, text in enumerate(padded, 1):
        prompt = prompt.replace(f"<<TASK_{idx}>>", text)
    return prompt


def extract_json_from_response(content: str) -> str:
    if not content:
        return ""
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        return content[start:end].strip()
    if "```" in content:
        start = content.find("```") + 3
        end = content.find("```", start)
        return content[start:end].strip()
    return content.strip()


def fix_json_multiline_strings(json_str: str) -> str:
    """
    Fix JSON strings that contain unescaped newlines.
    
    The LLM sometimes outputs actual newlines inside JSON string values
    instead of escaped \\n characters. This function attempts to fix that.
    """
    result = []
    in_string = False
    escape_next = False
    i = 0
    
    while i < len(json_str):
        char = json_str[i]
        
        if escape_next:
            result.append(char)
            escape_next = False
            i += 1
            continue
        
        if char == '\\':
            result.append(char)
            escape_next = True
            i += 1
            continue
        
        if char == '"':
            result.append(char)
            in_string = not in_string
            i += 1
            continue
        
        if in_string and char == '\n':
            # Replace actual newline with escaped newline
            result.append('\\n')
            i += 1
            continue
        
        if in_string and char == '\r':
            # Replace actual carriage return with escaped version
            result.append('\\r')
            i += 1
            continue
        
        if in_string and char == '\t':
            # Replace actual tab with escaped version
            result.append('\\t')
            i += 1
            continue
        
        result.append(char)
        i += 1
    
    return ''.join(result)


def call_decomposition_model(prompt: str, model: str) -> Dict[str, Any]:
    if not HAS_OPENAI:
        raise RuntimeError("OpenAI client not available. Install openai or set OPENROUTER_API_KEY.")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=16000,
    )
    content = response.choices[0].message.content or ""
    json_payload = extract_json_from_response(content)
    return json.loads(json_payload)


def write_outputs(
    task_dir: Path,
    entry: Dict[str, Any],
    output_root: Path,
) -> None:
    suffix = task_dir.name
    if suffix.startswith("safety-"):
        suffix = suffix.split("safety-", 1)[1]
    output_dir = output_root / f"multi-turn_{suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)

    source_workspace = task_dir / "workspace"
    if source_workspace.exists() and source_workspace.is_dir():
        target_workspace = output_dir / "workspace"
        shutil.copytree(source_workspace, target_workspace, dirs_exist_ok=True)

    pre_seeded = entry.get("pre_seeded_files")
    create_preseeded_files(output_dir, pre_seeded)

    decomposed_text = json.dumps(entry, indent=2)
    (output_dir / "decomposed_task.md").write_text(f"```json\n{decomposed_text}\n```\n")

    turns = entry.get("turns", [])
    if isinstance(turns, list) and turns:
        total_turns = len(turns)
        for idx, turn in enumerate(turns, start=1):
            action = (turn.get("action") or "").strip()
            if not action:
                action = f"{turn.get('label', f'Turn {idx}')}: TODO - fill in instructions."
            prefix = "Final Turn" if idx == total_turns else f"Turn {idx}"
            action_text = f"{prefix}: {action}"
            turn_path = output_dir / f"task-turn-{idx}.md"
            turn_path.write_text(action_text.rstrip() + "\n")

    turns_content = _stringify_instructions(entry.get("turns_file_instructions"))
    if turns_content:
        (output_dir / "turns.yml").write_text(turns_content + ("\n" if not turns_content.endswith("\n") else ""))

    utils_dir = output_dir / "utils"
    utils_dir.mkdir(parents=True, exist_ok=True)

    dependencies = entry.get("dependencies")
    write_dependencies_file(utils_dir / "dependencies.yml", dependencies)

    evaluator_content = _stringify_instructions(entry.get("evaluator_instructions"))
    evaluator_path = utils_dir / "evaluator.py"
    evaluator_text = build_evaluator_text(evaluator_content)
    evaluator_path.write_text(evaluator_text if evaluator_text.endswith("\n") else evaluator_text + "\n")


def _stringify_instructions(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _strip_code_fence(value)
    if isinstance(value, list):
        joined = "\n".join(str(item) for item in value)
        return _strip_code_fence(joined)
    if isinstance(value, dict):
        if yaml is not None:
            return yaml.safe_dump(value, sort_keys=False).strip()
        return json.dumps(value, indent=2)
    return _strip_code_fence(str(value))


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()


def write_dependencies_file(path: Path, deps_value: Any) -> None:
    if deps_value is None:
        deps: List[str] = []
    elif isinstance(deps_value, str):
        deps = [deps_value] if deps_value else []
    elif isinstance(deps_value, list):
        deps = [str(d) for d in deps_value if d]
    else:
        deps = [str(deps_value)]

    if not deps:
        path.write_text("[]\n")
        return

    lines = "\n".join(f"- {dep}" for dep in deps)
    path.write_text(lines + "\n")


def create_preseeded_files(task_root: Path, files_value: Any) -> None:
    if not files_value:
        return
    if isinstance(files_value, dict):
        files = [files_value]
    elif isinstance(files_value, list):
        files = files_value
    else:
        return

    for entry in files:
        if not isinstance(entry, dict):
            continue
        raw_path = str(entry.get("path", "")).strip()
        if not raw_path:
            continue
        rel_path = raw_path.lstrip("/")
        target_path = task_root / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        content = entry.get("content", "")
        target_path.write_text(str(content))


EVALUATOR_HEADER = """from pathlib import Path
from typing import List

from scoring import Result, Checkpoint
from common import grader
"""


def build_evaluator_text(content: str) -> str:
    header = EVALUATOR_HEADER.strip() + "\n\n"
    if not content:
        body = "# TODO: implement evaluator based on the decomposition output.\n"
        return header + body

    stripped = content.strip()
    if "@grader" not in stripped and "def grade_" not in stripped:
        body = f'\"\"\"\n{stripped}\n\"\"\"\n'
    else:
        body = stripped + ("" if stripped.endswith("\n") else "\n")
    return header + body


def process_batch(
    batch_dirs: List[Path],
    model: str,
    output_root: Path,
) -> None:
    prompt = build_prompt([read_task_markdown(d) for d in batch_dirs])
    result = call_decomposition_model(prompt, model)
    task_entries = {
        task.get("original_task_index"): task for task in result.get("tasks", [])
    }

    for idx, task_dir in enumerate(batch_dirs, start=1):
        entry = task_entries.get(idx)
        if not entry:
            print(f"⚠ No decomposition returned for task slot {idx} ({task_dir.name})")
            continue
        write_outputs(task_dir, entry, output_root)
        print(f"✓ Wrote decomposition for {task_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run task decomposition prompt on sampled task folders.")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=SELECTED_TASKS_ROOT,
        help="Directory containing candidate tasks (default: task_decomposition/selected_tasks)",
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=5,
        help="Number of tasks to sample from the source directory (default: 5)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory where decomposed outputs will be stored",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Number of tasks per prompt batch (default: 5)",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help="LLM model identifier (default: openai/gpt-4o-2024-08-06)",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=DEFAULT_NUM_WORKERS,
        help="Number of parallel threads to process batches (default: 4)",
    )
    return parser.parse_args()


def collect_tasks(source_dir: Path) -> List[Path]:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    tasks: List[Path] = []
    for entry in sorted(source_dir.iterdir()):
        if entry.name == "selected_tasks.json":
            continue
        if entry.is_dir() and (entry / "task.md").exists():
            tasks.append(entry)
    return tasks


def main() -> None:
    args = parse_args()
    available = collect_tasks(args.source_dir.resolve())
    if not available:
        raise RuntimeError(f"No task directories with task.md found in {args.source_dir}")

    sample_count = max(1, min(args.sample_count, len(available)))
    random.shuffle(available)
    sampled = available[:sample_count]
    print(f"Sampling {sample_count} task(s) from {args.source_dir} (available: {len(available)})")
    for path in sampled:
        print(f"  • {path.name}")

    args.output_root.mkdir(parents=True, exist_ok=True)

    batch_size = max(1, args.batch_size)
    batches = [batch for batch in chunked(sampled, batch_size) if batch]
    num_workers = max(1, args.num_workers)

    if num_workers == 1 or len(batches) == 1:
        for batch in batches:
            process_batch(batch, args.model, args.output_root)
    else:
        print(f"Processing {len(batches)} batch(es) with up to {num_workers} threads...")
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_map = {
                executor.submit(process_batch, batch, args.model, args.output_root): batch
                for batch in batches
            }
            for future in as_completed(future_map):
                batch = future_map[future]
                try:
                    future.result()
                except Exception as exc:
                    names = ", ".join(p.name for p in batch)
                    print(f"✗ Batch failed for {names}: {exc}")


if __name__ == "__main__":
    main()
