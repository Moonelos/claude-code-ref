---
title: Model a Turn as an Explicit Phase Machine
impact: HIGH
impactDescription: removes contradictory UI states like a spinner over a streaming answer
tags: state, reducer, state-machine, turn, chat
---

## Model a Turn as an Explicit Phase Machine

Three independent booleans (`isLoading`, `isStreaming`, `hasError`) permit eight combinations, most of which are nonsense, and every render site has to re-derive intent from them. The visible symptoms are a thinking indicator sitting above a half-streamed answer, a Send button enabled mid-turn, or an error bubble under a successful answer.

Give a turn one phase and one reducer.

**Correct:**

```ts
export type TurnPhase =
  | 'idle'
  | 'submitting'          // request sent, no frame yet
  | 'streaming_progress'  // tool/progress frames, no text yet
  | 'streaming_answer'    // text deltas arriving
  | 'completed'
  | 'failed'
  | 'uncertain'           // stream died; saved history is being checked
  | 'cancelled'

const ACTIVE = new Set<TurnPhase>([
  'submitting', 'streaming_progress', 'streaming_answer',
])
export const isTurnActive = (s: TurnState) => ACTIVE.has(s.phase)

function applyEvent(state: TurnState, event: AgentEvent): TurnState {
  switch (event.event) {
    case 'run.started':
      if (state.phase !== 'submitting') throw new Error('Turn already started')
      return { ...state, phase: 'streaming_progress', turnId: event.turn_id }
    case 'progress':
      return { ...state, phase: 'streaming_progress', progress: event.data.phase }
    case 'answer.delta':
      if (event.data.index !== state.nextDeltaIndex) {
        throw new Error('Unexpected answer delta')   // ordering violation
      }
      return {
        ...state,
        phase: 'streaming_answer',
        answer: state.answer + event.data.text,
        nextDeltaIndex: state.nextDeltaIndex + 1,
      }
    case 'run.completed':
      return { ...state, phase: 'completed', citations: event.data.citations }
    case 'run.failed':
      return { ...state, phase: 'failed', failure: { ...event.data } }
  }
}
```

What this buys:

- **One derived predicate.** `isTurnActive(turn)` drives the composer's disabled state, the Stop button, and the spinner — they can never disagree.
- **Lock submission synchronously.** Acquire a ref/attempt owner before the first `await`; React's next render is too late to reject two submissions in the same tick. Keep the lock through connecting and required reconciliation. Only the owning attempt or authoritative recovery may settle it; an unrelated history loader may not unlock it.
- **Rejected stray frames.** Validate `thread_id`, logical `turn_id`, and current `attempt_id` on every event and reject a mismatch, so a late frame from a superseded attempt cannot append text to the current answer.
- **Ordered deltas.** An explicit `index` on each delta catches out-of-order or duplicated frames instead of silently corrupting the answer.
- **Distinguish loading from progress.** An empty-answer loading indicator yields when text arrives. If meaningful backend progress remains visible during streaming, put it inside the same assistant turn as a separate status; do not render a second answer bubble or a redundant loading panel.

Keep the reducer pure and in its own module. It is the part of a chat UI with the most edge cases and the cheapest tests.

Related: [`state-reconcile-after-commit`](state-reconcile-after-commit.md), [`transport-terminal-error-frame`](transport-terminal-error-frame.md)
