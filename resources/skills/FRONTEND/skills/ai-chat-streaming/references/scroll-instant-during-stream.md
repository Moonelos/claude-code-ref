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
const syncScrollPosition = useCallback(() => {
  const el = scrollAreaRef.current
  if (!el) return
  // Check intent inside the frame: the reader may have detached since scheduling.
  if (isScrollPinnedRef.current) {
    el.scrollTop = el.scrollHeight
    previousScrollTopRef.current = el.scrollTop
  }
  setShowScrollDown(
    el.scrollHeight - el.scrollTop - el.clientHeight > SCROLL_END_TOLERANCE,
  )
}, [])

// Follow growing content only while pinned; always measure button visibility.
useEffect(() => {
  const frame = requestAnimationFrame(syncScrollPosition)
  return () => cancelAnimationFrame(frame)
}, [messages, streamingText, progress, syncScrollPosition])

// Resizing or content shrink/growth may change the end without a scroll event.
useEffect(() => {
  const el = scrollAreaRef.current
  if (!el) return
  let frame = 0
  const observer = new ResizeObserver(() => {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(syncScrollPosition)
  })
  observer.observe(el)
  if (el.firstElementChild) observer.observe(el.firstElementChild)
  return () => {
    observer.disconnect()
    cancelAnimationFrame(frame)
  }
}, [syncScrollPosition])
```

Details:

- **Observe both viewport and content.** Use the actual content wrapper (the first child in this example). Replace or reattach observers if those nodes change; the example assumes stable mounted elements. Visibility updates still run while detached and must never re-pin by themselves.
- **Only user actions re-pin.** A jump-to-latest action sets the ref and scrolls once, smoothly unless reduced motion is requested. Sending a new question also re-pins. Token/layout callbacks never turn a false ref back to true.
- **`requestAnimationFrame` before scrolling**, so the new content is laid out and `scrollHeight` is final; scrolling in the same tick lands short by one delta.
- **Scroll the owned container.** Assigning `scrollTop = scrollHeight` clamps to its true maximum, including padding. A sentinel can also work, but avoid `scrollIntoView` moving outer page containers and keep any sentinel after bottom padding.
- **Resync `previousScrollTopRef` after programmatic scrolls**, or the next `scroll` event reads the jump as the user scrolling and detaches pinning immediately.
- **Honor `prefers-reduced-motion`** — fall back to `'auto'` for the user-initiated case too.
- Consider `overflow-anchor: none` on the transcript container if the browser's own scroll anchoring interferes with the pinning logic.
- Keep the jump control out of transcript sizing (for example, position it over the composer). Showing/hiding it must not itself change the measured end and create a visibility loop.

Related: [`scroll-pinned-ref-not-state`](scroll-pinned-ref-not-state.md), [`pace-chunked-display`](pace-chunked-display.md)
