# Independent curriculum, audience, and transfer

This reference is shared by author and reviewer. The reviewer independently derives expectations;
copying the author's topic inventory is not an independent audit.

## Define what “complete” means

Start with the user's subject, requested depth, and actual starting knowledge. State:

- permitted prior knowledge, concretely (not just “developer” or “beginner”);
- subject and supporting concepts that must be taught before use;
- exit capabilities for foundation, practical use, deeper explanation, and production operation;
- version/environment scope where it changes behavior;
- exclusions and why they do not undermine the promised outcomes.

For “from zero,” do not assume adjacent specialist knowledge. Supply a small bridge for a needed
concept rather than quietly requiring another course. This does not require teaching all computing:
include only prerequisites the promised path uses. For a narrow requested edit, research the affected
mechanism and dependencies instead of expanding it into a new course.

## Build an independent expected curriculum

Research authoritative sources before treating an existing outline as the answer. Start with official
concept/architecture and getting-started documentation, then relevant guarantees, operations,
troubleshooting, and migration references. Specifications and maintained project examples can fill
mechanism gaps. Follow prerequisites and failures back to their underlying concepts. Use the mix of
sources appropriate to the subject, not a fixed source quota or the vendor's navigation as a syllabus.

For each expected item, record:

| Item / capability | Layer | Why necessary | Required depth | Primary evidence + checked date | Owner / gap / justified exclusion |
|---|---|---|---|---|---|

Layers are foundation, practical, deep dive, or production. One item is a teachable capability or
mechanism, not every noun in the documentation. Explain how an essential item supports the user's
goal. A production promise typically requires the relevant guarantees and limits, failure symptoms,
diagnosis, recovery, observability, security, capacity/cost trade-offs, and safe upgrades or rollback.
Do not mechanically impose every category on every subject or chapter.

Authors store this ledger in `_meta/curriculum_research.md`. Reviewers write their independent ledger
in `_audit/curriculum.audit.md`. Both include `Research: COMPLETE|INCOMPLETE`, the checked date,
audience assumptions, scope, version baseline, inspected sources, and unresolved research limitations.
`COMPLETE` means the scoped investigation was completed, not proof of universal exhaustiveness.

Reconcile every essential item against actual teaching. Distinguish missing coverage from shallow
coverage, and deliberate exclusion from accidental omission. Challenge an exclusion if it removes
knowledge needed for a promised capability. A stable fundamental absent from every note is still a
gap; internal mentions and recent release notes are not prerequisites for discovering it. Unsupported
hunches remain labeled research questions rather than confident findings. No arbitrary gap-count cap.

## Check currency and the current landscape

Web research is mandatory. Use WebSearch to find sources and WebFetch to read them; a search snippet
is not evidence. Mark research `INCOMPLETE` only when these tools are unavailable or fail, and say so
in the first lines of the report, not only in a metadata field.

Run these searches for every evolving subject (a stable subject still gets the first two):

1. Official release notes and changelog for the last 12–18 months.
2. Deprecations, removals, changed defaults, and migration guides.
3. Preview and beta features on the official roadmap or docs.
4. Emerging practice: widely adopted new tools, patterns, or integrations, found through
   maintainer blogs, conference talks, CNCF/foundation landscapes, popular OSS repositories, and
   engineering blogs from companies that run the technology at scale.

Label each item with its status and source tier:

| Status | Meaning |
|---|---|
| `GA` | Generally available in a released version. |
| `PREVIEW` | Beta, preview, experimental, or feature-flagged. |
| `DEPRECATED` | Deprecated or removed, or a default that changed. |
| `EMERGING` | A practice or tool gaining adoption, not an official feature. |

Source tiers are `primary` (official docs, release notes, specifications, maintainer statements) and
`community` (conference talks, well-known engineering blogs, adoption signals such as download counts
or stars). `EMERGING` items can come from community sources when you cite at least two independent
ones. A roadmap entry or accepted proposal is `PREVIEW` at most, never `GA`.

Report every item that a practitioner reading this collection would want to know about, not only
items that break an existing example. Then classify its relevance: `CHANGES-BASELINE` (the
recommended approach or an example must change), `ADD-TO-NOTES` (it belongs in an existing or new
note), or `MENTION` (worth a line in a "What's changing" section). Exclude only items clearly
outside the subject.

A historical or pinned-version course may be correct within its scope. Report new items as
migration context rather than as errors in that scope.

Cite the actual source and date for every external claim, including "nothing material changed."
Never present memory-based guesses as source evidence.

## Test transfer, not only restatement

Teach-back reconstructs an explanation from the text. Transfer tests whether those principles support
a new prediction, diagnosis, or choice. Use checkpoints at meaningful milestones, not per-file quotas.

1. Choose the capability being tested and cite the earlier teaching it depends on.
2. Change a meaningful condition: event order, crash point, input constraint, workload, trust boundary,
   or design requirement. Do not simply rename entities or ask for a copied definition.
3. Ask the learner to predict or choose and explain the causal reasoning before showing the solution.
4. Provide a worked solution: assumptions, intermediate reasoning, result, and why a plausible wrong
   answer fails. Code execution is optional unless the exercise claims a runnable verification.
5. Judge using only declared prior knowledge and earlier material. If the solution needs a missing
   premise, repair the lesson rather than smuggling new theory into the answer key.

A cache lesson might first trace expiry, then ask what a later read returns after a source value
changes while the cached entry is still valid. The solution must follow from taught expiry and
invalidation behavior; do not assume a freshness guarantee the lesson never established.

In review, record `TRANSFER: PASS|FAIL|NOT-CHECKED|n/a`, the scenario, reasoned expected answer,
teaching evidence, and missing premise. `n/a` needs a role/scope reason, such as a pure lookup path.
An absent published exercise alone is not proof of failed understanding: try an independent probe.
If it is solvable from the text, report any missing learner practice proportionately. If only expert
knowledge makes it solvable, the capability has not been taught. Model-generated answers are a
textual learning check, not evidence that actual human learners mastered the material.
