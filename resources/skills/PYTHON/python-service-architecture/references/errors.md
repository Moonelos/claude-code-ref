# Error design

This file owns how failures are raised, translated, classified, handled, and
exposed. Where error *modules* live is in
[boundaries.md](boundaries.md#errors-and-constants-follow-ownership). How much
exception detail is logged is owned by `python-logging`
(fallback: `../../python-logging/references/errors-and-security.md`,
"Exception detail"). Language-level error idioms are in `python-code-conventions`
(fallback: `../../python-code-conventions/SKILL.md`, "Error and async idioms").

## Broad except shapes

A broad `except Exception` (or `BaseException`) has exactly one of these shapes:

1. **Mark and re-raise** (add a note, set a span status, then `raise`).
2. **Clean up and re-raise.** Prefer `finally` or a context manager; bound
   cleanup that can hang. See
   [async-and-lifecycle.md](async-and-lifecycle.md#cancellation-safe-cleanup).
3. **Translate** to a port-owned error `from exc` at an adapter boundary.
4. **Process boundary** (request handler, message handler, worker loop): log once
   and apply a declared outcome.
5. **Recorded fallback:** a warning with `exc_info` and `error.type`, or a
   handled-failure recorder, plus a metric when a capability degrades.
6. **Best-effort shutdown or flush step** that logs at warning.

An `except` that does not re-raise catches specific types or records the
failure. `except ...: pass` carries a why-comment. Never silently return `()`,
`None`, or `False`. Lower layers raise with context; they do not log and
re-raise, because the handling boundary logs once.

## Never mislabel unknown failures

Never label an unknown exception as a specific cause (`database_unavailable`,
"dependency outage"); programming errors then look like outages. Deliberate
degradation catches a narrow, **owned** failure type and makes the fallback
explicit in the result with a reason code. A broad built-in such as
`ValueError` is never the degradation signal, and built-in `ValueError`,
`LookupError`, or `RuntimeError` never represents an expected business outcome
or an integrity fault.

## Translate once

- Code that already raised a port error re-raises it unchanged: put
  `except PortError: raise` before the broad arm.
- Do not raise a port error inside a `try` whose broad `except` translates, and
  do not raise a generic exception inside a `try` whose `except` catches only a
  narrower type.
- Each port owns distinct error classes. Aliasing another port's errors
  corrupts `error.type` and handling.
- GenAI uses two steps: framework error -> GenAI-private error -> port error
  (see [ai.md](ai.md#invocation-and-error-translation)).

## Classification bases

When retry or terminal policy depends on transient versus permanent failure,
define one small pair of bases where that policy lives, usually `domain/errors.py`
or `application/errors.py`. Port errors subclass them; application code catches
the bases, not tuples of every port error.

```python
from datetime import timedelta


class DependencyUnavailableError(Exception):
    """Transient: the same request may succeed later."""

    def __init__(self, *, error_code: str, retry_after: timedelta | None = None) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.retry_after = retry_after


class DependencyRejectedError(Exception):
    """Permanent: repeating the same request will fail the same way."""

    def __init__(self, *, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code
```

A port error subclasses its port base and one classification base; see the
example in [boundaries.md](boundaries.md#contract-ownership). Every attribute read from an exception is declared on its base; never
`getattr(exc, "error_code", default)`. This pair is a policy vocabulary, not a
universal adapter hierarchy: adapters still own private errors and translate.

## Public error mapping

Map exceptions to public errors in one exhaustive table in `api/`, keyed by
exception type (resolved along the MRO) or by a closed `StrEnum`. A test asserts
every member or registered type is mapped.

- Business exceptions state what happened. They do not carry `public_message`,
  `status_code`, or `retryable`.
- No `getattr(exc, "code")` resolution, no synthetic exceptions raised only to
  reach the mapper, no path branching in global handlers; one helper builds the
  response envelope.
- Routers do not `try`/`except` merely to re-raise.
- A code persisted in durable state is a `StrEnum` in `domain/`.
- Use a closed allowlist and `application/problem+json`; never copy exception
  text into the response; log only status >= 500 at the handler; send
  `Cache-Control: no-store` and `Retry-After` when retry metadata exists.

## Handling boundaries

Every failure a port can raise has a named handling boundary: an API
`exception_handler`, or a loop boundary that logs once and backs off (or exits
with a documented reason). An unhandled port failure becomes a 500 or kills a
supervisor. Loop failure policies are in
[api-and-workers.md](api-and-workers.md#long-running-worker).

## Uncertain external writes

For an external write that is not provably safe to replay, distinguish confirmed
success, confirmed rejection, and **unknown**. A timeout or connection loss after
dispatch is unknown. Persist enough identity to reconcile against an
authoritative read or idempotency key before writing again, and test that the
uncertain path never blindly replays. Ordinary retries are fine when the
provider verifies an idempotency key.
