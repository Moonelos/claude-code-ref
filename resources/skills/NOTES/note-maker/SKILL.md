---
name: note-maker
description: "Write technical study notes, a course, or a knowledge base that teaches a subject from explicit prerequisites through worked examples, diagrams, deeper mechanisms, and production operation, with current features researched on the web. Use whenever the user asks to create, write, extend, or refactor notes, study notes, learning material, a tutorial series, a knowledge base, or an in-depth explanation of a technology (\"make notes on X\", \"teach me X from zero\", \"write a guide to running X in production\"). Keeps a narrower scope when the user asks for a single topic or edit."
---

# Write a complete learning collection

Create notes that let a reader understand a concept completely at the promised depth, and then run
it in production, without inventing missing explanations or chasing external sources for essential
teaching. Complete means the user's learning goal is met against an independently researched
curriculum. It does not mean covering every adjacent topic or producing many files.

## Establish the reader and scope

Read `references/curriculum-research.md` before planning. State the assumed knowledge explicitly.
For "from zero," assume no knowledge of the subject or its domain-specific prerequisites. Use the
user's stated background. Otherwise state a concrete baseline, such as "basic programming and
ordinary command-line use" for a software topic. A developer does not automatically know messaging,
concurrency, networking, or distributed systems. Teach what the path needs, inline or in an earlier
bridge, and skip unrelated basics.

State the capabilities the collection will deliver, its version baseline, and justified exclusions.
A beginner-to-production collection must include the foundation, a usable baseline, deeper
mechanisms, and the operational path. Show the proposed learning map as a progress update and keep
going when the request authorizes writing. Ask only when an audience or scope choice would
materially change the work.

## Research and plan before drafting

1. **Research on the web.** Use WebSearch and WebFetch to cover both the established essentials and
   the current landscape (releases, deprecations, preview features, emerging practice), following
   `references/curriculum-research.md`. Do this even when the topic feels familiar. Record sources,
   checked dates, expected capabilities, landscape items, and justified exclusions in
   `<collection>/_meta/curriculum_research.md`. If the web tools are unavailable, mark research
   `INCOMPLETE` and say so in your final report.
2. **Plan the explanation.** Read `references/lesson-design.md` and plan each unit's learner
   question, running example, causal steps, required diagrams, and transitions before choosing file
   boundaries. Then read `references/curriculum-contract.md` and persist audience, prerequisite
   bridges, paths, canonical mechanism owners, required coverage levels, and transfer checkpoints
   in `<collection>/_meta/learning_contract.json`. Every researched essential gets an owner or a
   justified exclusion. The table of contents does not define completeness.
3. **Order by dependency.** Each idea builds only on what the reader already knows. Give an early
   concrete situation and trace, then develop the explanation and a runnable baseline. Aim for a
   useful result within two entries. Never skip a needed foundation to hit that target; justify any
   later milestone in the contract.

Read `references/delegation.md` before dispatching when a topic reaches 6 teaching files or the
collection reaches 8 files across topics.

## Write each lesson

Read `references/how-we-write-notes.md` before drafting. Read `references/example-selection.md` when
structured artifacts or interactions carry a mechanism. `references/example_note.md` shows one worked
tutorial. It is an illustration, not a template.

- **Develop, don't summarize.** Follow `references/lesson-design.md`: keep a running example across
  related ideas, show the intermediate reasoning, and let each concept settle before stacking more
  on it. A set of correct summaries is not a beginner course.
- **Explain causally.** Show why the problem exists, build the mental model, demonstrate the
  mechanism with concrete values, explain the result, and address real misconceptions. A title,
  glossary entry, command, or warning is not an explanation.
- **Draw the mechanism.** Add a Mermaid diagram wherever `lesson-design.md` requires one: multiple
  actors, ordering over time, state lifecycles, topology, data paths, or decision trees. Introduce
  each diagram, label it with the running example's real values, and interpret it afterward.
- **Test transfer.** At milestones, add a prediction, diagnosis, or design problem under a changed
  condition, with a reasoned solution (see `curriculum-research.md`). Renaming the entities in the
  original example doesn't count.
- **Close for retention.** End each foundation, tutorial, and implementation note with a recap,
  check-yourself questions with collapsed answers, and (for tutorials) a faded "try it" exercise,
  as described in `how-we-write-notes.md`. Maintain a root `GLOSSARY.md`.
