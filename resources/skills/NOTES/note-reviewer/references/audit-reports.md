# Audit reports and evidence ownership

Write one block per relevant unit, including clean units. Cite actual file sections/lines for local
findings and primary URLs plus checked dates for external claims. Every finding explains reader
impact and the smallest sufficient correction. A source link supports a claim; it does not supply
missing teaching on the note's behalf.

## Independent curriculum — `_audit/curriculum.audit.md`

Build this inventory independently using `curriculum-research.md`. The user's goal takes precedence
over an author's narrower self-declared scope. Record the investigation even when no gaps are found.

```text
# Independent curriculum — <checked date>
Research: COMPLETE|INCOMPLETE
Audience: <explicit assumed knowledge and needed prerequisite bridges>
Scope: <user outcomes, version baseline, justified exclusions>
Sources: <inspected primary URLs with checked dates>
Limitations: <unverified areas or none>

| Item / capability | Layer | Why necessary | Required depth | Primary evidence + checked date | Owner / gap / justified exclusion |
|---|---|---|---|---|---|
```

The inventory cross-references canonical findings in `coverage.audit.md` without repeating severity.
`COMPLETE` describes a completed scoped investigation, not perfect coverage by the notes. If research
was unavailable, use `INCOMPLETE` and distinguish locally observable defects from unverified gaps.

## Per-note reports — `_audit/<folder>.audit.md`

Use the full relative folder path encoded with `__` to avoid collisions; use `root.audit.md` for root
notes. Each learner-facing Markdown file gets a block. Pure indexes/references use role-appropriate
`n/a` verdicts with reasons; do not invent a tutorial requirement for them.

```text
# <relative/note.md> (<N> lines)
ORDERING: role <role>; PASS|FAIL|n/a; payoff <line/total or n/a>; <sequence evidence and reader impact>.
EXPLANATION: PASS|FAIL|n/a; teach-back PASS|FAIL|n/a (missing: <elements or none>); <evidence and optional diagnostic counts>.
LESSON: PASS|FAIL|NOT-CHECKED|n/a; <whole-unit evidence or link to its canonical lesson-quality block>.
Summary: N critical, N high, N med, N low

FIX-CRITICAL: <actively misleading or harmful behavior> — <specific correction>.
FIX-HIGH: <central capability blocked> — <specific correction>.
FIX-MED: <avoidable inference, detour, or uncertainty> — <specific correction>.
FIX-LOW: <presentation or navigation issue> — <specific correction>.
NO-ACTION: <evidence supporting a clean result>.
```

Use only applicable finding lines. `RELATED: <canonical report and finding>` may cross-reference
a coverage- or execution-owned defect without a duplicate severity. A FAIL verdict can therefore
have zero local findings; do not label that note NO-ACTION or imply it passed.
Keep ORDERING, EXPLANATION, LESSON, and Summary for clean blocks too.
LESSON FAIL prevents EXPLANATION PASS even if teach-back facts are extractable. A clean fact
audit must not suppress a structural teaching finding.
A clean note gets NO-ACTION, not an invented defect. Evidence-backed teach-back reconstructs each
applicable element: problem, state/decision, actor, transition/result, misconception boundary, and
first failure. Name the missing premise rather than supplying it from expert knowledge.

## Complete lessons — `_audit/lesson_quality.audit.md`

Evaluate full teaching units using `lesson-design.md`. A unit may span several files; list them so
all scoped teaching notes are accounted for. Pure lookup/index units may use n/a with an explicit
reason. Keep the verdict independent of local mechanism demonstration and execution.

```text
# <lesson or learning-unit name>
Files: <all files comprising this unit>
LESSON: PASS|FAIL|NOT-CHECKED|n/a
Reader: <permitted starting knowledge and promised capability>
Evidence: <development map across substantive promises, with exact passages, worked reasoning, and developed/stated/deferred status>
Reasoning burden: <what the learner must invent, or why the unit supplies the connections>
Visual support: <specific relationship to depict and interpret, existing sufficient support, or justified n/a>
Structure: <KEEP|LOCAL-EDIT|REORDER|MERGE|SPLIT|REWRITE; combination allowed, with reason>
Summary: N critical, N high, N med, N low

FIX-HIGH: <central learning outcome blocked by organizing/explanatory defect> — <structural correction>.
FIX-MED: <avoidable inferential load or fragmentation> — <correction>.
NO-ACTION: <why the unit teaches its promise; use only for a clean assessed unit>.
RELATED: <canonical finding elsewhere, without duplicate severity>.
```

Choose only applicable finding lines. For NOT-CHECKED, state what could not be read or evaluated;
never use NO-ACTION for unchecked/failed units. All required fields remain present with a scope
reason for n/a. A coherent short lesson may PASS; a factually correct long lesson may FAIL.

For a structural action (REORDER, MERGE, SPLIT, or REWRITE), add:

```text
Proposed sequence: <the learner questions and causal steps in their new order>
Content mapping: <existing sections/files -> keep/merge/move/develop destinations; preserve useful depth>
Example development: <named scenario, successive changes, interpreted visual where needed>
Rewrite sample: <representative replacement prose with a real worked inferential bridge>
Acceptance task: <new prediction/diagnosis and reasoning that repaired teaching must support>
```

Provide the actual passage under Rewrite sample, not a promise to write one. Do not prescribe a
new file solely to fix fragmentation, nor remove advanced material simply to make a beginner path
shorter. A NO-GAPS result elsewhere means no new notes were proposed; it says nothing about the
need to merge, reorder, or rewrite existing ones. One complete-unit owner reconciles cross-agent
findings and keeps systemic defects here; local/path reports cross-reference them.

## Reader paths — `_audit/reader_paths.audit.md`

