---
title: Make Streaming Conversations Work With Keyboard and Assistive Technology
impact: HIGH
impactDescription: avoids token-by-token announcements, focus loss, and inaccessible turn controls
tags: accessibility, aria-live, focus, keyboard, ime, chat
---

## Make Streaming Conversations Work With Keyboard and Assistive Technology

A transcript is readable content first. Do not mark the entire message list or the actively mutating answer as a live region: many screen readers will repeatedly announce growing text on every delta.

- Give the transcript a stable accessible name and semantic structure. Identify speakers in text or accessible labels rather than by color, alignment, or avatar alone.
- Put transient progress in a small `role="status"` region with `aria-live="polite"` and `aria-atomic="true"`. Update it only for meaningful phase changes, not every token or timer tick.
- When a turn settles, announce one concise completion or failure status. Leave the full answer in normal document flow so the user can navigate it at their own pace.
- Do not move focus when tokens arrive, history reconciles, or auto-scroll runs. After Send, normally keep focus in the composer; if Stop replaces Send, preserve a predictable keyboard path without forcing focus to the new button.
- If an explicit action requires restoring focus, use `composerRef.current?.focus({ preventScroll: true })`. Plain `focus()` after completion can pull a detached reader to the bottom. Do not restore composer focus after a reader has deliberately focused another control.
- Use a real form and labelled multiline control. Enter-to-send must not fire while an IME composition is active (`event.isComposing`/composition events); provide a discoverable way to insert a newline.
- Give Stop, Retry, Copy, attachment removal, and jump-to-latest controls explicit accessible names and visible focus indicators. Report copy success without moving focus.
- When the user scrolls away from the latest message, stop automatic following. The jump-to-latest control must be keyboard reachable and should state when new content is available.
- Respect reduced motion for caret animation, paced reveal, smooth scroll, and progress animation. Do not make animation the only indication of activity.

Test with keyboard-only navigation, zoom/reflow, reduced motion, and at least one screen reader in the browsers the product supports. Automated accessibility checks do not validate announcement timing or focus experience.

Related: [`pace-progress-before-first-token`](pace-progress-before-first-token.md), [`scroll-pinned-ref-not-state`](scroll-pinned-ref-not-state.md)
