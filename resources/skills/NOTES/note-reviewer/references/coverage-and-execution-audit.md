# Coverage maturity and executable-claim audit

This pass prevents formatted summaries from being mistaken for teaching and prevents inspected code
from being mistaken for reproduced behavior.

## Mechanism coverage levels

Classify each mechanism promised by the collection or required by the independently researched
curriculum in `curriculum.audit.md`. Do not restrict the inventory to mechanisms the author selected:

| Level | Required evidence |
|---|---|
| `mentioned` | The mechanism is named only for orientation. |
| `defined` | Its kind and basic purpose are grounded. |
| `explained` | Its need, owned state or decision, causal mechanism, and consequence are clear. |
| `demonstrated` | `explained` plus a named faithful trace or artifact and a meaningful contrast when needed. |
| `operationalized` | `demonstrated` plus verification, first real failure, recovery or rollback, and production boundary. |

Use the persisted contract when present, but challenge omissions and insufficient depth against the user goal and independent curriculum. Otherwise infer the required level from the reader promise:
core first-time mechanisms normally require `demonstrated`; a production implementation promise
normally requires `operationalized`; decision and reference material may legitimately stop earlier.

Do not award a level from headings, word count, code-block count, a glossary line, or a warning. Cite
the exact section that supplies each required piece. Record the achieved level even when it falls
short, so `defined` is never silently treated as `demonstrated`.

Coverage and whole-lesson quality are separate. A demonstrated mechanism may appear inside an
inadequately developed lesson; retain its honest local coverage while reporting LESSON FAIL in
`lesson_quality.audit.md`. Do not aggregate one example's coverage over other mechanisms in a chapter.

## Evidence-backed teach-back

For each core mechanism, reconstruct these six elements using only the canonical owner and declared
earlier prerequisites:

1. **Problem** — the world without the mechanism and its consequence.
2. **Owned state or decision** — what the mechanism remembers, controls, or chooses.
3. **Actor** — who reads or changes that state or decision.
4. **Transition** — one named input, action, resulting state, and observable result.
5. **Misconception boundary** — a plausible wrong model the prose or contrast rules out.
6. **First failure** — what breaks first and why another layer is needed.

Fail teach-back when any required element must be supplied from the auditor's domain knowledge,
later path entries, or an external source. State the missing elements in the per-file verdict. Do not
write a polished explanation on the note's behalf and then use that explanation as evidence.

## Overloaded foundation and role ownership

Inspect whether one foundation note claims several mechanisms with independently changing state,
different prerequisites, or different faithful carriers. Count promised central mechanisms, not
nouns. Flag the note when its prose can only define them or jump between them rather than reach the
required level. Prescribe development, a merger with prerequisite fragments, a split, or an explicit composition lesson as warranted; do not impose
a line quota.

Flag a core beginner mechanism first owned by a `deep dive`. A deep dive may refine a mechanism only
after an earlier foundation owner establishes the first correct model.

## Whole-tree coverage output

Write `_audit/coverage.audit.md`. Use one block per core mechanism, ordered by first-time path and
then production continuation:

```text
# <mechanism>
Promised by: <README/path/note claim or user outcome plus independently researched requirement>
Canonical owner: <path or missing>
Required: mentioned|defined|explained|demonstrated|operationalized
Achieved: mentioned|defined|explained|demonstrated|operationalized|absent
TEACH-BACK: PASS|FAIL|n/a; missing: <elements or none>
ROLE: PASS|FAIL; <reason>
SIGNAL: path-promise|canonical-owner|researched-essential|current-landscape
SOURCE: <note evidence, or primary-source URL plus checked date for current-landscape>

COVERAGE-HIGH: <reader harm> — <expand, split, move, or add a canonical owner>.
COVERAGE-MED: <reader uncertainty> — <specific correction>.
NO-ACTION: <why the promised level is met>.
```

