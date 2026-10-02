# Errors, Privacy, and Redaction

## Failure record contract

The boundary that decides the operation's final outcome emits exactly one `error` record while its correlation context is active. Include:

- a stable failure event name;
- bounded `error.type`, normally the exception class or stable provider/domain code;
- a safe authored message or stable reason code;
- current execution and permitted business correlation;
- exception detail according to the central policy.

Do not use `str(exc)` as `error.type`, an event name, or a bounded field. Do not log and re-raise at every layer. Inner code may wrap with a meaningful domain exception and preserve the cause, but it should not emit another terminal record. A function that logs a summary and re-raises omits `exc_info`; the handling boundary logs the exception.

A failed attempt that is handled and later succeeds follows `event-design.md#loops-and-pollers`. The successful outer operation is not an error.

## Silent degradation leaves a trace

When code catches and continues with a recorded fallback, it emits one `warning` with bounded `error.type` and the fallback taken, or carries a why-comment when a log would be pure noise. Which exception shapes may be caught at all is owned by `$python-service-architecture` (fallback `../../python-service-architecture/references/errors.md#broad-except-shapes`).

## Exception detail

This skill is the single owner of the exception-detail rule; tracing skills link here.

- **Call sites never build `exception.*` fields.** Pass `exc_info=exc` and nothing else. Hand-built stack traces drop the message and the `__cause__` chain. The central processor (`structlog-pipeline.md`) turns `exc_info` into `exception.type`, `exception.message`, and `exception.stacktrace`; that is the only field name for the traceback.
- **One typed setting controls detail**: `log_full_exception_trace: bool`. Where its value comes from (YAML, the safe default, per-environment overrides, never the environment name) is owned by `$python-settings-config` (fallback `../../python-settings-config/SKILL.md#ownership`). Shared code takes the value as a required input and bakes in no environment policy.
- When the service handles personal or financial data and no policy is stated, ask before enabling full detail in any environment.

The processor renders:

- **full:** fully qualified `exception.type`, the redacted message, the complete cause chain once in `exception.stacktrace`, no local-variable capture, `app.error.stacktrace_included=true`;
- **safe** (the production baseline): `exception.type`, a safe authored message, bounded `error.type`, stable reason/code, correlation, and `app.error.stacktrace_included=false`; no raw traceback or exception message.

Redact credentials and tokens in both modes.

### Record-size limits

A log backend can cap structured metadata per record — Grafana Loki, for example, rejects the whole line once it exceeds `max_structured_metadata_size`. A chained traceback or `ExceptionGroup` exceeds that easily, and the backend then drops the **entire record**, so the one failure record disappears with its correlation. Confirm the destination's limit before shipping full detail. Truncate the traceback safely below it and mark `app.error.stacktrace_truncated=true`; if the backend's log body has no comparable limit, carry `exception.stacktrace` in the body while bounded fields stay structured. Verify with a synthetic oversized traceback that exactly one record still arrives.

## Data classification

Default-deny these values:

```text
passwords, access/refresh tokens, API keys, session cookies
Authorization and Set-Cookie headers
private keys, connection strings, signed URLs
full request/response bodies and arbitrary message payloads
personal data, document contents, prompts and model outputs
```

Prefer allowlisting fields over chasing secret key names. One redaction module (patterns plus a recursive mask) serves the log processor and any content serializer; never write a second one. In a workspace with a shared observability library it lives there. A single-service repository, or the first service to need it, keeps it in `observability/redaction.py`, allowlist-first (named safe fields pass, everything else in a payload is masked), and moves it into the observability library when a second service needs the same policy. When redaction is needed, traverse nested dictionaries, sequences, exception metadata, and rendered URLs; key-only top-level filters are insufficient. Use a stable marker such as `[REDACTED]`, never a reversible transform. Hashing personal identifiers still creates personal data and high-cardinality values; it requires policy approval and rotation rules.

Never capture process environment, local variables, object `repr`, or whole configuration objects. Treat user-controlled log fields as untrusted: prevent reserved-key overwrite and sanitize control characters that could forge multiline records.

## Correlation and privacy

Identifiers such as `user_id`, `tenant_id`, conversation ID, order ID, IP address, and request body fragments need a concrete search purpose plus suitable retention and access control. Prefer opaque business IDs over names or emails. Do not copy all incoming headers into context.

Record data-classification and retention assumptions in the completion report when the repository does not define them. Do not invent consent or authorization.

