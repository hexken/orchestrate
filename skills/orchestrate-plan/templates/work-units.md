# Work units: <project>

The units still to build, the interfaces between them, and their order. How a unit runs is `.orchestrate/ORCHESTRATION.md` in the implementation repo.

## 1. How to read this

Read your unit's block in section 3, then the interfaces it names in section 4. Follow the sources a block cites only when you need them.

Unit IDs start with a milestone (`M1-`, `M2-`, …), `C-` (console) or `P-` (process).

## 2. Rules across units, and what is open

**Rules that span units.**
- <rule>

**Open** (the owner has not answered; units build on the assumption shown).

| Question | Assumption used | Units that move if the owner decides otherwise |
|---|---|---|
| <question> | <assumption> | <units> |

## 3. The units

| ID | Name | Milestone | Wave | Stream | Size | Needs |
|---|---|---|---|---|---|---|
| M1-EXAMPLE | <name> | 1 | 1 | backend | S | none |

### M1-EXAMPLE: <name>

- **Outcome**: <what is true when it merges, in the glossary's words; behaviours and guarantee numbers>
- **Scope**: <what it builds; what it leaves to later units>
- **Interfaces**: <creates or consumes, from section 4>
- **Sources**: <the files and sections it rests on>

## 4. The interfaces

### <Interface name>

- **Owner**: <unit>
- **Shape**: <signature, route, table or message, with types>
- **Consumers**: <units>

## 5. Order and parallelism

- **Wave 1**: <units>. Pairing: <which may run at once, and why they do not collide>.
- **Wave 2**: …

## 6. Changing an interface after work has started

The owning unit proposes the change in the inbox with the consumers named; consumers that have merged get a follow-up unit; consumers in flight finish against the old shape and adapt in their fix round.
