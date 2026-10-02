"""GenAI content serializers: prompts, completions, and tool payloads.

Template for `references/tracing/genai/content_capture.md`. Copy it into the
service's `observability/` package as `observability/genai_content.py`.

A complete framework-tolerant template, not a standalone sketch: it handles
dict messages, LangChain messages, normalized multimodal content blocks, tool
calls, batched LangChain chat-model input, and multiple output choices.
Every caller gates on the content-capture switch before calling it.
"""

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


# default=str is deliberate: a tool returning a dataclass, a Decimal, or a
# datetime must not make json.dumps raise inside a span.
def serialize_tool_input(args: Any) -> str:
    return json.dumps(args, default=str)


def serialize_tool_output(result: Any) -> str:
    return json.dumps(result, default=str) if not isinstance(result, str) else result
