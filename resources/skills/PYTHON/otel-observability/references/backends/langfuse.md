# Langfuse as a GenAI Destination

Read this only when Langfuse is one of the confirmed trace backends. The vendor-neutral
parts — the rooted GenAI projection, the two-branch Collector topology, and production
processor order — live in `../collector/genai_projection.md`, `../collector/component.md`,
and `../collector/production.md`. This file adds only what is specific to Langfuse: ingestion,
authentication, and the attribute mapping on the GenAI branch.

## Ingestion facts

- Langfuse ingests over **OTLP/HTTP** only. An OTLP/gRPC exporter pointed at it fails.
- Send either a complete trace or the rooted, ancestor-closed projection (contract:
  `../collector/genai_projection.md`), never only model leaves: Langfuse needs the entry root
  and each retained span's parent chain to build a readable trace.
- Langfuse is a trace and LLM-workflow backend, not a metrics backend. Operational metrics and
  alerts go to the metrics backend.
- `langfuse.*` attributes are added in the Langfuse Collector branch by a destination-specific
  `attributes` or `transform` processor, never in application code.
- If the project already uses the Langfuse SDK `CallbackHandler`, decide on one capture owner
  first (`../tracing/genai/langchain/architecture.md`, "Do not double-instrument").

## Exporter and authentication

```yaml
exporters:
  otlphttp/langfuse:
    # The otlphttp exporter appends /v1/traces for the traces pipeline.
    endpoint: ${env:LANGFUSE_OTEL_ENDPOINT}   # e.g. https://cloud.langfuse.com/api/public/otel
    headers:
      Authorization: "Basic ${env:LANGFUSE_AUTH_STRING}"
      x-langfuse-ingestion-version: "4"
    sending_queue:
      enabled: true
      queue_size: 10000
      storage: file_storage
    retry_on_failure:
      enabled: true
```

Use the correct regional or self-hosted base URL. The v4 header selects real-time ingestion;
omitting it can delay visibility. Re-check both when upgrading the contract in
`../compatibility.md`.

`LANGFUSE_AUTH_STRING` is base64 of `public_key:secret_key` — not a third credential:

```bash
LANGFUSE_AUTH_STRING="$(printf '%s' "${LANGFUSE_PUBLIC_KEY}:${LANGFUSE_SECRET_KEY}" | base64 | tr -d '\n')"
```

The trailing-newline strip matters; `base64` adds one and the header then fails authentication
with an unhelpful 401. Inject the value from a secret store.

## Destination mapping

Both processors run only on the Langfuse branch, after `filter/genai_projection` and before
`batch`. They **copy** rather than rename canonical `gen_ai.*`.

Trace-level fields that a concrete Langfuse filter or view needs:

```yaml
processors:
  transform/langfuse:
    error_mode: ignore
    trace_statements:
      - >
        set(span.attributes["langfuse.trace.name"],
            span.attributes["app.workflow.name"])
        where span.attributes["app.workflow.name"] != nil
      - >
        set(span.attributes["langfuse.release"],
            resource.attributes["service.version"])
        where resource.attributes["service.version"] != nil
      - >
        set(span.attributes["langfuse.trace.metadata.tenant_tier"],
            span.attributes["app.tenant.tier"])
        where span.attributes["app.tenant.tier"] != nil
```

Only map what a concrete Langfuse filter needs. Mirroring every application attribute into
`langfuse.trace.metadata.*` produces an unusable filter list.

## Observation input and output

When the portable `{role, parts}` envelope is valid but Langfuse needs its native display
shape, keep two representations (`../tracing/genai/content_capture.md`, "Backend rendering
is not the wire shape", owns the canonical side):

1. `gen_ai.system_instructions`, `gen_ai.input.messages`, and
   `gen_ai.output.messages` remain the portable OpenTelemetry source of truth.
2. `app.gen_ai.observation.input` / `output` carry a lossless, content-gated
   presentation. For text-only chat input, use `[{"role": ..., "content": ...}]`.
   For one valid structured-output text response, store the decoded JSON object; for
   ordinary single-text output, store the text scalar. Fall back to the canonical
   envelope for multipart, tool, multimodal, or otherwise ambiguous content.

Derive the second value only when the conversion is lossless. The `serialize_observation_*`
functions in `../../assets/genai_content.py` implement these rules.

If the pinned adapter sometimes emits an exactly empty normalized `reasoning` part next to one
text part, keep it in the canonical output fixture and assert that the backend presentation
projection omits only that empty part. A non-empty reasoning part must force canonical fallback.

The application must not emit a vendor namespace: no `langfuse.*`, `openinference.*`, or
another backend namespace in the provider callback. The Langfuse Collector branch maps the
neutral presentation attributes to `langfuse.observation.input` /
`langfuse.observation.output`, then deletes the neutral copies. Every other trace branch
deletes these payload attributes with the other GenAI content keys. This preserves
portability, prevents duplicate metadata, and keeps the capture switch and backend retention
policy authoritative. Never deform `gen_ai.*` to satisfy one UI.

Map and consume them here:

```yaml
processors:
  attributes/langfuse_observation_io:
    actions:
      - key: langfuse.observation.input
        from_attribute: app.gen_ai.observation.input
        action: upsert
      - key: langfuse.observation.output
        from_attribute: app.gen_ai.observation.output
        action: upsert
      - key: app.gen_ai.observation.input
        action: delete
      - key: app.gen_ai.observation.output
        action: delete
```

The branch retains canonical `gen_ai.*` for protocol fidelity and deletes the neutral sources
after projection so they do not also appear as metadata. General trace branches delete both
representations. Do not rename or flatten `gen_ai.input.messages` / `gen_ai.output.messages`.

An expandable JSON object in the Langfuse UI is presentation, not proof of the wire shape;
inspect the raw exported attributes before changing a serializer
(`../tracing/genai/content_capture.md`, "Backend rendering is not the wire shape").

## Wiring into the GenAI branch

In the `traces/genai` pipeline from `../collector/production.md`, rename it
`traces/langfuse`, put `transform/langfuse` and `attributes/langfuse_observation_io` after
`filter/genai_projection`, and export to `otlphttp/langfuse`.

## Verify

- [ ] The exporter uses OTLP/HTTP and sends `x-langfuse-ingestion-version: "4"`.
- [ ] Langfuse shows the same trace ID as the main backend, with one root and every retained
      parent present.
- [ ] The stored observation uses `langfuse.observation.input` / `output`; the neutral
      `app.gen_ai.observation.*` keys are absent from metadata. Expand or query the stored output
      and check the actual content — a collapsed object may show only an item count.
- [ ] Send a text-only and a native structured-output canary and inspect the stored observation,
      not only the raw span attributes.
- [ ] A text-only input has a role/content observation projection while the canonical input
      still has role/parts. One valid JSON text output projects to the decoded object. An
      exactly empty reasoning part may be omitted from that presentation projection only; an
      ambiguous or meaningful multipart response falls back byte-for-byte to the canonical
      envelope.
- [ ] The Langfuse Collector path maps the neutral observation projection and removes its
      source attributes; general trace backends receive neither copy.
