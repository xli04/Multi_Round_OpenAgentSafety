#!/usr/bin/env python3
"""
Sequentially run exploration tasks with nested execution/inference loops for experience optimization.

Workflow per Task:
    1. Outer Loop (run_time): Execute the task to generate a failure trace.
    2. Inner Loop (inference_time): 
       a. Generate experience candidates from that single trace.
       b. Merge and re-run immediately to score (KL Divergence).
       c. Update 'Best Candidate' if score improves.
    3. Update Global Experience Pool with the single best candidate.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exp_generate import (
    learn_from_task_state,
    apply_experience_result,
    load_experience_list,
    save_experience_list,
    judge_benign_behavior,
)

REPO_ROOT = Path("/root/OpenAgentSafety")
DEFAULT_TASK_ROOT = REPO_ROOT / "self_exploration" / "exp_examples"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "self_exploration" / "exp_output"
DEFAULT_EXPERIENCE_FILE = REPO_ROOT / "self_exploration" / "experience_list.json"
DEFAULT_EVAL_DIR = REPO_ROOT / "evaluation"
BASELINE_LOGPROB_PATH = REPO_ROOT / "self_exploration" / "gpt4o_logprobs_refusal.json"
LOGPROB_OUTPUT_DIR = REPO_ROOT / "evaluation" / "test_output"


def sanitize_logprob_tag(tag: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", tag)


@dataclass
class TaskRecord:
    task_number: int
    path: Path
    function: str
    task_type: str
    harm: Optional[str] = None


@dataclass
class VariantCandidate:
    label: str
    result: Dict[str, Any]
    experiences: Dict[str, str]
    metadata: Dict[str, Any]
    kl_score: Optional[float] = None
    benign_score: Optional[int] = None


@dataclass
class BenignBaseline:
    success: Optional[bool]
    output: str
    description: str
    outcome: Optional[int] = None


class LogprobTracker:
    """Track logprob JSON drops from run_eval executions."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._seen: set[Path] = {p.resolve() for p in self.directory.glob("logprobs_*.json")}

    def wait_for_new_file(self, timeout_seconds: float = 30.0) -> Path:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            candidates = sorted(
                self.directory.glob("logprobs_*.json"),
                key=lambda p: p.stat().st_mtime,
            )
            for cand in candidates:
                resolved = cand.resolve()
                if resolved not in self._seen:
                    self._seen.add(resolved)
                    return resolved
            time.sleep(0.5)
        raise RuntimeError("Timed out waiting for new logprob file")

    def sync(self) -> None:
        """Mark all existing logprob files as seen."""
        self._seen = {p.resolve() for p in self.directory.glob("logprobs_*.json")}


def read_task_state_output(task_number: int, output_dir: Path) -> str:
    """Read the serialized state output for a given task.
    
    Handles both:
    - Single-turn (task_number < 100): state_task.X.json
    - Multi-turn (task_number >= 100): state_multi_turn_task.X.json
    """
    if task_number < 100:
        # Single-turn
        path = output_dir / f"state_task.{task_number}.json"
    else:
        # Multi-turn: convert back to base number
        base_number = task_number - 100
        path = output_dir / f"state_multi_turn_task.{base_number}.json"
    
    if not path.exists():
        return ""
    try:
        return path.read_text()
    except Exception:
        return ""


def read_task_description(task_dir: Path) -> str:
    """Return task.md contents if available, or combine task-turn-*.md for multi-turn tasks."""
    # First, try single-turn format: task.md
    task_file = task_dir / "task.md"
    if task_file.exists():
        try:
            return task_file.read_text()
        except Exception:
            return ""
    
    # Second, try multi-turn format: task-turn-1.md, task-turn-2.md, etc.
    turn_files = sorted(task_dir.glob("task-turn-*.md"))
    if turn_files:
        contents = []
        for turn_file in turn_files:
            try:
                turn_content = turn_file.read_text()
                turn_name = turn_file.stem  # e.g., "task-turn-1"
                contents.append(f"=== {turn_name} ===\n{turn_content}")
            except Exception:
                continue
        if contents:
            return "\n\n".join(contents)
    
    return ""


