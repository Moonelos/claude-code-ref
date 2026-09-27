# Content Capture

Prompts, system instructions, tool definitions, tool arguments, tool results, retrieved documents, and model outputs can all contain user data. They are **opt-in**, everywhere, on every code path in this skill.

Read `attributes.md` first for the constants module this imports from.

## Contents

- [Capture switch](#one-switch)
- [System instructions vs chat history](#system-instructions-vs-chat-history)
- [Complete serializers](#the-serializers)
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

Plus retrieval query text and document contents (`provider_sdk.md`).

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

This is an observation-only projection of the physical request. It must not rewrite the request sent to the model. It also has no effect on token accounting: keep the provider-reported input count for the entire request, including system instructions. Do not subtract system tokens or re-tokenize the two telemetry fields separately; `token_usage.md` remains the sole owner of usage.

---

## The serializers

`gen_ai.system_instructions` is an array of content parts. `gen_ai.input.messages` and `gen_ai.output.messages` are message arrays of `{role, parts}`. They are serialized to JSON because the attribute type must be scalar. This is a **complete framework-tolerant template**, not a standalone sketch. It handles dict messages, LangChain messages, normalized multimodal content blocks, tool calls, batched LangChain chat-model input, and multiple output choices.

<!-- complete-python-template -->
```python
# observability/genai_content.py
import json
from typing import Any


ROLE_BY_MESSAGE_TYPE = {
    "human": "user",
    "ai": "assistant",
    "system": "system",
    "tool": "tool",
    "function": "tool",
}


def _role(message: Any, default: str = "user") -> str:
    if isinstance(message, dict):
        value = message.get("role") or message.get("type")
    else:
        value = getattr(message, "role", None) or getattr(message, "type", None)
    return ROLE_BY_MESSAGE_TYPE.get(str(value), str(value or default))


def _part(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"type": "text", "content": value}
    if not isinstance(value, dict):
        return {"type": "text", "content": str(value)}

    part_type = str(value.get("type") or "text")
    if part_type == "non_standard" and isinstance(value.get("value"), dict):
        # LangChain content_blocks wraps some provider-native blocks this way.
        # Unwrap without flattening so JSON and extension payloads survive.
        return _part(value["value"])
    if part_type in {"text", "reasoning"}:
        return {
            "type": part_type,
            "content": value.get("content", value.get("text", "")),
        }
    if part_type in {"tool_call", "tool_use"}:
        name = value.get("name")
        if not name:
            # A standard tool_call requires a name. Keep malformed provider
            # data as an extensible generic part instead of inventing identity.
            return {
                "type": "unknown_tool_call",
                "arguments": value.get("arguments", value.get("args", {})),
            }
        result = {
            "type": "tool_call",
            "name": str(name),
            "arguments": value.get("arguments", value.get("args", {})),
        }
        if call_id := value.get("id"):
            result["id"] = str(call_id)
        return result

    # Preserve normalized multimodal blocks when available. Content capture is
    # already opt-in; default=str below prevents SDK-specific objects raising.
    return dict(value)


def _parts(message: Any) -> list[dict[str, Any]]:
    if isinstance(message, dict):
        content = message.get("content", "")
        tool_calls = message.get("tool_calls") or []
    else:
        try:
            content = getattr(message, "content_blocks", None)
        except (AttributeError, TypeError, ValueError):
            content = None
        if content is None:
            content = getattr(message, "content", "")
        tool_calls = getattr(message, "tool_calls", None) or []

    values = content if isinstance(content, list) else [content]
    result = [_part(value) for value in values]
    if not any(part.get("type") == "tool_call" for part in result):
        for call in tool_calls:
            if isinstance(call, dict):
                result.append(_part({"type": "tool_call", **call}))
            else:
                result.append(
                    _part(
                        {
                            "type": "tool_call",
                            "id": getattr(call, "id", None),
                            "name": getattr(call, "name", None),
                            "args": getattr(call, "args", {}),
                        }
                    )
                )
    return result


def _message(message: Any, default_role: str = "user") -> dict[str, Any]:
    role = _role(message, default_role)
    if role == "tool":
        if isinstance(message, dict):
            response = message.get("content", "")
            tool_call_id = message.get("tool_call_id")
        else:
            response = getattr(message, "content", "")
            tool_call_id = getattr(message, "tool_call_id", None)
        part: dict[str, Any] = {
            "type": "tool_call_response",
            "response": response,
        }
        if tool_call_id:
            part["id"] = str(tool_call_id)
        return {"role": role, "parts": [part]}
    return {"role": role, "parts": _parts(message)}


def serialize_messages(messages: list[Any]) -> str:
    """Request messages -> the standard {role, parts} array."""
    return json.dumps([_message(message) for message in messages], default=str)


def _text_observation_messages(messages: list[dict[str, Any]], *,
                               omit_empty_reasoning: bool = False) -> list[dict] | None:
    """Canonical messages -> a concise projection without losing meaningful content."""
    rendered = []
    for message in messages:
        parts = message.get("parts")
        if not isinstance(parts, list):
            return None
        if omit_empty_reasoning:
            parts = [
                p for p in parts
                if not (isinstance(p, dict) and p.get("type") == "reasoning"
                        and p.get("content") == "")
            ]
        if len(parts) != 1:
            return None
        part = parts[0]
        if not isinstance(part, dict) or part.get("type") != "text":
            return None
        content = part.get("content")
        if not isinstance(content, str):
            return None
        rendered.append({"role": message["role"], "content": content})
    return rendered

def serialize_observation_input(messages: list[Any] | list[list[Any]]) -> str:
    """Readable backend-neutral input; preserve canonical shape on complex content."""
    if not messages:
        return "[]"
    conversation = list(messages[0]) if isinstance(messages[0], (list, tuple)) else messages
    canonical = [_message(message) for message in conversation]
    rendered = _text_observation_messages(canonical)
    return json.dumps(rendered if rendered is not None else canonical, default=str)


def serialize_chat_model_input(
    messages: list[Any] | list[list[Any]],
    *,
    separate_system_instructions: bool,
) -> tuple[str | None, str, int]:
    """LangChain input -> system JSON, message JSON, and batch size.

    The standard attribute describes one conversation. When LangChain batches
    several conversations into one physical request, capture the first and let
    the caller mark the telemetry as truncated instead of inventing a nested
    schema under the standard attribute. Split system messages only when the
    concrete provider adapter sends them through a separate system field.
    """
    if not messages:
        return None, "[]", 0
    if isinstance(messages[0], (list, tuple)):
        batches = messages
    else:
        batches = [messages]

    conversation = list(batches[0])
    system_instructions = None
    if separate_system_instructions:
        system_parts: list[dict[str, Any]] = []
        chat_history: list[Any] = []
        for message in conversation:
            if _role(message) == "system":
                system_parts.extend(_parts(message))
            else:
                chat_history.append(message)
        if system_parts:
            system_instructions = json.dumps(system_parts, default=str)
        conversation = chat_history

    return system_instructions, serialize_messages(conversation), len(batches)


def serialize_text_output(text: str, finish_reason: str | None) -> str:
    """A completed assistant response, streamed or not."""
    message: dict[str, Any] = {
        "role": "assistant",
        "parts": [{"type": "text", "content": text}],
        # Required by the pinned output-message schema. `unknown` is used only
        # when a framework omitted the provider's reason.
        "finish_reason": str(finish_reason or "unknown"),
    }
    return json.dumps([message])


def resolve_finish_reason(*sources: Any) -> str | None:
    """Provider/framework metadata -> one finish reason, preserving its value."""
    keys = ("finish_reason", "finishReason", "stop_reason", "stopReason")
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value is not None and str(value):
                return str(value)
    return None


def serialize_llm_result(response: Any) -> str:
    """LangChain LLMResult -> one assistant message per generation/choice."""
    output_messages: list[dict[str, Any]] = []
    for generation_list in getattr(response, "generations", None) or []:
        for generation in generation_list:
            source = getattr(generation, "message", None)
            if source is None:
                source = {"role": "assistant", "content": getattr(generation, "text", "")}
            message = _message(source, default_role="assistant")

            response_metadata = getattr(source, "response_metadata", None) or {}
            generation_info = getattr(generation, "generation_info", None) or {}
            finish_reason = resolve_finish_reason(response_metadata, generation_info)
            message["finish_reason"] = str(finish_reason or "unknown")
            output_messages.append(message)
    return json.dumps(output_messages, default=str)


def serialize_observation_output(response: Any, output_type: str | None) -> str:
    """Readable output; decode one valid JSON text response into its actual object."""
    canonical = json.loads(serialize_llm_result(response))
    rendered = _text_observation_messages(canonical, omit_empty_reasoning=True)
    if rendered is None:
        return json.dumps(canonical, default=str)
    if len(rendered) != 1:
        return json.dumps(rendered, default=str)
    content = rendered[0]["content"]
    if output_type == "json":
        try:
            return json.dumps(json.loads(content), default=str)
        except (TypeError, ValueError):
            pass
    return json.dumps(content, default=str)


def serialize_observation_text_output(text: str, output_type: str | None) -> str:
    """Streaming equivalent when the callback already owns the completed text."""
    if output_type == "json":
        try:
            return json.dumps(json.loads(text), default=str)
        except (TypeError, ValueError):
            pass
    return json.dumps(text, default=str)


def serialize_tool_input(args: Any) -> str:
    return json.dumps(args, default=str)


def serialize_tool_output(result: Any) -> str:
    return json.dumps(result, default=str) if not isinstance(result, str) else result
```

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
(`langchain/provider_compatibility.md`).

Keep two representations when the selected backend has a documented native display
shape:

1. `gen_ai.system_instructions`, `gen_ai.input.messages`, and
   `gen_ai.output.messages` remain the portable OpenTelemetry source of truth.
2. `app.gen_ai.observation.input` / `output` carry a lossless, content-gated
   presentation. For text-only chat input, use `[{"role": ..., "content": ...}]`.
   For one valid structured-output text response, store the decoded JSON object; for
   ordinary single-text output, store the text scalar. Fall back to the canonical
   envelope for multipart, tool, multimodal, or otherwise ambiguous content.

The application must not emit a vendor namespace. The selected backend's Collector
branch maps the neutral presentation attributes to, for example,
`langfuse.observation.input` / `langfuse.observation.output`, then deletes the neutral
copies. Every other trace branch deletes these payload attributes with the other GenAI
content keys. This preserves portability, prevents duplicate metadata, and keeps the
capture switch and backend retention policy authoritative. Never deform `gen_ai.*`
to satisfy one UI.

For batched LangChain input, record `app.gen_ai.input.batch_size` from the returned integer. If it is greater than one, set `app.gen_ai.input.capture_mode="truncated"`; the standard attributes intentionally contain only the first conversation and its system instructions rather than merging independent inputs.

`gen_ai.input.messages` is scoped to **one** model call — the history actually sent on that call. A stateless agent loop therefore repeats earlier turns on later inference spans. That is correct and faithful, not duplication to be optimised away.

### Mark a partial capture

If you deliberately record less than the full request, keep the standard array schema and say so:

```python
span.set_attribute(APP_INPUT_CAPTURE_MODE, "delta")  # none | full | delta | truncated
```

Without that marker, a filtered payload looks like a complete request, and someone will try to replay it and diagnose the wrong context. Do not invent a wrapper object inside `gen_ai.input.messages`; the standard field must remain a message array.

`gen_ai.conversation.compacted` is a different fact and must not be set here. It means the *model* received summarized or trimmed history, not that *telemetry* was truncated — see `attributes.md`.

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
- A text-only input has a role/content observation projection while the canonical input
  still has role/parts. One valid JSON text output projects to the decoded object. An exactly
  empty reasoning part may be omitted from that presentation projection only; an ambiguous or
  meaningful multipart response falls back byte-for-byte to the canonical envelope.
- The backend-specific Collector path maps the neutral observation projection and removes
  its source attributes; general trace backends receive neither copy.
- When the provider uses a separate system field, `gen_ai.system_instructions` contains its parts and no system-role message remains in `gen_ai.input.messages`; otherwise the system-role message stays in the input history and the separate attribute is absent.
- Provider-reported token usage is identical regardless of content capture or system-instruction projection; the serializer never computes or adjusts tokens.
- Multiple generations appear as independent assistant messages, each with a finish reason; tool responses, tool calls, and multimodal parts are preserved where available.
- Batched input records its batch size and marks the first-conversation capture as truncated.
- If capture is filtered or truncated, `app.gen_ai.input.capture_mode` marks it.
- With capture off, a long streamed response allocates nothing — check the chunk buffer is empty, not just the attribute absent.
