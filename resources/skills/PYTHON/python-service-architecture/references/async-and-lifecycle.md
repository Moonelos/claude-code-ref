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
retries={"max_attempts": ...})`. An outer `asyncio.timeout` around `to_thread`
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

The composition root uses one lifecycle idiom:

```python
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

import httpx

from my_service.adapters.ticket_api import HttpTicketApi
from my_service.application.sync_tickets import SyncTickets
from my_service.config.secrets import Secrets
from my_service.config.settings import Settings


@dataclass(frozen=True, kw_only=True)
class Runtime:
    sync_tickets: SyncTickets


@asynccontextmanager
async def runtime(settings: Settings, secrets: Secrets) -> AsyncIterator[Runtime]:
    async with AsyncExitStack() as stack:
        http = await stack.enter_async_context(
            httpx.AsyncClient(timeout=settings.ticket_api_timeout_seconds)
        )
        tickets = HttpTicketApi(client=http, token=secrets.ticket_api_token)
        yield Runtime(sync_tickets=SyncTickets(tickets=tickets))
```

`build_*` functions only construct; `run()` only orchestrates and maps outcomes
to exit codes. Register each process-wide teardown exactly once. A resource kept
only for disposal lives in the exit stack, not in `Runtime`. Never reach into a
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
  found in the results.
- Use `asyncio.shield` only with a why-comment, when cancellation could orphan a
  half-built resource.

## Health probes

Health and readiness probes have a timeout and log the failure reason on state
transitions, not on every probe. They never perform business work; readiness
calls a port method rather than running SQL in bootstrap.
