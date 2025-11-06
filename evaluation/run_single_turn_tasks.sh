#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="/root/OpenAgentSafety/workspaces/tasks"
OUTPUT_DIR="./test_output/single_turn_claude35"
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
        
        echo "Cleaning up OpenHands runtime containers..."
        docker ps -a | grep openhands-runtime | awk '{print $1}' | xargs -r docker rm -f
        
        echo "Task completed and cleaned up: $task_dir"
        echo "----------------------------------------"
    fi
done

