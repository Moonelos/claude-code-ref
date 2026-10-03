# Error design

This file owns how failures are raised, translated, classified, and handled.
How they are exposed over HTTP is in
[api-and-workers.md](api-and-workers.md#public-error-mapping). Where error *modules* live is in
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
   handled-failure recorder, plus a metric when a capability degrades and the
   service already has a metrics pipeline (the warning alone is enough until it
   does; do not add one only for this).
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
  corrupts `error.type` and handling. Ports implemented over the same database
  may share one deliberate family, declared once in `ports/` and named for the
  store, not for any one of the ports.
- Translate in one step, SDK or framework error -> port error. Add an
  intermediate private error only when the implementation itself catches and
  handles it before translating (see
  [ai.md](ai.md#invocation-and-error-translation)).

## Classification bases

When retry or terminal policy depends on transient versus permanent failure,
define one small pair of bases in `ports/errors.py`. They describe how an
external capability failed, which is part of the port contract, not a business
rule, so they do not belong in `domain/`; and `ports/` may not import
`application/`, so they never live in `application/errors.py`. Port errors
subclass them, and application code catches the bases, not tuples of every
port error.

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

Classify by *what* is wrong, not by the status code. Rejected means this
request is wrong (bad input, a business refusal for this item). A failure every
request would hit — expired or wrong credentials, a missing endpoint, a
misconfigured base URL, a quota exhausted for the account — is **unavailable**:
items wait and retry once an operator fixes it, and alerting on the outage
catches it. Classifying a 401 as rejected turns a rotated token into every item
failing permanently.
The same holds for any 4xx that does not specifically refuse this item's
business data (a wrong route, method, or request schema): it is unavailable,
not rejected. For a database port, classify connection loss, failover, and
statement timeouts or cancellation as unavailable and data or constraint errors
as integrity, inspecting the wrapped driver error where the dialect uses one
broad wrapper (SQLAlchemy's `DBAPIError`).

**Integrity** is not a third base. A port adds an integrity error for a fault in
data it owns: a constraint it did not expect to hit, or a stored row that no
longer decodes ([boundaries.md](boundaries.md#validate-external-structure)). It
subclasses the rejected base, because repeating the request fails the same way,
and it is named for its port (`SubmissionStoreIntegrityError`). It is almost
always our own defect, so it surfaces as a server error, never as the client's.

The bases describe a failing dependency only. An expected business outcome of
a port call (not found, a stale revision, already processed) is a named result
or a domain error, never a subclass of either base; otherwise a retry policy
would retry a conflict.

A port error subclasses one classification base directly; a per-port family
base is added only when a caller catches the whole family (example and rule in
[boundaries.md](boundaries.md#contract-ownership)). Every attribute read from an exception is declared on its base; never
`getattr(exc, "error_code", default)`. This pair is a policy vocabulary, not a
universal adapter hierarchy: adapters still own private errors and translate.

## Handling boundaries

Every failure a port can raise has a named handling boundary: an API
`exception_handler`, or a loop boundary that logs once and backs off (or exits
with a documented reason). An unhandled port failure becomes a 500 or kills a
supervisor. Loop failure policies are in
[api-and-workers.md](api-and-workers.md#long-running-worker).

An action that processes a batch decides per item. A failure owned by one item
(a row that no longer decodes, a provider rejection for that input) is recorded
in that item's result and the batch continues; otherwise one bad record stops
the loop on every restart. A dependency outage (the unavailable base) stops the
batch and reaches the loop boundary, unless the business declares an outcome for
it, such as "retry this order later"
([api-and-workers.md](api-and-workers.md#sqs-kafka-or-another-broker)); items already claimed but not processed
become due again when their lease expires, so the action does not release them
one by one.