- **Teach production for real.** Introduce deeper mechanisms through the failures that make them
  necessary. The production layer covers guarantees, limits, trade-offs, observability (what to
  measure and alert on), failure diagnosis with actual symptoms, recovery, security, cost, and safe
  upgrade or rollback, all specific to this subject. Include a production-readiness checklist in the
  note that owns production operation.
- **Meet the depth promise.** Core first-time mechanisms reach `demonstrated`; production
  implementation mechanisms reach `operationalized`. Never replace a missing lesson with a link to
  documentation.
- **Keep examples correct.** Minimal examples are never unsafe. Label excerpts honestly, keep syntax
  valid, and show the complete canonical example where one is needed.
- **Cover what's changing.** For an evolving subject, add a "What's changing" section (root README or
  the relevant decision guide) listing researched GA, preview, deprecated, and emerging items with
  sources and dates. Teach an item in the body when it changes the recommended baseline.

Give each file one role: foundation, tutorial, implementation, deep dive, decision guide, or
reference. A deep dive refines a model already taught on the beginner path. Split at a real
learning boundary instead of deleting advanced material. Merge fragments that answer one continuous
learner question.

Write the foundation path first, in dependency order. After each entry, check that the mechanism can
be reconstructed from that entry, earlier entries, and allowed prior knowledge alone. Draft later
material only after the foundation is done.

## Navigation and presentation

Use plain Markdown with a root `README.md` learning map. Keep an existing collection's conventions,
and add publishing infrastructure only when asked.

- Adapt `references/templates/root_readme.md` and `references/templates/directory_readme.md`. State
  audience, outcomes, entry points, milestones, and stop points.
- Root navigation routes by goal. Section indexes list notes in reading order. Every teaching note
  is discoverable, and links are updated when notes move.
- For a new sequential collection, number files (`01_topic_name.md`). Use directories when they
  reflect the learning progression.
- Use prose for explanation, Mermaid diagrams for interactions, time, and structure, and tables for
  comparison or lookup.
- Make the difference between foundation, production, and conditional material obvious. Badges are
  optional (`references/badges.md`).
- Keep `_meta/` out of learner navigation. Cite sources near version-sensitive claims, and
  distinguish the teaching baseline from newer alternatives.

## Verify and release

1. **Read every path as its reader.** Check prerequisite closure, causal explanations, concrete
   examples, required diagrams, retention blocks, transfer checkpoints, and the production
   continuation. Give each teaching unit a LESSON verdict (`references/lesson-design.md`). A passing
   command or fact checklist cannot override a failed lesson.
2. **Reconcile against the curriculum.** Compare the finished collection with the independent
   curriculum inventory and landscape. Essential omissions and unjustified exclusions stay defects
   even if every file passes.
3. **Run the examples.** Execute safe runnable, copyable, integration, test, and end-to-end examples
   exactly as documented. Record the environment, command, exit status, and output in
   `_meta/example_verification.json`. When infrastructure or authority is missing, record the
   dependency as unverified and disclose it. Inspection is not verification.
4. **Run the structural checks** (they also check Mermaid syntax):
   - `python3 <skill-directory>/scripts/validate_notes.py <note paths or directories>`
   - `python3 <skill-directory>/scripts/validate_learning_contract.py <collection>`
   - `python3 <skill-directory>/scripts/validate_example_verification.py <collection>`
5. **Get an independent review.** Invoke `note-reviewer` (or an independent evaluator) on the
   assembled collection without suggesting a verdict. Fix critical and high findings in newly
   authored material and recheck the affected paths. If review is unavailable, say so.

Report separate outcomes for research and landscape, curriculum coverage, understanding and transfer,
lesson quality, diagrams, example execution, structural validation, and independent review. Files
existing or a validator passing does not make the work complete. For a large collection, keep the
coverage ledger and continue through every promised stage, and report any blocked work explicitly.

## Delegation and maintenance

When available, delegate a topic with 6+ teaching files, or a multi-topic collection with 8+ files,
using `references/delegation.md`. Use coherent 3–6-file packages. One author writes the foundation
sequentially. Independent later branches start only after their prerequisites are accepted. The
coordinator owns shared indexes, metadata, integration, and the full reader-journey check.

`how-we-write-notes.md`, `example-selection.md`, `curriculum-research.md`, `lesson-design.md`, and
`delegation.md` are mirrored in `note-reviewer` so each skill works when installed alone. Edit the
copies here, then copy them to the reviewer. `tests/test_contract_regressions.py` fails if they
drift. When changing teaching behavior, calibrate against the reviewer fixtures and run a blind
forward test on a different collection.
