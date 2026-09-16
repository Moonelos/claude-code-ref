---
name: note-maker
description: "Create or extend complete technical study notes that teach a subject from explicit prerequisites through worked examples, deeper mechanisms, and production operation. Use for a learning collection, technical course, or substantial study notes; preserve narrower scope when the user requests a single topic or edit."
---

# Write a complete learning collection

Create notes a reader can learn from without inventing missing explanations or chasing external
sources for essential teaching. Completeness means fulfilling the user's learning goal against an
independently researched curriculum, not covering every adjacent topic or producing many files.

## Establish the reader and scope

Read `references/curriculum-research.md` before planning. State the assumed knowledge explicitly.
For “from zero,” assume no knowledge of the subject or its necessary domain-specific prerequisites.
Use the user's stated background; otherwise state a conservative baseline such as basic programming
and ordinary command-line use for a software topic. Do not silently assume messaging, concurrency,
networking, or distributed-systems expertise merely because the reader is a developer. Teach the
necessary parts inline or in an earlier bridge. Avoid reteaching unrelated basics.

State the capabilities the complete collection will deliver, its version baseline when applicable,
and justified exclusions. A requested introduction may be narrow; a complete beginner-to-production
collection must include the foundation, usable baseline, deeper mechanisms, and operational path.
Show the proposed learning map as a progress update and continue when the request authorizes writing.
Ask only if unresolved audience or scope choices would materially change the work.

## Research and plan before drafting

1. Research authoritative primary sources for both established essentials and recent changes.
   Follow `references/curriculum-research.md`; do not skip curriculum research because the topic
   feels familiar. Record sources, checked dates, expected capabilities, and justified exclusions in
   `<collection>/_meta/curriculum_research.md`. If research is unavailable, mark it incomplete and
   disclose the limitation instead of claiming comprehensive or current coverage.
2. Read `references/curriculum-contract.md`. Persist audience assumptions, prerequisite bridges,
   paths, canonical mechanism owners, required coverage levels, and transfer checkpoints in
   `<collection>/_meta/learning_contract.json`. Reconcile every researched essential with an owner
   or a justified exclusion. Do not let a self-selected table of contents define completeness.
3. Order dependencies so each new idea builds on what the reader actually knows. Give an early
   concrete situation and useful trace, then develop the explanation and runnable baseline as the
   subject warrants. Two entries is a useful early-payoff target, not a universal limit. Never skip
   necessary foundations to meet it. Set and justify the appropriate milestones in the contract.

Before dispatching work, read `references/delegation.md` when a topic reaches 6 teaching files or
the collection reaches 8 files across multiple topics. Plan semantic packages and dependency gates.

## Write and assemble

Read `references/how-we-write-notes.md` before drafting. Read `references/example-selection.md`
when structured artifacts or interactions carry a mechanism. `references/example_note.md` is one
worked tutorial illustration, not a universal template.

- Write the foundation path in dependency order. After each entry, reconstruct the mechanism using
  only that entry, earlier entries, and explicitly allowed prior knowledge. A title, glossary,
  command, or warning does not count as an explanation.
- Show why the problem exists, build the mental model, demonstrate the causal mechanism with
  concrete values, explain the result, and address likely misconceptions. Reuse a running scenario
  when it helps continuity, with locally understandable excerpts rather than duplicated programs.
- At meaningful milestones, include a new prediction, diagnosis, design choice, or changed-condition
  problem with a reasoned solution. Follow the transfer protocol in `references/curriculum-research.md`.
  Do not merely rename the entities in the original example or impose an exercise count per file.
- Complete the foundation path before drafting independent later material. Introduce deeper
  mechanisms through the failures or requirements that make them necessary. Teach production
  behavior through relevant guarantees, limits, trade-offs, observability, failure diagnosis,
  recovery, and safe change procedures, with examples specific to this subject.
- Match depth to the promise: core first-time mechanisms normally reach `demonstrated`;
  production implementation mechanisms reach `operationalized`. Full notes must explain the
  behavior, not send the reader to a documentation link for the missing lesson.