def extract_task_number(task_dir: Path) -> Optional[int]:
    """Extract task number from directory name.
    
    Handles both:
    - task.X → returns X
    - multi_turn_task.X → returns 100 + X
    """
    name = task_dir.name
    
    # Single-turn: task.X
    if name.startswith("task.") and not name.startswith("task-turn"):
        try:
            return int(name.split(".", 1)[1])
        except ValueError:
            return None
    
    # Multi-turn: multi_turn_task.X
    if name.startswith("multi_turn_task."):
        try:
            base_number = int(name.split(".", 1)[1])
            return 100 + base_number
        except ValueError:
            return None
    
    return None

def archive_task_state(
    task_dir: Path,
    outputs_dir: Path,
    run_counters: Dict[Tuple[int, str], int],
    label: str,
) -> None:
    task_num = extract_task_number(task_dir)
    if task_num is None:
        return
    
    key = (task_num, label)
    run_counters[key] = run_counters.get(key, 0) + 1
    suffix = f"_{label}_run.{run_counters[key]}"
    
    # Determine the correct file prefix based on task type
    if task_num < 100:
        file_prefix = f"task.{task_num}"
    else:
        base_number = task_num - 100
        file_prefix = f"multi_turn_task.{base_number}"
    
    artifacts = [
        (
            outputs_dir / f"state_{file_prefix}.json",
            outputs_dir / f"state_{file_prefix}{suffix}.json",
        ),
        (
            outputs_dir / f"summary_{file_prefix}.txt",
            outputs_dir / f"summary_{file_prefix}{suffix}.txt",
        ),
    ]
    for src, dst in artifacts:
        if src.exists():
            try:
                shutil.copy(src, dst)
            except Exception:
                pass


def load_generation_summary(summary_path: Path) -> Dict[str, Dict[str, List[TaskRecord]]]:
    """Load generation summary and bucket tasks by function/type."""
    if not summary_path.exists():
        raise FileNotFoundError(f"Generation summary not found: {summary_path}")
    
    with open(summary_path, "r") as fp:
        data = json.load(fp)
    
    grouped: Dict[str, Dict[str, List[TaskRecord]]] = {}
    
    # Build a lookup for single-turn tasks to get harm info for multi-turn
    single_turn_lookup: Dict[str, Dict] = {}
    single_turn_tasks = data.get("single_turn_tasks", {}).get("tasks", [])
    
    for task in single_turn_tasks:
        task_name = task.get("task_name", "")
        single_turn_lookup[task_name] = task
        
        # Extract task number from task_name (e.g., "task.2" -> 2)
        try:
            task_number = int(task_name.split(".")[-1])
        except ValueError:
            continue
        
        function = task.get("function", "unknown_function")
        task_type = task.get("type", "harmful")
        path = Path(task["path"])
        record = TaskRecord(
            task_number=task_number,
            path=path,
            function=function,
            task_type=task_type,
            harm=task.get("harm"),
        )
        grouped.setdefault(function, {"harmful": [], "benign": []})
        grouped[function][task_type].append(record)
    
    # Process multi-turn tasks
    multi_turn_tasks = data.get("multi_turn_tasks", {}).get("tasks", [])
    
    for task in multi_turn_tasks:
        task_name = task.get("task_name", "")
        # Extract task number from task_name (e.g., "multi_turn_task.5" -> 105)
        # Use 100+ offset to distinguish from single-turn tasks
        try:
            base_number = int(task_name.split(".")[-1])
            task_number = 100 + base_number  # e.g., multi_turn_task.5 -> 105
        except ValueError:
            continue
        
        function = task.get("function", "unknown_function")
        
        # Get type and harm from the original single-turn task if available
        original_task = task.get("original_task", "")
        original_info = single_turn_lookup.get(original_task, {})
        task_type = original_info.get("type", "harmful")
        harm = original_info.get("harm")
        
        path = Path(task["path"])
        record = TaskRecord(
            task_number=task_number,
            path=path,
            function=function,
            task_type=task_type,
            harm=harm,
        )
        grouped.setdefault(function, {"harmful": [], "benign": []})
        grouped[function][task_type].append(record)
    
    for bucket in grouped.values():
        bucket["harmful"].sort(key=lambda r: r.task_number)
        bucket["benign"].sort(key=lambda r: r.task_number)
    
    return grouped


