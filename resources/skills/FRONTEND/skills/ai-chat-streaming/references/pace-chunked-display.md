---
title: Pace Display Independently of Network Chunks
impact: MEDIUM
impactDescription: turns lumpy backend batches into an even, readable stream
tags: pace, animation, streaming, reduced-motion, ux
---

## Pace Display Independently of Network Chunks

Backends batch. A tool-calling agent can go silent for eight seconds and then emit a 600-character paragraph in one frame. Rendering deltas exactly as they arrive gives a stuttering wall-of-text effect that reads as broken even though nothing failed.

Decouple *arrival* from *display* with a bounded display queue. The network reader must enqueue and continue reading; it must never await the animation of one delta before reading the next protocol event.

**Correct:**

```ts
const DISPLAY_CHUNK_SIZE = 12
const DISPLAY_INTERVAL_MS = 22

function shouldPaceStream(): boolean {
  return !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

const displayQueue: string[] = []

function onNetworkEvent(event: AgentEvent) {
  if (event.event === 'answer.delta' && shouldPaceStream()) {
    displayQueue.push(...splitIntoDisplayChunks(event.data.text))
    scheduleDisplayPump() // do not await; the stream reader keeps draining
    return
  }
  if (isTerminal(event)) {
    flushDisplayQueue()   // answer is complete before final chrome appears
    dispatch(event)
    return
  }
  dispatch(event)
}
```

Non-negotiables:

- **Respect `prefers-reduced-motion`.** Paced reveal is an animation; users who opt out get the full delta immediately.
- **Never block the network reader.** The queue and its timer/rAF pump are separate from protocol consumption.
- **The pacer must observe abort and unmount.** Cancel its timer and clear its queue immediately.
- **Do not reuse transport ordering indices for display chunks.** Validate ordering before the display layer; the display queue is a derived presentation buffer.
- **Flush or explicitly discard on terminal events.** Completion/error must not sit behind seconds of cosmetic animation.
- **Bound the backlog and catch up.** If queued text exceeds a small time or character budget, increase chunk size or flush; never keep typing long after the server finished.
- **Keep it optional.** Respect reduced motion and consider no pacing at all for fast streams, background tabs, and users who prefer immediate text.

Related: [`pace-progress-before-first-token`](pace-progress-before-first-token.md), [`scroll-instant-during-stream`](scroll-instant-during-stream.md)
