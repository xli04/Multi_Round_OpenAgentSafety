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
from pathlib import Path
from typing import Any, Dict, List, Sequence

from decomposition_prompt import TASK_DECOMPOSITION_PROMPT

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
SELECTED_TASKS_ROOT = ROOT_DIR / "task_decomposition" / "selected_tasks"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "task_decomposition" / "decomposed_tasks"
DEFAULT_BATCH_SIZE = 5
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
    output_dir = output_root / f"decomposed_{suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "original_task.md").write_text(read_task_markdown(task_dir))
    decomposed_text = json.dumps(entry, indent=2)
    (output_dir / "decomposed_task.md").write_text(f"```json\n{decomposed_text}\n```\n")


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
    for batch in chunked(sampled, batch_size):
        process_batch(batch, args.model, args.output_root)


if __name__ == "__main__":
    main()
