---
name: orchestrate-align
description: Use at a breakpoint in an orchestrated build, or when the user says "align", "sync the docs", "check the specs match the code" or "one source of truth". Checks every source (specs, plans, decisions and status files, agent memory, build logs and unit summaries, code, tests, any docs) against the implementation and each other, so each concept, entity and rule has one home that matches the code; fixes what agents may edit and routes the rest.
---

# Align

`orch` is `<repo>/.orchestrate/bin/orch`. The sources and their owners are `[[sources.entries]]` in `orchestrate.toml`; the one home of each kind of fact is `[[homes]]`.

## 1. Inventory

1. Read `[[sources.entries]]` and `[[homes]]`.
2. `orch align` writes a worklist to `.orchestrate/align/align-<date>.md` and lists:
   - dead references: paths, `file:line` past the end of a file, identifiers the implementation no longer has;
   - terms defined in more than one source;
   - kinds of fact whose home is missing;
   - planning files no source entry classifies;
   - scan failures when the spec gate is on.
3. For each unclassified file, propose its source entry (kind, owner, compaction) and add it once the user agrees.

## 2. Compare meaning

The worklist is the mechanical half. Then, concept by concept (glossary terms, entities, rules, guarantees, decisions):
1. Find every place it is stated: grep the sources and the code.
2. Read the code that implements it. The code is what the product does; a spec that disagrees is either a defect in the code or a stale spec, and only the owner decides which when the spec is owner-owned.
3. Classify each statement: the home (keep), a copy (replace with a pointer to the home), stale (fix or delete), or a contradiction (route).

When implementation docs are deferred (`[sources].impl_docs = "deferred"`), their absence is not a finding; implementation docs or comments that restate the plan are copies.

## 3. Route each finding

| Finding in | Do |
|---|---|
| An agent-owned source (plans, notes, bookkeeping) | Edit it: pointer, fix or deletion |
| Agent memory | Fix the stale fact, delete a wrong one, merge duplicates, update the memory index |
| An owner-owned source (spec, product model) | Write a patch (`git diff` format) in `.orchestrate/rulings/align-<date>.patch` and list it for the digest; never edit the file |
| The code (it contradicts a spec the owner keeps) | An `INBOX.md` item addressed to the next unit that touches it, or a new unit in the work plan |

No change narration in the edits: say the fact, not that it changed.

## 4. Finish

Re-run `orch align` until only items routed to the owner or the inbox remain. Commit agent-owned edits in each repository they live in (one commit per repository, `docs: align <scope> with the implementation`) if the user allows commits there; otherwise leave them staged and say so. Give the breakpoint digest: counts per finding kind, the patches for the owner, the inbox items added.
