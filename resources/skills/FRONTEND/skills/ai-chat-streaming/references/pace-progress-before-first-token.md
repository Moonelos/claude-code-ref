---
title: Fill Time-to-First-Token With Real Progress, Then Yield Cleanly
impact: MEDIUM
impactDescription: covers multi-second agent latency without a dead or double-rendered UI
tags: pace, progress, loading, a11y, ux
---

## Fill Time-to-First-Token With Real Progress, Then Yield Cleanly

An agent that plans and calls tools can take seconds before its first token. An empty transcript reads as a hang. Show immediate activity for the submitting phase, then prefer meaningful backend progress. The empty-answer loading treatment yields when text arrives; a compact progress status may remain during streaming if the product requests it.

**Keep activity and text in one stable assistant turn:**

```tsx
<AssistantBubble
  key={turn.logicalId}
  turn={turn}
  progress={isTurnActive(turn) ? turn.progress : undefined}
  showEmptyLoading={isTurnActive(turn) && turn.answer.length === 0}
/>
```

Normally place the status near the assistant speaker/avatar, above the answer.
Keep it associated with the active turn rather than a detached status above the
composer, unless the product explicitly chooses a different placement. Avoid
duplicating an assistant label when a provisional loading bubble becomes a streamed
answer. Clear active progress when the turn settles; announce completion separately.

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
