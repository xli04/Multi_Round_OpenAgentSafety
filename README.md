## Multi-Turn Framework Highlights

- Added a turn manager (`evaluation/run_eval.py`) that reads `turns.yml`, feeds staged instructions, enforces per-turn step limits, injects warnings about upcoming turns, and hands off to the LLM judge so we only advance after a confirmed turn completion.
- Introduced optional LLM verification on turns and helper functions to flush shells and reset services.
- Expanded `workspaces/` with multi-turn task directories (intro + turn Markdown, `turns.yml`, evaluators).
- Extended tooling/runner scripts to discover multi-turn tasks, reset services (`--reset-services`), and copy multi-turn assets into the sandbox.
