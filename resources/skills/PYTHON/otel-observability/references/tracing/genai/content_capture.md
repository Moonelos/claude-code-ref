# Content Capture

Prompts, system instructions, tool definitions, tool arguments, tool results, retrieved documents, and model outputs can all contain user data. They are **opt-in**, everywhere, on every code path in this skill.

Read `attributes.md` first for the constants module this imports from.

## Contents

- [Capture switch](#one-switch)
- [System instructions vs chat history](#system-instructions-vs-chat-history)
- [Serializers](#the-serializers)
- [Partial and truncated capture](#mark-a-partial-capture)
- [Backend policy](#where-content-is-allowed-to-go)
- [Verification](#verify)

---

## One switch

**`CAPTURE_AI_CONTENT`**, read from the service config object (`../../setup/package_layout.md`), never from `os.environ` at a call site.

```python
# capture_ai_content is passed in from bootstrap, never read at import time.
if capture_ai_content:
    system_instructions, input_messages, _ = serialize_chat_model_input(
        messages,
        separate_system_instructions=provider_uses_separate_system_field,
    )
    if system_instructions is not None:
        span.set_attribute(GENAI_SYSTEM_INSTRUCTIONS, system_instructions)
    span.set_attribute(GENAI_INPUT_MESSAGES, input_messages)
    span.set_attribute(
        GENAI_OUTPUT_MESSAGES,
        serialize_text_output(answer, finish_reason),
    )
```

The attributes it gates:

```
gen_ai.system_instructions      gen_ai.tool.definitions
gen_ai.input.messages           gen_ai.tool.call.arguments
gen_ai.output.messages          gen_ai.tool.call.result
app.gen_ai.observation.input    app.gen_ai.observation.output
```

Plus retrieval query text and document contents (`retrieval.md`).

When capture is **off**, everything else is still recorded: model, provider, operation, parameters, latency, TTFC, token usage, finish reasons, errors. An observability implementation with content capture disabled is still fully useful for operations — it just cannot show you what was said.

Gate the *collection*, not only the *write*. A streaming callback that accumulates every token into a list and then skips `set_attribute` still buffers every response in memory for nothing (`langchain/model_callback.md`).

---

## System instructions vs chat history

Represent the request the way the concrete provider API receives it:

| Provider request shape | Telemetry ownership |
| --- | --- |
| A separate `system`, `instructions`, or equivalent field | Put those parts only in `gen_ai.system_instructions`; remove them from `gen_ai.input.messages` |
| A system-role message inside the ordinary chat history | Keep it only as `role="system"` in `gen_ai.input.messages`; omit `gen_ai.system_instructions` |

Never copy the same instruction into both attributes. Amazon Bedrock Converse, for example, has a top-level `system` field separate from `messages`, so a LangChain `SystemMessage` that its Bedrock adapter maps there belongs in `gen_ai.system_instructions`. The human input and any prior assistant/tool turns remain in `gen_ai.input.messages`.

This is an observation-only projection of the physical request. It must not rewrite the request sent to the model, and it never changes token accounting (`token_usage.md`, "The mapping rule", owns that rule).

---

## The serializers

`gen_ai.system_instructions` is an array of content parts. `gen_ai.input.messages` and `gen_ai.output.messages` are message arrays of `{role, parts}`. They are serialized to JSON because the attribute type must be scalar.

The complete framework-tolerant template is **`assets/genai_content.py`** (skill root); copy it into the service as `observability/genai_content.py`. It is not a standalone sketch: it handles dict messages, LangChain messages, normalized multimodal content blocks, tool calls, batched LangChain chat-model input, and multiple output choices. Its public functions:

| Function | Returns |
| --- | --- |
| `serialize_messages(messages)` | request messages as the standard `{role, parts}` JSON array |
| `serialize_chat_model_input(messages, *, separate_system_instructions)` | `(system_instructions_json \| None, input_messages_json, batch_size)` for LangChain chat-model input; splits system messages only when the provider adapter sends them through a separate field, and captures only the first conversation of a batch |
| `serialize_text_output(text, finish_reason)` | one completed assistant message, streamed or not, with `finish_reason` (`unknown` only when the framework omitted it) |
| `serialize_llm_result(response)` | a LangChain `LLMResult` as one assistant message per generation/choice, each with its finish reason |
| `resolve_finish_reason(*sources)` | the first `finish_reason` / `finishReason` / `stop_reason` / `stopReason` found in provider or framework metadata, value preserved |
| `serialize_observation_input(messages)`, `serialize_observation_output(response, output_type)`, `serialize_observation_text_output(text, output_type)` | the backend presentation projection (`app.gen_ai.observation.*`), see [Backend rendering](#backend-rendering-is-not-the-wire-shape) |
| `serialize_tool_input(args)`, `serialize_tool_output(result)` | tool arguments and results as JSON (a string result passes through) |

`default=str` on the tool serializers is deliberate: a tool returning a dataclass, a `Decimal`, or a `datetime` must not make `json.dumps` raise inside a span.

Preserve provider `reasoning` blocks in canonical output. The observation projection may omit an
exactly empty block; non-empty, signed, multimodal, tool, or other parts require canonical fallback.

Every output choice carries `finish_reason`, as required by the pinned JSON schema. Preserve the provider value; `unknown` is only a fail-soft fallback when a framework omits it. Optional tool-call IDs are omitted when unavailable, and a malformed nameless tool call is retained as a generic `unknown_tool_call` part rather than assigned a fabricated standard identity.

### Backend rendering is not the wire shape

Langfuse may parse a JSON string stored in a text part and display it as an
expandable object. That presentation does not prove the serializer emitted a
nested object, and flattening the message to make the UI look different can break
the OpenTelemetry `{role, parts, finish_reason}` contract. Inspect the raw exported
`gen_ai.input.messages`, `gen_ai.system_instructions`, and
`gen_ai.output.messages` attributes first, then compare the decoded JSON with the
pinned convention schema.

Conversely, a plausible UI does not prove fidelity. Provider adapters differ in
content-block normalization and metadata casing. A serializer must retain the
actual provider content blocks and use the provider compatibility gate in
`langchain/model_callback.md`; do not reduce every list block to its `text` key or
assume only snake_case finish reasons. Never infer provider serialization from
generic framework names; inspect the locked adapter source or current official
docs and protect raw callback and export shapes with provider fixtures
(`langchain/model_callback.md`, "Compatibility gate").

`gen_ai.system_instructions`, `gen_ai.input.messages`, and `gen_ai.output.messages`
remain the portable OpenTelemetry source of truth. When the selected backend has a
documented native display shape, the application additionally emits the content-gated
`app.gen_ai.observation.input` / `output` presentation; its lossless rules and Collector
mapping are Langfuse-specific and live in `../../backends/langfuse.md`
("Observation input and output"). Never deform `gen_ai.*` to satisfy one UI.

For batched LangChain input, record `app.gen_ai.input.batch_size` (`APP_INPUT_BATCH_SIZE`) from the returned integer. If it is greater than one, set `app.gen_ai.input.capture_mode="truncated"`; the standard attributes intentionally contain only the first conversation and its system instructions rather than merging independent inputs.

`gen_ai.input.messages` is scoped to **one** model call — the history actually sent on that call. A stateless agent loop therefore repeats earlier turns on later inference spans. That is correct and faithful, not duplication to be optimised away.

### Mark a partial capture

If you deliberately record less than the full request, keep the standard array schema and say so:

```python
span.set_attribute(APP_INPUT_CAPTURE_MODE, "delta")  # none | full | delta | truncated
```

Without that marker, a filtered payload looks like a complete request, and someone will try to replay it and diagnose the wrong context. Do not invent a wrapper object inside `gen_ai.input.messages`; the standard field must remain a message array.

Captured output has its own marker, `APP_OUTPUT_CAPTURE_MODE` (`app.gen_ai.output.capture_mode`): `truncated` when the bounded capture buffer (32 KiB in the templates) cut the text, `partial` when the response itself ended early because the stream failed after the first chunk. Omit it for a complete capture. Values: `attributes.md`.

Do not set `gen_ai.conversation.compacted` for a partial capture: it records what the *model* received, not what *telemetry* kept (`attributes.md`, "Conversation correlation").

---

## Where content is allowed to go

Capturing content in the application is one decision; which backend may store it is another. **`../../collector/component.md` owns the per-backend content policy** — read it before assuming a captured payload is allowed to leave the process.

The consequence for this file: capture being *on* does not mean every trace destination may receive the payload. If traces fan out to more than one backend, redact the payload attributes on the path to the general one — Collector work, in `../../collector/production.md` — and keep prompts out of the logs entirely (the `python-logging` skill, `../../../../python-logging/references/genai.md`).

Mask in the application first. A Collector `attributes` processor deletes by key; it cannot find a secret embedded inside an otherwise-permitted JSON string.

**Sampling is not a privacy control.** A trace not sampled today may be sampled tomorrow, and content capture must be correct either way.

---

## Verify

- With `CAPTURE_AI_CONTENT` unset or false, **no** payload attribute appears anywhere. Against a captured span dump (`../../verification.md` shows how to produce one):

```bash
grep -E 'gen_ai\.(input\.messages|output\.messages|system_instructions|tool\.definitions|tool\.call\.(arguments|result))' captured_spans.json
```

Expect no matches.

- With it enabled, the attributes appear and hold the standard message-array schema.
- Observation-projection checks (role/content input, decoded JSON output, canonical fallback, Collector mapping): `../../backends/langfuse.md`, "Verify".
- When the provider uses a separate system field, `gen_ai.system_instructions` contains its parts and no system-role message remains in `gen_ai.input.messages`; otherwise the system-role message stays in the input history and the separate attribute is absent.
- Usage is unchanged by capture or system-instruction projection: `token_usage.md`, "Verify". The serializer never computes or adjusts tokens.
- Multiple generations appear as independent assistant messages, each with a finish reason; tool responses, tool calls, and multimodal parts are preserved where available.
- Batched input records its batch size and marks the first-conversation capture as truncated.
- If capture is filtered or truncated, `app.gen_ai.input.capture_mode` or `app.gen_ai.output.capture_mode` marks it.
- With capture off, a long streamed response allocates nothing — check the chunk buffer is empty, not just the attribute absent.
