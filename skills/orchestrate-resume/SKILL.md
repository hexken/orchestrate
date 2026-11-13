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
| branch moved past the reviewed head with new commits | See what the builder changed beyond a clean merge: `tree=$(git merge-tree --write-tree <checked head> $(git merge-base <branch> origin/<destination>))`, then `git diff $tree <branch>` (empty output means only merges; a failed merge-tree means a conflict was resolved by hand: read the resolution). Send anything unsound to the builder | Once you have checked the change, `orch resume <UNIT> landing` lands the current head; or `orch resume <UNIT> fixing` for another fix round |
| unsettled fixes (a finding the review did not label low or nit was declined or deferred, or a finding has no Fixes line) | Read the reasons; agree, or send the finding back to the builder; ask for the missing Fixes lines | `orch resume <UNIT> landing --accept-head` once settled, or `orch resume <UNIT> fixing` |
| job over its time limit | Read its log; stop it if it is hung | `orch reland <UNIT>` or resume the stage it was in |
| merged | Tell the owner; update "Current state"; start the next unit. The supervisor has already told every builder still building or fixing to merge the destination (`briefs/refresh.md`); a unit in review gets it when its reviews end | |
| breakpoint reached | `orchestrate-breakpoint` | |

After any other event, `orch resume <UNIT> landing` keeps the checked head, so commits made since then are still caught; add `--accept-head` only once you have checked them. After fixes are in, resume to `landing` (or `light`, when the pipeline has one), never back to `fixing`. A branch that gained only clean merges of the destination since its checked head (its tree equals a re-merge of the checked head with the destination it took in; needs git 2.38 or later) lands again by itself, without a review. Anything else, including a conflict resolved by hand, is an event (not yet proven in a live build).
