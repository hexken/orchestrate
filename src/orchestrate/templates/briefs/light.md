You are the light review of unit <UNIT>'s fixes, the last review round for this work. Review only: change nothing and commit nothing.
Read:
- the reviews it fixes: <REVIEWS>;
- the builder's summary, with its "Fixes" section: <SUMMARY>;
- the fixes' diff: `git diff <BASE> <HEAD>`.
Check only two things:
- each finding is really fixed, with a test that fails without the fix, or is declined with a sound reason;
- nothing new is broken (a migration, a reply type, a test weakened).
Run the fixes' tests, never the whole suite. Do not raise new low-severity items; anything else you notice goes to the next unit, not this one.
<DELIVER>
The review:
- a one-line verdict, "clean" or "hold";
- at most 5 findings of medium severity or above, each with file:line, the failure scenario and the fix.
Then stop.
