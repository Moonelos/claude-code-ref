---
title: Handle Mid-Stream Failures as Frames, Not HTTP Status
impact: HIGH
impactDescription: turns a silently truncated answer into a visible, retryable error
tags: transport, sse, errors, retry, resilience
---

## Handle Mid-Stream Failures as Frames, Not HTTP Status

Once the first SSE byte is written the HTTP status is committed to 200. A model provider timing out at token 400 cannot be reported as a 502 — it arrives as a terminal error frame, or as a stream that simply ends. Code that only checks `response.ok` leaves a half-finished answer on screen with the caret still blinking.

**Correct (treat the error frame as a throw):**

```ts
if (event.error) {
  // Once the SSE stream is open the HTTP status is committed to 200, so the
  // backend reports mid-stream failures as a terminal error frame. Throw so
  // the caller's catch renders the generic message + retry affordance.
  throw new Error(
    typeof event.error === 'string' ? event.error : 'agent_stream_error',
  )
}

if (event.done) {
  // Prefer the server's canonical answer over the locally accumulated text —
  // it may be post-processed — but fall back to the buffer.
  finalData = {
    answer: typeof event.answer === 'string' ? event.answer : accumulated,
    evidence: event.evidence,
    sessionId: event.session_id ?? sessionId,
  }
  return
}
```

Three distinct endings, three distinct treatments:

| Ending | Signal | UI |
| --- | --- | --- |
| Success | terminal `done` frame | commit the answer, show actions |
| Explicit failure | `error` frame | error bubble + Retry, keep the partial text |
| Truncation | reader closes with no terminal frame | mark the turn *uncertain*, refetch history, then reconcile |

The third is the one usually missed. A connection dropped by a proxy produces a clean `done: true` from `reader.read()` without any terminal frame. Do not treat that as success: the backend may have persisted the answer, so refetch history and let the server's copy win rather than committing a partial buffer.

```ts
} catch (error) {
  if (controller.signal.aborted) {
    dispatch({ type: 'cancelled' })
    await reconcile(threadId)
  } else if (error instanceof ProtocolError) {
    dispatch({
      type: 'uncertain',
      message: 'The connection ended unexpectedly. Saved history is being checked.',
    })
    await reconcile(threadId)
  } else {
    dispatch({ type: 'transport-failed', failure: { message, retryable: true } })
  }
}
```

Retry the same logical `turn_id` with a new `attempt_id`. Reuse an `idempotency_key` only according to the backend contract. Prefer updating the failed turn in place; do not delete the user's question merely to hide a failed attempt, because that loses conversational history and can surprise assistive-technology users.

Related: [`state-explicit-phase-machine`](state-explicit-phase-machine.md), [`state-reconcile-after-commit`](state-reconcile-after-commit.md)
