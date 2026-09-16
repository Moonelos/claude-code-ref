# Curriculum contract and release gates

Use this contract before choosing files. It records what the collection promises to teach and gives
the author, validator, and independent reviewer the same acceptance target.

## Coverage levels

Use the lowest level that fully describes the intended reader outcome:

| Level | Evidence required |
|---|---|
| `mentioned` | The mechanism is named only for orientation. |
| `defined` | Its kind and basic purpose are grounded locally. |
| `explained` | The note shows the problem, owned state, causal mechanism, and consequence. |
| `demonstrated` | `explained` plus a faithful named trace or artifact and a meaningful contrast when needed. |
| `operationalized` | `demonstrated` plus verification, first real failure, recovery or rollback, and production boundary. |

A mechanism is not covered merely because a heading or definition exists. Core mechanisms on a
first-time path normally reach `demonstrated`; implementation mechanisms promised as production
ready reach `operationalized`.

## Machine-readable plan

Write `<collection>/_meta/learning_contract.json` before drafting. New collections use schema version 2.
Existing collections without a version remain readable; identify missing audience/research/transfer
information during review rather than declaring their prose invalid because metadata is old.

Version 2 adds:
- `assumed_knowledge`: explicit general skills (an empty list means none);
- `scope`: promised outcomes and exclusions;
- `research`: path to `_meta/curriculum_research.md`;
- `prerequisite_bridges`: objects with `concept` and canonical `owner` note path;
- `transfer_checks`: milestone objects with `path_name`, `after_note`, `prompt`, `expected_reasoning`,
  and nonempty `evidence_notes` containing only current/earlier path entries.
Include at least one meaningful transfer checkpoint for each non-reference learning path. A pure reference collection may use
an empty list with `transfer_exemption` explaining why. These fields document acceptance evidence;
validators cannot prove the research or reasoning is sound.

Every path is relative to the
collection root, such as `fundamentals/01_first_result.md`. A path `kind` is one of
`first-time`, `production`, `decision`, or `reference`. Use this shape:

```json
{
  "schema_version": 2,
  "audience": "Programmer new to the subject and its specialist prerequisites",
  "assumed_knowledge": ["basic programming", "ordinary command-line use"],
  "scope": "Explain and operate the scoped mechanism; unrelated platforms excluded",
  "research": "_meta/curriculum_research.md",
  "prerequisite_bridges": [],
  "transfer_checks": [{
    "path_name": "First-time path",
    "after_note": "fundamentals/02_mental_model.md",
    "prompt": "Predict the next observable result when the actor fails after the shown transition.",
    "expected_reasoning": "Trace the retained state and next actor action using the rules taught in the owner.",
    "evidence_notes": ["fundamentals/02_mental_model.md"]
  }],
  "paths": [
    {
      "name": "First-time path",
      "kind": "first-time",
      "entries": ["fundamentals/01_first_result.md", "fundamentals/02_mental_model.md"],
      "execution_payoff_by": 1,
      "understanding_payoff_by": 2,
      "stop_point": "Can run and explain the baseline"
    }
  ],
  "notes": [
    {
      "path": "fundamentals/01_first_result.md",
      "role": "foundation",
      "prerequisites": [],
      "entry_capability": "Basic programming and command-line use",
      "exit_capability": "Can trace the first concrete result"
    },
    {
      "path": "fundamentals/02_mental_model.md",
      "role": "foundation",
      "prerequisites": ["fundamentals/01_first_result.md"],
      "entry_capability": "Can observe one result",
      "exit_capability": "Can explain the state transition that produced it"
    }
  ],
  "mechanisms": [
    {
      "name": "partition ownership",
      "owner": "fundamentals/02_mental_model.md",
      "required_level": "demonstrated",
      "reader_must_explain": ["why it exists", "who changes it", "what happens on failure"],
      "carrier": "three actors, two partitions, one ownership change"
    }
  ]
}
```

Record `milestone_rationale` on paths whose first execution/trace or understanding payoff is later
than entry two. Explain the actual prerequisite sequence, not a desire to postpone teaching.
Reconcile the mechanism list with the independent research ledger before approving the contract.
An essential mechanism cannot disappear merely because no planned note claims it.

## Foundation decomposition test

A foundation note owns one central mental model. Split or explicitly justify the composition when
its mechanisms have independently changing state, different prerequisites, or separate faithful
carriers. A multi-noun title is a prompt to inspect the composition, not an automatic failure and
not a reason to split simple adjacent definitions.

A deep dive may refine a core mechanism only after an earlier foundation owner has established the
beginner-level model. It cannot silently become the first place where the path teaches that model.

## Evidence-backed teach-back

After each foundation entry, answer using only that entry and earlier path entries:

1. What problem existed before the mechanism?
2. What state or decision does it own?
3. Who or what changes that state?
4. Which named input and transition produce the visible result?
5. Which plausible wrong model does the explanation rule out?
6. What breaks first, and why is the next layer needed?

If any answer requires outside knowledge, later material, or repeating a rule without its cause, the
entry has not reached `demonstrated`.

## Example verification manifest

Write `<collection>/_meta/example_verification.json` with one record for every runnable claim:

```json
{
  "examples": [
    {
      "id": "first-round-trip",
      "note": "fundamentals/01_first_result.md",
      "claim": "runnable",
      "command": "uv run python example.py",
      "environment": "temporary local service",
      "exit_code": 0,
      "observed_output": ["created id=42", "read id=42"],
      "verified": true
    }
  ]
}
```

Use a `claim` value of `runnable`, `copyable`, `integration`, `test`, or `end-to-end`.

Inspection is not execution. If a dependency cannot be run, record it as unverified and report the
missing gate. An explanatory excerpt is appropriate only if it still fulfills the requested learning
role; do not remove a promised runnable outcome to make validation pass. Never manufacture output.

## Release gate

Before delivery, require separate verdicts for:

- independent curriculum research and essential-item reconciliation;
- explicit audience and prerequisite closure;
- transfer to new conditions at learning milestones;
- structural validation;
- execution verification;
- first-time-path execution payoff;
- first-time-path understanding payoff;
- mechanism coverage at the promised levels;
- independent audit;

Do not summarize these as one undifferentiated `PASS`.
