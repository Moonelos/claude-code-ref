# Async I/O and resource lifecycle

Read this for any service with async I/O. Bootstrap placement rules are in
[boundaries.md](boundaries.md#bootstrap); loop and supervisor shape is in
[api-and-workers.md](api-and-workers.md#long-running-worker).

## Blocking I/O

- Ports for remote I/O are `async`. An adapter wrapping a sync SDK (boto3,
  openpyxl, file I/O) calls each blocking operation through
  `await asyncio.to_thread(self._sync_method, ...)`, or uses an async client.
- Do not offload cheap pure computation or tiny `Path` calls.
- A one-shot CLI may block before `asyncio.run`.
- Bulk downloads use bounded concurrency (an `asyncio.Semaphore`).

## SDK clients

SDK clients are built once (adapter constructor or bootstrap), injected, and
closed by their owner's lifecycle. Adapters never create or close an injected
`httpx` or Redis client. boto3 low-level clients are thread-safe; the default
session is not, so never call `boto3.client()` inside a `to_thread` function.

## Timeouts and retries

Every SDK client gets explicit connect/read timeouts and a retry setting, for
example `botocore.config.Config(connect_timeout=..., read_timeout=...,
retries={"mode": "standard", "total_max_attempts": ...})`. Check what the SDK
counts: botocore's `max_attempts` counts retries, `total_max_attempts` counts
calls, so one attempt is `total_max_attempts=1`. An outer `asyncio.timeout` around `to_thread`
cancels the await, not the thread; the SDK timeout is what bounds the thread.

## Deadlines

A request or job deadline bounds every phase: pool acquisition,
`statement_timeout = min(configured, remaining)`, and provider calls
(`asyncio.timeout_at(deadline)`). Keep one `remaining(deadline)` helper per
member.

## Retry ownership

Exactly one layer retries each physical call.

- Under middleware or application retry, set SDK retries to zero with a comment.
- Delete an inner retry loop that bootstrap always configures to one attempt.
- The retry policy object owns its `retry_on` set.
- Library retry loops take injectable `sleep` and `clock`, expose attempts
  through a callback or result, and honour `Retry-After`.

## Resource acquisition

Acquire several resources with `AsyncExitStack`, or open each inside the `try`
that closes it. Factories return async context managers, not `launch()`/`close()`
pairs; never drive `__enter__`/`__exit__` by hand. Every acquired client, session,
browser, workbook, or streaming response body has an owner and is closed on
success and failure.

The composition root uses one lifecycle idiom: an `@asynccontextmanager
runtime(settings, secrets)` owning one `AsyncExitStack` and yielding a frozen
`Runtime` of implementations and policies. The canonical service's
[`bootstrap/runtime.py`](../assets/canonical_service/src/my_service/bootstrap/runtime.py)
is the executable version; it registers the engine's disposal with
`stack.push_async_callback(engine.dispose)`. A client that is itself an async
context manager is entered on the stack, then injected:

```python
http = await stack.enter_async_context(
    httpx.AsyncClient(timeout=settings.ticket_api_timeout_seconds)
)
tickets = HttpTicketApi(client=http, token=secrets.ticket_api_token)
```

What the runtime may hold, and how entry points use it, is in
[boundaries.md](boundaries.md#bootstrap).

`build_*` functions only construct; `run()` only orchestrates and maps outcomes
to exit codes. Register each process-wide teardown exactly once. Never reach into a
collaborator's `_private` fields to close it; it exposes `aclose()`.

When closing several independent resources, use
`gather(..., return_exceptions=True)` and report every failure.

## Cancellation-safe cleanup

Cleanup must survive cancellation: use `try/finally`, a context manager, or
`except BaseException: cleanup(); raise`. Never use `except Exception` for
resource cleanup; `CancelledError` bypasses it.

## Structured concurrency

- Sibling tasks started by one operation live in one lexical scope. Use
  `asyncio.TaskGroup` for fail-together fan-out.
- A first-completed race uses `create_task` plus `asyncio.wait` with a `finally`
  that cancels and awaits every remaining task while preserving the original
  failure. Keep one service-owned `gather_or_cancel` helper instead of
  re-implementing cancel-then-gather.
- Store or await every `create_task` result. Background tasks go in a set with a
  done-callback that logs failures.
- A supervisor that signals a stop event and waits for a graceful exit is **not**
  a `TaskGroup`; a `TaskGroup` cancels siblings immediately on the first failure.

## Cancellation-safe idioms

- In an async generator, wrap only the `await` in a timeout, never the `yield`.
- After `gather(..., return_exceptions=True)`, re-raise any `CancelledError`
  found in the results, except for tasks you cancelled yourself (a supervisor
  cancelling loops after the grace period expects them).
- Use `asyncio.shield` only with a why-comment, when cancellation could orphan a
  half-built resource.

## Health probes

Health and readiness probes have a timeout and log the failure reason on state
transitions, not on every probe. Readiness calls a port method rather than
running SQL in bootstrap. What a probe may read, and why it calls no action, is
in [api-and-workers.md](api-and-workers.md#health-and-readiness).
