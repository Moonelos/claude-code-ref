# GenAI Projection: One Trace, Two Destination Views

Read this when the same bounded application operation goes to both a main trace backend and a
specialized GenAI backend such as Langfuse. `component.md` owns the Collector topology;
`production.md` owns production processor order, redaction, sampling, and exporter configuration.

## The destination contract

An HTTP request, finite job, or one worker-message attempt gets one application root, one
`TracerProvider`, and ordinary parentage. The Collector owns the destination split:

```text
application — one OTLP trace
    │
    └── Collector
        ├── main trace backend
        │   └── complete span tree, verbose GenAI payloads removed
        └── GenAI backend (e.g. Langfuse)
            └── same trace ID, rooted ancestor-closed GenAI projection,
                approved captured GenAI context retained
```

The main backend explains the operation from entry to completion, including database, HTTP,
persistence, and other operational spans. Its branch deletes prompts, model outputs, embedding
inputs, tool definitions, tool arguments/results, and neutral presentation copies; it retains
model/provider identity, usage, latency, status, and bounded metadata. The GenAI branch keeps
approved content only when application capture policy allowed it and filters operational-only
subtrees. Universal secret redaction runs on both branches before export.

Fan-out and filtering MUST NOT rewrite trace IDs, span IDs, parent IDs, timestamps, or status.
Logs keep their actual current `trace_id` and `span_id`: the trace ID finds the same operation in
both backends, while a log from a span omitted by the GenAI projection naturally has no
observation-level counterpart there.

## The projection must be ancestor-closed

Mark every span retained in the GenAI view with the bounded, application-owned span attribute
`app.telemetry.category="genai"`. This is projection membership, not GenAI operation semantics:
the root and a business ancestor keep their real names and MUST NOT receive a fabricated
`gen_ai.operation.name` merely to survive filtering.

The retained set is:

1. the request/job/message root;
2. `invoke_workflow`, `invoke_agent`, `chat`, `embeddings`, `retrieval`, and
   `execute_tool` spans; and
3. every meaningful business span on the parent chain between that root and those GenAI spans.

The invariant is strict: if span `S` is retained, every parent from `S` to the root is retained.
The Collector filters span by span and cannot discover missing ancestors after the fact, so the
application or a service-aware enrichment rule must classify the connected set explicitly.
Dropping an unmarked leaf or complete operational subtree is safe. Keeping a marked child below
an unmarked parent creates an orphan and is a contract failure.

```text
run ingestion                                      keep: entry root
├── load documents                                 drop: operational subtree
├── index document                                 keep: meaningful business ancestor
│   ├── invoke_workflow indexing_embeddings        keep: GenAI workflow
│   │   ├── embeddings titan  chunk=0              keep: model call
│   │   └── embeddings titan  chunk=1              keep: model call
│   └── persist chunks                             drop: operational sibling
└── cleanup                                        drop: operational subtree
```

The GenAI backend receives `run ingestion → index document → invoke_workflow → embeddings` with
the same IDs those spans have in the complete trace. If the application has no meaningful
`index document` boundary, do not invent an empty wrapper for the UI: parent
`invoke_workflow indexing_embeddings` directly under the root and use that shorter path.
Conversely, retain a real business span that encloses the GenAI work; without it, the GenAI view
loses why the model was called.

## Collector projection

For an explicit marker, the pinned Collector's filter processor drops every unselected span:

```yaml
processors:
  filter/genai_projection:
    error_mode: ignore
    trace_conditions:
      # Conditions mean DROP. Nil or another category is operational-only.
      - 'span.attributes["app.telemetry.category"] != "genai"'
```

Run this processor only on the GenAI branch. The main trace branch remains unfiltered. In
production, make the retention decision from the complete trace before projection; otherwise an
operational error removed from the GenAI branch can change the sampling decision.
`production.md` shows the exact order.

A separate OTLP receiver may select which services or routes are eligible for GenAI fan-out,
but it is a transport boundary, not permission to create a second provider or root. Filtering on
`gen_ai.request.model` alone is invalid because it retains model leaves and discards the root,
workflows, agents, tools, and business ancestors.

## Bounded traces and durable work

This policy applies within one bounded execution lifetime. Delayed or independently retried
queue work, durable database transitions, and fan-out/fan-in may correctly start a new trace with
a `Link` as defined in `../tracing/async_handoffs.md`; each resulting bounded trace then applies
the destination-view policy independently. Across a synchronously continued multi-service
trace, every service that owns a retained parent-chain span must apply the same classification
contract, or the GenAI destination must receive the complete trace.

## Acceptance invariants

For one mixed business/GenAI/operational canary trace, verify:

- the main backend contains the complete retained operational tree and no verbose GenAI payload
  values, neutral `app.gen_ai.observation.*` presentation copies, or vendor payload copies;
- the GenAI backend resolves the same trace ID and contains one retained root;
- every retained span has its complete parent chain to that root;
- retained span IDs, parent IDs, timestamps, and status match the main backend;
- GenAI workflow/agent/model/embedding/retrieval/tool spans and meaningful business ancestors
  are present, while unrelated DB, HTTP-client, and persistence siblings are absent; and
- structural ancestors carry the projection marker but no fabricated GenAI semantic operation.

Application unit tests should prove classification (`../testing.md`); an exported-telemetry test
through the pinned Collector must prove destination behavior against the list above, in every
environment that configures a GenAI backend.
