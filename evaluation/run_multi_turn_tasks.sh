#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/root/OpenAgentSafety/workspaces/multi-turn-instru"
OUTPUT_DIR="./test_output/multi_turn_instru_claude45"
AGENT_CFG="agent"
ENV_CFG="env"
SERVER_HOST="localhost"
REMOTE_HOST="64.176.198.19"

for task_dir in "$BASE_DIR"/*; do
  if [[ -d "$task_dir" ]]; then
    echo "Running task: $task_dir"
    poetry run python run_eval.py \
      --agent-llm-config "$AGENT_CFG" \
      --env-llm-config "$ENV_CFG" \
      --outputs-path "$OUTPUT_DIR" \
      --server-hostname "$REMOTE_HOST" \
      --task-path "$task_dir"
  fi
done
