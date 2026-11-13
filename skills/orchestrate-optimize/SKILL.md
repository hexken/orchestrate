---
name: orchestrate-optimize
description: Use when the user wants the orchestration tuned from its own record, or says "optimize the loop", "which models should we use", "is the second review worth it" or "why is it slow". Reads the stage times, events, review yield and token use from the logs, and proposes changes to roles, models, harnesses, review pipelines, timeouts or parallelism, each with its evidence, applied only on the user's yes.
---

# Optimize

`orch` is `<repo>/.orchestrate/bin/orch`. The record is in `.orchestrate/logs/` (events, job output, and one archived folder per finished unit with its timeline, review files and session transcripts).

## 1. Read the record

`orch report` (Markdown) and `orch report --json`; `--since <date of the last breakpoint>` to look at the latest stretch. It gives, per unit, minutes per stage (build, review, fix, light review, land), fix rounds and events by kind; per reviewer role, reviews, findings, and findings fixed or declined; tokens per role and model (Claude sessions; print-mode reviews from other harnesses have no token record).

Also read `orch note` lines in `logs/events.jsonl` (owner inputs and hand interventions): every hand intervention is a candidate for automation.

## 2. Find where the time and money go

- **Stage times**: which stage dominates the median unit? A long land usually means slow checks or builds; a long review, an expensive reviewer; long fixing, findings the builder struggles with.
- **Review yield**: a reviewer's value is its findings that were fixed. Mostly declined findings mean noise; no findings over many reviews mean the review may be redundant with another; findings that only one reviewer raises mean it sees something the others miss (a cross-vendor review often does).
- **Events**: repeated stalls or wedges point at a harness, a model or a timeout; repeated land failures at the checks.
- **Tokens**: cost per role against that role's yield.

## 3. Propose, with the evidence

Each proposal: the change (as a diff to `orchestrate.toml`), the numbers behind it, the expected effect, and how to tell afterwards whether it worked. Typical changes: a smaller model or lower effort for a role with high cost and low yield; a stronger one where fix rounds pile up; dropping or adding a review in a `[pipeline]`; another harness for builders when one vendor's allowance runs short; `[timeouts]` that cause false stall events; `[land].checks` ordering (fast checks first); more or fewer worktrees.

Be honest about evidence: with a handful of units, differences are noise unless they are large. Prefer one change at a time, so its effect can be attributed, and changes that are easy to undo.

## 4. Apply only on the user's yes

1. Edit `orchestrate.toml`; `orch roles` shows the result.
2. `orch note - "owner input: <the change and why>"`.
3. The supervisor reads the config when it starts: `orch stop`, then restart `orch supervise` in the background. Running units keep the roles they started with; new units get the new ones.
4. If a new harness was chosen, set up and check its adapter first (`orchestrate-setup`, step 4).
