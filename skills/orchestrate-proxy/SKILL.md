---
name: orchestrate-proxy
description: Use in an orchestrated build with the spec gate on, when an agent has a question it would otherwise put to the owner (a spec gap, "accept these acceptance drafts?", a red that needs judgment), or when the user says "ask the proxy". A model rules in the owner's place, one batch at a time, with a blind first answer and a second vendor's vote where the kind of question calls for it; rulings are recorded and the owner confirms the ones that matter at each breakpoint.
---

# Owner proxy

The proxy is the role `[roles.proxy]` in `orchestrate.toml` (`orch roles` shows its model and effort); the second vote is `[roles.proxy_second]`, another vendor. Never substitute another model to save allowance.

## Scope

The proxy rules on: drafted acceptance tests and DSL changes; reds that need judgment; spec gaps. **How to build something is the builder's to decide**: if such a question reaches the proxy it answers "yours to decide".

It may only **recommend** on: what a guarantee or constraint requires; spec text (it proposes exact wording, the owner edits the spec); anything other people see, secrets, money, hard-to-undo git, merging. A proxy ruling is never the owner's approval.

## Kinds

| Kind | What it is | Blind answer first | Second vote | In the owner's digest |
|---|---|---|---|---|
| `draft` | An acceptance draft or DSL change | no | no | no |
| `red` | A red that needs judgment | no | no | no |
| `gap` | A spec gap with no guarantee reading | yes | no | no |
| `guarantee` | What a guarantee or constraint requires | yes | no | yes |
| `data-boundary` | What is stored, copied, kept or erased | yes | yes | yes |
| `statistics` | An estimator, interval, test, sample size or aggregation rule | yes | yes | yes |

A deterministic check comes first: a red that a strict `xfail(raises=...)` or a mutation run settles never goes to the proxy.

## Steps

1. **Batch the questions.** For each: its kind; the question in one or two sentences; options labelled (1), (2), … in no deliberate order, none marked as preferred; the evidence as diffs or paths. Keep your own preference out of the brief (note it separately for step 5).
2. **Call the proxy**, read-only, in two messages. With a Claude proxy use the Agent tool with the proxy role's model, in the background; with another harness, its adapter's print mode.
   - Blind round (only if the batch has a `gap`, `guarantee`, `data-boundary` or `statistics` question): "You are acting as the project owner's proxy and judge. Decide as a careful owner would: favour the spec's guarantees, small scope and plain wording. Read-only." Then the paths to read and those questions **without options**: "write your own answer from the spec, the decisions and the code, with the clauses it rests on."
   - Ruling: every question with its kind and options. Output per item: `Kind`, `Reasoning`, `Blind answer differs`, `Ruling` (an option, "none of these: …", "the owner's: …" or "yours to decide"), `Owner to confirm` (naming the guarantee), `Exact text`. Then `Missing from this brief` and a one-line verdict on any drafts.
   - Paths: the project rules, the decisions in force, the spec sections involved, the drafts, the active plan, review notes.
3. **Second vote** for `data-boundary` and `statistics`: the same brief, blind then with options, to `[roles.proxy_second]` in print mode. Where it differs, the item is **split; owner to confirm**. Carry on with the proxy's ruling, except on a split `data-boundary` item: take the ruling that stores, copies or keeps less.
4. **Apply** the rulings where agents may edit (drafts, plan, design notes, code). If drafts changed, ask the same proxy once to confirm each ruling was applied and nothing else changed.
5. **Record**: every brief and reply in full, with your preference notes, in `.orchestrate/rulings/<date>-<batch>.md`; one line per ruling in the active plan's "Rulings", tagged with its kind and `owner to confirm` or `split; owner to confirm` where it applies.
6. **Carry on**: install accepted drafts with `orch install-acceptance` (`orchestrate-acceptance`).
7. **At the breakpoint** the owner sees only: split rulings with both answers; every `guarantee`, `data-boundary` and `statistics` ruling; proposed spec text as exact before and after. One line each, with the rulings file. The owner confirms or overrules; also report, per kind, how often the owner confirmed the proxy since the last breakpoint. Answered rulings files are deleted after the owner's answers are recorded in their homes.
