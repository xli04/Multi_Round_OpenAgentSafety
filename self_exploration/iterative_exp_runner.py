#!/usr/bin/env python3
"""
Sequentially run exploration tasks while incrementally updating the safety experience pool.

Workflow:
    1. Execute each generated task with run_eval.py.
    2. After every run, call exp_generate.learn_from_task_state to distill a new/updated experience.
    3. Feed the refreshed experience list into the next task via --use-experience.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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


@dataclass
class BenignBaseline:
    success: Optional[bool]
    output: str
    description: str
    outcome: Optional[str] = None


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
    """Read the serialized state output for a given task."""
    path = output_dir / f"state_task.{task_number}.json"
    if not path.exists():
        return ""
    try:
        return path.read_text()
    except Exception:
        return ""


def read_task_description(task_dir: Path) -> str:
    """Return task.md contents if available."""
    task_file = task_dir / "task.md"
    if not task_file.exists():
        return ""
    try:
        return task_file.read_text()
    except Exception:
        return ""


def load_generation_summary(summary_path: Path) -> Dict[str, Dict[str, List[TaskRecord]]]:
    """Load generation summary and bucket tasks by function/type."""
    if not summary_path.exists():
        raise FileNotFoundError(f"Generation summary not found: {summary_path}")
    
    with open(summary_path, "r") as fp:
        data = json.load(fp)
    
    grouped: Dict[str, Dict[str, List[TaskRecord]]] = {}
    for task in data.get("tasks", []):
        function = task.get("function", "unknown_function")
        task_type = task.get("type", "harmful")
        path = Path(task["path"])
        record = TaskRecord(
            task_number=task["task_number"],
            path=path,
            function=function,
            task_type=task_type,
            harm=task.get("harm"),
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
        help="Number of independent runs per harmful task."
    )
    parser.add_argument(
        "--inference-time",
        type=int,
        default=1,
        help="Number of experience variants to collect per run."
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
) -> bool:
    """
    Execute a single task using run_eval.py.
    
    Args:
        task_dir: Path to task directory
        base_cmd: Base command list for run_eval.py
        workdir: Working directory for command execution
        experience_file: Path to experience file
        max_attempts: Maximum retry attempts
    
    Returns:
        True if task succeeded, False otherwise
    """
    cmd = base_cmd + ["--task-path", str(task_dir)]
    if experience_file.exists():
        cmd += ["--use-experience", str(experience_file)]

    for attempt in range(1, max_attempts + 1):
        print(f"  [Attempt {attempt}/{max_attempts}] Running task evaluation...")
        try:
            subprocess.run(cmd, check=True, cwd=workdir)
            print(f"  ✓ Task evaluation succeeded")
            return True
        except subprocess.CalledProcessError as exc:
            print(f"  ✗ Task evaluation failed (exit {exc.returncode})")
    
    print(f"  ✗ Exceeded retry budget; skipping task")
    return False


def run_task_with_cleanup(
    task_dir: Path,
    base_cmd: list[str],
    workdir: Path,
    experience_file: Path,
    max_attempts: int,
) -> bool:
    """Run a task and perform cleanup regardless of outcome."""
    success = run_task(task_dir, base_cmd, workdir, experience_file, max_attempts)
    cleanup_runtime_artifacts()
    remove_runtime_images()
    return success


def run_task_with_experience_dict(
    task_dir: Path,
    base_cmd: list[str],
    workdir: Path,
    experience_dict: Dict[str, str],
    args: argparse.Namespace,
) -> bool:
    """Run a task using a temporary experience file derived from a dict."""
    with temporary_experience_file(experience_dict, args.experience_file) as temp_exp:
        return run_task_with_cleanup(
            task_dir=task_dir,
            base_cmd=base_cmd,
            workdir=workdir,
            experience_file=temp_exp,
            max_attempts=args.max_attempts,
        )


def run_benign_baseline(
    benign_task: Optional[TaskRecord],
    experiences: Dict[str, str],
    args: argparse.Namespace,
    base_cmd: list[str],
    workdir: Path,
) -> Optional[BenignBaseline]:
    if not benign_task:
        return None
    print(f"  → Running benign baseline for {benign_task.function}")
    save_experience_list(experiences, args.experience_file)
    success = run_task_with_cleanup(
        benign_task.path,
        base_cmd,
        workdir,
        args.experience_file,
        args.max_attempts,
    )
    output = read_task_state_output(benign_task.task_number, args.output_dir)
    description = read_task_description(benign_task.path)
    return BenignBaseline(success=success, output=output, description=description)


def classify_benign_outcome(baseline: BenignBaseline) -> Optional[str]:
    if not baseline or not baseline.output:
        return None
    try:
        judgement = judge_benign_behavior(
            baseline.description,
            baseline.output,
        )
        outcome = judgement.get("outcome")
        if isinstance(outcome, str):
            baseline.outcome = outcome.strip().lower()
        return baseline.outcome
    except Exception as exc:
        print(f"      ⚠ Benign outcome classification failed: {exc}")
        return None


def generate_variant_candidates(
    harmful_task: TaskRecord,
    experiences: Dict[str, str],
    args: argparse.Namespace,
    base_cmd: list[str],
    workdir: Path,
    total_variants: int,
) -> List[VariantCandidate]:
    candidates: List[VariantCandidate] = []
    for idx in range(1, total_variants + 1):
        print(f"    • Variant {idx}/{total_variants} for task.{harmful_task.task_number}")
        save_experience_list(experiences, args.experience_file)
        success = run_task_with_cleanup(
            harmful_task.path,
            base_cmd,
            workdir,
            args.experience_file,
            args.max_attempts,
        )
        if not success:
            print("      Skipping variant due to task failure")
            continue
        result = learn_from_task_state(harmful_task.task_number)
        try:
            updated_exps, metadata = apply_experience_result(experiences, result)
        except ValueError as exc:
            print(f"      ✗ Failed to apply experience result: {exc}")
            continue
        candidates.append(
            VariantCandidate(
                label=f"{harmful_task.function}_variant_{idx}",
                result=result,
                experiences=updated_exps,
                metadata=metadata,
            )
        )
    return candidates


def filter_variants_by_benign(
    candidates: List[VariantCandidate],
    benign_task: Optional[TaskRecord],
    baseline_data: Optional[BenignBaseline],
    args: argparse.Namespace,
    base_cmd: list[str],
    workdir: Path,
) -> List[VariantCandidate]:
    if not (args.benign_check and benign_task and baseline_data):
        return candidates
    
    filtered: List[VariantCandidate] = []
    for cand in candidates:
        if not cand.metadata.get("changed", False):
            filtered.append(cand)
            continue
        print(f"    → Benign regression check for {cand.label}")
        benign_success = run_task_with_experience_dict(
            benign_task.path,
            base_cmd,
            workdir,
            cand.experiences,
            args,
        )
        current_output = read_task_state_output(benign_task.task_number, args.output_dir)
        variant_baseline = BenignBaseline(benign_success, current_output, baseline_data.description)
        variant_outcome = classify_benign_outcome(variant_baseline)
        if variant_outcome:
            cand.metadata["benign_outcome"] = variant_outcome
        baseline_rank = BENIGN_OUTCOME_RANK.get(
            baseline_data.outcome,
            2 if baseline_data.success else 1 if baseline_data.success is False else 1,
        )
        variant_rank = BENIGN_OUTCOME_RANK.get(
            variant_outcome,
            2 if benign_success else 1 if benign_success is False else 1,
        )
        changed = variant_rank < baseline_rank
        if not changed:
            filtered.append(cand)
        else:
            print(f"      ✗ Variant {cand.label} alters benign behavior; filtered out")
    return filtered


def score_variants_with_kl(
    candidates: List[VariantCandidate],
    harmful_task: TaskRecord,
    args: argparse.Namespace,
    base_cmd: list[str],
    workdir: Path,
    logprob_tracker: LogprobTracker,
    baseline_distribution: Dict[str, float],
) -> List[VariantCandidate]:
    scored: List[VariantCandidate] = []
    logprob_tracker.sync()
    for cand in candidates:
        if not cand.metadata.get("changed", False):
            cand.kl_score = 0.0
            scored.append(cand)
            continue
        print(f"    → KL scoring run for {cand.label}")
        success = run_task_with_experience_dict(
            harmful_task.path,
            base_cmd,
            workdir,
            cand.experiences,
            args,
        )
        if not success:
            print(f"      ✗ Unable to score {cand.label} (task failed)")
            continue
        try:
            logprob_path = logprob_tracker.wait_for_new_file()
            current_dist = parse_logprob_distribution(logprob_path)
            cand.kl_score = compute_kl_divergence(current_dist, baseline_distribution)
            print(f"      KL({cand.label}) = {cand.kl_score:.6f}")
            scored.append(cand)
        except Exception as exc:
            print(f"      ✗ Failed to compute KL for {cand.label}: {exc}")
    return scored


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
    experiences = load_experience_list(args.experience_file)
    save_experience_list(experiences, args.experience_file)

    total_variants = args.run_time * args.inference_time
    kl_enabled = args.run_time > 1 or args.inference_time > 1

    print("=" * 70)
    print("Function-grouped Task Execution with Experience Selection")
    print("=" * 70)
    print(f"Functions discovered: {len(grouped_tasks)}")
    print(f"Experience file: {args.experience_file}")
    print(f"run_time={args.run_time}, inference_time={args.inference_time}, benign_check={args.benign_check}")
    print(f"KL selection: {'enabled' if kl_enabled else 'disabled'}")

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

    benign_cache: Dict[str, BenignBaseline] = {}
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
        if args.benign_check and benign_task and function_name not in benign_cache:
            state_path = args.output_dir / f"state_task.{benign_task.task_number}.json"
            if state_path.exists():
                print(f"  → Using cached benign state for {function_name}")
                output = read_task_state_output(benign_task.task_number, args.output_dir)
                description = read_task_description(benign_task.path)
                benign_cache[function_name] = BenignBaseline(None, output, description)
            else:
                print(f"  → Running benign baseline for {function_name}")
                baseline = run_benign_baseline(
                    benign_task,
                    experiences,
                    args,
                    base_cmd,
                    args.eval_dir,
                )
                benign_cache[function_name] = baseline or BenignBaseline(None, "", "")
            classify_benign_outcome(benign_cache[function_name])
        baseline_data = benign_cache.get(function_name)

        harmful_task = harmful_lookup[task_num]
        print(f"\n  → Processing harmful task.{harmful_task.task_number} ({harmful_task.harm})")
        candidates = generate_variant_candidates(
            harmful_task,
            experiences,
            args,
            base_cmd,
            args.eval_dir,
            total_variants,
        )
        if not candidates:
            print("    ⚠ No viable variants generated for this task")
            continue

        candidates = filter_variants_by_benign(
            candidates,
            benign_task,
            baseline_data,
            args,
            base_cmd,
            args.eval_dir,
        )
        if not candidates:
            print("    ⚠ All variants filtered out by benign check")
            continue

        if kl_enabled:
            candidates = score_variants_with_kl(
                candidates,
                harmful_task,
                args,
                base_cmd,
                args.eval_dir,
                logprob_tracker,
                baseline_distribution,
            )
            if not candidates:
                print("    ⚠ Unable to score variants; skipping update")
                continue
            best_candidate = min(
                candidates,
                key=lambda c: c.kl_score if c.kl_score is not None else float("inf"),
            )
        else:
            best_candidate = candidates[0]

        if best_candidate.metadata.get("changed", False):
            experiences = best_candidate.experiences
            save_experience_list(experiences, args.experience_file)
            selection_count += 1
            kl_info = f" (KL={best_candidate.kl_score:.6f})" if best_candidate.kl_score is not None else ""
            print(f"    ✓ Selected {best_candidate.label}{kl_info}")
        else:
            print("    ○ No experience update required for this task")

    print(f"\n{'=' * 70}")
    print("Execution Summary")
    print('=' * 70)
    print(f"Functions processed: {len(grouped_tasks)}")
    print(f"Experiences selected: {selection_count}")
    print(f"Experience library: {args.experience_file}")
    print('=' * 70)


if __name__ == "__main__":
    main()
BENIGN_OUTCOME_RANK = {
    "finished": 2,
    "unfinished": 1,
    "refused": 0,
}
