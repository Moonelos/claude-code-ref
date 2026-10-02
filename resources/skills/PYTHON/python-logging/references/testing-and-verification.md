# Testing and Verification

Test application-owned processors and event decisions, not the logging library itself. Follow the repository's existing test framework; do not add a new framework solely for logging.

## Focused tests

When a suite exists, cover the changed behavior:

- the same event schema is produced for normal and error paths;
- timestamps, level/severity, event, and service identity are present and correctly typed;
- request/job context appears inside its boundary and is cleared afterward;
- two concurrent boundaries do not leak context into each other;
- valid active trace IDs are added when tracing exists and omitted when absent/invalid;
- reserved fields cannot be overwritten by untrusted context;
- nested canary secrets are redacted before serialization (see "Canary test");
- the full exception projection keeps the chained traceback once; the safe projection removes traceback, raw exception message, and canary PII while preserving classification and correlation;
- an allowlisting formatter rejects or marks unknown fields, and representative success, retry, and failure records still carry each event's needed fields;
- an oversized traceback is truncated with an explicit marker and the record survives;
- one escaping exception produces exactly one terminal error record;
- recovered retries produce no per-attempt record and no terminal error; an activated fallback produces its one warning;
- GenAI content canaries never appear in captured logs.

Capture the final serialized record or use the library's in-memory sink. Assertions should inspect parsed fields and value types, not fragile key ordering or the renderer's whitespace. Test design and placement belong to `$pytest`.

## Canary test

Each sink gets one test that pushes a canary secret through fields, a nested header, a URL, and an exception message, then asserts it never reaches the serialized output:

```python
import json
import logging

import pytest

from app.logging_setup import LoggingConfig, configure_logging  # the service's logging owner

logger = logging.getLogger(__name__)
CANARY = "sk-canary-7f3a9c"


def test_canary_secret_never_serialized(capsys: pytest.CaptureFixture[str]) -> None:
    # Full detail is the harder case: the exception message and traceback are rendered.
    configure_logging(
        LoggingConfig(service_name="canary-test", level="INFO", log_full_exception_trace=True)
    )
    headers = {"Authorization": f"Bearer {CANARY}"}
    logger.warning("provider_call_failed", extra={"headers": headers, "url": f"https://x.test/?api_key={CANARY}"})
    try:
        raise ValueError(f"api_key={CANARY}")
    except ValueError:
        logger.exception("request_failed")
    output = "".join(capsys.readouterr())
    assert CANARY not in output
    assert [json.loads(line) for line in output.splitlines()]
```

## Runtime verification

Run representative success, failure, retry, and shutdown paths and inspect the emitted output against the invariants: standalone JSON per line (multiline exception text included), stable event names with values in fields, correct severity, service and correlation with no stale context, one terminal failure record with the configured projection, no canary content, the documented sampling rule, and flushed shutdown records.

When delivery configuration is in scope, verify at the real destination: the event is searchable by event name, severity, service, and correlation field; field types survive ingestion; timestamp parsing is correct; size limits do not drop the exception record; and retention/access controls match the data policy. Local stdout proves serialization, not backend delivery.

## Symptom guide

| Symptom | Likely owner to inspect |
| --- | --- |
| Plain text or double-encoded JSON | competing formatter/handler or logging through an already rendered string |
| Duplicate records | propagation plus child handler, two startup configurations, framework and application owning the same event, or two delivery paths |
| Missing context | binding outside the boundary, wrong async/thread context mechanism, or early clearing |
| Context from another request/job | context not cleared in `finally` or unsafe global mutable state |
| Missing traceback | exception info lost before the central exception processor, or the safe projection configured |
| Secret still visible | redaction after serialization, shallow traversal, or leak through exception/URL/object representation |
| Final records missing | buffered/asynchronous handler not flushed within shutdown lifecycle |
| Field missing or unqueryable | allowlist dropped it, type/schema changed during ingestion, field nested unexpectedly, or backend indexing policy |

## Report honestly

State exactly which tests and runtime paths ran, which sink was inspected, and what could not be verified. Do not describe delivery as complete when only local serialization was tested.
