---
name: orchestrate-plan
description: Use when requirements are ready (READINESS.md says so) and the user wants the build split into units for several agents, or says "plan the units", "work plan" or "split this into milestones". Writes the work plan: units with outcomes and sizes, milestones, waves that may run in parallel, the interfaces between units, rules across units and open questions.
---

# Plan the units

Input: the requirements and `READINESS.md` from `orchestrate-onboard`. Output: one work-plan file in the planning repo, shaped like `templates/work-units.md`.

## 1. Check readiness

Read `READINESS.md`. If an item is `missing`, stop and say which; a unit cannot be planned from a gap. A `thin` item may be planned around if the unit that needs it is late and the gap is listed as an open question.

## 2. Cut units

A unit is one vertical slice: one behaviour through every layer it needs, with an outcome a reviewer can check against the requirements, small enough for one builder session and one pull request.
- **Size**: S (a few hours of agent work, under about 400 changed lines), M (a day), L (split it unless it cannot be split; say why).
- **Outcome**: one or two sentences in the glossary's words, naming the behaviours (and guarantee numbers, if the spec has them) it makes true.
- **Needs**: the units that must merge first.
- **Interfaces**: the contracts it creates or consumes.
- Put risky or uncertain units early. A refactor another unit needs is its own unit.

## 3. Group them

- **Milestones**: each ends in behaviour the owner can see work. Each milestone's end is a breakpoint, where alignment and compaction run and the owner reviews.
- **Waves**: within a milestone, units whose needs are met together. Two units in one wave may run at once only if they touch different files and interfaces; write the pairing rules down.
- **Hotspots**: list the files every unit of a stream will edit: registries, route or screen tables, check runners, sample-data indexes, generated files. Each one is a merge conflict, or a semantic break found only at land, waiting to happen when units pair. Before units pair, propose a layout with one file per feature (a folder the registry discovers, one check script per screen, one sample-data file per route) as an early refactor unit, and write the remaining hotspots into the pairing rules.
- **Streams**: optional labels (backend, console, process) when different skills or worktrees suit different units.

## 4. Fix the interfaces

For each interface two units share: its signature or data shape, who owns it, and how a change after work starts is handled (a short section, as in the template). Parallel units only start once their shared interfaces are written.

## 5. Write the file

Use `templates/work-units.md`. `orch` reads its units table: keep the `ID` and `Milestone` columns, with IDs of letters, digits and dashes. Then set `[project].work_plan` in `orchestrate.toml` to this file once setup has run.

## 6. Review with the owner

Show the milestones, the first wave and the open questions. The owner approves or changes them; record their answers in the plan's open-questions table, not as narration elsewhere.
