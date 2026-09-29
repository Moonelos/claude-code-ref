---
name: note-reviewer
description: "Review, audit, or fact-check technical study notes, a course, or a knowledge base. Checks whether a reader can fully understand each concept and run it in production: explanations from explicit prerequisites, whole-lesson development, missing or unexplained diagrams, retention practice, worked and runnable examples, production depth, and curriculum gaps. Searches the web for new, preview, deprecated, and emerging features the notes lack and reports them. Writes evidence-backed reports without editing notes. Use whenever the user asks to review, audit, grade, check, or find gaps in notes or learning material."
---

# Audit whether the collection teaches its subject

Judge whether the reader can explain, predict, build, and operate what the notes promise, and
whether the notes are current. Correct facts, attractive formatting, runnable examples, and a
complete table of contents are each insufficient on their own.

## Choose the mode

- **Full audit** (default for a collection, or when asked for a thorough review): every pass below
  and every report.
- **Quick review** (1–3 notes, or when the user asks for a quick look): passes 1, 2, and 6 only.
  Write `_audit/<folder>.audit.md` (with VISUAL and PRACTICE), `_audit/landscape.audit.md`, and
  `_audit/metrics.audit.md` with `Mode: quick`. Validate with `--quick`. Say in the summary that
  path, transfer, coverage, and execution passes were not run.

## Resolve scope and read the references

Use the collection root the user supplies. Include root teaching notes. Exclude `_audit/`, `_meta/`,
generated sites, dependencies, vendored content, hidden agent directories, build output, and fixtures
unless they are explicitly in scope. Read `_meta/` evidence when present, but it is neither teaching
nor proof.

Read each reference before its pass:

- `references/audit-examples.md`: filled report blocks; read first so your output matches them.
- `references/lesson-design.md`: whole-lesson development, required diagrams, structural repair.
- `references/how-we-write-notes.md`: the teaching contract, including retention practice.
- `references/curriculum-research.md`: independent scope, web research, landscape, transfer tests.
- `references/learning-curve-and-explanation-audit.md`: ordering, explanation, diagram, practice,
  and safety checks.
- `references/example-selection.md`: concrete artifacts and interaction examples.
- `references/coverage-and-execution-audit.md`: coverage levels, teach-back, execution.
- `references/audit-reports.md`: report formats and which report owns which defect.

Use the user's actual audience and scope ahead of the author's declarations. "From zero" includes the
needed subject-specific prerequisites. A label such as "for engineers" does not establish specialist
expertise. Record ambiguous assumptions and their impact on the reader.

For a large audit, read `references/delegation.md` once a topic reaches 6 teaching files or the
collection reaches 8.

## Audit passes

### 1. Web research: curriculum and landscape

Use WebSearch and WebFetch. This pass is mandatory, and a search snippet is not a source. Build the
expected curriculum from the user's goal and primary sources before looking at the author's chosen
topics. Then run the landscape searches in `curriculum-research.md`: releases, deprecations and
changed defaults, preview features, and emerging practice. Community sources count for `EMERGING`
items when you cite two independent ones.

Write `_audit/curriculum.audit.md` (expected capabilities versus actual teaching) and
`_audit/landscape.audit.md` (every new, preview, deprecated, or emerging item a practitioner would
want to know about, with relevance and placement). Cite URLs and checked dates. Mark research
`INCOMPLETE` only when the tools are unavailable or fail, and then put that at the top of the user
summary. Respect an explicit historical or version scope by reporting newer items as migration
context.

### 2. Per-note explanation, diagrams, and practice

Read the full prose, not only headings and code. Check audience assumptions, the problem and causal
explanation, local vocabulary, concrete carriers, correctness, misconceptions, examples, success
signals, failure symptoms, and production boundaries for anything the reader will act on.

Issue ORDERING, EXPLANATION, LESSON, VISUAL, and PRACTICE verdicts per note:

- **Teach-back:** reconstruct the six elements from the note and earlier material only. Cite the
  missing premise when it fails.
- **VISUAL:** find every explanation shape that requires a diagram (`lesson-design.md`). FAIL when
  one lacks an interpreted diagram, and put a Mermaid sketch with the note's own names in the
  finding.
- **PRACTICE:** foundation, tutorial, and implementation notes need a recap, check-yourself
  questions with reasoned answers, and (for tutorials) a faded exercise. Put a replacement question
  in the finding.

Verify time-sensitive claims against sources, with dates. Grade production material by the
integration and failure it actually addresses, not by the presence of a "best practices" heading.

