---
name: note-reviewer
description: "Independently audit technical learning notes for curriculum completeness, explanations from explicit prerequisites, progressive depth, transfer of understanding, reproducible examples, production readiness, and missing or outdated material researched from primary sources. Produces evidence-backed reports without editing notes."
---

# Audit whether the collection teaches its subject

Evaluate both the learning promise and whether that promise covers the user's requested subject.
Correct facts, attractive formatting, runnable examples, and a complete table of contents are each
insufficient on their own. Judge the reader's ability to explain, predict, build, and operate.

## Resolve scope and read the contract

Use the collection root supplied by the user. For MkDocs, use `docs_dir` and learner-facing `nav`.
Include root teaching notes; exclude `_audit/`, `_meta/`, generated sites, dependencies, vendored
content, hidden agent directories, build output, and fixtures unless explicitly in scope. Read
`_meta/` evidence when present without treating it as learner-facing teaching or proof.

Read these references before their corresponding passes:

- `references/how-we-write-notes.md`: shared audience and teaching contract, before judging prose.
- `references/curriculum-research.md`: independent scope, primary-source research, and transfer tests,
  before inspecting author coverage claims.
- `references/learning-curve-and-explanation-audit.md`: ordering, explanation, and safety checks.
- `references/example-selection.md`: concrete artifacts and interaction examples.
- `references/coverage-and-execution-audit.md`: coverage maturity, teach-back, execution, and currency.
- `references/audit-reports.md`: report ownership and output formats, before writing findings.

Use the user's actual audience and scope ahead of author declarations. “From zero” includes needed
subject-specific prerequisites unless the user explicitly supplies them as prior knowledge. A label
such as “for engineers” does not establish distributed-systems or other specialist expertise.
Record ambiguous assumptions and evaluate their reader impact; do not silently invent knowledge.

Before dispatching a large audit, read `references/delegation.md` when a topic reaches 6
teaching files or the collection reaches 8 files. Assign local batches and whole-collection owners.

## Required audit passes

### 1. Independent curriculum and research

Build the expected curriculum from the user's goal and primary sources before accepting the author's
chosen mechanisms. Research established essentials even for stable topics. Separately inspect current
versions, release/migration guidance, deprecations, and relevant production changes for evolving
subjects. Read sources, not just search snippets; cite URLs and checked dates. An accepted proposal
is not evidence that a feature shipped. Respect an explicit historical/version scope and distinguish
migration advice from errors in that scope.

Write `_audit/curriculum.audit.md`, including research status even when no gap was found. Compare
each expected capability with the actual teaching, required depth, and justified exclusions. Include
missing essentials even if no existing note mentions them. Do not cap externally substantiated gaps
at an arbitrary number. Avoid unrelated ecosystem wishlists by explaining how each item is needed
for an in-scope outcome. If browsing is unavailable, mark research `INCOMPLETE`; continue the local
audit but do not assert current or comprehensive coverage.

### 2. Per-note explanation and correctness

Read the full teaching prose, not only headings or code. Check audience assumptions, problem and
causal explanation, local vocabulary, concrete carriers, correctness, misconceptions, and examples.
Require relevant success signals, failure symptoms, limitations, and production boundaries for
material the reader will act on. Pure definitions and reference indexes need role-appropriate checks,
not invented operating procedures.

Apply the two independent ORDERING and EXPLANATION verdicts from the learning-audit reference.
Run evidence-backed teach-back using only the note, declared earlier learning, and permitted prior
knowledge. Cite the missing premise when it fails. Verify time-sensitive claims against primary
sources and record the source and checked date. Grade production tactics by the actual integration
and failure they address, not the presence of a generic “best practices” section.

### 3. Reader journey and transfer

Read each named learning path in order and in full, including production continuations. Use only
knowledge available at each step. Record what the reader can now explain, predict, choose, build,
or verify. Check the earliest unexplained dependency, overload, missing bridge, and premature depth.

Record execution and understanding payoffs separately. Two entries is a useful diagnostic target;
fail for an avoidable learning barrier or missed promised milestone, not a file count. A concrete
trace can be an appropriate first result without running code.

