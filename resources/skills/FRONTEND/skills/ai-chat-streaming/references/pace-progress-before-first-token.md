---
title: Fill Time-to-First-Token With Real Progress, Then Yield Cleanly
impact: MEDIUM
impactDescription: covers multi-second agent latency without a dead or double-rendered UI
tags: pace, progress, loading, a11y, ux
---

## Fill Time-to-First-Token With Real Progress, Then Yield Cleanly

An agent that plans and calls tools can take 5–15 seconds before its first token. An empty transcript reads as a hang. The indicator must appear immediately, reflect what the backend is actually doing where possible, and disappear at the exact frame the first token lands — never overlap it.

**Correct (mutually exclusive by construction):**

```tsx
const showAssistant = turn.answer.length > 0
const showActivity = isTurnActive(turn) && !showAssistant

{showActivity && <AgentActivity phase={turn.progress} />}
{showAssistant && <AssistantBubble turn={turn} />}
```

Prefer backend progress frames over invented copy. Map each phase to plain language:

```ts
const PROGRESS_LABELS: Record<ProgressPhase, string> = {
  planning: 'Planning the investigation',
  searching_evidence: 'Searching evidence',
  querying_records: 'Querying records',
  verifying_answer: 'Verifying the answer',
}
```

If the backend sends no progress frames, prefer one stable generic status such as “Working…”. A rotating visual message list is only a cosmetic fallback: keep those rotations out of the live region and do not imply steps that are not happening.

Accessibility and polish:

- **Announce it once.** `role="status"`, `aria-live="polite"`, `aria-atomic="true"` on the indicator; do not mark the streaming answer as a live region or a screen reader re-reads the whole answer on every delta.
- **Announce the answer when it settles**, not while it streams — assertive live regions on streaming text are unusable.
- **Keep the indicator in the transcript flow**, at the position the answer will occupy, so the bubble does not jump when it replaces the indicator.
- **A caret is not a loading state.** Show the caret only once text exists; before that, the activity indicator is the loading state.
- **Disable the composer's submit while `isTurnActive`**, and swap it for a Stop control rather than letting a second turn stack on the first.

Related: [`state-explicit-phase-machine`](state-explicit-phase-machine.md), [`render-stable-bubble-identity`](render-stable-bubble-identity.md)