def load_baseline_distribution(path: Path) -> Dict[str, float]:
    """Load the reference refusal token distribution."""
    with open(path, "r") as fp:
        data = json.load(fp)
    
    tokens = data.get("tokens", [])
    probs = data.get("avg_probs", [])
    distribution = {token: prob for token, prob in zip(tokens, probs)}
    total = sum(distribution.values())
    if total > 0:
        distribution = {token: prob / total for token, prob in distribution.items()}
    return distribution


def parse_logprob_distribution(logprob_path: Path) -> Dict[str, float]:
    """Parse a logprob JSON dump into a normalized probability distribution."""
    with open(logprob_path, "r") as fp:
        data = json.load(fp)
    
    entries = data.get("top_alternatives", [])
    distribution: Dict[str, float] = {}
    
    for entry in entries:
        token = entry.get("token")
        if not token:
            continue
        prob_percent = entry.get("probability_percent")
        if prob_percent is not None:
            prob = prob_percent / 100.0
        else:
            logprob = entry.get("logprob")
            if logprob is None or logprob <= -999:
                continue
            prob = math.exp(logprob)
        if prob > 0:
            distribution[token] = prob
    
    chosen_token = data.get("chosen_token")
    chosen_logprob = data.get("chosen_logprob")
    if chosen_token and chosen_token not in distribution and chosen_logprob is not None:
        if chosen_logprob > -999:
            distribution[chosen_token] = math.exp(chosen_logprob)
    
    total = sum(distribution.values())
    if total > 0:
        distribution = {token: prob / total for token, prob in distribution.items()}
    return distribution


def compute_kl_divergence(
    current: Dict[str, float],
    baseline: Dict[str, float],
    epsilon: float = 1e-12,
) -> float:
    """Compute D_KL(current || baseline)."""
    divergence = 0.0
    for token, p_prob in current.items():
        if p_prob <= 0:
            continue
        q_prob = baseline.get(token, epsilon)
        divergence += p_prob * math.log(p_prob / max(q_prob, epsilon))
    return divergence


@contextmanager
def temporary_experience_file(
    experiences: Dict[str, str],
    reference_path: Path
):
    """Write experiences to a temporary file for experimentation."""
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="exp_tmp_", suffix=".json", dir=reference_path.parent, delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)
    save_experience_list(experiences, tmp_path)
    try:
        yield tmp_path
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def run_shell(cmd: str) -> None:
    """Execute a shell command without raising on failure."""
    subprocess.run(cmd, shell=True, check=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run exploration tasks sequentially with iterative experience updates."
    )
    parser.add_argument(
        "--task-root", 
        type=Path, 
        default=DEFAULT_TASK_ROOT, 
        help="Directory containing task.* folders."
    )
    parser.add_argument(
        "--output-dir", 
        type=Path, 
        default=DEFAULT_OUTPUT_DIR, 
        help="Directory to store run_eval outputs."
    )
    parser.add_argument(
        "--experience-file", 
        type=Path, 
        default=DEFAULT_EXPERIENCE_FILE, 
        help="Path to the shared experience JSON."
    )
    parser.add_argument(
        "--agent-llm-config", 
        default="agent", 
        help="Agent LLM config name (matches run_eval.py)."
    )
    parser.add_argument(
        "--agent-llm-config-file", 
        default="agent_config/config.toml", 
        help="Agent LLM config file path."
    )
    parser.add_argument(
        "--env-llm-config", 
        default="env", 
        help="Env LLM config name (matches run_eval.py)."
    )
    parser.add_argument(
        "--env-llm-config-file", 
        default="agent_config/config_mcp.toml", 
        help="Env LLM config file path."
    )
    parser.add_argument(
        "--server-hostname", 
        default="64.176.198.19", 
        help="Remote runtime hostname."
    )
    parser.add_argument(
        "--remote-hostname", 
        default=None, 
        help="Alias for server hostname (if set overrides --server-hostname)."
    )
    parser.add_argument(
        "--eval-dir", 
        type=Path, 
        default=DEFAULT_EVAL_DIR, 
        help="Directory that contains run_eval.py."
    )
    parser.add_argument(
        "--max-attempts", 
        type=int, 
        default=3, 
        help="Max retries per task if run_eval fails."
    )
    parser.add_argument(
        "--run-time",
        type=int,
        default=1,
        help="Number of independent runs per harmful task to generate traces."
    )
    parser.add_argument(
        "--inference-time",
        type=int,
        default=1,
        help="Number of experience variations to generate per trace."
    )
    parser.add_argument(
        "--benign-check",
        action="store_true",
        help="Run benign regression checks for each function."
    )
    parser.add_argument(
        "--poetry-bin", 
        default="poetry", 
        help="Poetry executable name/path."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output with detailed experience updates."
    )
    return parser.parse_args()


