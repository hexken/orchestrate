---
name: orchestrate-start
description: Use when the orchestration workspace is set up and the user wants the build loop running, or says "start the units", "start orchestrating" or "kick off milestone N". Names this session the orchestrator, starts the first units in free worktrees, starts the supervisor in the background and the self-paced loop.
---

# Start the loop

`orch` is `<repo>/.orchestrate/bin/orch`. Run in Herdr (`test "${HERDR_ENV:-}" = 1`, else stop).

1. **Check.** `orch doctor` reports every line `ok`; `orch breakpoint list` shows no breakpoint `pending` or `reached` that blocks the units you mean to start; `orch status` shows which worktrees are busy.
2. **Name yourself**: `herdr-name orchestrator`.
3. **Read** `.orchestrate/ORCHESTRATION.md` (the rules) and `INBOX.md`.
4. **Pick units** from the work plan (`[project].work_plan`): the earliest wave whose needs have merged, within its pairing rules, one per free worktree. Starting a milestone's first unit adds that milestone's breakpoint automatically.
5. **Start each**: `orch start <UNIT> --worktree <path> --plan <milestone plan file, e.g. 2026-01-05-milestone-1.md>`; add `--role <builder role>` for a unit built on another harness, and `--scope <file>` for a unit outside the work plan.
6. **Supervise**: run `orch supervise` in the background (Bash with `run_in_background`). It prints `EVENT: …` and exits when something needs you. Never stop it by killing its background task: that kills the review and land jobs it started; use `orch stop`.
7. **Loop**: start the loop skill in dynamic mode with the prompt "Orchestrate the units: follow 'Each wake-up' in .orchestrate/ORCHESTRATION.md", with a 30-minute fallback wake-up. Each wake-up handles events, restarts the supervisor while units are active, and starts the next units when worktrees free up.
8. **Record**: update "Current state" in `ORCHESTRATION.md` (what is running, what is next); `orch note - "owner input: <their go>"` for the owner's instruction.

Tell the user in two or three lines what started and how to see it (`orch status`, each unit's Herdr tab with its live view).
