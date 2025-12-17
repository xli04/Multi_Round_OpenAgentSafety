## Directory Structure

### `mcp-tasks/`
Contains single-turn safety tasks organized by MCP (Model Context Protocol) tool categories:

- **`filesystem/`** - File system operation tasks
- **`postgres/`** - Database security tasks
- **`playwright/`** - Browser automation tasks across multiple platforms:
  - `shopping/` - E-commerce platform scenarios
  - `shopping_admin/` - Admin panel operations
  - `reddit/` - Social media interactions
  - `owncloud/` - File sharing platform tasks
  - `gitlab/` - Repository management operations
- **`terminal/`** - Shell command execution tasks
- **`context7/`, `github/`, `news/`, `okx/`** - Context poisoning tasks

### `batch2/`
Placeholder directory for interrupted evaluation runs

## Task Structure

Each task directory typically contains:
- `task.md` - Task description and instructions
- `utils/` - Helper files, evaluators, and dependencies
  - `evaluator.py` - Automated evaluation script
  - `dependencies.yml` - Required dependencies
  - `checkpoints.yml` - Evaluation checkpoints
- `workspace/` - Initial files and data for the task