Read the full prose of every named path, including the production continuation. Track entry knowledge,
exit capability, first missing premise, complexity jumps, stop points, and canonical ownership.
If no path is named, examine the evident reading sequence and identify it as inferred. Flag missing
navigation only when it creates real reader harm; a coherent single-note lesson needs no artificial
README path. For a pure lookup collection, record an n/a path block with its scope reason.

```text
# <README or entry file> :: <path name>
Outcome: <promised capability>
Files: <ordered paths; identify any inferred ordering>
EXECUTION PAYOFF: entry <N> (PASS|FAIL|n/a; <justified milestone and evidence>)
UNDERSTANDING PAYOFF: entry <N> (PASS|FAIL|n/a; <justified milestone and evidence>)
TRANSFER: PASS|FAIL|NOT-CHECKED|n/a
Checkpoint: <after which entry; or scope/availability reason>
Scenario: <meaningful changed condition>
Reasoning: <expected causal solution, not merely the final result>
Evidence: <earlier passages supplying the reasoning, or missing premise>
Summary: N critical, N high, N med, N low

FIX-HIGH: <earliest path-specific barrier> — <correction>.
FIX-MED: <avoidable path uncertainty> — <correction>.
FIX-LOW: <navigation issue> — <correction>.
NO-ACTION: <why the path works>.
```

For multiple checkpoints, use `##` subsections inside the same path block, each with TRANSFER,
Checkpoint, Scenario, Reasoning, and Evidence. The path-level verdict is FAIL if any necessary
checkpoint fails; NOT-CHECKED if none fails but a necessary checkpoint remains unchecked. Exclude
reasoned n/a checkpoints from denominators. A missing published exercise does not itself prove
failed understanding: independently test whether the text supports a changed-condition probe.

Execution and understanding are separate. A concrete conceptual trace can provide the first result.
Two entries is a diagnostic target, not an automatic severity. Judge missing or avoidably delayed
learning against necessary prerequisites and promised milestones. Do not borrow from later chapters.

## Depth and execution reports

Use the formats in `coverage-and-execution-audit.md` for `_audit/coverage.audit.md` and
`_audit/examples.audit.md`. Inventory both author's promises and independently researched essentials.
Coverage classifications describe achieved depth, not headings, word counts, or example counts.
The absence of runnable claims is recorded explicitly as `NO-EXECUTABLE-CLAIMS: <scope checked>`.

## New-note proposals — `_audit/gaps.audit.md`

Inspect the whole tree before deciding a topic is absent. Prefer repairing an existing canonical
owner when its role can carry the explanation. New notes are placement proposals, not the only way
to fix a substantive omission. Coverage findings remain actionable even if no new file is needed.

Use one block per content folder (including root); list folders with gaps first:

```text
# <folder>/
Suggested new notes: N
GAP: <topic or bridge> — <why this requires its own learning unit>.
  SIGNAL: leaned-on|learning-bridge|promised|researched-essential|domain-expectation
  EVIDENCE: <local evidence or primary-source URL and checked date; cross-reference coverage finding>
```

- `leaned-on`: a necessary concept used without teaching it.
- `learning-bridge`: cite both sides of the dependency jump and the path that forces it.
- `promised`: an advertised capability has no teaching owner.
- `researched-essential`: independently sourced in-scope requirement, even if no note mentions it.
- `domain-expectation`: an unverified research question; explicitly label the uncertainty.

Do not cap substantiated gaps by count. Explain their relevance to the user's scope; exclude unrelated
adjacent topics. With no new-note proposals, use `NO-GAPS: <why existing owners suffice; cross-reference
any shallow coverage>` instead of GAP lines. No FIX severities belong here. An audit does not itself
authorize fixes; in an already authorized authoring/remediation workflow the responsible author may
act on these proposals without treating this report format as a new approval requirement.

## Metrics — `_audit/metrics.audit.md`

Aggregate after all passes. Record included/excluded scope and each actual denominator, distinguishing
unchecked from failed. A zero denominator is n/a, not a 100% pass. Separate research completion from
coverage by the notes. Report at least:

```text
# Audit metrics — <checked date>
Scope: <included/excluded paths; teaching/index notes; paths; mechanisms; executable claims>
Research: COMPLETE|INCOMPLETE
Essential curriculum items accounted for: <N/N; justified exclusions and unresolved items>
Transfer checkpoints passed: <N/N checked; N unchecked; n/a excluded>
Lesson quality passed: <N/N assessed teaching units; failed and unchecked counts; n/a excluded>
Paths with an execution payoff within two entries: <N/N; diagnostic only>
Paths with an understanding payoff within two entries: <N/N; diagnostic only>
Core mechanisms at required coverage level: <N/N>
Executable claims reproduced: <N/N; broken/partial/not-run counts>
Current-landscape items absent or stale: <N, or unverified if research incomplete>
```

Additional useful metrics include unexplained prerequisite uses, unsupported prescriptions, missing
concrete examples, or first models deferred to deep dives. Counts and ratios are supporting evidence,
not pedagogical acceptance gates. Record historical baselines only when supplied for this actual
collection; never import measurements from another repository.

## One owner per defect

- Unsafe or broken executable behavior: `examples.audit.md`.
- Stale existing claims and local explanation issues: per-note report.
- Absent or underdeveloped mechanisms: `coverage.audit.md`.
- Whole-unit explanatory development and editorial structure: `lesson_quality.audit.md`.
- Sequence-only dependency problems: `reader_paths.audit.md`.
- Expected curriculum inventory and reconciliation: `curriculum.audit.md`.
- Optional new-file placement: `gaps.audit.md`.

One correction may improve several dimensions. Other reports may cross-reference its canonical owner
without repeating severity or counting it twice. Distinct root causes can have separate findings.
