# structlog Reference Pipeline

Read this when the repository uses `structlog` or stdlib `logging` and needs a concrete central pipeline. It implements the ordering in `implementation.md#one-central-pipeline`; adapt names to the existing logging owner rather than adding a second one.

```python
# app/logging_setup.py (or the existing logging owner)
import logging
import sys
import traceback
from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from app.observability.redaction import mask


@dataclass(frozen=True, slots=True, kw_only=True)
class LoggingConfig:
    service_name: str
    level: str
    log_full_exception_trace: bool  # set per environment; errors-and-security.md#exception-detail


def redact(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    return {key: mask(value) for key, value in event_dict.items()}


def _exception_of(exc_info: object) -> BaseException | None:
    if exc_info is True:
        exc_info = sys.exc_info()
    if isinstance(exc_info, tuple) and len(exc_info) == 3:
        exc_info = exc_info[1]
    return exc_info if isinstance(exc_info, BaseException) else None


def exception_detail(*, full: bool) -> Processor:
    """The only place exception.* fields are built."""

    def processor(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        exc = _exception_of(event_dict.pop("exc_info", None))
        if exc is None:
            return event_dict
        exc_type = type(exc)
        event_dict["exception.type"] = f"{exc_type.__module__}.{exc_type.__qualname__}"
        event_dict["app.error.stacktrace_included"] = full
        if full:
            event_dict["exception.message"] = str(exc)
            # format_exception keeps the message and the __cause__/__context__ chain.
            event_dict["exception.stacktrace"] = "".join(traceback.format_exception(exc))
        return event_dict

    return processor


def configure_logging(
    config: LoggingConfig, *, correlation: Sequence[Processor] = ()
) -> None:
    """`correlation` holds enrichers such as active trace IDs, supplied by the tracing owner."""

    def add_service_name(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service.name", config.service_name)
        return event_dict

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_service_name,
        *correlation,
        exception_detail(full=config.log_full_exception_trace),
        redact,  # after every field exists, before rendering
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    # The root stdlib logger renders through the same chain, so library records
    # get the same correlation, exception detail, and redaction.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            # ExtraAdder copies stdlib `extra=` fields into the event dict before
            # the shared chain redacts and renders them.
            foreign_pre_chain=[structlog.stdlib.ExtraAdder(), *shared],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(config.level.upper())
```

The composition root builds `LoggingConfig` from settings and calls `configure_logging` once, before application modules emit records. Nothing reads settings at import. `mask` is the one redaction module (`errors-and-security.md#data-classification`); `service.name` is the only service-identity key.

When the service is traced, the tracing owner supplies the enricher through `correlation` (OpenTelemetry: `$otel-observability`, fallback `../../otel-observability/references/logging/correlation.md`). Without tracing, pass nothing; the record stays complete with request/job context from `merge_contextvars`.

Output:

```json
{
  "event": "retrieval_completed",
  "level": "info",
  "timestamp": "2026-08-10T09:12:44.113Z",
  "service.name": "chat-api",
  "request_id": "req-4f1c",
  "returned_documents": 5
}
```

Do not let a library call `logging.basicConfig()` or install its own handler after this runs; it produces a second, unformatted copy of each record.

## Volume controls

Pick one mechanism deliberately for noisy `info`/`debug` records:

| Where | How | Cost |
| --- | --- | --- |
| Application | the root stdlib level set from `LoggingConfig.level` (add `structlog.stdlib.filter_by_level` first in `processors` to drop below-level structlog calls before the chain runs), and a per-event sampler for a known-noisy call site | Cheapest; the record never exists, so it cannot be recovered |
| Log pipeline/agent | a severity filter or sampling stage in the collector that ships the logs | Central and changeable without a deploy |
| Log backend | retention rules per severity or stream | Full-fidelity ingest, so you pay for volume you then discard |

Never sample terminal failures or audit-relevant state changes (invariant 12).
