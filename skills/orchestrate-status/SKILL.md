---
name: orchestrate-status
description: Use when the user asks how the orchestrated build is going, what is running, what is waiting, or how long units took ("status", "what's running", "where are we"). Reads the registry, timelines, breakpoints, Herdr agents and the newest logs and answers briefly.
---

# Status

`orch` is `<repo>/.orchestrate/bin/orch`. Read-only.

1. `orch status`: each unit's stage, harness, branch, tab and pull request; a waiting unit shows its event.
2. `orch breakpoint list`: pending, reached and passed breakpoints.
3. For a unit the user asks about: `orch timeline <UNIT>` (marks with the minutes between them) and its live view in its Herdr tab.
4. If a session looks wrong: `herdr agent list`, then `herdr agent read <name> --source recent --lines 40`.
5. "Current state" in `.orchestrate/ORCHESTRATION.md` for what is next.

Answer in a few lines: what merged since the last report, what is running and at which stage, what waits and on whom, what needs the owner.