Use `COVERAGE-HIGH` when a first-time or implementation promise cannot be fulfilled. Use
`COVERAGE-MED` when the mechanism works only after inference or detour. These are not missing-note
`GAP` lines and do not force a new file.

## Executable-claim inventory

Inventory every block or procedure described as runnable, copyable, integration, test, smoke test,
end-to-end, or promising output from an executable command. Narrative timelines, state tables,
and conceptual worked traces are not executable claims merely because they show exact values.
Audit their reasoning as teaching evidence; do not demand a runnable implementation.
Also inspect local imports, referenced fixture/test files,
services, credentials, topics, schemas, databases, process synchronization, and cleanup.

Assign one status:

- `VERIFIED` — executed exactly as shown in the documented environment; exit status and observed
  output match the claim.
- `BROKEN` — execution was safe and attempted, but the command, dependency, termination, assertion,
  or output failed.
- `PARTIAL` — only a smaller component could be reproduced; the composed claim remains unverified.
- `NOT-RUN` — execution would require unavailable infrastructure, credentials, unsafe mutation, or
  authority outside scope.
- `EXCERPT` — explicitly non-runnable explanatory material; check syntactic faithfulness and safety,
  but do not count it as an executable claim.

Inspection alone never yields `VERIFIED`. A manifest supplied by the author is evidence to reproduce,
not proof to trust blindly. Do not execute destructive, costly, or externally mutating procedures
without the required authority; use `NOT-RUN` and explain the boundary.

Write `_audit/examples.audit.md`:

```text
# <note path> :: <claim id or line>
Claim: runnable|copyable|integration|test|end-to-end|excerpt
Status: VERIFIED|BROKEN|PARTIAL|NOT-RUN|EXCERPT
Command: <exact command or n/a>
Environment: <bounded environment>
Observed: <exit status and concise output or reason not run>

FIX-CRITICAL: <unsafe executable claim> — <safe correction>.
FIX-HIGH: <broken central claim> — <specific correction>.
FIX-MED: <unverified supporting claim> — <specific correction or narrower label>.
NO-ACTION: <reproduced behavior>.
```

If the scoped collection contains no executable claims, write exactly
`NO-EXECUTABLE-CLAIMS: <scope checked>` instead of inventing a block.

Exclude `EXCERPT` blocks from executable-claim denominators. Unsafe executable defects are owned by
`examples.audit.md`; the per-file report may point to that block but must not repeat or recount the
same severity. A stale claim present in a note is owned by its per-file report. A significant current
mechanism missing from the collection is owned by `coverage.audit.md` with
`SIGNAL: current-landscape`.

## Current-landscape comparison

Always research foundational completeness using `curriculum-research.md`. For evolving subjects,
also build a dated landscape from primary sources before declaring coverage complete:

- supported/current versions;
- removed or deprecated mechanisms;
- recently generally available capabilities;
- preview or early-access capabilities that materially change advice;
- upgrade, downgrade, security, or operational changes with reader impact.

Compare that landscape with the collection. Add externally evidenced missing current mechanisms to
`coverage.audit.md` with `SIGNAL: current-landscape`; use `researched-essential` for missing established
fundamentals. Cite source URLs and checked dates. Stale claims already present belong to the per-file
report; cross-reference them here without duplicating severity.
Do not turn release notes into a wishlist: include only changes that alter the collection's declared
scope, recommended design, runnable examples, or production operation.

Record transfer evidence separately in reader-path reports; successful restatement does not prove
reasoning under a changed condition.

## Regression cases

Before accepting changes to this skill, test it against at least these behavior classes:

1. a strong foundation note that should pass;
2. a shallow but perfectly formatted note that must fail coverage;
3. an overloaded foundation that defines many mechanisms but demonstrates none;
4. a runnable example with a missing local import or fixture;
5. a correct reproduced example;
6. a path whose dependency appears later;
7. a deep dive incorrectly owning the beginner model;
8. a stale claim and a significant current feature absent from a fast-moving collection.

Judge verdicts and reader outcomes, not exact wording.
