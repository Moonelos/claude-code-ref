---
name: ai-chat-streaming
description: Build or review streaming AI chat interfaces in React and Next.js. Use when implementing a chatbot or agent UI, consuming an SSE or ReadableStream response, rendering streamed markdown, or fixing streaming defects such as text arriving in one lump, the answer reflowing or images reloading when the stream ends, duplicated messages, or auto-scroll fighting the user. Do not use for backend agent or model configuration.
---

# AI Chat Streaming UI Best Practices

Patterns for chat and agent interfaces that stream their answers. Contains 19 rules across 8 categories, prioritized by impact from critical (render continuity, transport, content safety) to incremental (display pacing). Derived from production chat UIs and web-platform contracts rather than framework demos.

## When to Apply

Reference these guidelines when:

- Building a chatbot, agent, or assistant panel in React or Next.js
- Consuming SSE or a `ReadableStream` from a route handler or gateway
- Rendering markdown that is still being written
- Proxying a streaming upstream through a Next.js route handler
- Debugging any of these symptoms:
  - the answer appears all at once instead of streaming
  - the answer visibly reflows, re-wraps, or **images reload** the moment the stream ends
  - the answer briefly appears twice, or the list jumps, after completion
  - tokens are missing or JSON parse errors appear at chunk boundaries
  - auto-scroll drags the viewport while the user is reading back
  - jump-to-latest stays visible when the reader is already at the end
  - initial history loading clears live progress or unlocks Send during a stream
  - a spinner sits above a half-streamed answer, or a caret blinks after a cancel

## Rule Categories by Priority

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Render Continuity | CRITICAL | `render-` |
| 2 | Stream Transport | CRITICAL | `transport-` |
| 3 | Content Safety | CRITICAL | `security-` |
| 4 | Turn State | HIGH | `state-` |
| 5 | Accessibility | HIGH | `a11y-` |
| 6 | Scroll Behavior | HIGH | `scroll-` |
| 7 | Testing | HIGH | `test-` |
| 8 | Pacing & Feedback | MEDIUM | `pace-` |

## The Two Defects Behind Most Complaints

**"It doesn't stream — the whole answer lands at once."** Trace the whole path: upstream provider, route handler, compression/CDN/reverse proxy, client decoder, and render throttling. A common cause is reading the body before returning it or buffering it in an intermediary. See [`transport-sse-proxy-headers`](references/transport-sse-proxy-headers.md).

**"When the stream finishes, everything reflows and the images reload."** The streaming view and the final view are different code paths. Fixing it is two rules: render both phases through one renderer ([`render-same-renderer-both-phases`](references/render-same-renderer-both-phases.md)) and keep the same element identity across the handoff ([`render-stable-bubble-identity`](references/render-stable-bubble-identity.md)). Everything else in this skill is secondary to those two.

## Quick Reference

### 1. Render Continuity (CRITICAL)

- [`render-same-renderer-both-phases`](references/render-same-renderer-both-phases.md) - One renderer for streaming and final text
- [`render-stable-bubble-identity`](references/render-stable-bubble-identity.md) - Same component and key across the handoff
- [`render-single-source-of-truth`](references/render-single-source-of-truth.md) - Never show the buffer and the persisted message at once
- [`render-normalize-markdown-once`](references/render-normalize-markdown-once.md) - Normalize agent markdown in both phases
- [`render-stable-media`](references/render-stable-media.md) - Stable identity for images, charts, and code blocks
- [`render-reserve-layout`](references/render-reserve-layout.md) - Let the bubble grow without rewrapping

### 2. Stream Transport (CRITICAL)

- [`transport-sse-proxy-headers`](references/transport-sse-proxy-headers.md) - Pass the SSE body through unbuffered
- [`transport-buffer-partial-lines`](references/transport-buffer-partial-lines.md) - Buffer partial lines when decoding
- [`transport-terminal-error-frame`](references/transport-terminal-error-frame.md) - Handle mid-stream failures as frames
- [`transport-abort-controller`](references/transport-abort-controller.md) - Own the stream with an AbortController ref

### 3. Content Safety (CRITICAL)

- [`security-untrusted-content`](references/security-untrusted-content.md) - Treat model output and remote media as untrusted content

### 4. Turn State (HIGH)

- [`state-explicit-phase-machine`](references/state-explicit-phase-machine.md) - Model a turn as one phase, not three booleans
- [`state-reconcile-after-commit`](references/state-reconcile-after-commit.md) - Reconcile after an ending; guard initial-load and polling races

### 5. Accessibility (HIGH)

- [`a11y-conversation-semantics`](references/a11y-conversation-semantics.md) - Announce settled turns and preserve keyboard and focus behavior

### 6. Scroll Behavior (HIGH)

- [`scroll-pinned-ref-not-state`](references/scroll-pinned-ref-not-state.md) - Separate follow intent from jump-button visibility; release on upward gestures
- [`scroll-instant-during-stream`](references/scroll-instant-during-stream.md) - Follow only while pinned; measure after content and viewport changes

### 7. Testing (HIGH)

- [`test-stream-contract`](references/test-stream-contract.md) - Test adversarial chunks, lifecycle races, safety, and accessibility

### 8. Pacing & Feedback (MEDIUM)

- [`pace-chunked-display`](references/pace-chunked-display.md) - Pace display independently of network chunks
- [`pace-progress-before-first-token`](references/pace-progress-before-first-token.md) - Fill time-to-first-token with real progress

## Implementation Checklist

Work top to bottom when building a new chat surface:

1. Route handler returns `upstream.body` directly; POST handlers are already dynamic in current Next.js. Apply explicit private/no-store response policy for user-specific chat and disable proxy buffering where the deployment supports it.
2. A spec-correct SSE decoder buffers partial UTF-8 and fields, dispatches on blank lines, and requires an explicit terminal event from the application protocol.
3. Validate every decoded event at the trust boundary before it reaches state.
4. Turn reducer with an explicit phase; `isTurnActive` derives every busy affordance.
5. One sanitized `formatMessage(text)` is used by streaming and committed bubbles alike.
6. One `MessageBubble` renders both, keyed by a stable logical `turn_id`; transport attempts use separate `attempt_id` values.
7. Reconcile history only on an ending; prevent initial loads and polling from overwriting the active turn's phase, progress, or submit lock. Preserve unmount/navigation abort cleanup even when skipping a loader.
8. Track follow intent in a ref and jump-button visibility from measured distance to the end. Detach on upward intent, including small gestures; measure after layout changes even when no scroll event fires. Read the scroll references when implementing this behavior.
9. Keep progress associated with the active assistant turn, normally near its speaker/avatar. Announce phase changes sparingly and the answer once when it settles; any justified focus restoration uses `preventScroll: true`.
10. Test small upward gestures during live deltas, return-to-end, non-scrollable content, resize/content shrink, initial-load races and overlapping sends, alongside protocol, safety and accessibility checks.

## Related Skills

- `react` and `vercel-react-best-practices` for memoization and re-render cost
- `nextjs` for route handler runtime, caching, and `dynamic` semantics
- `feature-arch` for keeping the decoder, reducer, and renderer in separate testable modules
- `vitest` for testing the decoder against adversarial chunk splits and the reducer against out-of-order frames
- `ui-design` and `web-design-guidelines` for the surrounding panel, empty states, and accessibility

## Reference Files

| File | Description |
|------|-------------|
| [references/_sections.md](references/_sections.md) | Category definitions and ordering |
| [metadata.json](metadata.json) | Version and reference information |
