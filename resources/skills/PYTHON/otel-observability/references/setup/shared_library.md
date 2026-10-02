# Shared observability library

Use this reference when creating or changing a reusable observability package,
or when discovery identifies repeated provider lifecycle, logging processors,
or propagation policy across current deployables. Evaluation does not authorize
consumer migration outside the task's scope; preserve the scope in `SKILL.md`.

## Read next

- Read `package_layout.md` for settings ownership and service-local placement.
- Read `sdk_bootstrap.md` for provider construction, startup, and shutdown.
- Use the `python-logging` skill when logging configuration or processors are
  part of the shared package, and `../logging/correlation.md` for the
  trace-context enricher.
- Read `../testing.md` before implementing deterministic helpers or migration
  contracts, and `../verification.md` last.
- In a uv workspace, use the `python-repository-setup` skill for member,
  dependency, lockfile, scoped-install, and Docker mechanics. Use
  `python-service-architecture` for the internal modularization of `libs/*`.

## The package must earn the boundary

Do not create a package merely because two files look similar. Extract only a
cohesive contract that has demonstrated reuse across current deployables and
the same operational meaning in each consumer. A library is justified when it
removes duplicated policy or lifecycle behavior without importing one
service's business model into the others. Whether duplication is a finding
that must be resolved (copy counts, semantic drift, an existing library of the
right kind) is decided by
`../../../python-service-architecture/references/shared-libraries.md`
(Extraction triggers).

Good shared responsibilities include:

- process-scoped OpenTelemetry provider construction and bounded shutdown;
- OTLP endpoint resolution and resource construction from explicit inputs;
- trace-context normalization, injection, extraction, and linked-root helpers;
- safe span context managers and narrowly scoped decorators;
- trace/log correlation, common JSON rendering, redaction, and explicitly
  configured exception projection;
- stable cross-service semantic constants whose meaning is genuinely shared.

Keep these service-local unless a stable cross-service contract already exists:

- business span names, workflow states, outcomes, and reason taxonomies;
- service metric instruments, histogram views, and business log event names;
- framework, vendor, browser, database, or GenAI instrumentation used by only
  one consumer;
- settings models, environment lookup, and deployment-specific policy;
- exporter filters or sampling decisions that intentionally differ by service.

## Ownership split

```text
shared observability package
  generic SDK lifecycle, spans, propagation, resource helpers
  common structured-logging processors and safety policy

service config/
  reads environment/secrets/YAML and validates service settings

service bootstrap/
  maps settings to library inputs, configures telemetry, owns shutdown order

service observability/
  service vocabulary, instruments, projections, and integration adapters

application boundary
  decides business outcome and supplies attributes known only after execution
```

Library inputs and dependencies follow `../../../python-service-architecture/references/shared-libraries.md`
(Library rules: Configuration, Dependencies; Flat first): typed values or a
library-owned frozen options object, no environment reads, no `BaseSettings`,
and no imports from a deployable. A separate `config.py` in the library is
optional and never implies ownership of deployment configuration.

For example, this illustrates the input boundary only, not a complete SDK setup:

```python
# Library: providers.py
from dataclasses import dataclass

@dataclass(frozen=True)
class TelemetryConfig:
    service_name: str
    otlp_endpoint: str | None

# Service bootstrap: settings were resolved by the service.
config = TelemetryConfig(
    service_name="worker",
    otlp_endpoint=settings.otlp_endpoint,
)
providers = configure_observability(config)
```

## Suggested package growth

Start flat and create only modules with a current responsibility:

```text
src/company_observability/
├── __init__.py          # small intentional public API
├── providers.py         # provider lifecycle and its typed input values
├── spans.py             # context managers and optional decorators
├── propagation.py       # bounded W3C carriers and links
└── logging.py           # shared processors/configuration, when justified
```

