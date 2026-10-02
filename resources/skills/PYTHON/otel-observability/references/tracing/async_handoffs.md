# Asynchronous Trace Handoffs

Read this file when work crosses a queue or durable database boundary. It owns
the parent-versus-link decision and the carrier invariants shared by broker
messages and persisted work. It does not contain transport adapters or worker
lifecycle code.

## Decide parent-or-link first

| Shape | Work span's parent | Use when |
| --- | --- | --- |
| **Continued trace** | the extracted producer/transition context | The work is causally part of the producer's request, runs promptly, and the resulting trace is still readable |
| **New trace + link** | empty context; producer context becomes a `Link` | Work is delayed, batched, independently retried, fanned in or out, or owned by a different lifecycle |

Default to **new trace + link** for anything retried or delayed. A message that
sits in a queue for ten minutes does not extend the already-ended producer root
span, but it stretches the trace's temporal envelope and may arrive after a
backend or tail sampler has finalized that trace. Independent retries make the
topology harder to interpret and can be split or dropped as late spans. A new
trace per attempt plus a causal link keeps each execution lifetime honest.

Whichever you choose, say so explicitly in your report — this is a policy
decision, not an implementation detail.

## Carrier contract

- Propagate a complete allowlisted W3C carrier: `traceparent` plus optional
  `tracestate`. A bare trace ID cannot reconstruct a remote `SpanContext`.
- Inject while the span that makes the work available is current. Persist or
  publish the carrier atomically with the work when the transport is durable.
- Extract from an explicit empty base context when ambient poll-loop, request,
  or database spans might be current.
- To create a new root with a link, pass `context=otel_context.Context()` at
  span creation. `context=None` means "use the current context"; it does not
  mean "create a root." This is the single most common bug in linked-consumer
  code, and it is invisible until you inspect an exported trace.
- Treat an incoming or persisted carrier as untrusted metadata. Ignore invalid
  values and start an unlinked root rather than failing the business work.
- Do not propagate baggage unless the user explicitly requested an allowlisted
  cross-service value and the baggage reference was loaded.

Verify parent/link policy from exported spans. An in-memory `links` list does
not prove that an ambient context did not become the parent.

## Then

- broker transports and carrier adapters: `queue_messaging.md`
- database-backed handoffs: `durable_work.md`
- asserting the exported shape in tests: `../testing.md`
- final checks: `../verification.md` §4
