# Orchestration: {{name}}

The owner's instruction: build the units of the work plan without waiting on the owner, from implementation through review, the push, the build and the merge into `{{destination}}`. The owner steps in at breakpoints and for what "Not unlocked" lists.

The orchestrating session decides what to build and handles judgment; `orch` does the mechanical work. This file holds the rules and the current state. Each other fact has one home:
- roles, models, review pipelines, timeouts, checks and sources: `orchestrate.toml` (`orch roles` prints the role table);
- open work items: `INBOX.md`;
- running units: `units.json` (`orch status`);
- what happened: `git log`, the forge, and `logs/`;
- restarting a session: `RESUME.md`;
- harness and permission setup: `AGENT-SETUP.md`.

## Current state

- No unit is running. The work plan is `{{work_plan}}`.

## Where things are

- **Worktrees**, any unit in any free one: `[worktrees].paths` in `orchestrate.toml`. Each has a clean push checkout beside it (`<worktree>-push`).
- **One branch per unit**: `agent/<unit in lowercase>`, cut from `origin/{{destination}}` when the unit starts, one PR into `{{destination}}`.
- **One Herdr tab per unit**, labelled with the unit's name: the builder, a live view below it (`orch watch <UNIT>`), reviewers beside it. The tab closes when the unit merges.
- **Never touch the main checkout** `{{repo}}` or its branches. This workspace (`.orchestrate/`) is shared into each worktree by a symlink.
- **Briefs** in `briefs/`, filled by `orch` per unit: `builder.md`; `review.md` (interactive review); `second_reviewer.md` (print-mode review from another vendor); `light.md` (the review of the builder's fixes). A role may have its own `briefs/<role>.md`.
- **Plans**: one per milestone in `plans/`, made by its first builder; each unit adds its own section and its rulings.
- **Unit files**, in the unit's worktree under `scratch/units/`: `<UNIT>.md` (the builder's summary, with a "Fixes" section after the reviews), `<UNIT>-<role>.md` per review, `<UNIT>-light.md`. Each review starts with its verdict.

## How a unit flows

`orch supervise` does every step marked *auto*; the orchestrator does the rest.

1. **Start.** `orch start <UNIT> --worktree PATH --plan FILE [--role ROLE]`, then `orch supervise` in the background.
2. **Build.** The builder builds and commits, writes its summary, and stops in its session. It never pushes.
3. **Reviews and land** (*auto*, when the summary exists and the builder is idle): the reviews of the builder's pipeline, and the land (push, PR, build) at the same time. A docs-only change gets no review.
4. **Fixes** (*auto*, when a review holds): the builder fixes every finding or declines it with a reason, appends "Fixes" and stops.
5. **Light review** (*auto*, when "Fixes" appears); the fixes land again.
6. **Merge** (*auto*) when the build of the landed head is green and every required review is clean.
7. **Freshness** (*auto*): a land whose pushed commit lacks the current destination lands again; a branch that moved past the reviewed head is an event.
8. **Events** move the unit to `waiting` and end `orch supervise` with `EVENT: <unit> <what>`: a light review that still holds, a failed land, an agent gone, blocked, on a dialog or idle too long, a review with no verdict, a job over its limit, every merge, every breakpoint.

## Rules

- **Never block on a question.** Owner questions go in the status message; carry on with the proxy's recommendation, marked "owner to confirm".
- A test is never weakened, skipped or deleted to make it pass; the reviews check this.
- **No change narration** in specs, plans, docs or code ("now", "changed from", "per the owner's request"). Why a change was made goes in the unit summary or the rulings.
- One PR per unit, merged only into `{{destination}}` under the merge condition.
- No images or PDFs to any model if a proxy blocks them; check UIs by text.
- Never edit a shell script a job is running: bash reads it as it goes. `orch stop` then restart the supervisor after changing the package.

## Not unlocked

These need the owner: merging anywhere but `{{destination}}`; editing an owner-owned source (`[sources]` with `owner = "owner"`); spending real money; logins; answering another session's permission dialog.

## Breakpoints

A milestone's end is a breakpoint; the owner adds others (`orch breakpoint add`). At each, run `[breakpoints].steps` with the `orchestrate-breakpoint` skill: freeze (running units finish), align, compact, then one message to the owner. Wait for `orch breakpoint pass`, unless `[breakpoints].conditional_go` holds.

## Each wake-up

The orchestrator wakes on a supervisor event or a 30-minute fallback.
1. Read the events; `orch status`; `herdr agent list` if a session looks wrong.
2. Handle each event, then `orch resume <UNIT> <status>`. After a merge: tell the owner, update "Current state", start the next unit when a worktree is free.
3. Restart `orch supervise` in the background while any unit is active, and set the fallback. To stop it, `orch stop`; never kill its background task from the harness, which kills the review and land jobs it started.
