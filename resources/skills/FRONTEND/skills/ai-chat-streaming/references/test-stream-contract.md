---
title: Test the Stream Contract at Adversarial Boundaries
impact: HIGH
impactDescription: catches protocol corruption, lifecycle races, unsafe rendering, and inaccessible interaction
tags: testing, sse, race-conditions, security, accessibility
---

## Test the Stream Contract at Adversarial Boundaries

Happy-path snapshots do not exercise streaming failure modes. Keep the decoder, protocol validator, reducer, reconciliation logic, and optional display queue separable enough for deterministic tests.

Minimum test matrix:

- Split every fixture at every byte boundary, including inside multi-byte UTF-8 characters, CRLF pairs, field names, and JSON payloads. The decoded event sequence must remain identical.
- Cover comments/heartbeats, BOM, LF/CRLF/CR, repeated `data:` fields, unknown event types, malformed known events, duplicate or out-of-order delta indices, and EOF without an application terminal event.
- Exercise abort before headers, before the first token, mid-token, after terminal receipt, during display backlog, on unmount, and when a retry supersedes an attempt. No stale attempt may update the active turn.
- Cover explicit failure, uncertain EOF, reconciliation failure, persisted history arriving before/after the provisional buffer, pagination during a turn, and refetch-on-focus while active.
- Verify one bubble and stable identity across completion: media does not remount, text selection survives, and the provisional/persisted copies never appear together.
- Test malicious Markdown/HTML, unsafe and encoded URLs, remote media policy, extreme nesting, large tables/code blocks, and size limits against the configured production parser and plugins.
- Test keyboard Send/Stop/Retry, IME composition, focus retention, reduced motion, scroll detachment, jump-to-latest, and live-region announcement counts.

For scroll and submission regressions, exercise these specific behaviors in a browser:

- With a real incremental stream held open, move upward by a small amount still near the end, then release another delta. The viewport must stay at the reader's position. Cover wheel, touch, and keyboard intent appropriate to the supported devices; a large programmatic `scrollTop = 0` alone misses the near-end defect.
- Return to the true end manually and through jump-to-latest. The button hides at the end; an upward gesture on non-scrollable content must not show it merely because follow detached.
- Grow the viewport or shrink/remove content while detached; the button hides if the end becomes visible. Append content while detached; it appears if the end moves offscreen. Test these even when no scroll event fires, and verify observers/queued frames are cleaned up.
- Delay an initial history response until after the stream begins. Empty or stale history must not erase progress or enable Send. Try another submission during connection and streaming; only one transport request is accepted. Navigation/unmount must still abort when the loader was skipped.
- Finish/reconcile while the reader is detached; focus restoration must not scroll them down. Verify a single progress region remains associated with the active assistant turn and clears on settlement.

Use fake timers only around the isolated display queue. Drive component assertions through observable UI state, and use a streaming mock that controls each chunk and terminal event explicitly. Add one browser-level test through the deployed proxy path, because unit mocks cannot reveal CDN, compression, or reverse-proxy buffering.

Related: [`transport-buffer-partial-lines`](transport-buffer-partial-lines.md), [`state-explicit-phase-machine`](state-explicit-phase-machine.md), [`security-untrusted-content`](security-untrusted-content.md)
