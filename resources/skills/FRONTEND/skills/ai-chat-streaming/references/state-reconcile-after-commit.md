---
title: Reconcile With Server History Only After the Turn Commits
impact: HIGH
impactDescription: prevents the transcript jumping or duplicating at the end of a stream
tags: state, reconciliation, optimistic, history, chat
---

## Reconcile With Server History Only After the Turn Commits

The user message is optimistic and the assistant answer lives in a client buffer; the server holds the durable copy of both. Refetching history while the stream is still running replaces the optimistic user bubble with a server one mid-flight — the list reorders, the scroll position jumps, and the streaming bubble can briefly render twice.

Sequence it: stream → terminal frame → refetch → swap.

**Correct:**

```tsx
async function runAttempt(payload: InvokeRequest) {
  dispatch({ type: 'begin', payload })
  try {
    await invokeAgent(payload, { signal, onEvent: (e) => dispatch({ type: 'event', event: e }) })
    await reconcile(payload.thread_id)         // only after the terminal frame
  } catch (error) {
    // ...classify; reconcile for cancelled / uncertain endings too
  }
}

async function reconcile(threadId: string) {
  try {
    const [threadPage, messagePage] = await Promise.all([
      loadThreads(),
      loadMessages(threadId),
    ])
    setThreads(threadPage.items)
    setMessages(messagePage.items)
  } catch {
    // The provisional state stays visible; a later navigation or retry fixes it.
  }
}
```

Rules:

- **Never reconcile mid-stream.** Not on `progress` frames, not on a `visibilitychange`, not on a window focus refetch. Disable any automatic refetch-on-focus for the transcript query while a turn is active.
- **Reconcile on every ending, not just success** — cancelled and uncertain endings also need the server's view, since the backend may have persisted a partial or complete answer.
- **Let a failed reconcile be non-fatal.** The optimistic transcript is still correct enough to read; throwing away the answer because a history refetch 500'd is worse than showing stale state.
- **Merge, don't replace, when paginating.** "Load older messages" prepends a page; merge by message id so the streaming turn at the bottom is untouched.
- **Guard the initial-load race.** Creating/selecting a conversation can trigger a history effect while submission starts. Skip that load while the transport owns the turn, and reject stale responses from loads already in flight. An empty history response must not clear progress, reset the phase to idle, or unlock Send.
- **Gate polling from submission onward.** Checking only for a streaming bubble is too late: there is no bubble yet while connecting. Suspend active-turn polling and automatic refetches whenever the transport is active; recover saved work after an ending or when no transport owns the turn.
- **Keep cleanup when skipping work.** A loader effect's early return must not remove the only abort-on-unmount/navigation path. Give the stream a separate lifecycle owner or return its required cleanup on every branch.
- **Preserve identity across thread creation.** Use client-generated IDs only when the API supports them. If the server creates the conversation, obtain its ID before opening the stream and keep the chat/bubble identity stable through selection and URL updates.

Related: [`render-single-source-of-truth`](render-single-source-of-truth.md), [`state-explicit-phase-machine`](state-explicit-phase-machine.md)
