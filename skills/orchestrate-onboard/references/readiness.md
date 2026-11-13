# The readiness bar

Requirements are ready to plan from when every item below is `present`. "Present" means a builder who reads only the named file could write a test for it.

| # | Item | Present when | Typical question when missing |
|---|---|---|---|
| 1 | Purpose | One paragraph: what the product does and for whom, and what "done" means for this build. | "What must be true for this build to count as finished?" |
| 2 | Users and roles | Each kind of user, what they do, and what each may and may not do. | "Who uses it, and is there anything a given role must never be able to do?" |
| 3 | Glossary | One word per concept, each defined once. No two words for one thing. | "Are X and Y the same thing? Which word do we keep?" |
| 4 | Behaviours | Each behaviour is a checkable statement with at least one concrete example (input, action, expected result). | "What happens when …? Give one example with real values." |
| 5 | Constraints and exact values | Limits, thresholds, formats, data shapes, invariants, with numbers and units. | "What is the limit, exactly, and what happens at it?" |
| 6 | Components and data flow | Box-level: the parts, what each owns, how data moves between them, what is stored where. | "Which part owns this data, and who may change it?" |
| 7 | External systems | Each outside system: what is sent and received, who owns the credentials, what happens when it is down. | "What happens when that service is unavailable?" |
| 8 | Homes | Where each kind of fact is specified: one file per kind. | "Where should a future reader look for this rule?" |
| 9 | Out of scope | What this build will not do, stated. | "Is X in this build or later?" |
| 10 | Open questions | Each open question listed, with the assumption used until it is answered. | (list them) |
| 11 | Acceptance | How the owner will judge a milestone: tests, a demonstration, a review. | "How will you decide a milestone is done?" |

Items 6 and 7 may be thin for a small project; say so rather than inventing structure. Item 4 is never optional: units are planned from behaviours.
