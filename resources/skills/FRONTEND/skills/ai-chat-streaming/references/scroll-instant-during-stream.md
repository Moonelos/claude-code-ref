---
title: Scroll Instantly While Streaming, Smoothly Only for User Actions
impact: MEDIUM
impactDescription: removes the stuttering "chasing" scroll during fast streams
tags: scroll, animation, streaming, ux
---

## Scroll Instantly While Streaming, Smoothly Only for User Actions

`behavior: 'smooth'` animates over ~300ms. Deltas arrive faster than that, so each new token interrupts the previous animation and the viewport lurches and stutters, never catching the bottom. Smooth scrolling belongs to discrete user actions; token-driven follow must be instant.

**Correct:**

```tsx
const scrollToBottomWithBehavior = useCallback((behavior: ScrollBehavior) => {
  isScrollPinnedRef.current = true
  setShowScrollDown(false)
  requestAnimationFrame(() => {
    scrollEndRef.current?.scrollIntoView({ behavior })
    previousScrollTopRef.current = scrollAreaRef.current?.scrollTop ?? 0
  })
}, [])

// token-driven follow — instant
useEffect(() => {
  if (isScrollPinnedRef.current) scrollToBottomWithBehavior('auto')
}, [messages, isLoading, streamingText, scrollToBottomWithBehavior])

// user pressed "jump to latest" — smooth
const scrollToBottom = useCallback(
  () => scrollToBottomWithBehavior('smooth'),
  [scrollToBottomWithBehavior],
)
```

Details:

- **`requestAnimationFrame` before scrolling**, so the new content is laid out and `scrollHeight` is final; scrolling in the same tick lands short by one delta.
- **Anchor on a sentinel `<div ref={scrollEndRef} />`** as the last child rather than computing `scrollTop = scrollHeight`, which is off by any bottom padding.
- **Resync `previousScrollTopRef` after programmatic scrolls**, or the next `scroll` event reads the jump as the user scrolling and detaches pinning immediately.
- **Honor `prefers-reduced-motion`** — fall back to `'auto'` for the user-initiated case too.
- Consider `overflow-anchor: none` on the transcript container if the browser's own scroll anchoring interferes with the pinning logic.

Related: [`scroll-pinned-ref-not-state`](scroll-pinned-ref-not-state.md), [`pace-chunked-display`](pace-chunked-display.md)
