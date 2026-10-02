# GenAI Span Vocabulary

Read this for any service that calls a model, whether through LangChain or a provider SDK directly. It defines the names the other `genai/` files use, and the three facts that are easy to get subtly wrong: the operation vocabulary, conversation correlation, and which first-chunk latency you are measuring.

Two neighbours own the rest:

| Topic | File |
| --- | --- |
| Token counts and per-provider usage adapters | `token_usage.md` |
| Prompts, completions, tool payloads, `CAPTURE_AI_CONTENT` | `content_capture.md` |

---

## Put the names in one module

The GenAI semantic conventions are still evolving. Scattering string literals across forty call sites means every convention change is a forty-file diff. One constants module makes it a one-file diff.

```python
# observability/genai_attributes.py
"""OpenTelemetry GenAI semantic convention names used by this service.

Checked against the OpenTelemetry GenAI semantic conventions on <date>.
Keys prefixed app.* are organisation-owned and have no OTel equivalent.
"""

# --- operation identity (set at span creation; samplers can see these) ---
GENAI_OPERATION_NAME = "gen_ai.operation.name"
GENAI_PROVIDER_NAME = "gen_ai.provider.name"
GENAI_REQUEST_MODEL = "gen_ai.request.model"
GENAI_REQUEST_STREAM = "gen_ai.request.stream"

# --- response ---
GENAI_RESPONSE_MODEL = "gen_ai.response.model"
GENAI_RESPONSE_ID = "gen_ai.response.id"
GENAI_FINISH_REASONS = "gen_ai.response.finish_reasons"
GENAI_TIME_TO_FIRST_CHUNK = "gen_ai.response.time_to_first_chunk"  # seconds
GENAI_OUTPUT_TYPE = "gen_ai.output.type"

# --- usage (see token_usage.md) ---
GENAI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GENAI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GENAI_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GENAI_CACHE_WRITE_INPUT_TOKENS = "gen_ai.usage.cache_write.input_tokens"
GENAI_REASONING_OUTPUT_TOKENS = "gen_ai.usage.reasoning.output_tokens"
GENAI_AUDIO_INPUT_TOKENS = "gen_ai.usage.audio.input_tokens"
GENAI_AUDIO_OUTPUT_TOKENS = "gen_ai.usage.audio.output_tokens"

# Organisation-owned: complete source detail maps, serialized for fidelity.
# Standard scalar projections above are emitted as well; never invent a
# catch-all detail-map attribute under gen_ai.*.
APP_INPUT_TOKEN_DETAILS = "app.gen_ai.usage.input_token_details"
APP_OUTPUT_TOKEN_DETAILS = "app.gen_ai.usage.output_token_details"

# --- request parameters ---
GENAI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GENAI_REQUEST_TOP_P = "gen_ai.request.top_p"
GENAI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GENAI_REQUEST_SEED = "gen_ai.request.seed"
GENAI_REQUEST_REASONING_LEVEL = "gen_ai.request.reasoning.level"

# --- agents, tools, workflows ---
GENAI_AGENT_NAME = "gen_ai.agent.name"
GENAI_AGENT_ID = "gen_ai.agent.id"
GENAI_WORKFLOW_NAME = "gen_ai.workflow.name"
GENAI_TOOL_NAME = "gen_ai.tool.name"
GENAI_TOOL_TYPE = "gen_ai.tool.type"
GENAI_TOOL_CALL_ID = "gen_ai.tool.call.id"
APP_TOOL_REQUESTED_NAME = "app.gen_ai.tool.requested_name"  # raw name, when bucketed
APP_TOOL_RESULT_SIZE_BYTES = "app.gen_ai.tool.result_size_bytes"
APP_AGENT_TIME_TO_FIRST_CHUNK = "app.agent.time_to_first_chunk"  # seconds
APP_AGENT_STEP_COUNT = "app.agent.step_count"

# --- streaming ---
APP_STREAM_CHUNK_COUNT = "app.gen_ai.stream.chunk_count"

# --- conversation ---
GENAI_CONVERSATION_ID = "gen_ai.conversation.id"
GENAI_CONVERSATION_COMPACTED = "gen_ai.conversation.compacted"

# --- opt-in content (see content_capture.md) ---
GENAI_SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"
GENAI_INPUT_MESSAGES = "gen_ai.input.messages"
GENAI_OUTPUT_MESSAGES = "gen_ai.output.messages"
GENAI_TOOL_DEFINITIONS = "gen_ai.tool.definitions"
GENAI_TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
GENAI_TOOL_CALL_RESULT = "gen_ai.tool.call.result"
APP_INPUT_CAPTURE_MODE = "app.gen_ai.input.capture_mode"  # none|full|delta|truncated
APP_INPUT_BATCH_SIZE = "app.gen_ai.input.batch_size"  # conversations in one request
# truncated = capture buffer cut the text; partial = the stream failed mid-response
APP_OUTPUT_CAPTURE_MODE = "app.gen_ai.output.capture_mode"  # none|full|truncated|partial
APP_OBSERVATION_INPUT = "app.gen_ai.observation.input"
APP_OBSERVATION_OUTPUT = "app.gen_ai.observation.output"

ERROR_TYPE = "error.type"
```

Record the date you checked the conventions in the module docstring. `gen_ai.system` is legacy — use `gen_ai.provider.name` in new code.

---

## Span discipline

- Spans are write-only: never read attributes back from a span to make a
  decision or build another signal.