Do not create `tracing/`, `metrics/`, `logging/`, `exporters/`, or `plugins/`
subpackages in advance; when to promote a slice is in `../../../python-service-architecture/references/shared-libraries.md` (Flat
first). `__init__.py` re-exports the small supported API, not every SDK type or
internal helper (same file, Public API and compatibility).

## Explicit lifecycle

Importing the package must be inert:

```python
import company_observability  # no provider, logger, or instrumentation side effect
```

Each process configures it explicitly from its composition root:

```python
providers = configure_observability(config, third_party_views=views)
configure_logging(logging_config, correlation=[add_otel_trace_context])
```

Implement only the lifecycle invariants a current consumer exercises. With one
bootstrap call per process, "configure once; raise on a second call" is enough.
Always:

- one provider owner per process; never mix code-owned and zero-code setup;
- provider handles are returned to bootstrap rather than hidden behind imports;
- shutdown is idempotent, bounded where the runtime requires it, and runs after
  clients/background work stop;
- telemetry export or shutdown failures do not replace the business result;
- process-wide instrumentation is installed explicitly and at most once.

Expose narrowly typed extension inputs such as metric views, a sampler, or a
span-exporter wrapper only when current consumers need them. Do not build a
plugin/factory system around hypothetical service differences. Framework- and
vendor-specific integrations stay outside the generic provider module.

## Spans: context manager first

The primary helper is a context manager because callers often add attributes,
links, status, and business outcome during execution. Its shape, including when
`set_status_on_exception` may be disabled and how cancellation is recorded, is
`start_span` in `../conventions/errors.md`. The library also owns the one
`error_type_of(exc)`, provider error-code extraction, and transient-failure
classification.

A decorator may wrap a stable synchronous or asynchronous execution boundary
when its span name and initial attributes are available before the call. It is
only convenience over the same context manager: preserve the wrapped signature
and metadata, do not instrument arbitrary helper functions, and do not hide
outcome handling that belongs in the caller. A decorator or context manager
cannot detect an exception swallowed inside the wrapped body; handled terminal
failures must mark the active span explicitly.

The generic helper may set standard failure status and bounded `error.type`.
Beyond `app.outcome=cancelled`, it must not guess a service's outcome, retry classification, HITL state,
or metric labels. A thin service-local wrapper may add those semantics.

## Shared structured logging

Logging belongs in the same shared package when multiple services use the same
transport, JSON schema, redaction rules, and exception-detail policy. Sharing
only a `get_logger()` call while each service has a different processor chain
is not a useful abstraction.

What the shared logging module owns, and how it is built (inert on import,
explicit `configure_logging(...)`, root stdlib logger through the same chain,
one redaction module, the exception-detail processor), is owned by the
`python-logging` skill (`../../../python-logging/SKILL.md`). This skill adds
only `add_otel_trace_context` (`../logging/correlation.md`), passed into that
pipeline by bootstrap. Business event names and fields stay at the call site.
Preserve one delivery path per record.

## Migration

Follow `../../../python-service-architecture/references/shared-libraries.md` (Extraction and modularization
sequence). What observability adds:

- the inventory also covers public imports, provider ownership, shutdown
  behavior, and logging paths;
- keep a thin service-local compatibility facade when imports cannot move
  atomically;
- each consumer's verification includes its package-scoped install and
  startup/shutdown tests.

The shared change stays additive until the migration is complete. Do not update
unrelated services merely to make their folder trees symmetrical.

## Verification

- Importing the library creates no providers, instruments, or logging handlers.
- A second initialization is rejected deterministically.
- Success, escaping failure, handled failure, cancellation, and linked-root
  behavior satisfy the common contract.
- Logging inside a span has valid trace/span identifiers and applies the same
  redaction and exception-detail behavior in every consumer.
- A record has one delivery path; a boundary has one span owner.
- Shutdown flushes each enabled signal once and cannot replace business failure.
- Library tests pass independently, then each migrated consumer's contract and
  startup/lifecycle tests pass under a package-scoped install.