At meaningful milestones, evaluate a changed-condition scenario using the transfer protocol. The
answer must follow from already taught principles; model expertise cannot repair missing teaching.
Distinguish an absent exercise from a failure to supply the knowledge needed to solve it. Report
prompt, expected reasoning, supporting passages, and verdict in `_audit/reader_paths.audit.md`.

### 4. Mechanism depth and production continuation

Classify actual coverage as absent, mentioned, defined, explained, demonstrated, or operationalized.
Use the author's learning contract when present, but challenge missing essentials and insufficient
required levels against the independent curriculum. Inspect canonical owners in full. Foundational
mechanisms must be taught before a deep dive relies on them. Production promises require relevant
verification, failure diagnosis, recovery, limits, and trade-offs, not just configuration snippets.
Write `_audit/coverage.audit.md`; this report owns substantive coverage findings, including essentials
never mentioned in the collection. The curriculum report maps expectations and cross-references them.

### 5. Reproduce executable claims

Inventory runnable, copyable, integration, test, smoke-test, and end-to-end claims across the whole
collection. Reproduce safe, authorized examples exactly as shown, including local files, dependencies,
services, and setup. An author manifest is an inventory, not proof. Record `VERIFIED`, `BROKEN`,
`PARTIAL`, or `NOT-RUN`; explicitly non-runnable material is `EXCERPT`. Do not perform destructive,
costly, credentialed, or externally mutating procedures without authority. Record the limitation
rather than inventing output. Write `_audit/examples.audit.md`.

### 6. Missing notes and synthesis

Inspect the whole tree for missing learning bridges and absent topics. Repair within an existing
owner when that preserves a coherent role; propose a new note only when a real teaching boundary
warrants one. Write `_audit/gaps.audit.md` as placement proposals, cross-referencing canonical coverage
findings without double-counting. Missing fundamentals are findings even when a new file is optional.

After all passes, aggregate `_audit/metrics.audit.md` and run:
`python3 <skill-directory>/scripts/validate_audit_outputs.py <collection>/_audit`.
This checks report structure, not judgment quality. Record research and transfer status alongside
coverage and execution; a clean file audit cannot compensate for an incomplete curriculum audit.

## Severity and evidence

| Severity | Reader impact |
|---|---|
| `FIX-CRITICAL` | Actively misleading, unsafe, or materially harmful behavior. |
| `FIX-HIGH` | Cannot learn or complete a central promised capability. |
| `FIX-MED` | Must infer, detour, reread, or work with avoidable uncertainty. |
| `FIX-LOW` | Presentation or navigation issue without material outcome impact. |

Use corresponding `COVERAGE-HIGH`/`COVERAGE-MED` for depth findings. Every finding names concrete
evidence, reader impact, and an actionable correction. Formatting, line counts, payoff ratios,
list length, and callout counts are diagnostics; none independently determines severity. A correct
long explanation can pass; a concise, polished but causally empty note must fail.

Assign one owner per defect: unsafe/broken executable behavior to examples; stale existing claims
to per-note reports; absent or underdeveloped mechanisms to coverage; sequence-only defects to reader
paths. Other reports cross-reference without repeating severity. Preserve useful depth when fixing
ordering. Do not manufacture findings, force runnable code on conceptual lessons, or demand duplicate
implementations. Distinguish unverified claims from disproven claims.

## Execution boundaries and maintenance

Audit only: write reports, not notes or fixes. This boundary does not require a new approval pause
when the user already authorized a separate remediation workflow; the author/fix phase owns edits.

When available and permitted, proactively delegate local topic reviews at 6+ teaching files per
topic or 8+ files across multiple topics, following `references/delegation.md`. Prefer coherent
3–6-file batches. Reviewers may read prerequisite owners across folder boundaries. Keep curriculum,
reader journey, coverage/gaps, and execution accountable across the complete collection. Use unique
fragments when several workers contribute to one report; a single report owner merges and verifies
them. Aggregate metrics last. If delegation is unavailable, perform the same passes sequentially.

The shared prose, example-selection, curriculum-research, and delegation references mirror the canonical copies
in `note-maker`; keep them synchronized so each skill remains independently usable. When changing
this skill, calibrate against `tests/fixtures/expected_behavior.md` and run a blind forward test on a
different collection. Passing report-format validation does not establish calibrated judgments.
