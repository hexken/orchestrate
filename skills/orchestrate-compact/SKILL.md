---
name: orchestrate-compact
description: Use at a breakpoint in an orchestrated build, or when the user says "compact", "clean up the notes", "remove the changelog noise" or "tidy the plans". Removes change narration from specs, plans, docs and code comments with a conservative, meaning-preserving pass, and properly compacts internal notes, memory, the inbox and status files.
---

# Compact

`orch` is `<repo>/.orchestrate/bin/orch`. Each source's strength is `compact` in `[[sources.entries]]`: `conservative`, `full` or `none`.

## Conservative (specs, plans, docs, code comments)

Remove only change narration: "now", "no longer", "changed from/to", "previously", "instead of" an option that is history, "per the owner's request", "as discussed", dated update notes, "(new)" markers, and reasons for a change that the text does not need to state the rule. Keep everything else word for word. Never touch a section headed Changelog, History, Decisions or Rulings.

For each file:
1. `orch compact scan <file>` lists the candidate lines (a worklist, not a verdict: "instead of" can be a real requirement).
2. Edit only the narration. "The limit is now 20 (changed from 10 at the owner's request)." becomes "The limit is 20."
3. `orch compact verify --rev HEAD <file>` (or `orch compact verify BEFORE AFTER`) must print "meaning kept": it refuses a pass that dropped a guarantee or other ID, a heading, a code block, a link, a table row, a normative word (must, never, always, only, at most) or a quantity with a unit. If it flags something you meant to remove, put it back: a conservative pass never removes those.
4. An owner-owned file gets a patch in `.orchestrate/rulings/compact-<date>.patch` instead of an edit.

Code comments follow the project's comment rules; narration in a comment ("changed to fix X", "was Y") goes.

## Full (notes, memory, inbox, status files)

Compact for the next reader:
- merge duplicates; drop items that are resolved or superseded (their outcome is in git, the rulings or the code);
- fold what the logs taught into lasting facts in the right note or memory file, then leave the logs archived (`logs/` is never deleted);
- keep pointers to homes instead of restating them;
- update any memory index so every line points to a file that exists.

## Finish

One commit per repository you are allowed to commit in (`docs: compact <scope>`), else leave the changes staged and say so. For the digest: lines removed per file, patches for the owner.
