# Sections

This file defines all sections, their ordering, impact levels, and descriptions.
The section ID (in parentheses) is the filename prefix used to group rules.

---

## 1. Render Continuity (render)

**Impact:** CRITICAL
**Description:** The single biggest source of "ugly" AI chat UIs. If the streaming view and the final view are different component trees or different renderers, the answer visibly reflows, images re-fetch, and code blocks re-highlight the instant the stream ends.

## 2. Stream Transport (transport)

**Impact:** CRITICAL
**Description:** Buffered proxies, naive line splitting, and un-aborted fetches make the stream arrive in one lump, drop characters at chunk boundaries, or keep writing into an unmounted component.

## 3. Content Safety (security)

**Impact:** CRITICAL
**Description:** Model text, citations, links, and media are untrusted input. Render them through restrictive policies so a useful Markdown feature cannot become script execution, credential leakage, or a tracking channel.

## 4. Turn State (state)

**Impact:** HIGH
**Description:** An explicit phase machine for a turn prevents double sends, orphaned spinners, duplicated messages after reconciliation, and unhandled mid-stream failures.

## 5. Accessibility (a11y)

**Impact:** HIGH
**Description:** Streaming must not create token-by-token screen-reader noise, steal focus, break IME input, or hide essential controls from keyboard users.

## 6. Scroll Behavior (scroll)

**Impact:** HIGH
**Description:** Auto-scroll that fights the user is the second most common complaint. Pinning must be a ref-tracked intent, not a blanket scrollIntoView on every token.

## 7. Testing (test)

**Impact:** HIGH
**Description:** Streaming bugs live at protocol boundaries and lifecycle races. Deterministic adversarial tests cover failures that happy-path snapshots cannot reach.

## 8. Pacing & Feedback (pace)

**Impact:** MEDIUM
**Description:** Backends emit uneven chunks. Display pacing and pre-token progress states make the same byte stream read as a smooth conversation.
