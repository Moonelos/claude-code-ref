# AWS Lambda Functions

**Do not open this file unless the target is a Python function running in the
managed AWS Lambda runtime.** A Lambda execution environment is frozen and
reused between invocations, so the lifecycle here contradicts the ordinary
server/worker startup/shutdown pattern on purpose: do not apply that pattern
mechanically to a Lambda, and do not apply this one to a normal process, where
it breaks flushing.

The AWS Lambda semantic-convention guidance is still marked **Development**.
Re-check `../compatibility.md` and the upstream guidance when upgrading:

- [AWS Lambda semantic conventions](https://opentelemetry.io/docs/specs/semconv/faas/aws-lambda/)
- [OpenTelemetry Lambda auto-instrumentation](https://opentelemetry.io/docs/platforms/faas/lambda-auto-instrument/)
- [AWS Python Lambda tracing](https://docs.aws.amazon.com/lambda/latest/dg/python-tracing.html)

## Contents

- [Choose one invocation owner](#choose-one-invocation-owner)
- [Choose the export path](#choose-the-export-path)
- [Propagators](#propagators)
- [Invocation and trigger boundaries](#invocation-and-trigger-boundaries)
- [Flush without shutdown](#flush-without-shutdown)
- [Resource identity](#resource-identity)
- [Mock trigger fixtures](#mock-trigger-fixtures)
- [Verification](#verification)

## Choose one invocation owner

Prefer a maintained Lambda instrumentation layer or
`opentelemetry-instrumentation-aws-lambda` to own the function invocation span.
Add business child spans inside the handler; do not wrap the same invocation in
a second manual `SERVER` span.

Choose exactly one setup:

| Setup | Invocation owner | Collector/export owner |
| --- | --- | --- |
| AWS-managed ADOT Python layer | ADOT Lambda instrumentation | Collector bundled with or configured by the selected ADOT layer |
| Community OTel instrumentation layer | `opentelemetry-instrumentation-aws-lambda` | separate Collector Lambda layer or explicitly configured external Collector |
| Fully manual package setup | application wrapper | application SDK plus Collector endpoint |

Layer ARNs are regional, architecture-specific, and versioned. Resolve the
current ARN in deployment configuration; never copy a stale ARN into this
skill or application code.

The community instrumentation wrapper uses:

```text
AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-handler
```

The AWS-managed ADOT Python layer has historically used
`/opt/otel-instrument`. Follow the documentation for the exact selected layer;
do not install both layers or combine their wrapper paths.

## Choose the export path

Backends still block implementation. Record whether traces go to AWS X-Ray or
to an OTLP backend such as a gateway Collector/Langfuse/APM. The choice changes
the Collector and propagator configuration.

For a community instrumentation layer, add a Collector Lambda layer unless an
external Collector is explicitly configured; the instrumentation layer does
not include one. Prefer local extension export over making the handler wait on
a remote vendor request. Keep credentials and fan-out in Collector
configuration, not in handler code.

Do not enable a Lambda layer, a hand-built in-code provider, and another
automatic launcher together. That creates duplicate invocation spans and
competing flush owners.

## Propagators

For OpenTelemetry spans exported to AWS X-Ray from a Lambda with active X-Ray
tracing, configure:

```text
OTEL_PROPAGATORS=tracecontext,xray-lambda
```

Do not include both `xray` and `xray-lambda`; that prevents the Lambda-specific
propagator from working correctly.

When exporting OpenTelemetry traces to a backend other than AWS X-Ray, do
**not** use `xray-lambda`; upstream warns that it breaks the reported traces.
Use `tracecontext` for W3C carriers. Add `baggage` only when discovery approved
an allowlisted cross-service value and `baggage.md` was loaded. Add the ordinary
`xray` propagator only when the selected trigger contract actually carries an
X-Ray header that must be extracted.

## Invocation and trigger boundaries

The invocation instrumentation owns one function span. For a generic trigger,
the upstream convention uses the function name, `SpanKind.SERVER`,
`faas.invocation_id=context.aws_request_id`, and
`aws.lambda.invoked_arn=context.invoked_function_arn`. The convention is
development-status, so do not hand-copy additional incubating keys without
checking the pinned compatibility revision.

### API Gateway

For a proxy event, use the configured route rather than a concrete path as the
span name/`http.route`, and set the available HTTP semantic attributes from the
event. The Lambda invocation instrumentation owns the server boundary; do not
also apply FastAPI/ASGI server instrumentation unless the function actually
hosts that framework through an adapter and duplicate ownership has been
verified away.

### SQS event source mapping

Lambda owns polling and invokes the handler with a batch. Do not copy the
long-running worker loop from `worker_runtime.md` into the function.

- Keep one batch/invocation consumer boundary.
- When messages can fail independently, create one child processing span per
  message and return the matching partial-batch failure response.
- Link each message span to its valid producer context rather than making a
  multi-message batch the child of one arbitrary producer.
- Use the version-pinned Lambda instrumentation's SQS extraction when it
  supports the deployed carrier. Otherwise extract the agreed W3C message
  attribute or `AWSTraceHeader` explicitly and verify the exported links.
- Read `queue_messaging.md` for the producer side, but not for its direct
  consumer polling loop.

## Business child span

With the automatic invocation span already current, add only business work:

```python
from observability.spans import start_span


def process_price_update(update: PriceUpdate) -> None:
    with start_span("process price update", attributes={"app.pricing.source": update.source}):
        apply_update(update)
```

Keep `aws_request_id`, message IDs, customer IDs, and other high-cardinality
values on spans or structured logs only. Do not label metrics with them.

## Flush without shutdown

Configure providers once during cold start, outside the handler. Do not create
a provider per invocation and do not call `shutdown_observability()` at the end
of the handler: the execution environment may be reused.

`opentelemetry-instrumentation-aws-lambda` force-flushes trace and metric
providers after the invocation because Lambda may freeze the process. Its
timeout is controlled by the version-sensitive
`OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT`; keep enough invocation time in
reserve and verify the selected layer's default before overriding it.

If the application fully owns manual instrumentation, call `force_flush()` in
the outer wrapper's `finally` block with a bounded timeout smaller than
`context.get_remaining_time_in_millis()`. Keep the provider alive for warm
invocations. A timeout, exception, or partial SQS batch is exactly where flush
verification matters.

## Resource identity

Keep the common `service.namespace`, `service.name`, immutable
`service.version`, and `deployment.environment.name` contract from
`../setup/resource_identity.md`. Let the Lambda resource detector populate:

```text
cloud.provider = aws
cloud.platform = aws_lambda
cloud.region   = AWS_REGION
faas.name      = AWS_LAMBDA_FUNCTION_NAME
faas.version   = AWS_LAMBDA_FUNCTION_VERSION
faas.instance  = AWS_LAMBDA_LOG_STREAM_NAME
```

Do not use `context.aws_request_id` as `service.instance.id`; it identifies an
invocation, not the reused execution environment. This skill requires an
instance ID, so reuse the full `AWS_LAMBDA_LOG_STREAM_NAME` as
`service.instance.id` when available; it identifies the warm execution
environment and is also the prescribed `faas.instance` value. If a custom
runtime does not expose it, generate one UUID once at module initialization
and reuse it for the lifetime of that warm environment.

## Mock trigger fixtures

Use a fake context and a minimal event. Do not make tests depend on the entire
AWS event payload:

<!-- complete-python-template -->
```python
from types import SimpleNamespace

API_GATEWAY_EVENT = {
    "resource": "/prices/{product_id}",
    "path": "/prices/sku-123",
    "httpMethod": "GET",
    "headers": {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"},
    "requestContext": {"requestId": "api-request-1"},
}

SQS_EVENT = {
    "Records": [
        {
            "messageId": "message-1",
            "eventSource": "aws:sqs",
            "eventSourceARN": "arn:aws:sqs:eu-west-1:111122223333:pricing-jobs",
            "attributes": {
                "AWSTraceHeader": (
                    "Root=1-67891233-abcdef012345678912345678;"
                    "Parent=53995c3f42cd8ad8;Sampled=1"
                )
            },
            "messageAttributes": {},
            "body": "{\"product_id\": \"sku-123\"}",
        }
    ]
}

LAMBDA_CONTEXT = SimpleNamespace(
    aws_request_id="79104EXAMPLEB723",
    function_name="pricing-handler",
    function_version="42",
    invoked_function_arn=(
        "arn:aws:lambda:eu-west-1:111122223333:function:pricing-handler:prod"
    ),
    get_remaining_time_in_millis=lambda: 30_000,
)
```

Test success, raised exception, timeout-near-flush, warm second invocation,
multi-message SQS, invalid/missing carrier, and partial-batch failure. Assert
one invocation span, no duplicate owner, and the expected parent or links.

## Verification

- Invoke the function twice in one warm environment; provider construction
  happens once and both invocations export.
- Inspect an exported invocation span for the function/route name,
  `faas.invocation_id`, and the selected parent.
- For SQS, inspect message spans and links; do not infer success from parsing
  alone.
- Force an exception and a near-timeout path; confirm correlated logs and the
  final spans arrive.
- Check cold-start duration and extension overhead against the function's
  timeout and memory configuration.
- Confirm the deployed layer ARN matches region, architecture, runtime, and
  the package versions pinned in `../compatibility.md`.
