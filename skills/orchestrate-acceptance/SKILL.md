---
name: orchestrate-acceptance
description: Use in an orchestrated build with the spec gate on, when a unit drafts or installs acceptance tests, when the user mentions scenario titles, guarantees, the DSL or "the scan", or when a red or green gate needs checking. Acceptance tests are written in the spec's domain language against a small DSL, drafted by agents, ruled on by the owner proxy, installed by script, and checked against the spec's scenario titles and guarantee numbers.
---

# Acceptance tests (DSL-first)

Settings are `[spec_gate]` in `orchestrate.toml`: the spec, `acceptance_dir`, `drafts_dir`, `install_checks`, the title and guarantee patterns, and `milestone`.

## The layers

1. **Acceptance tests** (`acceptance_dir`): plain tests in the glossary's words, plus the DSL interface they call. A test's name is a scenario title from the spec; `# Given`, `# When`, `# Then` mark its parts; a marker names the guarantee its title cites (`@pytest.mark.guarantee("G7")` by default); the body calls only the DSL and has no control flow. One module per feature. Agents draft these; they reach `acceptance_dir` only through the install step.
2. **The DSL implementation**, written by agents.
3. **The protocol driver** (for example HTTP against the running service).
4. **The system.**

The DSL interface is two typed protocols: `Platform`, the domain verbs through the front door (it can hand out several client handles for concurrency scenarios), and `Outside`, what a scenario does around the system (alter stored data, inject a fault, skew a clock). A test that uses `Outside` visibly bypasses the system. Grow the DSL one scenario at a time.

## Drafting and installing

1. `orch install-acceptance --sync` refreshes `drafts_dir` from `acceptance_dir`.
2. Draft in `drafts_dir`, mirroring `acceptance_dir`. Write `drafts_dir/COMMIT_MSG` for the batch.
3. Take the drafts to the owner proxy (`orchestrate-proxy`, kind `draft`).
4. `orch install-acceptance` copies the drafts in, runs `install_checks`, and commits only `acceptance_dir` with `COMMIT_MSG`. On a failed check it puts `acceptance_dir` back and commits nothing.

## Gates

- **Red**: before a scenario's system slice starts, its test must fail for the right reason. A new test carries a strict expected-failure mark listing the exceptions it expects (`xfail(strict=True, raises=NotImplementedError)`), so an outage fails instead of passing as expected. A red that needs judgment (a test that passes as soon as it is written, or stops in its Given) goes to the proxy with a mutation that turns it red.
- **Green**: when the test passes, remove the mark in the draft and install it. A strict unexpected pass is never pushed.

## The scan

`orch scan` compares the spec with the tests: a scenario title (a list line under a `### <section>.<milestone>` heading by default) with no test of that name; a test matching no title; a marker naming an unknown guarantee; guarantees with no test. Untested titles of milestones before `[spec_gate].milestone` fail the scan; later ones are only reported. Raise `milestone` when a milestone starts. Property tests (under `property_dir`) need no title.

A spec edit is the owner's: titles a unit needs go to the owner as a patch, and the unit's tests that depend on them wait in a patch in `.orchestrate/rulings/` until the titles exist. The breakpoint counts these held tests, since the scan passes without them.

If a test runs the scan on the real spec, every spec edit becomes a gate on every push: a spec line and the test changes it implies (a renamed title, a re-marked guarantee) must land together, in one change. Better still, let that test warn rather than fail on a marker the spec has just changed, and leave the failing to `orch scan` at the breakpoint.
