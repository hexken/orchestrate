---
name: orchestrate-optimize
description: Use when the user wants the orchestration tuned from its own record, or says "optimize the loop", "which models should we use", "is the second review worth it" or "why is it slow". Reads the stage times, events, review yield and token use from the logs, and proposes changes to roles, models, harnesses, review pipelines, timeouts or parallelism, each with its evidence, applied only on the user's yes.
---

# Optimize

`orch` is `<repo>/.orchestrate/bin/orch`. The record is in `.orchestrate/logs/` (events, job output, and one archived folder per finished unit with its timeline, review files and session transcripts).

## 1. Read the record

`orch report` (Markdown) and `orch report --json`; `--since <date of the last breakpoint>` to look at the latest stretch. It gives, per unit, minutes per stage (build, review, fix, light review, land), fix rounds, forge build minutes (when the land adapter prints `BUILD-MINUTES`) and events by kind; per reviewer role, reviews, findings (the items of each review's "Findings" section), and findings fixed, declined or deferred (from the builders' Fixes lines); tokens per role and model (Claude sessions; print-mode reviews from other harnesses have no token record).

Also read `orch note` lines in `logs/events.jsonl` (owner inputs and hand interventions): every hand intervention is a candidate for automation.

## 2. Find where the time and money go

- **Stage times**: which stage dominates the median unit? A long land usually means slow checks or builds; a long review, an expensive reviewer; long fixing, findings the builder struggles with.
- **Build minutes**: a forge's build minutes are a budget, often shared across projects, not only a wait. The push step has already run the checks locally, so a pull-request build can audit them (lint, types, a sample of a slow check such as a mutation-testing sample) instead of repeating whole suites; path conditions skip steps a change cannot affect (a UI-only change skips the server's steps); full suites and images run on the protected branch after the merge. On forges where a more specific pull-request selector overrides a generic one (check the forge's docs), give agent branches a slim pipeline and keep the full one for everyone else's pull requests. Steps that do not depend on each other can run in parallel. Re-lands after a sibling merge repeat whatever the build does, so cache or reuse results where the check allows.
- **Builds by source**: count builds and minutes per source branch, agent branches apart from everyone else's. Branches that have not taken a slimmer pipeline, or keep a run-on-every-push pipeline, go on spending minutes after the agents' share drops. Report it to the owner; never change or delete other people's branches or their pipeline settings.
- **Sibling merges**: re-lands and fix rounds right after another unit merged point at shared files (`orchestrate-plan`, Hotspots), not at the builder.
- **Review yield**: a reviewer's value is its findings that were fixed. Mostly declined findings mean noise; no findings over many reviews mean the review may be redundant with another (in one build, a light review of the fixes found nothing in 18 rounds, which is why it is off by default); findings that only one reviewer raises mean it sees something the others miss (a cross-vendor review often does: keep it, and cheap, even when its unique yield is low). A reviewer whose verdict word does not track its findings is caught by the Findings rule, but say so in its brief.
- **Events**: repeated stalls or wedges point at a harness, a model or a timeout; repeated land failures at the checks.
- **Tokens**: cost per role against that role's yield.

## 3. Propose, with the evidence

Each proposal: the change (as a diff to `orchestrate.toml`), the numbers behind it, the expected effect, and how to tell afterwards whether it worked. Typical changes: a smaller model or lower effort for a role with high cost and low yield; a stronger one where fix rounds pile up; dropping or adding a review in a `[pipeline]`; another harness for builders when one vendor's allowance runs short; `[timeouts]` that cause false stall events; `[land].checks` ordering (fast checks first) and a check for every CI step (`orch doctor`); the project's CI pipeline (build minutes); more or fewer worktrees. A change to the project's own CI or code is a unit of work, not a config edit.

Be honest about evidence: with a handful of units, differences are noise unless they are large. Prefer one change at a time, so its effect can be attributed, and changes that are easy to undo.

## Changing the tooling and its rules

The same care applies to `orch` itself, its adapters, briefs and any project copy of that logic:
- **Review a tooling change** like a unit, with a fresh reviewer. A finding in one copy of a rule (the package, a project's own predecessor script, an adapter) applies to every copy: fix them all, or note in `INBOX.md` which copy still has it.
- **Replay before deploying** a change to the verdict, findings or Fixes parsing: `orch verdict --replay > before.txt` on the old version, the same on the new, then `diff before.txt after.txt`. Every changed line must be an intended change; check it against the review file. Synthetic cases miss real prose (a "no defects found" sentence, a checklist headed "findings checked"), so the archive of real reviews is the test set. Add each surprise as a test.

## 4. Apply only on the user's yes

1. Edit `orchestrate.toml`; `orch roles` shows the result.
2. `orch note - "owner input: <the change and why>"`.
3. The supervisor reads the config when it starts: `orch stop`, then restart `orch supervise` in the background. Running units keep the roles they started with; new units get the new ones.
4. If a new harness was chosen, set up and check its adapter first (`orchestrate-setup`, step 4).
