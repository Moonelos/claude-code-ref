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

Use fake timers only around the isolated display queue. Drive component assertions through observable UI state, and use a streaming mock that controls each chunk and terminal event explicitly. Add one browser-level test through the deployed proxy path, because unit mocks cannot reveal CDN, compression, or reverse-proxy buffering.

Related: [`transport-buffer-partial-lines`](transport-buffer-partial-lines.md), [`state-explicit-phase-machine`](state-explicit-phase-machine.md), [`security-untrusted-content`](security-untrusted-content.md)
