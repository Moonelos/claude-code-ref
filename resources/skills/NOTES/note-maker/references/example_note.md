# Example Note File

This is one filled-in tutorial illustration. Adapt its teaching moves to the reader and subject; its headings, callouts, and ordering are not a mandatory template. The annotation table after the example maps each part of the note to the move it demonstrates.

The example below would live at `python/02_context_managers.md` in a Python notes repo.

---

## Example: `python/02_context_managers.md`

````markdown
# Context Managers and the `with` Statement

> **Who this is for**: Python developers who know functions and exceptions but have not
> built their own context managers.

## The short version

Cleanup written after an operation is skipped when that operation raises. A **context
manager** is an object with two hooks: `__enter__` acquires or prepares something, and
`__exit__` releases it even when the body fails. Those are the only two pieces because
every managed lifetime has exactly two boundaries: start and finish.

**What you need (2 things):**

1. An acquisition step — here, printing `acquire` and returning a value.
2. A release step — here, printing `release` from `__exit__`.

**The code:**

```python
class Opened:
    def __enter__(self):
        print("acquire")
        return "the resource"

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("release")
        return False

with Opened() as resource:
    print(resource)

# acquire
# the resource
# release
```

**Success signal:** `release` prints after `the resource`, including when the body raises.

**Not handled yet:** [partial acquisition failures](#5-what-breaks-in-practice) and
[async resource lifetimes](#6-when-not-to-use-one).

---

For optional background on the decorator syntax used later, see
[01_decorators.md](01_decorators.md). It is not needed for the baseline above.

## 1. The Cleanup You Wrote Will Not Run

You open a file, parse it, close it. The parse raises on a malformed row, `close()` never
runs, and the file descriptor leaks. Do that in a request handler and the process
eventually dies on `OSError: [Errno 24] Too many open files` — a failure that shows up
hours later, far from the code that caused it. Every resource with a release step has this
shape: files, database connections, locks, sockets.

`with` is the fix: it guarantees the release step runs, exception or not.

```python
# ❌ Wrong — an exception between open() and close() leaks the file descriptor
f = open("data.csv")
records = parse(f)   # raises ValueError on malformed input
f.close()            # never reached

# ✅ Correct — __exit__ is called even if parse() raises
with open("data.csv") as f:
    records = parse(f)
```

> **The near-miss**: `with` looks like sugar for `try/finally`, which makes it feel like a
> readability preference. It's a protocol. Any object implementing `__enter__` and
> `__exit__` works with it — which is why file handles, locks, decimal contexts,
> `mock.patch`, and database transactions all share the same two lines of caller code.
> You aren't shortening a `try/finally`; you're implementing an interface.

---

## 2. Implement the Protocol: `__enter__` and `__exit__`

> **Core:** a context manager is complete when acquisition happens in `__enter__` and
> release happens in `__exit__`. Everything else is policy layered on those boundaries.

The minimal version first. This runs, and it is the entire protocol:

```python
class Opened:
    def __enter__(self):
        print("acquire")
        return "the resource"      # this is what `as` binds

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("release")
        return False               # don't suppress exceptions

with Opened() as r:
    print(r)

# acquire
# the resource
# release
```

> **Production:** real resources need transaction policy and cleanup when the body fails.
> The next version adds those concerns; they are not needed to understand the protocol.

Now the hardened version. Each addition is here for one specific failure:

```python
import psycopg2

class ManagedConnection:
    """Wraps a psycopg2 connection so callers never call .close() manually."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: psycopg2.extensions.connection | None = None

    def __enter__(self) -> psycopg2.extensions.connection:
        self._conn = psycopg2.connect(self._dsn)
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._conn:                  # connect() may have raised before assigning
            if exc_type is None:
                self._conn.commit()     # commit only a clean block — committing a failed
            else:                       # one persists half a transaction, which is worse
                self._conn.rollback()   # than losing all of it
            self._conn.close()          # unconditional: runs on both paths, so a raising
        return False                    # block can't leak the connection back to the pool
```

**How you know it's working**: the row count in `pg_stat_activity` returns to baseline
after the block exits. If it climbs by one per call, `__exit__` isn't running — almost
always because the object was constructed without a `with` (`conn = ManagedConnection(dsn)`
on its own acquires nothing and releases nothing, and fails silently).

| Return value of `__exit__` | Effect                        |
|---------------------------|-------------------------------|
| `False` / `None`          | Exception propagates normally |
| `True`                    | Exception is suppressed       |

⚠️ Returning `True` is almost always wrong, and *any* truthy value counts — a stray
`return "ok"` silently swallows every exception raised in the block.

---

## 3. Reach for `@contextmanager` for Anything Simple

`contextlib` ships a dozen helpers. **In practice you write `@contextmanager` for nearly
everything**, reach for `closing` or `suppress` occasionally, and rarely touch the rest.

| Helper | Reach for it when | How often |
|--------|-------------------|-----------|
| **`@contextmanager`** | **You're writing your own manager and it holds no state between calls** | **Default** |
| `closing` | Wrapping a legacy object that has `.close()` but no `__exit__` | Occasional |
| `suppress` | Ignoring one specific expected exception | Occasional |
| `ExitStack` | Entering a number of managers not known until runtime | Rare |
| `nullcontext` | A `with` target that's conditionally a no-op | Rare |
| `redirect_stdout` | Capturing print output, mostly in tests | Rare |

```python
from contextlib import contextmanager
import logging
import time

logger = logging.getLogger(__name__)

@contextmanager
def timed_block(label: str):
    """Log how long a block of code takes. Works even if the block raises."""
    start = time.perf_counter()
    try:
        yield                        # execution enters the `with` block here
    finally:                         # runs on clean exit and on exception alike —
        elapsed = time.perf_counter() - start   # the same guarantee __exit__ gives
        logger.info("%s completed in %.3fs", label, elapsed)

with timed_block("index rebuild"):
    rebuild_search_index(db)
```

> **Rule**: everything before `yield` is `__enter__`; everything after it, inside `finally`,
> is `__exit__`. The `try/finally` is required — without it, an exception in the block skips
> your cleanup entirely.

---

## 4. Execution Flow

```
caller                   context manager
  │                            │
  │─── __enter__() ───────────>│
  │<── returns value ──────────│
  │                            │
  │  [with block executes]     │
  │                            │
  │─── __exit__(exc_info) ────>│  ← called even if block raised
  │<── bool (suppress?) ───────│
  │                            │
  ▼
continues (or re-raises)
```

---

## 5. What Breaks in Practice

**Forgetting `try/finally` in `@contextmanager`** — the most common bug here, and it
surfaces as a hang rather than an error, because the lock is never released.

```python
# ❌ Cleanup skipped if the with-block raises
@contextmanager
def bad_lock(resource):
    resource.acquire()
    yield
    resource.release()  # not reached on exception — deadlock

# ✅ Always wrap yield in try/finally
@contextmanager
def good_lock(resource):
    resource.acquire()
    try:
        yield
    finally:
        resource.release()
```

⚠️ There is no error message for this one. The tell is a process that stops making
progress while holding a lock some other thread is waiting on.

**Acquiring more than one resource in `__enter__`** — if the second acquisition raises,
`__exit__` never runs and the first resource leaks. Use `ExitStack` inside `__enter__`, or
acquire in nested `with` blocks so each has its own guarantee.

> **Edge case:** multiple acquisitions need their own cleanup stack because `__exit__`
> cannot run until `__enter__` has completed successfully.

```python
# ❌ If the second connect() raises, the first is never closed
def __enter__(self):
    self.a = connect(dsn_a)
    self.b = connect(dsn_b)   # raises — self.a leaks
```

---

## 6. When Not to Use One

A context manager ties a resource's lifetime to a **lexical block** — the indented code
whose start and end are visible in the source. Skip it when that is not the lifetime you
want:

- **The resource outlives the block** — a connection pool or HTTP client held for the
  process lifetime belongs in application startup/shutdown, not a `with`. Wrapping it
  forces a re-connect per use.
- **The caller needs to keep the resource** — a factory returning an open handle can't use
  one; the handle would be closed before the caller touched it.
- **The work is async** — `with` doesn't await. You need `__aenter__`/`__aexit__` and
  `async with`; a sync manager wrapping an async resource closes it before the coroutine
  completes.

---

## 7. Prove Cleanup Runs on Both Exit Paths

The protocol matters only if clean and failing bodies both release the resource. This
small integration check drives the same manager through both paths:

```python
events = []

class Recorded:
    def __enter__(self):
        events.append("acquire")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        events.append("release")
        return False

with Recorded():
    events.append("success")

try:
    with Recorded():
        events.append("failure")
        raise ValueError("broken row")
except ValueError:
    pass

assert events == [
    "acquire", "success", "release",
    "acquire", "failure", "release",
]
print("cleanup verified")
```

**Success signal:** the script prints `cleanup verified`. If the second `release` is
missing, the exception path bypassed cleanup even though the success path looked correct.

> **Key insight**: the value isn't the cleanup — it's that the cleanup becomes impossible
> to skip. Any time you write a comment reminding the next person to call something, you've
> found a context manager.

---

**Next**: [03_generators.md — Iterators and Generator Pipelines](03_generators.md)
````

---

## What each part demonstrates

| Part of the example | Required move |
|---|---|
| Short version | Counted inputs, locally grounded terms, runnable baseline, exact success signal, and linked deferrals before prerequisites |
| §1 opening paragraph | Lead with the problem — the reader's failure, with the error they'll see, before any definition |
| §1 `> **The near-miss**` | Name the wrong model before building the right one |
| §2 `Core` and `Production` markers | Altitude is explicit; a learner can stop before hardening |
| §2 two code blocks | Baseline first, hardened second — comments name the failure each addition prevents |
| §2 "How you know it's working" | Success signal, plus the tell for the silent failure |
| §3 helper table | Navigable enumeration — six entries, default marked in bold, and the default is the one shown in use below it |
| §5 headers and `⚠️` | Failure modes with the observable symptom; `⚠️` spent only on landmines |
| §6 | When *not* to use it, with what to reach for instead |
| §7 integration check | Separately explained pieces compose on success and failure paths |
| §7 `> **Key insight**` | An optional callout making a transferable, non-obvious insight visible |
| All `## N.` headers | Claims, not labels ("The Cleanup You Wrote Will Not Run", not "Introduction") |

---

## Ordering before and after: make JWKS usable before hardening it

This is the canonical example of the ordering rule. In the bad sequence, the reader's
first encounter with **JWKS** (a JSON document containing an issuer's public keys) is a
45-line production client: metadata discovery, issuer byte comparison, URL validation,
`Cache-Control` parsing, bounded caching, and an emergency reload hook. Every concern is
valid, but the baseline is invisible inside the hardening.

Put the two-line mechanism first:

```python
# Baseline — fetches the issuer's public keys and picks the right one by `kid`.
jwks = PyJWKClient("https://auth.example.com/.well-known/jwks.json")
key = jwks.get_signing_key_from_jwt(token).key
```

> **Production:** this hard-codes the JWKS path and refetches on every miss. A later
> section replaces both with metadata discovery and a bounded cache.

The information did not get thinner; its order changed. The reader owns the mechanism
after two lines, then learns why production needs the other forty-five.