def cleanup_runtime_artifacts() -> None:
    """Mirror run_single_turn_tasks.sh cleanup routine."""
    print("  🧹 Cleaning up OpenHands runtime containers and volumes...")
    run_shell("docker ps -a | grep openhands-runtime | awk '{print $1}' | xargs -r docker rm -f")
    run_shell("docker volume prune -f")
    print("  ✅ Cleanup completed")


def remove_runtime_images() -> None:
    """Remove cached runtime images similar to the shell script."""
    run_shell("docker images | awk '/ghcr.io\\/all-hands-ai\\/runtime/ {print $3}' | xargs -r docker rmi -f")
    run_shell("docker images | grep ghcr.io/all-hands-ai/runtime || true")


def run_task(
    task_dir: Path,
    base_cmd: list[str],
    workdir: Path,
    experience_file: Path,
    max_attempts: int,
    logprob_tag: Optional[str] = None,
) -> Tuple[bool, Optional[Path]]:
    """Execute a single task using run_eval.py."""
    cmd = base_cmd + ["--task-path", str(task_dir)]
    if experience_file.exists():
        cmd += ["--use-experience", str(experience_file)]

    for attempt in range(1, max_attempts + 1):
        print(f"  [Attempt {attempt}/{max_attempts}] Running task evaluation...")
        try:
            env = os.environ.copy()
            tag_with_attempt = None
            if logprob_tag:
                tag_with_attempt = f"{logprob_tag}_attempt{attempt}"
                env["LOGPROB_TAG"] = tag_with_attempt
            else:
                env.pop("LOGPROB_TAG", None)

            subprocess.run(cmd, check=True, cwd=workdir, env=env)
            print(f"  ✓ Task evaluation succeeded")
            logprob_path = None
            if tag_with_attempt:
                safe = sanitize_logprob_tag(tag_with_attempt)
                logprob_path = LOGPROB_OUTPUT_DIR / f"logprobs_{safe}.json"
            return True, logprob_path
        except subprocess.CalledProcessError as exc:
            print(f"  ✗ Task evaluation failed (exit {exc.returncode})")
    
    print(f"  ✗ Exceeded retry budget; skipping task")
    return False, None


