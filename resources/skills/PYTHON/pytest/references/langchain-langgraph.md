# LangChain and LangGraph agents

Use this reference for agent, graph, tool, checkpoint, interrupt, stream, and
model-provider behavior. Inspect the installed LangChain/LangGraph versions and
the application's wrapper APIs before copying a current-doc example; graph,
event-stream, and fake-model interfaces are versioned.

## Keep three kinds of evidence separate

| Evidence | Best use | Ordinary assertions |
| --- | --- | --- |
| Deterministic pytest | Tools, schemas, policy, routing, reducers, state, interrupts, side effects, app wiring | Exact typed state and invariants |
| Live provider integration | Current tool calling, structured output, streaming, credentials, model/provider compatibility | Shape, allowed tool/schema, termination, bounded latency; not prose |
| Dataset evaluation | Nondeterministic answer quality and acceptable trajectories across examples and repetitions | Scores, thresholds, distributions, regressions |

Do not turn a single stochastic model response or one LLM-judge decision into a
blocking unit test. Do not use eval averages to replace hard deterministic
checks for authorization, tool allowlists, side effects, state transitions, and
schema validity.

## Build explicit seams

- Construct the graph or agent through a factory that accepts models, tools,
  service clients, clocks, ID generators, stores, and checkpointers used by the
  implementation.
- Keep nodes focused enough to test meaningful decisions directly. Test pure
  routing and transformation functions without compiling a graph, then add a
  smaller number of compiled-graph tests for wiring and runtime semantics.
- Put business effects behind application ports. Test the tool or node with a
  recording fake; test the concrete provider adapter separately.
- Create a fresh graph and fresh in-memory checkpointer for each test unless a
  test deliberately spans invocations. Give each scenario a unique thread ID.
- Never share a scripted fake model iterator, invocation counter, message list,
  graph state, store, or checkpointer across tests.

Directly invoking a node bypasses graph routing and checkpoint behavior. State
that boundary accurately and retain a compiled-graph test for runtime semantics
the application relies on.

## Test tools as application boundaries

Test a tool function directly before testing it through an agent:

- argument and result schema owned by the application;
- authorization, tenant scope, validation, and dangerous-action preconditions;
- timeout, cancellation, retry classification, and domain-error mapping;
- durable or irreversible effect and idempotency key;
- sanitization and safe error content;
- structured metadata required by later graph nodes.

Then add a small agent-stack test proving the model-visible tool name and schema,
tool-call argument decoding, execution, tool-call-ID correlation, and
success/error feedback. Do not retest the tool's full business matrix through
the model loop.

## Use model fakes for protocol, not intelligence

