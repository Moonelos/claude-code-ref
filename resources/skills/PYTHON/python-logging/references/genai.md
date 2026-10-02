# GenAI Logging

Apply this on top of the normal event, implementation, and security rules.

## Content stays out of logs

Never log prompts, system instructions, completions, tool arguments/results, retrieved documents, embedding inputs, or raw provider requests/responses. A tracing or evaluation system's content-capture switch does not authorize the log backend, whose retention and access controls differ.

Bounded metadata is acceptable when useful: provider, requested/response model, normalized tool or agent name, attempt, token counts, duration, finish reason, outcome, and permitted conversation/session identifiers. User-provided tool names must be normalized or kept out of grouping fields.

## Default decisions

| Situation | Decision |
| --- | --- |
| Successful model call | No routine log; latency, usage, and success belong in existing telemetry or aggregate reporting |
| Model failure inside `genai/` | No log: the capability translates it into its port error and raises (`../../python-service-architecture/references/errors.md`, "Broad except shapes") |
| Model failure the calling action degrades from (human review, default answer) | One recorded-fallback `model_fallback_activated` warning in the action, with `error.type` |
| Model failure escaping to the HTTP, job, or worker boundary | One `model_request_failed` error at that handling boundary only |
| Recovered provider/tool retry | Per `event-design.md#loops-and-pollers` |
| Provider/model fallback | `model_fallback_activated` warning |
| Guardrail block | `guardrail_blocked` |
| Agent step limit | `agent_step_limit_reached` |
| Cancellation | `agent_invocation_cancelled` |
| Empty retrieval | `retrieval_empty` |
| Summarization/compaction | `summarization_triggered` |
| Successful agent/retrieval completion | Only when audit or business search needs it independently |

Do not create success logs for every model, tool, and agent layer. One failed user operation must not produce duplicate stack traces from provider, retry middleware, tool, agent, and HTTP handler.

## Suggested fields

Use standard semantic field names already established by the project where possible, for example `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.provider.name`, `gen_ai.tool.name`, and `gen_ai.agent.name`. Add bounded `attempt`, `error.type`, and `outcome`.

Conversation, session, and user identifiers are high-cardinality and privacy-sensitive. They may appear only for an approved search purpose. They never justify logging content.

