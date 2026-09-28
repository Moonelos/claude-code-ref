# Canonical backend template

Use this reference to produce a concrete target tree after applying the
ownership and dependency rules in [boundaries.md](boundaries.md). Omit unused
directories; never add empty packages merely to complete a drawing.

## Application shell

```text
src/<package>/
├── __init__.py
├── main.py                         # Thin executable entry point
├── bootstrap/                      # Composition and process lifecycle
│   ├── runtime.py                  # Build/dispose long-lived dependencies
│   ├── app.py                      # ASGI/FastAPI factory, when applicable
│   └── supervisor.py               # Background lifecycle, when applicable
├── config/
│   ├── settings.py
│   └── secrets.py
├── api/                            # HTTP transport, when present
├── application/                    # Business actions and orchestration
├── domain/                         # Reused business nouns and pure rules
├── ports/                          # Application-facing external contracts
├── adapters/                       # Concrete external integrations
├── genai/                          # Mandatory when any GenAI exists
├── db/                             # Persistence boundary, when present
├── observability/
└── diagnostics/                    # Optional operator diagnostics
```

This `config/` is Python settings code, not the home of YAML baselines; see
`python-settings-config`. `core/` is deliberately absent
([boundaries.md](boundaries.md#core)). For APIs, workers, consumers, and hybrid
processes, use the trees in [api-and-workers.md](api-and-workers.md).

## Representative service tree

This example demonstrates placement, not required contents:

```text
src/<package>/
├── application/
│   ├── email_admission.py
│   ├── email_classification.py
│   └── email_replay.py
├── domain/
│   ├── email.py
│   └── parsing.py
├── ports/
│   ├── raw_email_store.py
│   └── email_classifier.py
├── adapters/
│   └── aws/
│       ├── clients.py
│       ├── sqs_consumer.py
│       ├── sqs_serialization.py
│       └── s3_raw_email_store.py
└── genai/
    └── email_classification/
        ├── schemas.py
        ├── prompts.py
        └── classifier.py
```

When several application actions form one cohesive capability, promote only
that slice, for example:

```text
application/
├── email/
│   ├── admission.py
│   ├── classification.py
│   └── replay.py
└── alerts/
    └── send.py
```

For GenAI variants use [ai.md](ai.md); for file-to-package promotion use
[boundaries.md](boundaries.md#flat-first-growth-across-boundaries).

## Use-case shape

An application action is a class named with an imperative verb phrase, with
keyword-only dependencies (ports, a UoW factory, typed policy objects, effect
seams), **one** public `async def execute(*, ...) -> <FrozenResult>`, and failures
raised as action- or port-owned exceptions. Use a plain module function when
there are no dependencies.

```python
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from my_service.domain.email import AdmissionOutcome, EmailId, admission_decision
from my_service.ports.admission_store import AdmissionStore


@dataclass(frozen=True, kw_only=True)
class AdmissionResult:
    email_id: EmailId
    outcome: AdmissionOutcome  # StrEnum: ADMITTED, DUPLICATE, REJECTED


class AdmitEmail:
    def __init__(
        self,
        *,
        store: AdmissionStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._clock = clock

    async def execute(self, *, email_id: EmailId) -> AdmissionResult:
        observed = await self._store.observe(email_id=email_id)
        decision = admission_decision(observed=observed, now=self._clock())
        await self._store.apply(decision=decision)
        return AdmissionResult(email_id=email_id, outcome=decision.outcome)
```

## Placement test

Use these questions in order when ownership is ambiguous:

| Question | Location |
| --- | --- |
| Does it deliver an understandable business action or outcome? | `application/` |
| Is it a reusable business noun, value object, or pure rule? | `domain/` |
| Does it define an external or nondeterministic capability an action needs? | `ports/` |
| Does it implement that need with an ordinary external SDK or system? | `adapters/` |
| Does it contain an LLM, agent, prompt, AI schema, tool, graph, model binding, or behavior-changing AI middleware? | `genai/` |
| Does it exist only to trace, meter, log, or correlate GenAI execution? | `observability/` |
| Does it expose HTTP transport concerns? | `api/` |
| Does it execute persistence queries or own sessions/repositories? | `db/` |
| Does it construct or dispose the runtime graph? | `bootstrap/` |

GenAI, API, and database code use their specialized root boundaries rather than
the general `adapters/` category.

## Tests

Keep tests beside the member, outside its import package. Use
[testing.md](testing.md) as the single authority for the target test tree,
execution profiles, fixture ownership, markers, CI selection, and migration.
