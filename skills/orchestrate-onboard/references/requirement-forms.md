# Requirement forms and how each maps to the readiness bar

Every form reduces to the same bar (`readiness.md`). For each form: what to extract, and what it usually lacks.

## Prose requirements or user stories

- Extract: purpose; roles from "As a …"; behaviours from "so that …" and acceptance criteria; constraints from any numbers.
- Usually lacks: concrete examples (item 4), exact values (5), out of scope (9). Stories often use two words for one concept: build the glossary from the nouns and ask about near-synonyms.

## Gherkin features

- Extract: each scenario is a behaviour with an example; `Background` and `Given` steps name state and roles; the step vocabulary is a glossary draft.
- Usually lacks: components and data flow (6), why a rule exists, constraints that no scenario exercises. Check that step phrases mean one thing each.

## An ontology (entities, relations, attributes, invariants)

- Extract: the glossary (entities and relations) and the constraints (cardinalities, invariants, attribute types).
- Usually lacks: behaviours (4): an ontology says what exists, not what happens. Ask for the operations on each entity: who creates, changes, approves and deletes it, and what is refused.

## An ontology with flows (state machines, sequence diagrams, flowcharts)

- Extract: behaviours from each transition (from state, event, guard, to state, effect); roles from the actors; components from the swimlanes.
- Usually lacks: examples with real values, error paths (the transitions not drawn), and exact values for guards. Diagrams as images cannot be read here: ask for them as text (Mermaid, PlantUML, or a transition table).

## An architecture or design document

- Extract: components, data flow, external systems, constraints, homes.
- Usually lacks: behaviours from the user's side and acceptance. Separate mechanism (how) from requirement (what must be true): only the second belongs in a spec.

## Mixed sources

Pick, per kind of fact, which source is its home (item 8) and mark the others as copies to point at it. Record every disagreement between sources as a conflict; never resolve one silently.
