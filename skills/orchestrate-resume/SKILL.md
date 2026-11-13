---
name: orchestrate-resume
description: Use when an orchestrator session restarts (new session, context reset, after a stop or a laptop restart), when the user says "resume orchestration" or "pick up where we left off", or when a unit is waiting after an event. Rebuilds the picture from the workspace files and puts waiting units back in the flow.
---

# Resume

`orch` is `<repo>/.orchestrate/bin/orch`.

## Restart the orchestrator

Follow `.orchestrate/RESUME.md` step by step. In short: read `ORCHESTRATION.md` and `INBOX.md`; `herdr-name orchestrator`; `orch status`, `orch breakpoint list`, `herdr agent list`, the newest files in `.orchestrate/logs/`; restart `orch supervise` in the background if any unit is active; restart the loop unless a breakpoint or the current state says to wait. Trust the files, `git log` and the forge over memory.

## Put a waiting unit back

`orch status` shows each waiting unit's event. Handle it, record what you did (`orch note <UNIT> "orchestrator: …"`), then resume:

| Event | Handle | Then |
|---|---|---|
| builder gone, blocked, on a dialog, stalled or wedged | Look at its pane (`herdr agent read <name>`); prompt it to carry on, or restart it; a dialog only the owner may answer | `orch resume <UNIT> building` (or `fixing` if it was fixing) |
| reviewer gone or stalled | | `orch resume <UNIT> reviewing` (or `light`, when the pipeline has a light review): missing reviews start again, finished ones stand |
| review with no verdict | Ask the reviewer to add the verdict line, or delete the file | `orch resume <UNIT> reviewing` |
| print-mode review ended twice with no output | Read its job log in `logs/` | `orch resume <UNIT> reviewing` |
| land failed (push, checks, build) | Send the failure to the builder (`herdr agent prompt <name> …`) | `orch resume <UNIT> fixing` |
| land failed on a transient forge error | | `orch reland <UNIT>` |
| light review still holds | Move what is open to `INBOX.md` for a later unit | `orch resume <UNIT> landing`, or `orch close <UNIT>` |
| branch moved past the reviewed head with new commits | Read `git log --no-merges <checked head>..<branch>`; send anything unsound to the builder | `orch resume <UNIT> landing` lands the current head (you have checked it), or `orch resume <UNIT> fixing` for another fix round |
| job over its time limit | Read its log; stop it if it is hung | `orch reland <UNIT>` or resume the stage it was in |
| merged | Tell the owner; update "Current state"; start the next unit. The supervisor has already told every builder still building, in review or fixing to merge the destination (`briefs/refresh.md`) | |
| breakpoint reached | `orchestrate-breakpoint` | |

After fixes are in, resume to `landing` (or `light`, when the pipeline has one), never back to `fixing`. A branch that gained only merges of the destination since its checked head lands again by itself, without a review (not yet proven in a live build: if it misbehaves, review the merge and `orch resume <UNIT> landing`).