Use the fake model supported by the installed LangChain version, such as
`GenericFakeChatModel`, to script strings, `AIMessage` tool calls, provider-like
errors, and basic streaming. `GenericFakeChatModel` does not support
`bind_tools`, so it cannot drive `create_agent` or any code that binds tools.
For those, use one canonical scripted tool-calling model per member, a
`BaseChatModel` subclass whose `bind_tools` returns `self` and records the tools
and `tool_choice`, which mints fresh message and tool-call IDs per call, records
the messages it saw, and fails when its script is exhausted
([exhaustion rule](core-principles.md#doubles-must-be-correct);
[example](examples-langchain-langgraph.md#canonical-scripted-tool-calling-model)).

- Derive retry/resume-safe fake responses from received messages or state where
  possible. A fake that returns "tool call on invocation 1, answer on invocation
  2" can break when checkpoint resume or retry legitimately repeats a call.
- Build realistic `AIMessage`, `ToolMessage`, structured-output, and error
  shapes rather than mocking LangChain internals.
- Use a recording model when invocation count, bound tool schema, or request
  metadata is the actual contract.
- Keep current-provider feature support in live integration; a fake proves only
  application logic around the protocol.

Hand-inserting tool messages into graph state does not necessarily emit the
runtime's real tool-stream events. Execute the tool path when event telemetry is
the behavior under test.

## Nodes, routers, reducers, and graph wiring

### Nodes and routers

- Test every policy-significant destination, `END`, malformed or partial state,
  and loop termination.
- Assert the semantic state delta or command, not private helper calls.
- Use table-driven examples for a finite routing matrix and Hypothesis for broad
  state invariants when valuable.
- Test retry or fallback classification at the node boundary without calling a
  live model.

### Reducers and parallel branches

- Test append versus replacement semantics and representative message/state
  round trips.
- Cover conflicting parallel updates, fan-out/fan-in, and ordering only where
  the graph promises an order.
- Do not assume scheduler order between parallel branches. Assert sets or final
  semantic state unless order is contractual.

### Wiring

Use a few compiled-graph tests to prove node registration, edges, conditional
routes, subgraph boundaries, termination, and error propagation. Be alert when a
node has both static edges and dynamic `Command(goto=...)` or conditional
routing: more than one route can execute if the graph is wired that way.

For a meaningful section, prefer a subgraph as a public test boundary. When the
installed API supports it, partial graph execution can use state injection with
`update_state(..., as_node=...)` plus an interrupt point. Do not infer
checkpointer correctness from direct node invocation.

## State and checkpointing

Fast tests with a fresh in-memory saver should cover application semantics:

- same-thread multi-turn accumulation;
- different-thread isolation;
- reducers and representative serializable state;
- semantic current-state fields and pending work;
- state-history meaning rather than generated checkpoint identifiers;
- failure then resume;
- pending writes or successful parallel siblings not repeating after resume;
- stateful versus stateless subgraph behavior when used.

Avoid assertions on checkpoint UUIDs, message IDs generated by the framework,
timestamps, incidental checkpoint count, or internal serialized layout unless
they are an exported compatibility contract.

An in-memory saver cannot validate the production saver. Add marked integration
tests against the actual PostgreSQL, Redis, or other checkpoint implementation
for setup, migrations, serialization, concurrent thread IDs, namespaces,
cleanup, and restart/resume. If implementing a custom saver, run the official
LangGraph checkpointer conformance suite against it.

When recovery guarantees matter, test the durability mode actually configured.
Synchronous, asynchronous, and exit-time persistence have different crash
windows; do not generalize from one to another.

### Checkpoint and store security

Treat persisted state as production data, not test plumbing:

- prove tenant and principal authorization before reading, listing, resuming, or
  deleting a thread; a guessed `thread_id` must not cross a tenant boundary;
- test namespace isolation for checkpoints and long-term stores with distinct
  principals, not only distinct thread IDs;
- exercise the configured serializer and encryption path, including missing or
  wrong keys and key-rotation behavior the service promises;
- keep secrets, raw credentials, and unnecessary PII out of checkpoint, store,
  stream, trace, and failure-artifact payloads; assert redaction at the owned
  serialization or observability boundary;
- test retention and deletion semantics, including associated store data and
  subgraph namespaces, when the product exposes deletion or regulatory cleanup.

Never enable an executable or otherwise unsafe serializer for untrusted state
merely to make a fixture convenient. An in-memory saver cannot prove any of
these production controls.

## Interrupt and resume are replay workflows

For each human-in-the-loop or external approval workflow, prove:

1. the initial invocation pauses and exposes the intended JSON-serializable
   payload;
2. downstream destructive work has not happened;
3. the checkpoint shows the intended pending work;
4. resume uses the same thread ID and a `Command(resume=...)` value compatible
   with the installed API;
5. resume reaches the correct semantic final state;
6. a new or wrong thread cannot resume another workflow;
7. rejection, timeout, malformed response, and cancellation follow explicit
   policy where supported;
8. synchronous and asynchronous paths match if production exposes both.

LangGraph resumes an interrupted node from its beginning. Code before the
interrupt can execute again. Count or record dangerous side effects and prove
they are absent, idempotent, or moved into a later node. Test this explicitly;
do not rely on source inspection.

Do not swallow the interrupt in a broad exception handler. Keep interrupt call
order stable within a node, and use only serializable payloads. For parallel
interrupts, associate resume values with the exposed interrupt identities while
wildcarding generated IDs in assertions.

## Streaming

Test the stream mode and public event protocol consumed by the application:

- state `updates` or `values` and the semantic final state;
- message content reconstructed across chunks;
- custom domain-event name and payload schema;
- tool start/finish/error and tool-call-ID correlation;
- interrupt status/payload and resume stream;
- provider or node error propagation;
- early consumer cancellation and async cleanup.

Do not snapshot token boundaries, timestamps, generated namespace suffixes, or
order between parallel branches. Providers and buffering can change chunking
without changing content. Normalize documented unstable fields and assert the
stable node name, sequence field, event type, semantic payload, and final state.

Current LangGraph event APIs are versioned. Use the version already consumed by
the service and verify its public schema; do not upgrade a stream version as an
incidental test change.

## Evals belong beside, not inside, deterministic tests

Use datasets and evaluation for model-dependent qualities:

- final-answer correctness, groundedness, safety, relevance, and style;
- single-step tool selection;
- message/tool or graph-node trajectory;
- unnecessary tools, looping, efficiency, and multi-turn recovery;
- prompt/model/provider regressions over production-derived sanitized cases.

Choose trajectory matching to fit the contract:

- **strict:** exact ordered route only when order is mandatory;
- **unordered:** the same required steps may occur in any order;
- **superset:** required steps may be accompanied by valid extras;
- **subset:** restrict unnecessary or forbidden actions according to the
  evaluator's documented semantics.

For semantic judges, use a precise rubric and calibrated examples. Run repeated
trials where variance matters, compare aggregate results, retain model/prompt
versions as metadata, and feed sanitized production failures back into the
dataset. A threshold should represent an accepted quality regression budget,
not be tuned until CI turns green.

## Live-provider checks

Selection, secrets, budgets, and cassettes follow
[core-principles.md](core-principles.md#live-checks). Model-specific additions:

- Maintain only the capability matrix the product supports: tool calling,
  structured output, streaming, and relevant error mapping by provider/model
  family.
- Assert types, schema, allowed tool names and arguments, non-empty content,
  termination, and defensible latency—not exact natural-language wording.

## Primary references

- [LangChain testing overview](https://docs.langchain.com/oss/python/langchain/test)
- [LangChain unit testing and fake chat models](https://docs.langchain.com/oss/python/langchain/test/unit-testing)
- [LangChain integration testing](https://docs.langchain.com/oss/python/langchain/test/integration-testing)
- [LangChain agent evals](https://docs.langchain.com/oss/python/langchain/test/evals)
- [LangGraph testing patterns](https://docs.langchain.com/oss/python/langgraph/test)
- [LangGraph graph API and routing](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [Thinking in LangGraph](https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph checkpointers and durability](https://docs.langchain.com/oss/python/langgraph/checkpointers)
- [LangGraph production checkpoint choices](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph streaming modes](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangGraph event streaming](https://docs.langchain.com/oss/python/langgraph/event-streaming)
- [LangGraph checkpointer conformance suite](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-conformance)
- [LangSmith trajectory evaluation](https://docs.langchain.com/langsmith/trajectory-evals)
- [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- [LangSmith repetitions](https://docs.langchain.com/langsmith/repetition)
- [LangSmith pytest integration](https://docs.langchain.com/langsmith/pytest)