- `gen_ai.usage.*` goes only on model-call spans (and the agent span that owns
  them); roll-ups on business spans use `app.*` keys.
- No spans as events: a point-in-time occurrence is a log plus a counter.
- Do not copy `http.*` attributes onto internal spans; the server span has them.

## Operation vocabulary

`gen_ai.operation.name` names the logical operation, and the span name is `{operation} {subject}`.

| Operation | For |
| --- | --- |
| `chat` | a chat-style model call |
| `generate_content` | multimodal generation |
| `text_completion` | plain completion |
| `embeddings` | an embedding model call |
| `retrieval` | vector store, search system, managed retrieval API |
| `invoke_agent` | one agent invocation |
| `invoke_workflow` | a coordinated process across agents or steps |
| `execute_tool` | a tool execution |
| `create_agent`, `plan` | agent construction, planning/decomposition |
| `search_memory`, `create_memory`, `update_memory`, `upsert_memory`, `delete_memory` | long-term memory operations |

The five you will use in almost every agent service are `invoke_agent`, `chat`, `execute_tool`, `retrieval`, and `embeddings`. Add the memory operations only if the service has a real memory store.

Span-name rules — low cardinality, operation then stable subject — are in `../../conventions/naming.md`.

## Provider values

`gen_ai.provider.name` uses the provider the client actually talks to:

```
openai            azure.ai.openai      azure.ai.inference
anthropic         aws.bedrock          gcp.gemini
gcp.vertex_ai     gcp.gen_ai           cohere
mistral_ai        deepseek             groq
x_ai              perplexity           ibm.watsonx.ai
moonshot_ai
```

Through a proxy or gateway, set the platform you can actually see at span start. If the upstream provider becomes known later, record it as `app.gen_ai.upstream_provider`.

---

## Conversation correlation

Multi-turn conversations should **not** be one enormous trace. Each user interaction is its own trace; `gen_ai.conversation.id` correlates them.

```
conversation_id = abc123

trace 1  user turn 1   gen_ai.conversation.id = abc123
trace 2  user turn 2   gen_ai.conversation.id = abc123
trace 3  user turn 3   gen_ai.conversation.id = abc123
```

A single trace spanning a whole conversation has a root span that lasts as long as the user is engaged, so its duration means nothing, it never completes while the session is open, and no backend can render it usefully.

Set the ID on the root span of each turn — the agent span, or the HTTP/worker span in a non-agent service — and on the model spans if your backend filters at observation level. For LangChain, that means putting it in the invocation config or reading it from agent state in the callback.

It is a **trace** dimension: never a metric attribute. One time series per conversation is a cardinality incident.

`gen_ai.conversation.compacted=true` means the model received compacted context — summarized or trimmed history, for example after `SummarizationMiddleware` ran (`langchain/tools_and_middleware.md`). Set it only on the model call that actually received it, and never because telemetry was truncated or partially captured (that is `app.gen_ai.*.capture_mode`, `content_capture.md`); confusing those makes dashboards report context compaction that never occurred.

---

## Three different first-chunk latencies

Streaming produces up to three "time to first token" numbers. They answer different questions, and reporting one as another hides where the latency actually is.

| Measurement | Attribute | Spans from | Owned by |
| --- | --- | --- | --- |
| API first byte | `app.response.time_to_first_chunk` | request received → first byte to the client | `../http_service.md` |
| Agent TTFC | `app.agent.time_to_first_chunk` | agent invocation → first chunk visible to the caller, including planning, retrieval, and tool calls | `langchain/streaming_and_agent_span.md` |
| Model TTFC | `gen_ai.response.time_to_first_chunk` | one model request → first chunk from that model | `langchain/model_callback.md`, `provider_sdk.md` |

An agent that calls two tools before answering can have a 4-second agent TTFC and a 200-millisecond model TTFC. Only the model one has a standard attribute; the other two are organisation-owned because `gen_ai.response.time_to_first_chunk` belongs to a single model request and nothing else.

Each must be measured on the real stream. Agent-level *step* updates arrive when a graph node finishes, long after the first token left the model — computing TTFC from them gives a number several times too large.

---

## What a good GenAI trace answers

Use this as the acceptance test for the spans you produce:

| Question | Comes from |
| --- | --- |
| Which request or job triggered this? | the parent HTTP/worker span |
| Which model was asked, and which answered? | `gen_ai.request.model`, `gen_ai.response.model` |
| Was it streaming, and how fast was the first chunk? | `gen_ai.request.stream`, `gen_ai.response.time_to_first_chunk` |
| How many tokens, and how much came from cache? | `gen_ai.usage.*` |
| Did retrieval help or hurt? | retrieval/embedding child spans |
| Did a tool fail? | `execute_tool` spans with `error.type` |
| Did the agent loop? | repeated model/tool spans under one `invoke_agent` span |
| Which conversation is this turn part of? | `gen_ai.conversation.id` |

If the trace is one opaque span saying "called the model" with a duration, it is not enough. It tells you a dependency was slow, not why the workflow behaved as it did.

---

## Then

| Next | File |
| --- | --- |
| Token counts | `token_usage.md` |
| Prompts and payloads | `content_capture.md` |
| Direct provider SDK | `provider_sdk.md` |
| LangChain / LangGraph | `langchain/architecture.md` |
| GenAI metrics | `../../metrics/genai.md` |
| GenAI logging | the `python-logging` skill (`../../../../python-logging/references/genai.md`) |
