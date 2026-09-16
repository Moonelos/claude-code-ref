# How we write notes

This is the house style for note prose. It governs two jobs: writing a new note, and applying approved audit fixes to an existing one. These are the standards every note is held to — an audit measures notes against them, and an edit should move the note toward them, not just patch the flagged line.

Most of what follows is a **required move**, not a prohibition. A note that only avoids the failure modes comes out accurate and teaches nothing. The devices below are what make it land on a first read and stick after.

## Contents

- [Audience and teaching balance](#who-the-note-is-for)
- [Collection and note ordering](#the-collection-has-a-learning-contract)
- [Role-aware opening payoff](#open-with-the-payoff-that-fits-the-notes-role)
- [Explanation moves](#ground-every-term-at-first-use)
- [Concrete carriers](#make-the-mechanism-visible-in-its-native-artifact)
- [Examples and safety](#examples-baseline-first-hardened-second)
- [Density, altitude, and completion](#mark-altitude-and-control-prescriptive-density)

## Who the note is for

Write for the explicit audience in the learning contract. For **from zero**, assume no subject
knowledge or adjacent specialist prerequisites unless the user supplies them as prior knowledge.
State concrete general skills that are assumed; do not use “competent engineer” as a substitute.

- Teach the subject's vocabulary and mechanics from zero.
- Teach necessary supporting concepts inline or in an earlier bridge; links alone do not teach them.
- Skip general basics only when the audience contract explicitly permits that knowledge.
- Never assume the reader already knows the thing the note is supposed to teach.

Read `curriculum-research.md` to establish this boundary and independently validate the curriculum.

Their existing expertise is also the cheapest teaching tool you have — see *Work with the model the reader already has*.

## The core balance: detail vs. simplicity

Aim for the middle of the spectrum between soundbite and reference-manual dump:

- Not **too simple** — stating that a thing exists without the mechanism to use it, or an analogy that never cashes out into how it actually works.
- Not **too dense** — jargon before intuition, one unknown explained via three more unknowns, every flag listed with no signal of which ones matter.

**The move:** build the correct mental model in plain language first, then attach the precise mechanism that makes it actionable. Say what to actually do, and which option is the default. One well-chosen example beats five abstract sentences.

## Develop complete lessons

Read `lesson-design.md` before choosing boundaries. Develop the inference between claims through
continuous examples and interpreted visuals where useful. A successful six-element teach-back
checks extractable evidence; it does not prove the complete lesson is developed for its reader.
Review recurring concept overload and fragmentation at chapter/sequence level, and merge or rewrite
when local additions cannot repair them. Preserve necessary depth at explicit destinations.

## The collection has a learning contract

The goal is not merely complete notes. It is a path that takes a first-time reader through four layers in order:

1. **Concept** — the problem, plain-language mental model, and minimum vocabulary.
2. **Minimal usable mechanism** — the smallest complete implementation or worked trace that produces an observable result.
3. **Production hardening** — the defaults and safeguards that make the mechanism safe under real load and failure.
4. **Operational awareness** — failure symptoms, limits, trade-offs, recovery procedures, and the practitioner tricks that prevent or diagnose them.

A single file does not need to carry all four layers. The **full learning path as a whole does**; shorter paths may stop at a declared milestone. Each file needs one primary role: foundation, tutorial, implementation, deep dive, decision guide, or reference. A foundation owns a mental model and concrete trace; a tutorial owns a guided runnable result. Do not turn either into a production reference in the name of completeness.

Four rules keep the progression usable:

- **Build intuition and a concrete result early, then deepen and harden.** A useful trace within two entries is a diagnostic target, not a limit. Teach needed prerequisites before action and justify milestones by the learning dependency. A path may revisit an earlier note for depth; label the revisit.
- **Teach the smallest complete system before its advanced variants.** A reader should see one durable task before a stateful workflow, one claim before fencing and reconciliation, or one request before a full deployment topology.
- **Provide stop points.** After the conceptual and minimal layers, say who can stop there and which new requirement makes the next layer necessary.
- **Give each mechanism one canonical owner.** One note owns the full schema, implementation, or option set. Other notes use a small trace or excerpt and link to that owner instead of repeating the reference material.

A first-time path fails this contract if every individual note is accurate but the reader must learn several production mechanisms before they can explain or build the baseline.

## Coverage has levels; a heading is not coverage

Use five levels to state what a collection promises about a mechanism:

1. **Mentioned** — named only for orientation.
2. **Defined** — grounded with its kind and basic purpose.
3. **Explained** — its need, owned state or decision, causal mechanism, and consequence are clear.
4. **Demonstrated** — the explanation is carried by a named trace or faithful artifact, with a changed-input contrast when the distinction is non-obvious.
5. **Operationalized** — the reader can verify it, recognize its first real failure, and apply its recovery, rollback, or production boundary.

Core mechanisms on a first-time path normally reach at least **demonstrated** in their canonical
owner. A definition plus a failure warning does not meet that bar. Production implementation notes
reach **operationalized** for the behavior they promise to assemble.

Keep each foundation note centered on one mental model. When several mechanisms have independently
changing state, different prerequisites, or different faithful carriers, split them or explain why
their composition is the lesson. A short note is welcome when the mechanism is simple; compactness
is not permission to collapse several teachable mechanisms into a glossary with warnings.

A deep dive may refine a core idea only after an earlier foundation owner establishes the first
correct model. It cannot be the first place a beginner path actually teaches a required concept.

At the end of a foundation note, test whether a reader can state, from the note itself: the problem,
the state or decision the mechanism owns, who changes it, one named transition and result, the
plausible wrong model it rules out, and the first failure that motivates the next layer. This is the
evidence-backed teach-back; a bare `PASS` without those reconstructable elements is not evidence.

## Open with the payoff that fits the note's role

Every teaching note gives the reader a useful reason to continue early, but it does not need a
universal `## The short version` block or fixed labels. Choose the opening payoff from the note's
declared role:

| Note role | Useful opening payoff |
|---|---|
| Foundation | A concrete situation, faithful trace, and the first correct mental model. |
| Tutorial | The smallest runnable path, bounded inputs, visible output, and the explanation that makes it intelligible. |
| Implementation | The smallest runnable path, its bounded inputs, and the observable result. |
| Deep dive | The failure, constraint, or surprising behavior that requires this deeper mechanism. |
| Decision guide | A named decision, the few criteria that change it, and an initial recommendation. |
| Reference | Scope, lookup map, and defaults or common subset; an example only when it improves lookup. |

Use a natural heading such as `Quick start`, `Worked example`, or a claim that names the payoff—or
no separate payoff heading when the opening paragraphs already do the job. Exact labels, counted
input lists, and a fixed block order are optional. A title plus a generic summary is not a payoff.

When the opening asks the reader to perform an action, bound the required inputs and show the exact
success signal. When a minimal example intentionally defers production concerns, name the relevant
omissions nearby and point forward; `Not handled yet` is a useful label, not mandatory syntax. A
genuine prerequisite may appear before the payoff when the intended audience cannot proceed without
it; keep optional background advisory and do not use it as a gate.

Judge proximity semantically. The payoff should arrive before setup detail, taxonomies, or hardening
that the reader does not yet need. Do not force a deep dive, decision guide, or reference to recreate
a baseline already owned by another note merely to satisfy an opening template.

The opening has two possible acceptance tests, applied only where the role warrants them:

- **Execution/decision:** the reader can run, trace, or make the promised first decision and observe
  the stated result.
- **Teach-back:** the reader can reconstruct why the example, scenario, or criteria produce that result from evidence in the note.

A code block can pass execution and fail teach-back. A conceptual or decision-oriented opening may
need only the teach-back test.

## Lead with the problem, then state the *why*

A teaching opening should make the need intelligible, usually through a concrete situation followed by the central explanation. A brief definition may come first when it clarifies the situation; judge whether the reader understands the need, not the sentence order. Reference notes may open with scope and lookup guidance.

❌ "Hooks are user-defined handlers that run at specific lifecycle events."

✅ "You told Claude in CLAUDE.md to run prettier after every edit. It does — most of the time. Hooks are how you make it every time: the harness runs your command on a lifecycle event, with no model in the loop to forget."

The test: a reader who stops after three sentences should be able to say what this is *for*. If your opening would work equally well as a dictionary entry, it isn't an opening.

The same obligation holds section by section, not just at the top. For any concept, say what problem it solves — not just what it is. Cover what's easy to get wrong, and when to use it vs. when not to.

## Ground every term at first use

Never require the reader to leave the note to learn its vocabulary. At the first use **in this note**, expand acronyms and add a short inline gloss that answers: *what kind of thing is this?* Keep cross-links for depth, not as the only definition.

❌ "The verifier picks a key from the JWKS using `kid`."

✅ "The verifier picks a key from the **JWKS** — a JSON file the issuer publishes with its current public keys — using `kid`, the short key identifier in the token header."

This applies inside the opening payoff. Familiarity elsewhere in the collection does not excuse an ungrounded first use here; search-engine readers and readers following a different path still need the six-word gloss.

## Introduce a mechanism through the problem it solves

Before describing how a mechanism works, show the world without it and the consequence. "A JWKS lists public keys" describes a thing. "A pasted public key works until rotation makes every request fail; a JWKS lets the verifier follow the issuer's current keys" explains why the thing exists.

For every mechanism introduced, ask: **what breaks if this does not exist?** If the reader cannot answer, the mechanism was described but not explained. State the rule only after this causal explanation; a rule is the conclusion of understanding, not a substitute for it.

## Explain the adversary before the defense

For security controls, the attack is the explanation. Walk through the attacker's input, the verifier or system decision they exploit, and the observable consequence before prescribing the defense. End by naming exactly which choice the defense moves from untrusted input to trusted configuration.

Do not stop at "pin the algorithm." Show that an attacker changes `alg`, why a permissive verifier obeys it, which key material is reused incorrectly, and how an explicit algorithm list prevents the token from choosing the verification method. Keep the attack concrete enough that the reader can recognize the same bug in differently shaped code.

## Put concrete instances before abstractions

Use a real value before a definition table. Show `"aud": "https://api.orders.example.com"` reaching the billing API and being refused before listing every claim type. Tables, taxonomies, full schemas, and production topologies remain valuable reference material, but they follow the instance that gives their rows meaning.

The test is simple: could the reader point to one actor, value, transition, and consequence before being asked to generalize? If not, the section started too high.

## Make the mechanism visible in its native artifact

A note can contain a strong opening example and still leave later mechanisms floating in prose.
Run the **concrete-carrier test** at each high-leverage explanation: if the reader must write,
inspect, review, or debug a policy, configuration, schema, query, payload, command, or state
transition, or if the result depends on a particular field, order, or interaction, show the
smallest faithful form of that thing near its first explanation.

Match the carrier to the mechanism. Use a policy/config snippet for structured rules, a
request/response for protocols, named rows and output for data transformations, an event/state
trace for temporal behavior, and two or three input-to-decision rows for precedence or
intersection. Code is not the universal representation.

A useful local teaching unit is:

1. one sentence of context with a named actor or input;
2. the smallest faithful carrier;
3. a mapping from its important field or transition to the observed result; and
4. when the distinction is non-obvious, one changed input that produces a different result.

This is a semantic obligation, not an example quota. Do not add artifacts to simple definitions,
repeat an earlier example that already carries the same behavior, or duplicate a canonical full
implementation. A local excerpt plus a link is enough when another note owns the full artifact.
Anything presented as copyable must be complete, valid, and safe. A deliberately incomplete block
must be labeled as an **explanatory excerpt**, remain syntactically faithful, and never omit
correctness- or security-critical context. Labels and annotations belong outside a code fence when
its declared language does not support comments; a `json` fence, including an excerpt, must parse
as JSON.

Read `example-selection.md` for the carrier matrix, sizing rules, anti-overfitting guardrails, and
calibration cases.

## Work with the model the reader already has

Readers don't arrive empty. They arrive with adjacent expertise and a guess about how this works. Both are leverage.

**Anchor to what they already know.** Where a mechanism has a genuine structural analogue in something this audience understands, name it once, precisely, and say where it stops holding.

> A `PreToolUse` hook is an admission controller for the agent loop: it sees the request before it executes and can allow, deny, or rewrite it. The analogy stops at scope — there's no cluster-wide policy object, just per-project config.

The "stops at" clause is not optional. An analogy without a boundary produces a confident wrong model, which costs more than no model. If you can't state the boundary, skip the device.

**Name the wrong model before you build the right one.** Where a specific, common misconception exists, say it out loud and kill it. This is the highest-retention move available, because the correct model attaches to a belief the reader already holds instead of to blank space. Write it as a contrast, not a warning:

> **The near-miss**: hooks look like "CLAUDE.md, but enforced." They're a different layer. CLAUDE.md is advice to the model — it can be reasoned around, compacted away, or overridden by a later instruction. A hook is harness behavior: it runs whether or not the model cooperates.

Use this only where the misconception is real; there is no required count. A manufactured "you might think X" is worse than nothing — it plants a wrong idea the reader didn't arrive with.

## Enumerations must be navigable

When a long enumeration asks the reader to choose among unfamiliar alternatives, provide an entry point. Useful moves:

1. **Mark the subset that matters**, or explain the decision criteria when there is no general default.
2. **Show a choice in use** when that is needed to understand the options. A lookup list or already explained set does not need an artificial default or another example.

Applies to lifecycle events, CLI flags, config keys, IAM actions, model options — anywhere the full set is long and the used set is short. The goal is that the reader can choose or look up what they need. If you write "most people only need a few," name them in the same sentence.

## Every instruction ships with its success signal

If a note tells the reader to configure, install, or run something, it must also say how they know it worked — and what they see when it didn't. Without that, the reader can't tell a working setup from a silent no-op, and has no way to learn from their own attempt.

Cover both directions:

- **Worked:** the exact observable. The log line, the `/hooks` entry, the field in the response, the line in `terraform plan` output.
- **Didn't:** the most common silent failure and its tell. "Hook missing from `/hooks`? The JSON failed to parse — malformed hook blocks are skipped without warning."

⚠️ An unnamed silent failure is the most expensive gap a technical note can have. The reader either concludes the feature is broken, or — worse, for anything security-shaped — believes they're protected when they aren't.

## Completeness — answer the reader's questions, in priority order

These are the reader's questions, roughly in the order they'll ask them. Phrased as questions on purpose: a topic gets mentioned, a question gets answered.

**Non-negotiable — a note missing these is incomplete regardless of length:**

- *What breaks first when I use this for real?* — failure modes, with the error text or symptom the reader will actually see
- *When should I not use this?* — the boundary, and what to reach for past it
- *How do I know it's working?* — see the success-signal rule above

**Include where the subject warrants it:**

- *What did I just do that I can't undo?* — destructive or irreversible operations, cost and security exposure
- *What will a colleague ask me in review?* — the trade-off against the obvious alternative
- *Where does this stop scaling?* — limits, quotas, edge cases

Judge against the note's own stated scope first, general completeness second. The three non-negotiables are not scope-dependent: if the note teaches something the reader will act on, all three apply.

## Examples: baseline first, hardened second

In a **tutorial or implementation note that owns the runnable path**, no production mechanism may
appear before the baseline runs end to end. Caching, rotation, retries, pooling, discovery or
metadata indirection, emergency hooks, observability, and failure taxonomies are hardening. Show the
baseline, state its operational risk in one line, link forward, and only then harden it. A deep dive
may begin from the failure that requires one of these mechanisms when it states or links the baseline
it assumes; it does not reproduce that baseline in full.

Use this structural test: **delete every section after the first runnable end-to-end example. Does what remains still teach a correct, usable baseline?** If not, the note is ordered wrong.

The sequence inside a tutorial or implementation note is:

1. Run the smallest correct end-to-end example and show its visible output.
2. Explain why it works until the reader can restate the mechanism.
3. Name relevant omissions near the baseline and link each one forward; the label is optional.
4. Harden in a later block, with a comment on each addition naming the failure it prevents.
5. Finish with an integration or end-to-end check that you execute exactly as displayed. Include the required database connections, services, fixtures, and synchronization; a comment explaining why the shown block cannot run in its stated environment makes it a sketch, not a test.

> **Principle**: simplify the operational, never the correctness-critical. A minimal example should be acceptable in a junior engineer's pull request: small and unpolished, not unsafe.

Never omit these when they apply:

- algorithm or cipher pinning; untrusted input never chooses the algorithm
- audience, issuer, expiry, or freshness validation
- constant-time comparison for secrets or signatures
- TLS certificate verification; never use `verify=False` or `rejectUnauthorized: false`
- parameterized queries; never build SQL through string interpolation
- keeping secrets, credentials, and tokens out of logs and error strings

Safe deferrals include caching and connection reuse, retries and backoff, key rotation, metrics and tracing, granular error mapping, configuration indirection, and dependency injection. A minimal example that omits relevant production concerns names them nearby and points to the section that owns them; do not require a particular label or repeat concerns that do not apply.

One 60-line production block teaches less than a small baseline followed by a hardened diff.

Concept-heavy foundation notes follow the same ladder without pretending diagrams are code:

1. Start with a small concrete trace: named actors or rows, one input, one transition, and one visible outcome.
2. Explain the causal mechanism behind the outcome.
3. Replay the trace with the first crash, race, or scale constraint that requires hardening.
4. Only then introduce the full schema, decision matrix, or production topology.

A 100-line SQL block is not minimal merely because it is self-contained. The reader must be able to state what changed and why before reading the complete implementation.

## Mark altitude and control prescriptive density

Uniform density makes core ideas and rare edge cases look equally important. Make the reading altitude clear through navigation, headings, prose, or optional callouts such as:

- `> **Core:**` — required to understand or use the baseline
- `> **Production:**` — required before shipping, skippable while learning
- `> **Edge case:**` — conditional material to read only when its condition occurs

Rules, warnings, and correct/incorrect markers are conclusions. They follow the mechanism or consequence that earns them. A large imbalance between prescriptions and causal explanation prompts inspection; it is not a paragraph quota. Add the missing reasoning where it is needed, not filler to improve a ratio.

Inspect long notes for conflicting roles, excessive prerequisite load, or poor navigation. Split at a real learning boundary when it helps; neither 500 lines nor a length-justification comment determines quality. Advanced material follows the baseline it depends on, while a deep dive may open with its motivating failure.

## Finish with evidence-backed teach-back

Accuracy and runnable code are necessary, not sufficient. Before shipping, ask:

> Could the declared reader, using only this note and earlier prerequisites, explain the concept correctly in their own words?

If the reader can only recite rules, the note transferred instructions rather than understanding.
Make the verdict evidence-based: identify where the note supplies the problem, owned state or
decision, actor, named transition and result, misconception boundary, and first failure. Apply this
test to the role-appropriate opening payoff, each core mechanism, and the completed note as a whole.
At meaningful milestones also test transfer to a changed condition using `curriculum-research.md`,
with a reasoned solution grounded in material already taught.

## Use headings and insights to aid understanding

**Section headers should answer, not label.** "Lifecycle Events" says what's in the section; "Which events you'll actually use" says what the reader leaves with. The second is also what a returning reader scans for six months later.

**Highlight transferable insights when useful.** A callout should explain something beyond the specific example rather than repeat a heading. No exact label or number of callouts is required; an insight taught clearly in prose is sufficient.

**`⚠️` marks failure modes and nothing else.** That turns a decorative marker into navigation: a returning reader scans for ⚠️ to find the landmines without re-reading the note.

## Currency — verify, don't assume

Anything time-sensitive (versions, deprecated APIs, pricing, "current best practice," product names) must reflect the live current state. If a fix depends on a fact that could have changed, confirm it against a current source before writing it in. Don't restore stale claims from training-data memory.

## Tone

Plain, direct, concrete. No filler, no hedging, no narration of your own process. Prefer a short accurate sentence over a long vague one.
