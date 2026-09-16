# Develop a lesson the reader can actually follow

Use this shared contract before choosing chapter boundaries, during authorship, and when reviewing
an entire learning unit. A unit can be one note or a short sequence. Evaluate it for the stated
reader: an expert's ability to extract facts is not evidence that a novice was taught their connections.

## Plan the explanation before the files

After curriculum research, sketch each unit's learner question, starting knowledge, exit capability,
and explanatory sequence. For a collection, keep this in `_meta/lesson_plan.md`; for a small edit,
a concise working plan is enough. It is an editorial plan, not a second inventory of headings.

Describe the situation the reader starts in, the missing idea that situation makes necessary, the
example that develops it, what changes next, and the question that leads to the next stage. Choose
file/section boundaries after this sequence exists. Include any moved/deferred material and its
teaching destination. A file per term is not a curriculum, and one file per agent is not a lesson.

For an existing collection, reconstruct the intended learning sequence rather than treating current
file boundaries as fixed. Retain useful facts and operational depth while changing their placement.
A merger is appropriate when separate fragments answer one continuous learner question and force
repeated context loading. A split is appropriate when a new outcome really needs a different model,
prerequisite, or reading mode. Reordering or developing an existing chapter may be enough. Neither
fewer files nor longer prose is an objective in itself.

## Develop causal reasoning, not an annotated inventory

At each load-bearing idea, show the intermediate reasoning that connects the named inputs, rule,
and result. Explain what the actors know, what state changes, what stays unchanged, and why the
next action follows. A diagram plus a conclusion may omit the entire lesson between them.

A developed example normally moves from a concrete situation through an observable sequence to a
reasoned result, then changes a meaningful condition. Carry the same named actors, records, and
state through related stages when it helps the learner compare. Introduce a new example when the
old one no longer fits, with a clear bridge. Do not force one story across unrelated subjects.

Watch for these failures even when every sentence is technically correct:

- **Assertions instead of explanation:** the text says “X causes Y” or “choose Z” but does not
  explain the link a new reader needs in order to predict Y or choose Z.
- **Unpaid concept load:** a new term is glossed, then immediately used to introduce several more
  mechanisms before the reader can use or reason about the first. Naming is not assimilation.
- **Example reset:** each subsection swaps actors, data, or scale so the reader cannot see which
  single condition caused the changed behavior.
- **Fragmented teaching:** tiny claim/warning sections continually restart context, or several
  files jointly contain a lesson that none develops. Headings alone do not earn a boundary.
- **Premature expert detail:** configuration variants, compatibility concerns, or rare failure
  cases interrupt construction of the first working model. Keep necessary correctness boundaries;
  move specialist depth to a later identified destination.

Do not turn these into quotas for paragraphs, terms, headings, diagrams, or length. A simple idea
may be fully taught in a short paragraph. An advanced reference can be intentionally dense.

## Make visuals do explanatory work

Use a visual when reasoning requires the reader to track multiple actors, independently changing
positions, containment, or a temporal handoff that prose leaves difficult to simulate. Choose a
representation for that question: a labeled topology, before/after state table, annotated timeline,
or sequence. Markdown tables, text diagrams, or Mermaid are sufficient; no image-generation or
external diagram service is required. Match the repository's supported rendering.

Introduce what to inspect, explain the arrows/positions and their causal meaning, and interpret
what changed after the action. Keep labels and example values consistent with surrounding prose.
A diagram that simply repeats three nouns and arrows is not proof that the relationship was taught.
One evolving diagram may be more useful than several unrelated sketches. When prose already makes
the mechanism easy to follow, do not demand a visual just to satisfy a style preference.

In review, identify the specific reasoning burden a visual would relieve and what it must show.
“Add diagrams/examples” is not an actionable finding. Neither is “make this more engaging.”

## Two independent checks: extractability and learning experience

Teach-back asks whether the required facts can be reconstructed. LESSON asks whether the prose
actually develops them into an accessible explanation for the stated reader. A note can pass the
first and fail the second. Evaluate the complete unit, not just its best opening example.

Read in order, keeping only permitted prior knowledge and what has been earned so far. At each
substantive transition, identify:

1. what the reader can already explain, rather than merely recognize as a term;
2. which new relationship or reasoning step is demanded;
3. the actual passage, worked step, or interpreted visual that teaches that relationship;
4. what a plausible novice would have to invent if that support is absent.

Cite the exact gap. Do not fill it with a polished explanation generated from evaluator expertise.
Try a changed-condition probe that requires combining taught relationships or reasoning through
intermediate state, rather than selecting a conclusion almost verbatim from the text. Explain the
answer from earlier teaching evidence. An incorrect question outside the promised scope is not a
lesson defect. Failure to include an exercise is not itself evidence of failed comprehension.

### Check development across the promised scope

Do not silently narrow a chapter to its strongest opening mechanism. Build a compact development
map of its substantive learner promises: concept/decision, prior knowledge, teaching passage,
worked reasoning, and status (developed, merely stated, explicitly deferred). Include recommendations
in later sections, not only the title. A recommendation to choose or implement an approach creates
an instructional obligation unless it is clearly a signpost to a named later lesson.

For example, “use a stable logical bucket” is not a taught migration strategy merely because the
reader understands that changing partition count can change placement. The text must develop the
indirection and its limits, or explicitly defer the strategy. Similarly, naming several alternative
solutions does not teach a novice how to choose among them. Do not demand implementation depth
from an honest signpost; do not reinterpret unexplained prescriptions as signposts to award PASS.

For a beginner-to-production learning request, an overview that makes conclusions recoverable but
repeatedly omits the worked path to applying them needs development. Report the underdeveloped
promises even if the main mechanism passes teach-back. Repeated undeveloped decisions across a
chapter justify LESSON FAIL and an editorial plan; a single peripheral gap may need only a local
repair. Judge the promised learning experience, not whether a knowledgeable reader can reconstruct
a defensible narrow summary. The development map belongs in the lesson-quality evidence and must
not become another required decorative section in the published lesson.

Issue `LESSON: PASS|FAIL|NOT-CHECKED|n/a` independently of runnable output and local fact coverage.
Use n/a for an actual lookup/index role, with a reason. Short teaching notes still get a real verdict.
A FAIL needs observable reader harm, such as a central causal inference left to the beginner, not an
editorial taste or generic claim of dullness. Missing evidence is NOT-CHECKED, never an inferred PASS.
An EXPLANATION PASS cannot coexist with LESSON FAIL: record the failed instructional result while
preserving an honest teach-back PASS if the facts really are extractable.

## Prescribe the right scale of repair

Use a local edit when a single definition, bridge, or interpreted step genuinely repairs the issue.
Use a lesson refactor when the defect recurs across the unit or comes from its organizing principle.
Adding a sentence to each subsection can make a fragmented outline longer without making it teach.

For a structural repair, name the current fragments and propose an executable editorial plan:

- target learning sequence and chapter/section responsibilities;
- what to keep, merge, move, develop, or rewrite, with destination for preserved depth;
- the running example and its staged changes;
- the useful visual's actors, states, or relationships and how the prose will interpret it;
- a representative replacement passage showing the intended explanatory development;
- a learner task whose reasoned solution would demonstrate the repair worked.

The replacement passage should contain a real inferential bridge and example, not another abstract
instruction to write better. It is an illustration inside the report, not authorization to edit
notes. It does not replace a full independent check after rewriting. Record structural findings once
in `lesson_quality.audit.md`; local and path reports cross-reference instead of repeating severity.

## Calibration boundaries

A short correct note about one simple transition can pass. A deliberately scoped reference can be
n/a. A polished overview with an actor, state, tiny trace, warning, and all expected labels can still
fail as a beginner lesson when the reasoning between its claims remains implicit. Likewise a long
lesson with many drawings can fail if they never explain the changing state.

The reviewer's `tests/fixtures/lesson_quality/` cases exercise these distinctions. Its earlier
`demonstrated_foundation.md` fixture establishes local mechanism demonstration only; it is not the
quality ceiling for a multi-mechanism chapter or a complete course. New behavioral tests should
include a realistic false-positive candidate, not only an obviously empty glossary.
