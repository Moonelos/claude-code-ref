# LangChain Provider Compatibility

Read this when adding or changing a model provider, provider adapter, LangChain,
LangGraph, or a backend that renders captured LLM input/output. Provider
serialization is a versioned adapter contract, not a naming convention.

## Compatibility gate

Before implementing or repairing a callback:

1. Read the repository lockfile and identify the exact framework and provider-adapter
   versions used in production.
2. Inspect the installed adapter's request conversion and response parsing source.
   Confirm whether system instructions leave the message list, how structured output
   is requested, which content blocks reach `AIMessage`, and the exact response metadata
   keys. If local source does not settle the contract, search current **official**
   framework and provider documentation; do not rely on blogs or remembered casing.
3. Capture one bounded representative callback start/end payload and the raw exported
   span attributes. Inspect those raw values before interpreting how Langfuse or another
   backend renders them. Then inspect the backend's stored observation input/output: an
   expandable `parts[0]` object can contain the output even when the collapsed UI says only
   `2 items`, while a correct raw attribute can still fail backend ingestion mapping.
4. Add a hermetic provider fixture containing the observed shapes. Assert system-field
   ownership, decoded input/output message JSON, structured-output type, finish reason,
   model identity, usage, preservation of relevant non-text content blocks, and any
   destination presentation projection. For a JSON response, assert both the canonical
   text part and the decoded observation object.
5. Keep a marked live provider check for capability drift when its credentials and cost
   are justified. A unit fixture proves one recorded adapter shape, not current provider
   behaviour.

Normalize only the stable OpenTelemetry envelope (`role`, `parts`,
`finish_reason`). Do not flatten every provider part to text, assume one metadata
casing, or treat a backend's expandable JSON rendering as raw wire evidence. See
`../content_capture.md`, "Backend rendering is not the wire shape".

If the pinned adapter sometimes emits an exactly empty normalized `reasoning` part next to one
text part, keep it in the canonical output fixture and assert that the backend presentation
projection omits only that empty part. A non-empty reasoning part must force canonical fallback.

When a backend renders a different native shape, retain the canonical envelope and
derive a second, content-gated `app.gen_ai.observation.input` / `output` value only
when the conversion is lossless. Map it to the vendor attributes at the Collector.
Do not put `langfuse.*`, `openinference.*`, or another backend namespace in the
provider callback.

For example, the reviewed `langchain-aws` Bedrock Converse adapter sends
`SystemMessage` content through Bedrock's top-level `system` field and preserves the
provider's camel-case `stopReason` in response metadata. Generic code that keeps the
system message in chat history or reads only `stop_reason` produces plausible but
false telemetry.

## Attach configuration to the physical adapter

| Situation | Attach |
| --- | --- |
| Non-streaming model | `OTelModelCallback(capture_content=...)` |
| Streaming model | `OTelModelCallback(capture_content=..., streaming=True)` |
| Adapter with a separate system field, such as Bedrock Converse | `OTelModelCallback(capture_content=..., separate_system_instructions=True)` |
| Both in one service | Use one instance per model with matching flags; instances may be shared only by models with the same wire contract |
| Completion-style non-chat LLM | Add `on_llm_start` as described in `model_callback.md` |

Choose `separate_system_instructions` from the adapter's wire contract, not merely
because the framework object is named `SystemMessage`. This projection never changes
provider-reported token usage.

## Sync versus async invocation

Whether an `AsyncCallbackHandler` also covers synchronous `invoke()` or `stream()`
depends on the pinned `langchain-core`. Resolve it once using the exact production
invocation style:

1. Call the agent exactly as production does.
2. Confirm that a `chat <model>` span exports.
3. If none appears, attach a `BaseCallbackHandler` with equivalent synchronous methods
   and record that both implementations are required.

Never verify with `ainvoke` and ship `invoke`. Instrumentation often fails silently,
so a missing callback invocation otherwise looks like a healthy quiet service.
