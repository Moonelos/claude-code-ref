---
title: Never Show the Streaming Buffer and the Persisted Message at Once
impact: CRITICAL
impactDescription: prevents the answer appearing twice for one or more frames
tags: render, state, duplication, reconciliation, chat
---

## Never Show the Streaming Buffer and the Persisted Message at Once

When the turn completes, two representations of the same answer exist: the accumulated streaming buffer and the server-persisted message that arrives from a history refetch. If both are rendered, the answer flickers as a duplicate — or the list jumps as one replaces the other.

Pick one source per turn and filter the other out by a correlation id the client generated before sending.

**Incorrect (buffer and history both rendered):**

```tsx
{messages.map((m) => <MessageBubble key={m.id} msg={m} />)}
{streamingText && <StreamingBubble text={streamingText} />}
// after reconcile(), messages contains the same answer → shown twice
```

**Correct (correlate on a client-generated logical turn id):**

```tsx
const activeTurnId = turn.payload?.turn_id
const showStreamed = turn.answer.length > 0

// the persisted copy of the in-flight turn is hidden while the buffer is shown
const visibleMessages = showStreamed
  ? messages.filter((m) => m.turn_id !== activeTurnId)
  : messages
```

Use distinct identifiers with explicit contracts:

- `turn_id` (or `correlation_id`) identifies the logical user/assistant turn and remains stable across retries and persistence. Use it for rendering and reconciliation.
- `attempt_id` is new for every transport attempt, so late frames from a superseded attempt can be rejected.
- `idempotency_key` follows the backend's persistence contract. Reuse it when retrying the same logical operation if the backend supports idempotency; do not assume a correlation id provides idempotency by itself.

Have the backend echo the logical `turn_id` on persisted messages so an interrupted turn can recover from history without duplicating.

Order the handoff so it never gaps:

1. Stream completes; buffer still rendered, now with the final chrome (citations, copy button).
2. Refetch history in the background.
3. Clear the buffer only once the persisted message with that `turn_id` is present in state.

Clearing the buffer *before* the refetch lands leaves an empty frame — the answer vanishes and reappears.

Related: [`state-reconcile-after-commit`](state-reconcile-after-commit.md), [`render-stable-bubble-identity`](render-stable-bubble-identity.md)