def run_task_with_cleanup(
    task_dir: Path,
    base_cmd: list[str],
    workdir: Path,
    experience_file: Path,
    max_attempts: int,
    outputs_dir: Path,
    run_counters: Dict[Tuple[int, str], int],
    label: str,
    capture_logprob: bool = False,
) -> Tuple[bool, Optional[Path]]:
    """Run a task and perform cleanup regardless of outcome."""
    task_num = extract_task_number(task_dir)
    run_index = 1
    if task_num is not None:
        run_index = run_counters.get((task_num, label), 0) + 1
    
    logprob_tag = None
    if capture_logprob and task_num is not None:
        # Use correct prefix for logprob tag
        if task_num < 100:
            logprob_tag = f"task.{task_num}_{label}_run.{run_index}"
        else:
            base_number = task_num - 100
            logprob_tag = f"multi_turn_task.{base_number}_{label}_run.{run_index}"
    
    success, logprob_path = run_task(
        task_dir,
        base_cmd,
        workdir,
        experience_file,
        max_attempts,
        logprob_tag=logprob_tag,
    )
    archive_task_state(task_dir, outputs_dir, run_counters, label)
    cleanup_runtime_artifacts()
    remove_runtime_images()
    return success, logprob_path


def run_task_with_experience_dict(
    task_dir: Path,
    base_cmd: list[str],
    workdir: Path,
    experience_dict: Dict[str, str],
    args: argparse.Namespace,
    run_counters: Dict[Tuple[int, str], int],
    label: str,
    capture_logprob: bool = False,
) -> Tuple[bool, Optional[Path]]:
    """Run a task using a temporary experience file derived from a dict."""
    with temporary_experience_file(experience_dict, args.experience_file) as temp_exp:
        return run_task_with_cleanup(
            task_dir=task_dir,
            base_cmd=base_cmd,
            workdir=workdir,
            experience_file=temp_exp,
            max_attempts=args.max_attempts,
            outputs_dir=args.output_dir,
            run_counters=run_counters,
            label=label,
            capture_logprob=capture_logprob,
        )


def run_benign_baseline(
    benign_task: Optional[TaskRecord],
    experiences: Dict[str, str],
    args: argparse.Namespace,
    base_cmd: list[str],
    workdir: Path,
    run_counters: Dict[Tuple[int, str], int],
    label: str,
) -> Optional[BenignBaseline]:
    if not benign_task:
        return None
    print(f"  → Running benign baseline for {benign_task.function}")
    save_experience_list(experiences, args.experience_file)
    success, _ = run_task_with_cleanup(
        benign_task.path,
        base_cmd,
        workdir,
        args.experience_file,
        args.max_attempts,
        outputs_dir=args.output_dir,
        run_counters=run_counters,
        label=label,
    )
    output = read_task_state_output(benign_task.task_number, args.output_dir)
    description = read_task_description(benign_task.path)
    return BenignBaseline(success=success, output=output, description=description)


def classify_benign_outcome(baseline: BenignBaseline) -> Optional[int]:
    if not baseline or not baseline.output:
        return None
    try:
        judgement = judge_benign_behavior(
            baseline.description,
            baseline.output,
        )
        outcome = judgement.get("outcome")
        if isinstance(outcome, str):
            outcome = int(outcome.strip())
        if isinstance(outcome, bool):
            outcome = int(outcome)
        if isinstance(outcome, int):
            baseline.outcome = 1 if outcome >= 1 else 0
        return baseline.outcome
    except Exception as exc:
        print(f"      ⚠ Benign outcome classification failed: {exc}")
        return None


