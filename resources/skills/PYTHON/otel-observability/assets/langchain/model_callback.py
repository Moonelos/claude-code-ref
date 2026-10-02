"""LangChain model callback: one span per physical model request.

Template for `references/tracing/genai/langchain/model_callback.md`. Copy it into the
service's `observability/` package and adapt the imports to the modules that exist there.
`observability.genai_content` is the template in `assets/genai_content.py`.
"""

import time
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from observability.agent_counters import current_counters
from observability.genai_attributes import (
    APP_OBSERVATION_INPUT,
    APP_OBSERVATION_OUTPUT,
    APP_INPUT_BATCH_SIZE,
    APP_INPUT_CAPTURE_MODE,
    APP_OUTPUT_CAPTURE_MODE,
    APP_STREAM_CHUNK_COUNT,
    ERROR_TYPE,
    GENAI_FINISH_REASONS,
    GENAI_INPUT_MESSAGES,
    GENAI_OPERATION_NAME,
    GENAI_OUTPUT_MESSAGES,
    GENAI_OUTPUT_TYPE,
    GENAI_PROVIDER_NAME,
    GENAI_REQUEST_MAX_TOKENS,
    GENAI_REQUEST_MODEL,
    GENAI_REQUEST_STREAM,
    GENAI_REQUEST_TEMPERATURE,
    GENAI_REQUEST_TOP_P,
    GENAI_RESPONSE_ID,
    GENAI_RESPONSE_MODEL,
    GENAI_SYSTEM_INSTRUCTIONS,
    GENAI_TIME_TO_FIRST_CHUNK,
)
from observability.genai import resolve_provider, resolve_request_model
from observability.genai_content import (
    resolve_finish_reason,
    serialize_chat_model_input,
    serialize_llm_result,
    serialize_observation_input,
    serialize_observation_output,
    serialize_observation_text_output,
    serialize_text_output,
)
from observability.metrics import (
    record_model_operation,
    record_time_to_first_chunk,
)
from observability.genai_usage import set_usage_attributes
from observability.spans import error_type_of, mark_error

# Copy into this module, next to their only caller:
# - extract_usage_metadata(): references/tracing/genai/token_usage.md
# - extract_response_metadata(): model_callback.md, "Reading the LLMResult"
#   (it is the caller of resolve_finish_reason)

tracer = trace.get_tracer(__name__)
MAX_CAPTURED_OUTPUT_CHARS = 32_768


