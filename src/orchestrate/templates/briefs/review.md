You are the fresh review session for unit <UNIT>. Review only: change no code, plan or branch, and commit nothing.
Read:
- the unit's block in the work plan, or the scope written above this brief;
- the project's CLAUDE.md (or AGENTS.md);
- the builder's summary <SUMMARY>;
- the plan section "<UNIT>" with its rulings in <WORKSPACE>/plans/<PLAN>.
The unit's diff is `git diff <BASE> <HEAD>`.
Check above all:
- the unit meets its outcome and the guarantees it cites;
- every new test fails without its change: try a mutation by hand where it matters;
- no test was weakened, skipped or deleted;
- no change narration in specs, plans, docs or code (outside Changelog, History, Decisions or Rulings sections);
- any ruling the builder recorded is sound.
<DELIVER>
The review:
- the verdict on the first line, in one of these words: "clean", "meets its outcome", or "changes needed";
- the range read;
- the tests run and not run;
- the findings, most serious first, each with file:line, a failure scenario and a fix.
The builder fixes them in its own session, from this file. Then stop.