def main() -> None:
    args = parse_args()

    if args.run_time <= 0 or args.inference_time <= 0:
        raise ValueError("run_time and inference_time must be positive integers")

    task_root = args.task_root
    if not task_root.exists():
        raise FileNotFoundError(f"Task root not found: {task_root}")

    summary_path = task_root / "generation_summary.json"
    grouped_tasks = load_generation_summary(summary_path)
    if not grouped_tasks:
        print("No tasks described in generation_summary.json")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.experience_file.parent.mkdir(parents=True, exist_ok=True)

    # Build base command for run_eval.py
    hostname = args.remote_hostname or args.server_hostname
    base_cmd = [
        args.poetry_bin,
        "run",
        "python",
        "run_eval.py",
        "--agent-llm-config",
        args.agent_llm_config,
        "--agent-llm-config-file",
        args.agent_llm_config_file,
        "--env-llm-config",
        args.env_llm_config,
        "--env-llm-config-file",
        args.env_llm_config_file,
        "--outputs-path",
        str(args.output_dir),
        "--server-hostname",
        hostname,
    ]

    logprob_tracker = LogprobTracker(args.eval_dir / "test_output")
    baseline_distribution = load_baseline_distribution(BASELINE_LOGPROB_PATH)
    
    # Load Initial Experience Pool
    experiences = load_experience_list(args.experience_file)
    save_experience_list(experiences, args.experience_file)

    print("=" * 70)
    print("Sequential Task Execution with Nested Loop Optimization")
    print("=" * 70)
    print(f"Functions discovered: {len(grouped_tasks)}")
    print(f"Experience file: {args.experience_file}")
    print(f"Configuration: run_time={args.run_time}, inference_time={args.inference_time}")
    print(f"Benign Check: {'enabled' if args.benign_check else 'disabled'}")

    # Prepare Tasks
    function_to_benign: Dict[str, TaskRecord] = {}
    task_to_function: Dict[int, str] = {}
    harmful_lookup: Dict[int, TaskRecord] = {}
    
    for func_name, suite in grouped_tasks.items():
        if suite["benign"]:
            function_to_benign[func_name] = suite["benign"][0]
        for harmful_task in suite["harmful"]:
            task_to_function[harmful_task.task_number] = func_name
            harmful_lookup[harmful_task.task_number] = harmful_task
    
    all_harmful_tasks = sorted(task_to_function.keys())
    run_counters: Dict[Tuple[int, str], int] = {}
    selection_count = 0
    current_function = None

    for index, task_num in enumerate(all_harmful_tasks, 1):
        function_name = task_to_function[task_num]
        if function_name != current_function:
            current_function = function_name
            print(f"\n{'=' * 70}")
            print(f"Function: {function_name}")
            print("=" * 70)

        benign_task = function_to_benign.get(function_name)
        baseline_data: Optional[BenignBaseline] = None
        
        # 1. Establish Benign Baseline (Once per function/task context)
        if args.benign_check and benign_task:
            baseline_data = run_benign_baseline(
                benign_task,
                experiences,
                args,
                base_cmd,
                args.eval_dir,
                run_counters,
                label=f"{function_name}_benign_baseline",
            )
            if baseline_data:
                classify_benign_outcome(baseline_data)

        harmful_task = harmful_lookup[task_num]
        print(f"\n  → Processing harmful task.{harmful_task.task_number} ({harmful_task.harm})")

        # Track the best candidate for THIS task across all runs/inferences
        best_candidate: Optional[VariantCandidate] = None

        # --- OUTER LOOP: RUN (Generate Traces) ---
        for r_idx in range(1, args.run_time + 1):
            print(f"    [Run {r_idx}/{args.run_time}] Executing task to generate trace...")
            
            # Execute Harmful Task with CURRENT experiences (to get the trace/state)
            save_experience_list(experiences, args.experience_file)
            run_success, _ = run_task_with_cleanup(
                harmful_task.path,
                base_cmd,
                args.eval_dir,
                args.experience_file,
                args.max_attempts,
                outputs_dir=args.output_dir,
                run_counters=run_counters,
                label=f"{task_num}_run{r_idx}",
            )

            # If it succeeded (didn't refuse), we have something to learn from.
            # Even if it failed (refused), we might still want to see if we can improve refusal quality (KL),
            # but typically we only learn from failures. Assuming learn_from_task_state handles this.
            
            # --- INNER LOOP: INFERENCE (Generate & Score Experience) ---
            skip_kl_scoring = (args.run_time == 1 and args.inference_time == 1)

            for i_idx in range(1, args.inference_time + 1):
                label = f"{task_num}_run{r_idx}_inf{i_idx}"
                # 1. Generate Experience from the trace we just made
                result = learn_from_task_state(harmful_task.task_number)
                
                # 2. Merge with existing pool
                try:
                    updated_exps, metadata = apply_experience_result(experiences, result)
                except ValueError as exc:
                    if args.verbose:
                        print(f"      (Inference {i_idx}) Skipped: {exc}")
                    continue
                
                # If nothing changed, skip scoring
                if not metadata.get("changed", False):
                    continue

                candidate = VariantCandidate(
                    label=label,
                    result=result,
                    experiences=updated_exps,
                    metadata=metadata,
                )

                # 3. Benign Check (Filter)
                # If benign check is enabled, we verify the new experience doesn't break benign tasks
                if args.benign_check and benign_task and baseline_data:
                    # Run benign task with CANDIDATE experience
                    b_success, _ = run_task_with_experience_dict(
                        benign_task.path,
                        base_cmd,
                        args.eval_dir,
                        candidate.experiences,
                        args,
                        run_counters,
                        label=f"{label}_benign_chk",
                    )
                    
                    # Score Benign
                    curr_out = read_task_state_output(benign_task.task_number, args.output_dir)
                    var_baseline = BenignBaseline(b_success, curr_out, baseline_data.description)
                    var_outcome = classify_benign_outcome(var_baseline)
                    base_outcome = baseline_data.outcome if baseline_data.outcome is not None else 1
                    
                    # If degraded, discard this candidate
                    if var_outcome is not None and var_outcome < base_outcome:
                        print(f"      ✗ Candidate {label} failed benign check. Discarding.")
                        continue
                
                # 4. KL Scoring (Re-run Harmful Task)
                # We re-run the harmful task with the NEW experience to see how it performs
                if skip_kl_scoring:
                    # No need to score, just accept this candidate
                    print(f"      ✓ Single candidate mode - skipping KL scoring")
                    best_candidate = candidate
                else:
                    # Original KL scoring logic
                    logprob_tracker.sync()
                    kl_success, logprob_path = run_task_with_experience_dict(
                        harmful_task.path,
                        base_cmd,
                        args.eval_dir,
                        candidate.experiences,
                        args,
                        run_counters,
                        label=f"{label}_kl_score",
                        capture_logprob=True,
                    )

                    if kl_success:
                        # Calculate KL
                        try:
                            if logprob_path and logprob_path.exists():
                                curr_dist = parse_logprob_distribution(logprob_path)
                            else:
                                curr_dist = parse_logprob_distribution(logprob_tracker.wait_for_new_file())
                            
                            candidate.kl_score = compute_kl_divergence(curr_dist, baseline_distribution)
                            print(f"      ✓ Candidate {label} KL Score: {candidate.kl_score:.6f}")

                            # Update Best Candidate Logic
                            if best_candidate is None:
                                best_candidate = candidate
                            elif candidate.kl_score is not None and best_candidate.kl_score is not None:
                                if candidate.kl_score < best_candidate.kl_score:
                                    print(f"        (New Best for Task {task_num})")
                                    best_candidate = candidate
                        except Exception as exc:
                            print(f"      ⚠ Failed to calculate KL for {label}: {exc}")

        # --- END OF LOOPS FOR THIS TASK ---
        
        # If we found a valid improvement across all runs/inferences, apply it permanently
        if best_candidate:
            experiences = best_candidate.experiences
            save_experience_list(experiences, args.experience_file)
            selection_count += 1
            if best_candidate.kl_score is not None:
                print(f"    ★ Updated Experience Pool with {best_candidate.label} (Final KL={best_candidate.kl_score:.6f})")
            else:
                print(f"    ★ Updated Experience Pool with {best_candidate.label} (KL scoring skipped)")
        else:
            print(f"    ○ No experience improvement found for Task {task_num}.")

    print(f"\n{'=' * 70}")
    print("Execution Summary")
    print('=' * 70)
    print(f"Functions processed: {len(grouped_tasks)}")
    print(f"Experiences selected: {selection_count}")
    print(f"Experience library: {args.experience_file}")
    print('=' * 70)


if __name__ == "__main__":
    main()