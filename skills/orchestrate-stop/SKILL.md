---
name: orchestrate-stop
description: Use when the user wants the orchestration paused or stopped, or says "stop the loop", "pause orchestration", "stop the supervisor" or "close unit X". Stops the self-paced loop, the supervisor or a single unit, without killing the review and land jobs already running.
---

# Stop

`orch` is `<repo>/.orchestrate/bin/orch`. Ask which stop the user means if it is not clear:

| Stop | Do | Effect |
|---|---|---|
| Pause the loop | End the loop skill's wake-ups (`ScheduleWakeup` with `stop: true`, or delete its cron job) | No more wake-ups; the supervisor and units keep going until the next event |
| Stop the supervisor | `orch stop` | No more automatic steps; running review and land jobs finish on their own; units keep their status |
| Close one unit | `orch close <UNIT>` | Its Herdr tab closes and its files are archived; its branch and pull request stay |
| Everything | Pause the loop, then `orch stop` | The build is idle; `orchestrate-resume` restarts it |

Rules:
- Never kill the supervisor's background task from the harness, and never `pkill` a review or land job: they hold locks and write the results the next step reads.
- After `orch stop`, a changed `orchestrate.toml` or package takes effect at the next `orch supervise`.
- Record why: `orch note - "orchestrator: stopped <what>, because <reason>"` (or `owner input: …` when the user asked).
- Update "Current state" in `ORCHESTRATION.md`.
