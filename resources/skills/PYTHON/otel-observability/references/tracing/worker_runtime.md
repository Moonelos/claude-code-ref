# Worker Process Runtime

Read this file only for a long-running worker loop or when work crosses a
thread, executor, or independently scheduled in-process task. Queue carrier
semantics and durable DB handoffs live in their own references.

## Long-running worker loops

The process loop is lifecycle, not a trace boundary. Never keep one span current
around `while not stopping`: it creates an unbounded trace, gives child work the
wrong parent, and exports nothing until shutdown. Each independently owned
message, job, batch, or retry attempt gets its own bounded root/consumer span
and custom child spans for its meaningful business phases.

Parent-or-link is decided by `async_handoffs.md`. A poll/receive, database
claim, or previous loop iteration is never the parent merely because its context
happens to be current. Keep a stable workflow/job ID on spans and important logs
for cross-trace search, never as a metric label.

On the work boundary record bounded job/message type, attempt, outcome, and
queue or workflow identity. Child business spans record the decision, strategy,
result count/category, dependency, and `error.type` actually needed to explain
the phase; do not copy payloads or every available value.

Start the root span only after the claim or receive returns work; count empty
polls with a counter instead of tracing them, and never filter empty-poll spans
at the exporter.

Loop structure, stop signalling, and drain are owned by the
`python-service-architecture` skill
(`../../../python-service-architecture/references/api-and-workers.md`, Long-running
worker). The telemetry parts: configure providers once at startup, one bounded
span per unit of work, and shut telemetry down last, after the in-flight unit
finishes:

```python
import asyncio
import signal

from opentelemetry.trace import SpanKind


async def run_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        message = await receive_message()
        if message is None:
            empty_polls.add(1)
            continue
        with start_span("process pricing-jobs", kind=SpanKind.CONSUMER, links=links_for(message)):
            await handle_message(message)


async def main() -> None:
    settings = load_settings()
    configure_observability(telemetry_config(settings))
    configure_logging(logging_config(settings), correlation=[add_otel_trace_context])
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await run_worker(stop)
    finally:
        shutdown_observability()
```

## Context loss inside the worker

Context flows through normal calls and is copied by modern
`asyncio.create_task()` and `asyncio.to_thread()`. It is **not** copied by a raw
thread, `ThreadPoolExecutor.submit()`, or `loop.run_in_executor()`. Capture and
attach it only at those non-propagating boundaries; attaching a context that
already flows can create confusing ownership and detach errors. The symptom of
a real loss is a span that should be a child suddenly becoming a root.

```python
from concurrent.futures import Executor

from opentelemetry import context
from opentelemetry.context import Context


def submit_background_work(executor: Executor, payload: Payload) -> None:
    current_ctx = context.get_current()
    executor.submit(_run_with_context, current_ctx, payload)


def _run_with_context(parent_ctx: Context, payload: Payload) -> None:
    token = context.attach(parent_ctx)
    try:
        with start_span("process payload"):
            process(payload)
    finally:
        context.detach(token)
```

Verify that child spans keep the boundary span's trace ID, that shutdown waits
for the in-flight unit of work, and that providers are configured exactly once
per process.

## Then

- the unit-of-work transport: `queue_messaging.md` or `durable_work.md`
- metrics: `../metrics/service.md` — queue depth, oldest-message age, job duration
- logs: the `python-logging` skill, with `../logging/correlation.md`
- final checks: `../verification.md`