- Keep examples correct even when minimal. Do not defer correctness- or security-critical behavior
  to a later “production” section. Label explanatory excerpts honestly; preserve valid syntax and
  show the canonical complete example when one is needed.

Choose a role for each file: foundation, tutorial, implementation, deep dive, decision guide, or
reference. A deep dive refines a model already taught on the beginner path. Avoid making every file
both an introduction and a reference manual. Preserve depth by reorganizing or splitting at a real
learning boundary rather than deleting advanced material.

## Navigation and presentation

For new collections, use plain Markdown and a root `README.md` learning map. Preserve an existing
collection's conventions. Do not add publishing infrastructure unless requested.

- Use `references/templates/root_readme.md` and `references/templates/directory_readme.md` as adaptable
  examples. State audience assumptions, learning outcomes, entry points, milestones, and stop points.
- Root navigation routes by goal and area; section indexes list their notes in useful reading order.
  Keep every teaching note discoverable. Update indexes and relative links whenever notes move.
- Prefer numbered `01_topic_name.md` files for a new sequential collection. Use directories when they
  clarify the subject's learning progression. Names, numbers, headings, and callouts are navigation
  choices, not evidence of teaching quality.
- Use prose for explanation, diagrams for interactions, and tables for comparison or lookup.
  Highlight a transferable insight when useful; no exact callout wording or count is required.
- Keep long notes navigable and split when their learning roles conflict. Length alone is not a
  defect. Provide an obvious distinction between foundation, production, and conditional detail
  without requiring particular labels. Badges are optional; see `references/badges.md` if needed.
- Keep `_meta/` contributor evidence out of learner navigation. Cite authoritative sources near
  version-sensitive claims and distinguish the supported teaching baseline from newer alternatives.

## Verification and release

1. Read every named path in order as its declared reader. Check prerequisite closure, causal
   explanations, concrete examples, transfer checkpoints, and the promised production continuation.
2. Reconcile the finished collection against the independent curriculum inventory, not only its
   contract. Essential omissions and unjustified exclusions remain defects even if every file passes.
3. Execute safe examples presented as runnable, copyable, integration, test, or end-to-end exactly
   as documented; record environment, command, exit status, and observed output in
   `_meta/example_verification.json`. If infrastructure or authority is unavailable, record the
   unverified dependency and disclose it. Never claim verification by inspection or weaken a
   promised runnable learning outcome merely to make validation pass.
4. Run the structural checks:
   - `python3 <skill-directory>/scripts/validate_notes.py <note paths or directories>`
   - `python3 <skill-directory>/scripts/validate_learning_contract.py <collection>`
   - `python3 <skill-directory>/scripts/validate_example_verification.py <collection>`
5. When available and permitted, invoke `note-reviewer` or an independent evaluator on the assembled
   collection without giving the desired verdict. It must independently check curriculum breadth,
   first-time understanding, transfer, examples, and current guidance. Fix critical/high findings in
   newly authored material and recheck affected paths and examples. Disclose unavailable review.

Report separate outcomes for research completeness, curriculum coverage, understanding and transfer,
example execution, structural validation, and independent review. Do not call unfinished work
complete because files exist or a validator passes. For a large collection, keep its coverage ledger
and continue through all promised stages; report any genuine blocked work explicitly.

## Delegation and maintenance

When available and permitted, proactively delegate a topic with 6+ teaching files or a multi-topic
collection with 8+ files using `references/delegation.md`. Prefer coherent 3–6-file packages; adjust
for density and dependencies. A small wholly dependent task can stay local. Give the foundation
one sequential author; launch independent later branches only after their prerequisites are accepted.
The coordinator owns shared indexes/metadata, integration, and the complete reader-journey check.

The shared references (`how-we-write-notes.md`, `example-selection.md`,
`curriculum-research.md`, and `delegation.md`) are mirrored in `note-reviewer` so either skill works independently.
Edit the maker copies as canonical and synchronize the reviewer copies; the regression tests check
that they remain identical. When changing teaching behavior, calibrate against the reviewer fixtures
and run a blind forward test on a different collection, not just report-format validation.
