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
- **Create the thread id client-side** for the first message of a new conversation (`crypto.randomUUID()`), then `history.replaceState` to the thread URL. Waiting for the server to mint an id forces a remount of the whole conversation mid-stream.

Related: [`render-single-source-of-truth`](render-single-source-of-truth.md), [`state-explicit-phase-machine`](state-explicit-phase-machine.md)
