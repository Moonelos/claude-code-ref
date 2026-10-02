# Behavioral expectations

- `shallow_formatted.md` must not reach `demonstrated`: it has the expected formatting but no owned
  state, actor/decision trace, changed-input contrast, or causal first-failure explanation.
- `demonstrated_foundation.md` should reach `demonstrated`: it supplies the problem, stored state,
  actor, transition, contrast, misconception boundary, and first failure. This local mechanism
  demonstration is not a calibration ceiling for a complete multi-mechanism lesson.
- `broken_runnable.md` must receive execution status `BROKEN` because the referenced local script
  does not exist; inspection of the command is not verification.
- `verified_runnable.md` must receive execution status `VERIFIED` only after the exact command is
  run from the fixture directory and its output matches.
- `overloaded_foundation.md` must fail coverage: it defines six independently stateful mechanisms
  without explaining or demonstrating any of them.
- The contract's first-time path must fail prerequisite order because
  `01_uses_later_concept.md` depends on `02_defines_later_concept.md`, which appears later.
- `lease renewal` must fail role ownership because its first-time canonical owner is a deep dive and
  achieves only a definition rather than the promised demonstration.
- `stale_current.md` must receive a dated primary-source currency finding; the reviewer must not rely
  on memory or silently treat a historically valid architecture as current.

Evaluate verdicts and reader outcomes, not exact report wording.

## Curriculum and transfer regression scenarios

Use these as behavioral variations on the fixtures, not keyword assertions:

- A complete author-supplied contract that omits a primary-source-supported essential must not earn
  complete curriculum coverage. Give the missing essential a coverage finding even when no local
  note mentions it; do not limit substantiated omissions to two per folder.
- With research tools unavailable, local judgments may proceed but the curriculum report must say
  INCOMPLETE. A clean local audit cannot imply current or comprehensive coverage.
- A historical/version-pinned collection must be evaluated within that scope. New releases are
  relevant migration context, not automatic proof that a historical explanation is wrong.
- On `demonstrated_foundation.md`, ask whether worker B can claim at t=40 after A renews at t=20.
  The taught deadline supports rejection until t=50. A prose trace does not require runnable code.
- On the same fixture, ask the reader to implement the actual fencing boundary. This exceeds the
  foundation's stated scope: the note names the later need but does not promise that implementation.
  Do not turn every legitimate forward reference into a missing production lesson.
- For an explicitly beginner-to-production collection, a correct introductory trace plus a list of
  operational terms is insufficient. Evaluate the production continuation at operationalized depth.
- A new transfer answer that requires an untaught premise fails even if the reviewer can solve it
  from expertise. An absent published exercise does not fail comprehension when an independent
  changed-condition probe is fully supported by the text.
- A long, causally clear lesson with no Key insight callout can pass; an unexplained short lesson
  with all style markers must fail. A justified third-entry payoff is not an automatic failure.

Run structural regressions with `python3 -m unittest discover -s <skill>/tests -p 'test_*.py'`.
The maker suite also checks that the shared references remain identical. Behavioral verdicts still
require the independent forward test; unit tests do not evaluate prose quality.

## Diagram, practice, and landscape scenarios

- A foundation note that explains a three-actor handoff (for example a lease renewal between two
  workers and a lock server) only in prose must get `VISUAL: FAIL` with a Mermaid sketch using the
  note's own actors and values. `demonstrated_foundation.md`'s single-actor trace may pass without one.
- A diagram that repeats nouns and arrows with no interpretation fails VISUAL even though a diagram
  is present.
- A foundation note with no recap or check-yourself questions gets `PRACTICE: FAIL`. Questions that
  only ask for a definition also fail. A reference note is `PRACTICE: n/a`.
- For `stale_current.md`, `landscape.audit.md` must list the current replacement with status,
  relevance, placement, and a dated URL. A memory-based item with no URL is a failure.
- With web tools available, `Research: INCOMPLETE` is a failure of the audit, not an acceptable
  shortcut. With no tools, the landscape header records what could not be searched and the user
  summary says so first.
- An emerging practice backed by a single blog post stays out of the report or is labeled as a
  research question. It is not an `EMERGING` item.

## Whole-lesson calibration

Use `lesson_quality/expectations.md` after a blind evaluation of its four note fixtures. Do not give
those expectations to the evaluating agent before it issues verdicts. Include the compressed but
factually correct lesson, its developed counterpart, the short micro-lesson, and the scoped reference.
Inspect causal evidence and repair quality, not output wording, note length, or diagram count.

For realistic forward testing, review an actual multi-mechanism beginner chapter, then author a
replacement and independently review it. Keep source notes unchanged during skill calibration and
retain an explicit scope for the test; a pedagogical pass is not a complete technical/currency audit.
