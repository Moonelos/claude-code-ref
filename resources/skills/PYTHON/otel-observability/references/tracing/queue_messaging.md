# Queue Messaging

Read `async_handoffs.md` with this file. This reference owns broker producer
and consumer boundaries, carrier adapters, batch semantics, and automatic
instrumentation ownership. It does not cover DB-backed work or scheduled jobs.

## Contents

- [Producer side](#producer-side)
- [SQS carrier adapter](#sqs-carrier-adapter)
- [Consumer: continued trace](#queue-consumer-side--continued-trace)
- [Consumer: new trace with a link](#queue-consumer-side--new-trace-with-a-link)
- [Batch consumers](#batch-consumers)
- [Automatic instrumentation](#automatic-queue-instrumentation-may-already-own-this)
- [Other brokers](#other-brokers)
- [Attributes and next signals](#attributes-and-next-signals)

## Producer side

The producer span must be **current** when the carrier is injected. Injecting from an outer request span skips the queue boundary and produces a trace where the consumer appears to hang off the HTTP handler.

```python
from opentelemetry.propagate import inject
from opentelemetry.trace import SpanKind

from observability.spans import start_span


def publish_pricing_job(queue: PricingQueue, payload: PricingJob) -> None:
    with start_span(
        "send pricing-jobs",
        kind=SpanKind.PRODUCER,
        attributes={
            "messaging.system": "aws_sqs",
            "messaging.destination.name": "pricing-jobs",
            "messaging.operation.name": "send",
            "messaging.operation.type": "send",
        },
    ):
        carrier: dict[str, str] = {}
        # inject() only fills the carrier; queue.publish() performs the transport.
        inject(carrier)
        queue.publish(payload, headers=carrier)
```

### SQS carrier adapter

SQS does not carry a flat string map. Propagated fields live inside nested `MessageAttributes`, so the getter/setter adapters are required even when automatic instrumentation is disabled:

```python
from opentelemetry import propagate
from opentelemetry.instrumentation.boto3sqs import Boto3SQSGetter, Boto3SQSSetter

outgoing: dict = {}
propagate.inject(outgoing, setter=Boto3SQSSetter())
sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=body,
    MessageAttributes=outgoing,
)
```

Importing the adapters does not enable automatic spans; they only translate the carrier representation.

**But the package must be installed**, and `../setup/auto_instrumentation.md` lists
`boto3sqs` under "leave off". Both are correct; the resolution is explicit:

| Setup | What to do |
| --- | --- |
| Code-based | Install `opentelemetry-instrumentation-boto3sqs` for the adapters. Never call `Boto3SQSInstrumentor().instrument()`; without that call the package patches nothing. |
| Zero-code | Install it **and** disable the entry point: `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=boto3`. `opentelemetry-instrument` activates every installed package, so an un-disabled install silently produces the double consumer span described below. |
| Neither is acceptable | Inline the two adapters. SQS message attributes are `{name: {"DataType": "String", "StringValue": value}}` — an eight-line getter/setter pair with no instrumentation dependency at all. |

**On the receive side, SQS returns attributes only if you ask for them — and
there are two different kinds:**

```python
response = sqs.receive_message(
    QueueUrl=queue_url,
    MaxNumberOfMessages=10,
    # W3C traceparent/tracestate written by a producer: USER attributes.
    MessageAttributeNames=list(propagate.get_global_textmap().fields),
    # X-Ray context written by AWS itself: a SYSTEM attribute. Requesting it
    # under MessageAttributeNames returns nothing.
    MessageSystemAttributeNames=["AWSTraceHeader"],
)
```

| Carrier | Requested with | Written by |
| --- | --- | --- |
| `traceparent`, `tracestate`, `baggage` | `MessageAttributeNames` | your instrumented producer |
| `AWSTraceHeader` | `MessageSystemAttributeNames` (legacy: `AttributeNames`) | AWS, for X-Ray-propagated flows including Lambda event sources |

Omit the matching one and the propagated fields silently never arrive. The
consumer produces orphan traces with no error — the single most common cause of
"propagation looks configured but doesn't work." A direct (non-Lambda) consumer
of an X-Ray-carried trace hits this even with `MessageAttributeNames` set
correctly, because it is asking for the wrong kind of attribute. The Lambda side
of `AWSTraceHeader` is in `lambda_functions.md`.

Two SQS limits bite here: a message carries at most **10** user message
attributes, and attributes count toward the **1 MiB** maximum message size
(raised from 256 KiB in August 2025). A W3C carrier is 2–3 of those 10.

## Queue consumer side — continued trace

```python
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind

from observability.spans import start_span


def handle_message(message: QueueMessage) -> None:
    parent_ctx = extract(message.headers)

    with start_span(
        "process pricing-jobs",
        context=parent_ctx,
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": "aws_sqs",
            "messaging.destination.name": "pricing-jobs",
            "messaging.operation.name": "process",
            "messaging.operation.type": "process",
        },
    ):
        process(message.payload)
```

## Queue consumer side — new trace with a link

```python
from opentelemetry import context as otel_context, trace
from opentelemetry.propagate import extract
from opentelemetry.trace import Link, SpanKind

from observability.spans import start_span


def handle_message(message: QueueMessage) -> None:
    incoming_ctx = extract(message.headers)
    producer_ctx = trace.get_current_span(incoming_ctx).get_span_context()
    links = [Link(producer_ctx)] if producer_ctx.is_valid else []

    with start_span(
        "process pricing-jobs",
        # Explicit empty Context = new root; None reuses the current context
        # (async_handoffs.md, "Carrier contract").
        context=otel_context.Context(),
        kind=SpanKind.CONSUMER,
        links=links,
        attributes={
            "messaging.system": "aws_sqs",
            "messaging.destination.name": "pricing-jobs",
            "messaging.operation.name": "process",
            "messaging.operation.type": "process",
            "app.message.attempt": message.receive_count,
        },
    ):
        process(message.payload)
```

`context=None` is the most common linked-consumer bug; the rule is in `async_handoffs.md`, "Carrier contract".

### How to know it worked

Look at an exported consumer span, not at whether `links` is non-empty:

```
process pricing-jobs
  trace_id       != the producer's trace_id
  parent_span_id  empty
  links           one entry, with the producer's valid SpanContext
```

If it shares the producer's trace ID, the extracted or current context became its parent. If a second consumer span also appears, automatic instrumentation is still active and owns the same boundary — see below.

## Batch consumers

One span for the batch, linked to every message it contains:

```python
links = []
for message in messages:
    ctx = extract(message.headers)
    sc = trace.get_current_span(ctx).get_span_context()
    if sc.is_valid:
        links.append(Link(sc))

with start_span(
    "process pricing-jobs",
    context=otel_context.Context(),
    kind=SpanKind.CONSUMER,
    links=links,
    attributes={
        "messaging.system": "aws_sqs",
        "messaging.destination.name": "pricing-jobs",
        "messaging.operation.name": "process",
        "messaging.operation.type": "process",
        "messaging.batch.message_count": len(messages),
    },
) as span:
    process_all(messages)
```

If individual messages can fail independently, add one child span per message so a single failure does not mark the whole batch as an error.

## Automatic queue instrumentation may already own this

`opentelemetry-instrumentation-boto3sqs` creates a `CONSUMER` receive span and a per-message process span that links to the producer. That is already a new trace with a causal link — close to the linked pattern above, but with an extra receive parent.

On the pinned `0.65b0` line, propagation is current but the instrumentor's
telemetry schema is not: it declares schema URL `1.11.0`, uses legacy
destination/operation attributes and `messaging.system="aws.sqs"`, and names
spans destination-first. Do not describe that output as semantic-convention
1.44 telemetry. If current messaging names and attributes are a requirement,
disable the instrumentor and use the manual templates above (or perform an
explicit, tested migration at the Collector).

Choose one owner:

| If | Then |
| --- | --- |
| Its extra receive span **and legacy 1.11 telemetry schema** are acceptable | Use it. Add only business child spans. Do not write a consumer span. |
| You need different parent/link semantics | Disable that instrumentor in the worker process and own the boundary manually |
| You require the pinned 1.44 messaging schema | Disable it and own the boundary manually with the templates above |

```bash
OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=boto3 opentelemetry-instrument python worker.py
```

That disables the whole entry point, producer side included, so the worker must then inject manually if it also publishes. Keep unrelated instrumentation (HTTP, database) enabled. Re-verify the exported shape after every instrumentation upgrade; queue semantics are version-specific.

## Other brokers

The producer/consumer shapes above are transport-independent; only the carrier
adapter and the ownership question change. `../discovery.md` names these as
detection signals, so here is what each one needs:

| Transport | Carrier | Ownership note |
| --- | --- | --- |
| Kafka (`confluent_kafka`, `aiokafka`) | Record headers: `list[tuple[str, bytes]]`. Needs a getter/setter that decodes/encodes UTF-8, because W3C values are strings and headers are bytes. | Kafka instrumentation, where installed, owns produce and consume spans. Pick one. |
| Celery | Celery's own message headers | **`opentelemetry-instrumentation-celery` already owns both the publish and task-execution spans.** On `0.65b0`, its default `use_span_links=False` continues the producer context as parent; code-based `.instrument(use_span_links=True)` starts the task span without that parent and adds a link instead. Zero-code activation cannot pass that Python argument. Both modes still declare the legacy `1.11.0` messaging schema. Do not add another boundary; choose the relationship explicitly and add only business child spans inside the task. |
| RabbitMQ / AMQP via `kombu` or `pika` | AMQP `headers` property — already a string map, so `inject(headers)` / `extract(headers)` work directly | No first-party instrumentation for raw `pika`; you own the boundary. |
| Redis Streams | No header space. Put the carrier in a named field of the entry, e.g. `otel_traceparent`, and document the field name as a contract. | `redis` instrumentation traces the `XADD`/`XREADGROUP` commands, not the work. Those are transport spans, never the parent of processing. |
| Google Cloud Pub/Sub | Message `attributes`, a string map | Check whether the client library already injects; some versions do. |

Whatever the transport: the carrier is untrusted input, the parent-or-link
decision is unchanged (`async_handoffs.md`), and a command-level span from a
client instrumentation is never the causal parent of the work.

## Attributes and next signals

| Attribute | Why |
| --- | --- |
| `messaging.system`, `messaging.destination.name`, `messaging.operation.name`, `messaging.operation.type` | Standard. `messaging.operation.name` is required and determines the span-name prefix; `messaging.operation.type` is the bounded category (`send`, `process`, and so on). |
| `app.message.attempt` / receive count | Distinguishes a first attempt from a fifth |
| `app.outcome` | bounded, from the closed set in [`../conventions/naming.md`](../conventions/naming.md#the-app-shape) |
| Domain identifiers (`order_id`, `supplier_id`) | Only when they are worth finding one trace by; keep them off metrics |

- metrics: `../metrics/service.md` — queue depth, oldest-message age,
  processing duration, retry and dead-letter counts;
- logs: the `python-logging` skill — `job_failed` from the owner plus one terminal business
  event per message; trace IDs: `../logging/correlation.md`;
- if the worker calls a model: `genai/attributes.md` for the span vocabulary,
  then the direct-SDK or LangChain path beneath it.
