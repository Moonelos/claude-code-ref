# External read-only databases and untrusted SQL

## External read-only databases

A database the service reads but doesn't own (another team's system, a
reporting replica) gets all six of these:

1. **A least-privilege read-only role**, verified by a runnable acceptance
   check (a test or probe that confirms a write is refused).
2. **`SET TRANSACTION READ ONLY` plus local limits** at the start of every
   transaction (`engine-and-session.md`, "Per-transaction limits").
3. **Results bounded in SQL:** `LIMIT :n + 1` to detect truncation, or keyset
   pagination.
4. **`text()` or Core, mapped into frozen dataclasses.** No ORM models for
   tables the service doesn't own.
5. **`max_overflow=0` and an acquisition timeout** on its engine.
6. **One `…SourceUnavailableError`** for every connection or timeout failure.

```python
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from myservice.db.transactions import apply_transaction_limits


class BillingSourceUnavailableError(Exception):
    """The billing database could not be reached or timed out."""


@dataclass(frozen=True, kw_only=True, slots=True)
class Invoice:
    invoice_id: str
    amount_cents: int


@dataclass(frozen=True, kw_only=True, slots=True)
class InvoicePage:
    invoices: tuple[Invoice, ...]
    truncated: bool


_RECENT_INVOICES = text(
    "SELECT invoice_id, amount_cents FROM billing.invoices"
    " WHERE customer_id = :customer_id ORDER BY issued_at DESC, invoice_id LIMIT :limit"
)


class BillingReader:
    def __init__(
        self, *, engine: AsyncEngine, statement_timeout: timedelta, max_rows: int
    ) -> None:
        self._engine = engine
        self._statement_timeout = statement_timeout
        self._max_rows = max_rows

    async def recent_invoices(self, *, customer_id: str) -> InvoicePage:
        try:
            async with self._engine.connect() as conn, conn.begin():
                # First SQL statement in this transaction, before local limits.
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                await apply_transaction_limits(conn, statement_timeout=self._statement_timeout)
                result = await conn.execute(
                    _RECENT_INVOICES,
                    {"customer_id": customer_id, "limit": self._max_rows + 1},
                )
                rows = [
                    Invoice(invoice_id=row.invoice_id, amount_cents=row.amount_cents)
                    for row in result
                ]
        except (OperationalError, InterfaceError, PoolTimeoutError) as exc:
            raise BillingSourceUnavailableError from exc
        return InvoicePage(
            invoices=tuple(rows[: self._max_rows]), truncated=len(rows) > self._max_rows
        )
```

## Untrusted or LLM-authored SQL

SQL written by a user or a model is hostile input. Every layer is required;
none substitutes for another:

1. **AST allowlist before pool checkout:** parse (e.g. `sqlglot`), accept a
   single `SELECT` over allowlisted relations and functions, reject
   everything else. Validate once and pass the validated plan down; later
   layers never re-parse the raw text.
2. **A dedicated reader role** with `default_transaction_read_only=on`, a
   pinned `search_path`, and grants only on `security_barrier` views.
3. **Transaction-local timeouts** (`set_config(..., true)`), never a
   session-level `SET` that leaks to the next pool user.
4. **Wrap the query:** `SELECT * FROM (<validated>) AS q LIMIT :max_rows_plus_one`.
   This f-string is the one allowed interpolation, and only of the validated plan.
5. **Cap rows and bytes while fetching** (`fetchmany` in chunks), stopping at
   either limit.
6. **Retry transient connection errors only**, never `QueryCanceled`
   (a timeout is the query's fault, not the network's).
7. **Don't route trusted internal queries through this path**; it exists for
   untrusted text only.

Agent tools that expose this path are wired as described in
`../../python-service-architecture/references/ai.md`.
