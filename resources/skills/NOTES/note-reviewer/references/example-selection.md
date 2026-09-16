# Selecting the right concrete example

Use this reference when a note teaches a mechanism expressed through structured input, state, or
interaction. The goal is not to increase the number of examples. The goal is to remove the places
where the reader must mentally invent the artifact or simulate the mechanism unaided.

## Contents

- [The concrete-carrier test](#the-concrete-carrier-test)
- [Choose the carrier that matches the mechanism](#choose-the-carrier-that-matches-the-mechanism)
- [Choose the smallest useful example size](#choose-the-smallest-useful-example-size)
- [A complete local teaching unit](#a-complete-local-teaching-unit)
- [When not to add another example](#when-not-to-add-another-example)
- [Calibration cases](#calibration-cases)

## The concrete-carrier test

A mechanism needs a nearby concrete carrier when any of these is true:

- the reader is expected to write, inspect, review, or debug a structured artifact;
- behavior depends on a particular field, value, ordering rule, or interaction;
- two or more grants, limits, states, layers, or inputs combine, override, or intersect;
- the prose uses verbs such as *matches*, *evaluates*, *inherits*, *overrides*, *narrows*,
  *retries*, or *transitions*, but the reader cannot point to the object or event causing it;
- a realistic review question would be “what exactly would I write, send, configure, or observe?”

Do not satisfy this test with an unrelated example elsewhere in the note. Put the carrier at the
first point where the reader needs to simulate the mechanism, or show a small local excerpt and
link to the canonical full implementation.

## Choose the carrier that matches the mechanism

| Mechanism shape | Preferred concrete carrier |
|-----------------|----------------------------|
| Policy, configuration, schema, manifest | Small valid JSON/YAML/HCL/schema block |
| API or protocol | Request plus relevant response or verifier decision |
| Query or data transformation | Named input rows, query/expression, resulting rows |
| State machine, workflow, distributed interaction | Actor/event/state trace with one transition |
| Override, intersection, precedence, fallback | Two or three inputs followed by the final decision |
| CLI or operational procedure | Exact command plus observable output and common failure tell |
| Architecture or product choice | Two or three named scenarios with different requirements |
| Security control | Attacker-controlled input, vulnerable decision, consequence, then defended result |

Code is not the universal answer. Match the representation to the thing the reader must reason
about.

## Choose the smallest useful example size

Use one of three sizes deliberately:

1. **Explanatory excerpt** — usually 2–15 lines showing one field, statement, transition, or
   interaction. Label it as an excerpt when surrounding structure is omitted. It must remain
   syntactically faithful and must not hide correctness- or security-critical context. Keep labels
   and annotations outside the code fence when the declared language does not support comments;
   for example, a `json` fence must still parse as JSON.
2. **Minimal complete example** — the smallest copyable artifact or runnable path that produces the
   promised outcome. Anything presented as copyable must be valid, safe, and complete for its claim.
3. **Composed integration example** — joins mechanisms already taught locally and shows how their
   boundaries interact. Use it after the smaller mechanisms are independently visible.

An excerpt may omit irrelevant boilerplate such as an outer document wrapper. It may not omit a
required audience check, TLS verification, parameter binding, deny condition, credential boundary,
or another property whose absence would teach an unsafe pattern. If safe excerpting is impossible,
show the minimal complete artifact.

## A complete local teaching unit

A high-leverage local example normally has four moves:

1. **Context** — one sentence naming the actor and desired outcome.
2. **Carrier** — the smallest faithful artifact, request, state trace, or scenario.
3. **Mapping** — explain which field, value, or transition causes the outcome.
4. **Contrast** — when the distinction is non-obvious, change one meaningful input and show the
   different result.

The contrast is not mandatory when the mapping is already obvious. It is especially valuable for
allow/deny evaluation, precedence, retry behavior, state transitions, cache invalidation, and
security controls.

## When not to add another example

Do not add an example merely because a section exists. Prose is sufficient when:

- the section defines a simple term and no non-obvious behavior follows from its structure;
- an earlier nearby example already carries the same mechanism and the new section adds no new
  semantics;
- the file is a pure index or lookup reference;
- the only possible addition would duplicate a canonical implementation without teaching a local
  distinction;
- a short causal sentence is clearer than an artificial toy artifact.

One well-annotated example may cover several adjacent concepts. Prefer expanding its input/output
mapping over adding parallel examples that differ only in names. Never infer quality from the
number of code blocks, examples, or lines.

## Calibration cases

### Policy evaluation needs the policy

Too abstract:

> A permissions boundary limits the maximum permissions a role can receive.

Right-sized carrier:

```json
{"Effect":"Allow","Action":["s3:GetObject"],"Resource":"arn:aws:s3:::reports/*"}
```

Pair that excerpt with two outcomes: an identity-policy `GetObject` grant survives the boundary;
an identity-policy `PutObject` grant does not. The full policy document belongs only in the
canonical policy note.

### Temporal behavior needs a trace

For a cache with `TTL=60s`, show `t=0 miss → load v1`, `t=20 hit → v1`, and
`t=61 miss → load v2`. A class diagram or list of cache methods would not carry expiration behavior.

### A simple definition may need no artifact

“An IAM group is a container for users and is not itself a principal” is already concrete when the
note immediately states that nobody can sign in as a group. Adding JSON would not reveal another
mechanism. Do not manufacture it.
