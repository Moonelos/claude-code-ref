# Embedding and Retrieval Spans (RAG)

Read this on **either** GenAI path. Embedding, retrieval, and reranking calls
are made by the service's own retriever code — no LangChain callback and no
provider wrapper sees them — so the spans are the same whether the chat call
comes from `provider_sdk.md` or `langchain/model_callback.md`.

Names and constants come from `attributes.md`; the error contract from
`../../conventions/errors.md`; the content switch from `content_capture.md`.

---

## One span per stage

Embeddings, retrieval, and reranking are **separate** spans. Collapsing them
into the generation span means you cannot tell a slow vector store from a slow
model — which is the single most common thing a RAG trace is opened to answer.

The fences below are **boundary sketches**, not complete templates: the
ellipsis is the service's real provider or vector-store call, which must keep
the error contract, content gating, and response parsing of that dependency.

```python
from opentelemetry.trace import SpanKind

from observability.spans import start_span  # sets ERROR + error.type on failure

with start_span(
    f"embeddings {model}",
    kind=SpanKind.CLIENT,
    attributes={
        GENAI_OPERATION_NAME: "embeddings",
        GENAI_PROVIDER_NAME: "openai",
        GENAI_REQUEST_MODEL: model,
        "app.embedding.input_count": len(texts),
    },
) as span:
    ...
    # Through the writer, like every other usage write in this skill — an
    # embedding call reports input tokens only, and normalize_usage() treats
    # every field as optional, so no special case is needed here.
    set_usage_attributes(span, {"input_tokens": response.usage.prompt_tokens})
```

```python
with start_span(
    f"retrieval {data_source_id}",
    attributes={
        GENAI_OPERATION_NAME: "retrieval",
        "gen_ai.data_source.id": data_source_id,
        "gen_ai.request.top_k": top_k,
    },
) as span:
    ...
    span.set_attribute("app.retrieval.result_count", len(docs))
    if docs:
        span.set_attribute("app.retrieval.top_score", docs[0].score)
```

Reranking follows the retrieval shape with `gen_ai.operation.name` left at the
provider's own operation and the candidate count in
`app.retrieval.candidate_count`.

---

## What is safe by default, and what is opt-in

Retrieval query text and document contents are opt-in content, on the same
`CAPTURE_AI_CONTENT` switch as prompts (`content_capture.md`).

| Always safe | Opt-in only |
| --- | --- |
| data source ID, top-k, result count | query text |
| top score, score distribution summary | document text and snippets |
| retriever/index version, embedding model | document metadata, titles, URLs |
| latency, `error.type` | user-specific filters and permissions |

An empty-result retrieval is a real product signal — record
`app.retrieval.result_count=0` rather than skipping the span, and see
`../../metrics/genai.md` for the matching histogram.

---

## Wrap a multi-step flow

When retrieval, generation, and post-processing form one product operation,
give them a parent so the whole flow has a duration:

```
POST /ask                          SERVER
  invoke_workflow product_rag      INTERNAL
    embeddings text-embedding-3-small
    retrieval product_docs
    chat gpt-5
```

`gen_ai.operation.name=invoke_workflow` and `gen_ai.workflow.name` go on the
parent; `../../metrics/genai.md` owns `gen_ai.invoke_workflow.duration`.

On the LangChain path this parent is usually the `invoke_agent` span you
already write (`langchain/streaming_and_agent_span.md`) — add
`invoke_workflow` only when several agents or non-agent steps are coordinated.

---

## Verify

- Embedding and retrieval appear as their own spans, not attributes on the chat
  span.
- `app.retrieval.result_count` is present, including when it is `0`.
- With `CAPTURE_AI_CONTENT` unset, no query text or document text appears
  anywhere in the exported spans.
- A slow vector store shows up as a slow `retrieval` span, not as a slow model
  call.

---

## Then

- token counts: `token_usage.md`
- metrics: `../../metrics/genai.md`
- logging: the `python-logging` skill (`../../../../python-logging/references/genai.md`)