### 3. Whole lessons, reader paths, and transfer

Apply `references/lesson-design.md` to each complete teaching unit and to the sequence. LESSON is
independent of teach-back and execution. Map development across every substantive promise, including
later recommendations. Write `_audit/lesson_quality.audit.md`. When the structure itself is the
problem, give the full repair: target sequence, keep/merge/move mapping, staged example, diagram,
rewrite sample, and acceptance task.

Read each named path in order and in full, using only knowledge available at each step. Record
execution and understanding payoffs separately. At milestones, run a changed-condition transfer
probe. The answer must follow from what was taught; your own expertise cannot repair missing
teaching. Write `_audit/reader_paths.audit.md`.

### 4. Mechanism depth and production continuation

Classify each mechanism as absent, mentioned, defined, explained, demonstrated, or operationalized,
against the independent curriculum and the author's contract. Foundational mechanisms must be taught
before a deep dive relies on them. Production promises require verification, observability, failure
diagnosis with real symptoms, recovery, limits, security, cost, and safe upgrade or rollback. Write
`_audit/coverage.audit.md`.

### 5. Reproduce executable claims

Inventory runnable, copyable, integration, test, smoke-test, and end-to-end claims. Reproduce safe,
authorized ones exactly as shown and record `VERIFIED`, `BROKEN`, `PARTIAL`, `NOT-RUN`, or `EXCERPT`.
Never run destructive, costly, credentialed, or externally mutating procedures without authority.
Write `_audit/examples.audit.md`.

### 6. Gaps, metrics, and the user summary

Write `_audit/gaps.audit.md` with placement proposals for missing bridges and topics (full mode).
Aggregate `_audit/metrics.audit.md` last, then run:

`python3 <skill-directory>/scripts/validate_audit_outputs.py <collection>/_audit [--quick]`

The validator checks structure, not judgment.

Reply to the user in this order:

1. **Verdict:** can the declared reader learn this subject from these notes? (one or two sentences)
2. **New and missing from the landscape:** a table of the `landscape.audit.md` items with status,
   relevance, and placement, `CHANGES-BASELINE` items first. If research was incomplete, say so here.
3. **Biggest teaching repairs:** failed lessons and structural rewrites, with a link to
   `lesson_quality.audit.md`.
4. **Diagrams and practice:** the notes failing VISUAL or PRACTICE, and what each needs.
5. **Other findings by severity**, then a link to each report.

## Severity and evidence

| Severity | Reader impact |
|---|---|
| `FIX-CRITICAL` | Actively misleading, unsafe, or materially harmful behavior. |
| `FIX-HIGH` | Cannot learn or complete a central promised capability. |
| `FIX-MED` | Must infer, detour, reread, or work with avoidable uncertainty. |
| `FIX-LOW` | Presentation or navigation issue without material outcome impact. |

Use `COVERAGE-HIGH`/`COVERAGE-MED` for depth findings. Every finding names concrete evidence, the
reader impact, and a correction specific enough to apply. Line counts and ratios are diagnostics, not
severities. A long, correct explanation can pass; a concise, polished, causally empty note fails.

Each defect has one owner: unsafe or broken executables → examples; stale claims in a note, missing
diagrams, and missing practice → per-note; absent or shallow mechanisms → coverage; new, preview,
deprecated, and emerging items → landscape; sequence-only defects → reader paths; systemic teaching
and organization problems → lesson quality. Other reports cross-reference without repeating the
severity. Don't manufacture findings, force runnable code on conceptual lessons, or confuse unverified
with disproven.

## Boundaries and maintenance

This skill audits only: it writes reports, not notes or fixes. When the user has already authorized
a separate remediation workflow, the author/fix phase owns the edits and needs no new approval pause.

When available, delegate local topic reviews at 6+ teaching files per topic or 8+ files across topics
(`references/delegation.md`), in coherent 3–6-file batches. Keep curriculum, landscape, lesson
quality, reader journey, coverage and gaps, and execution owned at the collection level. When several
workers contribute to one report, a single owner merges and verifies it. Aggregate metrics last.
Without delegation, run the same passes sequentially.

`how-we-write-notes.md`, `example-selection.md`, `curriculum-research.md`, `lesson-design.md`, and
`delegation.md` mirror the canonical copies in `note-maker` so each skill works when installed alone.
Edit them in `note-maker`, then copy them here. When changing this skill, calibrate against
`tests/fixtures/expected_behavior.md` and run a blind forward test on a different collection.
