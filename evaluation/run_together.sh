#!/usr/bin/env bash
set -euo pipefail

# ---- Single-turn tasks ----
BASE_DIR="/root/OpenAgentSafety/workspaces/tasks"
OUTPUT_DIR="./test_output/single_turn_gpt5-mini"
AGENT_CFG="agent"
ENV_CFG="env"
SERVER_HOST="localhost"
REMOTE_HOST="64.176.198.19"

# for task_dir in "$BASE_DIR"/*; do
#     if [[ -d "$task_dir" ]]; then
#         echo "Running single-turn task: $task_dir"
#         poetry run python run_eval.py \
#             --agent-llm-config "$AGENT_CFG" \
#             --env-llm-config "$ENV_CFG" \
#             --outputs-path "$OUTPUT_DIR" \
#             --server-hostname "$REMOTE_HOST" \
#             --task-path "$task_dir"

#         echo "Cleaning up OpenHands runtime containers..."
#         docker ps -a | grep openhands-runtime | awk '{print $1}' | xargs -r docker rm -f

#         echo "Task completed and cleaned up: $task_dir"
#         echo "----------------------------------------"
#     fi
# done

# ---- Multi-turn tasks ----
BASE_DIR="/root/OpenAgentSafety/workspaces/multi-turn-tasks"
OUTPUT_DIR="./test_output/multi_turn_gpt5-mini"

for task_dir in "$BASE_DIR"/*; do
    if [[ -d "$task_dir" ]]; then
        echo "Running multi-turn task: $task_dir"
        poetry run python run_eval.py \
            --agent-llm-config "$AGENT_CFG" \
            --env-llm-config "$ENV_CFG" \
            --outputs-path "$OUTPUT_DIR" \
            --server-hostname "$REMOTE_HOST" \
            --task-path "$task_dir"

        echo "Task completed: $task_dir"
        echo "----------------------------------------"
    fi
done

BASE_DIR="/root/OpenAgentSafety/workspaces/multi-turn-instru"
OUTPUT_DIR="./test_output/multi_turn_instru_gpt5-mini"

for task_dir in "$BASE_DIR"/*; do
    if [[ -d "$task_dir" ]]; then
        echo "Running multi-turn task: $task_dir"
        poetry run python run_eval.py \
            --agent-llm-config "$AGENT_CFG" \
            --env-llm-config "$ENV_CFG" \
            --outputs-path "$OUTPUT_DIR" \
            --server-hostname "$REMOTE_HOST" \
            --task-path "$task_dir"

        echo "Task completed: $task_dir"
        echo "----------------------------------------"
    fi
done
