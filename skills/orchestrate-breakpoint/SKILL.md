---
name: orchestrate-breakpoint
description: Use when a breakpoint is reached in an orchestrated build (the supervisor prints "breakpoint … reached"), at a milestone's end, or when the user says "add a breakpoint", "stop after unit X", "pause after this milestone" or "pass the breakpoint". Adds breakpoints, and at one runs its steps (freeze, align, compact, digest) and sends the owner one message.
---

# Breakpoints

`orch` is `<repo>/.orchestrate/bin/orch`.

## Adding one

- After given units: `orch breakpoint add <name> --after UNIT[,UNIT]`.
- After whatever is running now: `orch breakpoint add <name> --now`.
- At a milestone's end: added automatically when the milestone's first unit starts; by hand, `orch breakpoint add <name> --milestone <N>`.

While a breakpoint is not passed, `orch start` refuses units it holds back: a milestone-N breakpoint holds back units of later numbered milestones (units of milestone N, and units outside numbered milestones such as console or process units, still start); a breakpoint added with `--after` or `--now` holds back every unit it does not wait for. `orch breakpoint list` shows them.

## When one is reached

The supervisor prints `EVENT: - breakpoint <name> reached` once every unit it waits for has merged or closed. Run the steps in `[breakpoints].steps`, in order:

1. **freeze**: nothing new starts (automatic). Check `orch status`: every unit the breakpoint waits for is merged or closed.
2. **align**: `orchestrate-align`.
3. **compact**: `orchestrate-compact`.
4. **digest**: one message to the owner, short, with:
   - what was added: units merged (with pull requests), acceptance tests added;
   - held acceptance tests: with the spec gate on, count the drafts waiting in `.orchestrate/rulings/` on scenario titles the spec does not have yet. While they wait the scan passes without them, so say how many there are and which units they belong to, and give the owner one patch with every title they need, merged across units, not one patch per unit;
   - hotspots: files touched by three or more of the milestone's units (`git log --name-only` over its merges, counted per unit). Each one is a candidate for a one-file-per-feature split before the next milestone pairs units (`orchestrate-plan`, Hotspots);
   - what needs the owner: the proxy's digest (`orchestrate-proxy`, step 7), spec patches with their paths, alignment items routed to the owner;
   - `orch report --since <last breakpoint>` in two or three lines: median stage times, fix rounds, events, review yield; and any proposed tuning (`orchestrate-optimize`);
   - the next order: the next milestone's first wave;
   - a short retrospective: what went well, what to change in the process.
   Archive the orchestrator's own transcript into `logs/units/orchestrator/` (copy it from the harness's session folder).

Then wait for the owner's go and record it: `orch note - "owner input: <answer>"`, `orch breakpoint pass <name>`. Record each answer in its home (an overruled proxy ruling is corrected where it lives), and delete the answered rulings files.

**Conditional go**: if `[breakpoints].conditional_go` is set, it states conditions under which the build goes on without waiting. Check each condition against the record; if all hold, send the digest, pass the breakpoint, and start the next units; otherwise stop and say which condition failed.
