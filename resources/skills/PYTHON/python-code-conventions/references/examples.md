# Examples

Longer bad/good pairs for the rules in `../SKILL.md`, under the same headings. Good versions pass `mypy --strict` (with the pydantic plugin) on Python 3.13; imports are omitted.

## Data containers

```python
@dataclass                                  # bad: mutable, list field, positional bool
class ClaimResult:
    ids: list[str]
    retried: bool

@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimResult:                          # good
    ids: tuple[str, ...]
    retried: bool

class StrictModel(BaseModel):
    """Base for every boundary model in this member."""
    model_config = ConfigDict(frozen=True, extra="forbid")

class ToolArgs(StrictModel):
    query: str                                                    # bare annotation: required
    limit: int = Field(default=10, ge=1, le=50, description="Server clamps to 50.")
```

## Keyword construction

```python
batch = Batch("orders", 50, True, None)                              # bad
batch = Batch(queue="orders", size=50, dry_run=True, deadline=None)  # good
```

## Closed vocabularies

```python
if job.state in ("done", "failed") or "fail" in job.state: ...   # bad

class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

TERMINAL_STATES: frozenset[JobState] = frozenset({JobState.DONE, JobState.FAILED})

if job.state in TERMINAL_STATES: ...                             # good
row = {"job_id": job.job_id, "state": job.state.value}          # .value only at the edge
```

## Outcome contracts

```python
async def renew_lease(self, job_id: str) -> bool: ...           # bad: which falsy cause?

class RenewOutcome(StrEnum):
    RENEWED = "renewed"
    LOST = "lost"                  # another worker holds the lease
    ALREADY_DONE = "already_done"

async def renew_lease(self, *, job_id: str) -> RenewOutcome: ... # good

async def find_job(self, *, job_id: str) -> Job | None:
    """Return the job, or None when no job has that id."""       # good: one cause, documented
```

## Type escape hatches

```python
def parse_env(raw: str) -> Environment:
    return raw  # type: ignore[return-value]                     # bad

_ENVIRONMENTS: Mapping[str, Environment] = {env.value: env for env in Environment}

def parse_env(raw: str) -> Environment:                           # good
    env = _ENVIRONMENTS.get(raw)
    if env is None:
        raise UnknownEnvironmentError(raw)
    return env

def extract_text(payload: object) -> str:                         # good: object, narrowed
    """Translate an untyped SDK payload into the text we use."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, Mapping):
        content = payload.get("content")
        if isinstance(content, str):
            return content
    raise UnexpectedPayloadError(type(payload).__name__)
```

## No assert in production

```python
job = await store.find_job(job_id=job_id)
assert job is not None                                            # bad: stripped by -O

job = await store.find_job(job_id=job_id)
if job is None:                                                   # good
    raise JobNotFoundError(job_id)

def fail_unsupported(kind: str) -> NoReturn:
    raise UnexpectedPayloadError(kind)
```

## Fixed-key dicts are records

```python
summary: dict[str, Any] = {}                                      # bad
_add_counts(summary, jobs)
return Report.model_validate(summary)

@dataclass(frozen=True, slots=True, kw_only=True)
class OutcomeCounts:
    total: int
    failed: int

def count_outcomes(jobs: tuple[Job, ...]) -> OutcomeCounts:       # good: returns a value
    failed = sum(1 for job in jobs if job.state is JobState.FAILED)
    return OutcomeCounts(total=len(jobs), failed=failed)

counts = count_outcomes(jobs)
return Report(total=counts.total, failed=counts.failed)
```

## Named types and constraints

```python
def inject(carrier: dict[str, str]) -> None: ...                  # bad: repeated in three modules
confidence: float = Field(ge=0, le=1)                             # bad: same bound on four models

type TraceCarrier = dict[str, str]                                # good, at the tracing owner
type Confidence = Annotated[float, Field(ge=0, le=1)]
type Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

class Finding(StrictModel):
    digest: Sha256Hex
    confidence: Confidence

def first[T](items: tuple[T, ...]) -> T | None:
    return items[0] if items else None
```

## Magic values and constants

```python
if len(body) > 262144: ...                                        # bad
if "reasoning" in settings.model_id: ...                          # bad: substring of a deployed value

MAX_MESSAGE_BYTES = 256 * 1024  # queue's hard message limit
TICKET_REF = re.compile(r"^[A-Z]{3}-\d{6}$")
if len(body) > MAX_MESSAGE_BYTES: ...                             # good
if settings.supports_temperature: ...                             # good: a setting, not a substring
```

## Constructors and wrappers

```python
class ReportHandler:                                              # bad: forwards, adds nothing
    def __init__(self, *, service: ReportService) -> None:
        self._service = service

    async def handle(self, report_id: str) -> Report:
        return await self._service.build(report_id)

report = await report_service.build(report_id)                    # good: callers use the service

@dataclass(frozen=True, slots=True, kw_only=True)
class RetryPolicy:                                                # good: scalars consumed together
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float

    def __post_init__(self) -> None:
        if self.base_delay_seconds > self.max_delay_seconds:
            raise InvalidRetryPolicyError(self.base_delay_seconds, self.max_delay_seconds)

```

## One owner per semantics

```python
# bad: billing/adapters/export.py keeps a second, drifted copy
def _canonical_hash(payload: Mapping[str, object]) -> str: ...

from orders.domain.fingerprint import canonical_hash              # good: import the one owner
```

## Imports and package markers

```python
# bad: services/worker/src/worker/__init__.py
from worker.bootstrap.runtime import build_runtime
__all__ = ["build_runtime"]

# good: services/worker/src/worker/__init__.py is empty
# good: libs/tracekit/src/tracekit/__init__.py
from tracekit.carrier import TraceCarrier, inject
__all__ = ["TraceCarrier", "inject"]
```

## Docstrings and comments

```python
async def claim(self, limit: int) -> tuple[Job, ...]:
    """Claim jobs.

    Args:
        limit: The limit.
    """                                                           # bad: restates the signature

async def claim(self, limit: int) -> tuple[Job, ...]:
    """Claim up to `limit` due jobs; empty means none are due."""  # good
```

## Error and async idioms

```python
try:                                                  # bad: bugs become InvalidOrderError
    data = json.loads(body)
    order = Order(order_id=data["id"], total_minor=data["total"])
except (KeyError, TypeError, ValueError):
    raise InvalidOrderError(ref)

try:                                                  # good: minimal try, chained cause
    order = Order.model_validate_json(body)
except ValidationError as exc:
    raise InvalidOrderError(ref) from exc

try:
    await queue.claim(10)
except asyncio.CancelledError:                        # good: does something different, re-raises
    stop.set()
    raise
```
