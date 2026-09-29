# Divide large collections without breaking the learning path

Read this when planning a multi-topic collection or audit. Use subagents proactively at the workload
thresholds below when tools and instructions permit delegation. These are scheduling defaults, not
content quotas: never create extra notes or split a coherent explanation to reach a threshold.
If delegation is unavailable or prohibited, run the same dependency-ordered batches locally and
retain all verification gates. A small job does not need authoring workers just because they exist.

## Choose work packages

For these thresholds, count learner-facing content-note Markdown files, including substantive
reference notes, but exclude indexes, metadata, audit reports, generated files, and fixtures. Group them by teaching topic and dependency rather than alphabetical
ranges or arbitrary directory boundaries. Estimate research difficulty, prose volume, and runnable
setup as well as file count; four dense chapters may need more work than ten short references.

| Workload | Default scheduling decision |
|---|---|
| 1–5 teaching files total | Keep authorship/local prose review with the coordinator; retain any required independent release review. |
| A topic has 6+ teaching files | Assign a dedicated topic worker; usually divide work into coherent batches of 3–6 files, in dependency order. |
| Collection has 8+ files across at least two substantial topics | Delegate independent topic packages, usually 3–6 files each. The coordinator may own one package. |
| A proposed package exceeds roughly 8 files or contains several dense mechanisms | Inspect for a smaller semantic boundary; split by subtopic, outcome, or prerequisite stage. |

A threshold triggers delegation only when the task has useful independent work alongside it.
Keep a wholly dependent small sequence local rather than spawning an agent merely to wait on it.
A longer foundation can be assigned to one dedicated author while the coordinator researches later
material; the worker still writes it sequentially. Adjust package size for context and complexity,
and briefly record why when departing from these defaults. Do not split every file into its own agent.

Before spawning, the coordinator records a small work ledger in `_meta/delegation.md` for authoring
or `_audit/_parts/delegation.md` for review: package ID, topic/files, dependencies, assigned worker,
allowed writes, expected outputs, and pending/running/accepted/blocked status. This is contributor
state, not learner navigation. A directory name is not sufficient specification of ownership.

## Authoring schedule

1. The coordinator establishes the audience, expected curriculum, lesson plan, concept vocabulary,
   running example, canonical owners, and learning contract. Research scouts may investigate distinct areas and return
   sources and proposed omissions; the coordinator reconciles them before chapter authors start.
2. Give the foundation path one accountable author, either coordinator or one worker. It writes in
   prerequisite order and passes teach-back and transfer checkpoints before later chapters depend on
   it. Do not distribute adjacent beginner chapters among simultaneous authors. Send downstream
   workers the accepted actual foundation text, not only an outline or a promised glossary.
3. After foundation acceptance, launch independent branches concurrently. If operations depends on
   reliability, wait for the relevant reliability package to be accepted; other independent work can
   continue. Dependencies decide readiness, not available worker slots alone.
4. Each worker owns only assigned notes and their uniquely assigned example assets. Workers return
   proposed index/contract changes and example-verification records in a unique package output under
   `_meta/delegation/<package-id>/`; they do not concurrently edit root/section READMEs, the canonical
   learning contract, research ledger, or combined example manifest. The coordinator merges these.
5. Accept each package by reading the prose, checking required depth and transfer reasoning, and
   inspecting execution evidence. Resolve mismatched vocabulary and cross-package links. Peer links
   awaiting an unfinished package remain pending until final assembly; they are not a release pass.

A completion message is not proof of teaching or execution. The coordinator reads every assembled
learning path, reconciles independent curriculum coverage, and runs collection-wide checks.
Keep independent review separate from authorship: a worker cannot be the independent judge of its
own chapter. Another reviewer may review it; author self-checks remain useful but distinct.

## Review schedule

Partition local full-prose reviews into coherent topic batches, usually 3–6 files. Topic reviewers
read declared earlier prerequisites and linked canonical owners as needed, even outside their assigned
batch. Their findings concern their assigned files; they send cross-topic issues to the appropriate
report owner. Read access is broader than write ownership. Later notes must not supply knowledge to
a simulated beginner at an earlier step.

Alongside local reviews, assign these collection-wide responsibilities explicitly. They may share a
worker or be run by the coordinator when slots are limited; do not create a separate agent for every
label automatically:

- **Curriculum research and landscape:** derive the expected scope independently from the user goal
  and primary sources, and run the landscape searches (releases, deprecations, previews, emerging
  practice) with WebSearch and WebFetch. Return evidence for omissions and relevant changes. Do not
  inherit the author's verdict.
- **Whole-lesson quality, reader journey, and transfer:** follow each selected complete path in order
  and full prose,
  including the transitions between packages. Apply `lesson-design.md`; one accountable whole-unit
  reviewer can recommend mergers, reordered sections, or rewrites across worker boundaries. Never
  concatenate per-folder approvals into a path PASS.
- **Coverage and gaps:** reconcile expected capabilities with canonical owners across the whole tree;
  inspect relevant full explanations. Missing concepts cannot be detected from isolated folder lists.
- **Example execution:** inventory and reproduce claims with their complete cross-file setup. Separate
  sandboxes, ports, files, and service state when running independent examples concurrently; serialize
  shared-state setup/cleanup rather than allowing one worker to invalidate another's evidence.

Keep one accountable owner per final report. If several workers inspect the same folder or divide a
large global pass, each writes a unique fragment under `_audit/_parts/<package-id>/`. The assigned
report owner verifies and merges fragments into the canonical audit reports. The global owner must
retain the complete inventory and reconcile cross-package evidence; fragmentation is not permission
to skip full reader-path prose or judge coverage from summaries alone. Only aggregate metrics after
all required passes are accepted and duplicate findings have been assigned a canonical owner.

## Worker brief and return

Give each worker the applicable skill and reference paths, audience/assumed knowledge, user outcomes,
version scope, assigned files/mechanisms, prerequisite packages and actual accepted text, canonical
owners, required coverage levels, and the shared example/vocabulary conventions. Also specify:

- task and role (research, author, reviewer, or execution), dependencies, and completion criteria;
- exact writable paths and read-only shared files;
- output location, evidence/report schema, and verification commands;
- execution environment and authority boundaries where examples need services or credentials;
- source URLs and checked dates for research, distinguishing inherited evidence from new verification.

Return paths written/read, capabilities addressed, cited evidence, checks actually run and their
outputs, unresolved prerequisites or contradictions, and suggested changes to shared artifacts.
Do not return only “done” or an unsupported PASS. Keep worker summaries compact; retain detailed
reasoning and source/execution evidence in the assigned artifacts for coordinator inspection.

## Capacity and handoffs

Use the actual available agent capacity, reserving a slot for the coordinator. Dispatch ready packages
in bounded waves; reuse idle workers with fresh task briefs instead of unbounded fan-out. Keep
spawning under coordinator control rather than allowing workers to recursively expand the team.
If a worker fails or stalls, inspect its artifacts, mark unfinished work, then resume or reassign
that package. Never mark missing work accepted merely to finish the batch. When an accepted upstream
explanation changes, identify affected downstream packages and repeat their relevant checks.
