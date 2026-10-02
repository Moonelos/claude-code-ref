# LangChain / LangGraph: Instrumentation Architecture

Read this before any of the other `langchain/` files. It explains which layer owns which spans, so the pieces you build later fit together instead of duplicating each other.

Everything here builds on the shared GenAI vocabulary one level up. Read `../attributes.md` first; pull in `../token_usage.md` and `../content_capture.md` when you reach the layer that needs them.

---

## Why an agent needs three layers

An agent is not one call. One `agent.invoke()` can contain several model calls, several tool calls, retries at both levels, and a summarization model call — all inside a graph you did not write. A single span around `invoke()` tells you it took 14 seconds and nothing about why.

Each layer has a different hook because each observes a different execution boundary:

```
callback           -> model observability     every physical model request
wrap_tool_call     -> tool observability      every physical tool execution
outer wrapper      -> whole-agent observability the user-visible unit of work
```

None of the three sees retrieval — that is your own code, and its spans live in
`../retrieval.md`.

They compose into the trace you want:

```
invoke_agent support_agent               outer wrapper
├── chat gpt-5                           callback
├── execute_tool web_search  ERROR       wrap_tool_call
├── execute_tool web_search  OK          wrap_tool_call
├── chat gpt-5                           callback
├── chat gpt-5-mini                      callback  (summarization model)
└── chat gpt-5                           callback
```

---

## Why the callback, specifically, for models

The callback fires around the **actual model request**, below any middleware. That single fact does most of the work:

```
ModelRetryMiddleware
    ↓
actual model invocation
    ↓
OTelModelCallback          <- fires here, once per physical attempt
```

So retries need no retry-specific tracing code, and `ModelRetryMiddleware` needs no tracing-specific configuration. Attempt one, attempt two, and attempt three each produce their own model span, with their own duration, status, and token counts, for free. This diagram is the one the other `langchain/` files refer to.

The callback also sees the summarization model, if you attach it there — see `tools_and_middleware.md`.

## Why middleware, specifically, for tools

Tools have no equivalent low-level hook, so tracing must happen at the middleware layer — where `ToolRetryMiddleware` also lives. That makes **ordering** a real decision with a visible consequence, covered in `tools_and_middleware.md`.

## Why an explicit outer span

Nothing in the framework emits a span for "one agent invocation." Without it, the model and tool spans hang directly off the HTTP or worker span and you lose the unit that agent-level metrics (`gen_ai.invoke_agent.duration`, model calls per invocation) are computed over.

---

## Build order

Each step is independently verifiable, so build and check them in this order:

1. **SDK bootstrap** — providers, exporters, shutdown. `../../../setup/sdk_bootstrap.md`
2. **The instruments and fan-out counters** — in the service's existing
   metrics module, from `../../../metrics/genai.md`. Every
   tracing layer below imports them, so they come **before** the tracing code,
   not after it. Build the module here; the dashboards, cardinality traps, and
   fan-out rationale in that file can wait until step 6.
3. **Model callback** — attach to the model, confirm one span per model call with token usage. `model_callback.md` + `../token_usage.md`
4. **Tool middleware** — confirm one span per tool execution. `tools_and_middleware.md`
5. **Outer agent span** — confirm model and tool spans nest under it. `streaming_and_agent_span.md`
6. **Metrics** — the rest of `../../../metrics/genai.md`: instruments beyond the module, dashboards, alerting.
7. **Logging** — the `python-logging` skill (`../../../../../python-logging/references/genai.md`), with `../../../logging/correlation.md`

Do not build every layer and then debug. A missing token count is trivial to find at step 3 and painful at step 6.

Step 2 is not optional sequencing advice. `model_callback.md`,
`tools_and_middleware.md`, and `streaming_and_agent_span.md` all import
`record_model_operation`, `record_time_to_first_chunk`,
`record_tool_execution`, `record_agent_invocation`, `invocation_counters`,
`bind_counters`, and `current_counters`. Writing the tracing layer first
produces a pile of `ImportError`s, and the tempting fix — inventing local
recorder functions — is exactly the label drift the shared module exists to
prevent.

If the agent does retrieval, add embedding and retrieval spans as well — they are made by your retriever code, which no callback or middleware can see. The span shapes are in `../retrieval.md`, and they are the same on both paths.

---

## Where the code lives

Framework-specific instrumentation stays out of the generic SDK module but in
the service's existing observability package by default
(`../../../setup/package_layout.md`):

```
observability/
    tracing.py               generic SDK setup — no langchain imports
    metrics.py               instruments, incl. record_model_operation() and friends
    logging.py
    genai_attributes.py      shared constants — no langchain imports
    genai_usage.py           set_usage_attributes()
    genai_content.py         message and payload serializers
    agent_counters.py        invocation_counters() / current_counters(), if not in metrics.py
    genai.py                 OTelModelCallback, build_trace_tool_call, and agent
                             invocation wrappers; may import LangChain
```

The module split is load-bearing: `observability/tracing.py` and the package
initializer must not import LangChain. A sibling `observability/genai.py` may do
so and is loaded only by GenAI composition. Do not add a parallel nested
observability package until the framework-specific surface has real size,
independent change, lifecycle/test needs, or demonstrated import pressure.

---

## Wiring it together

The complete wiring — one model callback on the main and summarization models, retry
middleware, the tool tracing middleware, and their order — is in
`tools_and_middleware.md`, "Complete middleware stack". How many callback instances to
build, and why the callback attaches to the model rather than the invocation config:
`model_callback.md`, "How to attach it".

---

## Do not double-instrument

If the project already uses a framework integration that creates generations — the Langfuse `CallbackHandler`, an OpenInference instrumentor, a LiteLLM gateway callback — decide on **one** primary capture path per model call.

Two paths means two generation records for the same call: doubled token counts, doubled cost, unusable analytics. Symptoms are easy to miss because both traces look correct in isolation.

| Situation | Do |
| --- | --- |
| Vendor-neutral OTel is the requirement | Use the callback in this skill; route to Langfuse at the Collector |
| Langfuse SDK is already the tracing owner | Use its `CallbackHandler`; add your own spans only for business steps it cannot see |
| A gateway (LiteLLM) already logs model calls | Do not also instrument the model in the app, unless you deliberately want both views and know how to reconcile them |

---

## Version note

The APIs used here — `create_agent`, the `langchain.agents.middleware` decorators, `ToolRetryMiddleware`, `ModelRetryMiddleware`, `SummarizationMiddleware`, and `usage_metadata` — are LangChain v1 APIs. Pin the versions in the project's lockfile and re-run the verification in `../../../verification.md` after any LangChain upgrade; middleware ordering semantics and callback payload shapes are exactly the sort of thing a minor release adjusts.