class OTelModelCallback(AsyncCallbackHandler):
    """One span per physical model request.

    Sits below every middleware, so each retry attempt produces its own span.
    Pass streaming=True for a model built with streaming=True; that only sets
    `gen_ai.request.stream` and the chunk-count attribute. Everything the
    stream actually produces is observed, not assumed.
    """

    def __init__(
        self,
        *,
        capture_content: bool,
        streaming: bool = False,
        separate_system_instructions: bool = False,
    ) -> None:
        # Bootstrap passes the settings value; never read settings at import.
        self._capture_content = capture_content
        self._streaming = streaming
        # Set from the concrete provider adapter's wire contract. For example,
        # Bedrock Converse sends system instructions separately from messages.
        self._separate_system_instructions = separate_system_instructions
        # Keyed by run_id: LangChain runs model calls concurrently.
        self._runs: dict[Any, dict[str, Any]] = {}

    async def on_chat_model_start(
        self,
        serialized,
        messages,
        *,
        run_id,
        parent_run_id=None,
        metadata=None,
        **kwargs,
    ) -> None:
        model = resolve_request_model(serialized, metadata, kwargs)
        provider = resolve_provider(metadata)
        span_name = f"chat {model}" if model else "chat"

        counters = current_counters()
        if counters is not None:
            counters.inference_calls += 1

        attributes = {
            GENAI_OPERATION_NAME: "chat",
            GENAI_PROVIDER_NAME: provider,
            GENAI_REQUEST_STREAM: self._streaming,
        }
        if model:
            attributes[GENAI_REQUEST_MODEL] = model

        # Resolve this from the actual callback/provider request shape. Native
        # `json_schema` or `json_object` requests set `gen_ai.output.type=json`;
        # tool calling is not mislabeled as JSON merely because arguments are JSON.
        invocation_params = kwargs.get("invocation_params") or {}
        response_format = invocation_params.get("response_format") or {}
        output_type = None
        if response_format.get("type") in {"json_schema", "json_object"}:
            output_type = "json"
            attributes[GENAI_OUTPUT_TYPE] = output_type

        # start_span (not start_as_current_span): the callback returns before
        # the model call finishes, so this span cannot be a context manager.
        # Its parent is whatever span is current right now — the agent span.
        span = tracer.start_span(
            span_name,
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
        )

        for attribute, key in (
            (GENAI_REQUEST_TEMPERATURE, "temperature"),
            (GENAI_REQUEST_MAX_TOKENS, "max_tokens"),
            (GENAI_REQUEST_TOP_P, "top_p"),
        ):
            if invocation_params.get(key) is not None:
                span.set_attribute(attribute, invocation_params[key])

        if self._capture_content:
            captured_system, captured_input, batch_size = serialize_chat_model_input(
                messages,
                separate_system_instructions=self._separate_system_instructions,
            )
            if captured_system is not None:
                span.set_attribute(GENAI_SYSTEM_INSTRUCTIONS, captured_system)
            span.set_attribute(GENAI_INPUT_MESSAGES, captured_input)
            span.set_attribute(APP_OBSERVATION_INPUT, serialize_observation_input(messages))
            span.set_attribute(APP_INPUT_BATCH_SIZE, batch_size)
            if batch_size > 1:
                span.set_attribute(APP_INPUT_CAPTURE_MODE, "truncated")

        self._runs[run_id] = {
            "span": span,
            "started_at": time.perf_counter(),
            "model": model,
            "provider": provider,
            "first_chunk_seen": False,
            # Operational count is unconditional. Content is separate, bounded,
            # and absent when capture is disabled.
            "chunk_count": 0,
            "captured_chunks": [] if self._capture_content else None,
            "captured_chars": 0,
            "capture_truncated": False,
            "output_type": output_type,
        }

    async def on_llm_new_token(self, token, *, run_id, chunk=None, **kwargs) -> None:
        """Fires only for a streaming model. Owns time-to-first-chunk."""
        run = self._runs.get(run_id)
        if run is None:
            return

        run["chunk_count"] += 1

        if not run["first_chunk_seen"]:
            elapsed = time.perf_counter() - run["started_at"]
            run["span"].set_attribute(GENAI_TIME_TO_FIRST_CHUNK, elapsed)
            record_time_to_first_chunk(
                elapsed,
                operation="chat",
                provider=run["provider"],
                request_model=run["model"],
            )
            run["first_chunk_seen"] = True

        if run["captured_chunks"] is not None:
            text = str(token)
            remaining = MAX_CAPTURED_OUTPUT_CHARS - run["captured_chars"]
            if remaining > 0:
                captured = text[:remaining]
                run["captured_chunks"].append(captured)
                run["captured_chars"] += len(captured)
            if len(text) > max(remaining, 0):
                run["capture_truncated"] = True

    async def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        span = run["span"]

        metadata = extract_response_metadata(response)
        if "response_model" in metadata:
            span.set_attribute(GENAI_RESPONSE_MODEL, metadata["response_model"])
        if "response_id" in metadata:
            span.set_attribute(GENAI_RESPONSE_ID, metadata["response_id"])
        if "finish_reasons" in metadata:
            span.set_attribute(GENAI_FINISH_REASONS, metadata["finish_reasons"])

        # Extracted once, used twice: the span attributes and the token
        # histogram must come from the same dict or they can drift apart.
        usage = extract_usage_metadata(response)
        set_usage_attributes(span, usage)

        if self._streaming:
            span.set_attribute(
                APP_STREAM_CHUNK_COUNT, run["chunk_count"]
            )

        if self._capture_content:
            # Observed, not configured: if chunks actually arrived, the joined
            # buffer is the response. Otherwise the LLMResult is.
            if run["chunk_count"]:
                span.set_attribute(
                    GENAI_OUTPUT_MESSAGES,
                    serialize_text_output(
                        "".join(run["captured_chunks"]),
                        (metadata.get("finish_reasons") or ["unknown"])[0],
                    ),
                )
                span.set_attribute(
                    APP_OBSERVATION_OUTPUT,
                    serialize_observation_text_output(
                        "".join(run["captured_chunks"]), run["output_type"]
                    ),
                )
                if run["capture_truncated"]:
                    span.set_attribute(
                        APP_OUTPUT_CAPTURE_MODE, "truncated"
                    )
            else:
                span.set_attribute(
                    GENAI_OUTPUT_MESSAGES, serialize_llm_result(response)
                )
                span.set_attribute(
                    APP_OBSERVATION_OUTPUT,
                    serialize_observation_output(response, run["output_type"]),
                )

        record_model_operation(
            duration_s=time.perf_counter() - run["started_at"],
            operation="chat",
            provider=run["provider"],
            request_model=run["model"],
            response_model=metadata.get("response_model"),
            usage=usage,
        )
        span.end()

    async def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        span = run["span"]

        if self._streaming:
            span.set_attribute(
                APP_STREAM_CHUNK_COUNT, run["chunk_count"]
            )

        # A framework callback cannot use start_span, so it marks the span
        # itself (../../references/conventions/errors.md). The boundary logs the detail.
        mark_error(span, error)

        record_model_operation(
            duration_s=time.perf_counter() - run["started_at"],
            operation="chat",
            provider=run["provider"],
            request_model=run["model"],
            error_type=error_type_of(error),
        )
        span.end()

    def abandon_runs_older_than(self, max_age_s: float) -> None:
        now = time.perf_counter()
        for run_id, run in list(self._runs.items()):
            if now - run["started_at"] > max_age_s:
                run = self._runs.pop(run_id, None)
                if run:
                    run["span"].set_status(Status(StatusCode.ERROR))
                    # Documented sentinel, not a class name: no exception occurred.
                    # The closed set is in ../../references/conventions/errors.md.
                    run["span"].set_attribute(ERROR_TYPE, "_ABANDONED")
                    if self._streaming:
                        run["span"].set_attribute(
                            APP_STREAM_CHUNK_COUNT, run["chunk_count"]
                        )
                    record_model_operation(
                        duration_s=now - run["started_at"],
                        operation="chat",
                        provider=run["provider"],
                        request_model=run["model"],
                        error_type="_ABANDONED",
                    )
                    run["span"].end()
