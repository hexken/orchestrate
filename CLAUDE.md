# CLAUDE.md

Orchestrate: a Herdr-native set of skills and a small Python package (`orch`) that take a project from requirements to a supervised loop of coding-agent build units. The path and the skills are in `README.md`; the config keys are in `README.md`, "Config".

## Rules

- Generic only. No client, employer, project, repository, branch or path from any real project in any file, test or commit. Examples use `myapp`, `main`, `~/Dev/myapp`.
- Runtime is the Python standard library only (Python 3.11+). Dev tools: pytest, ruff (line length 100), mypy strict.
- No comments or explanatory docstrings in code, except a short note marking something not yet implemented.
- Herdr is required: agent sessions run in Herdr panes; code that drives Herdr refuses to run without `HERDR_ENV=1`.
- Harness and land integrations are adapters behind contracts (`src/orchestrate/adapters.py`); worked examples are in `examples/adapters/`. A project's own adapters live in its `.orchestrate/adapters/`.
- Tests use fakes for `herdr`, harness CLIs, remotes and forge CLIs. Never start a real agent session from a test.
- Commits are conventional commits, subject at most 72 characters.

## Checks

```shell
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest -q
```
