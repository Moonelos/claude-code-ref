---
title: Track Scroll Pinning in a Ref and Release It on User Intent
impact: HIGH
impactDescription: stops auto-scroll fighting a user who is reading back
tags: scroll, refs, ux, streaming, chat
---

## Track Scroll Pinning in a Ref and Release It on User Intent

Calling `scrollIntoView` on every delta drags the viewport back to the bottom while the user is reading earlier text. Storing "should I follow?" in state re-renders the whole transcript on every scroll event. Keep the intent in a ref and update it from real user gestures.

**Correct:**

```tsx
const isScrollPinnedRef = useRef(true)
const previousScrollTopRef = useRef(0)
const SCROLL_END_TOLERANCE = 4 // example rounding tolerance, in CSS pixels

const detachAutoScroll = useCallback(() => {
  isScrollPinnedRef.current = false
  // Do not set button visibility here: an upward gesture may not move the viewport.
}, [])

const handleScrollChange = useCallback(() => {
  const el = scrollAreaRef.current
  if (!el) return
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  const isAtBottom = distanceFromBottom <= SCROLL_END_TOLERANCE
  const isScrollingUp = el.scrollTop < previousScrollTopRef.current
  const isScrollingDown = el.scrollTop > previousScrollTopRef.current

  previousScrollTopRef.current = el.scrollTop

  if (isScrollingUp) detachAutoScroll()
  else if (isScrollingDown && isAtBottom) isScrollPinnedRef.current = true

  setShowScrollDown(!isAtBottom) // geometry, independent of follow intent
}, [detachAutoScroll])
```

Listen for intent directly, not just for the resulting scroll position — programmatic scrolling also fires `scroll`, so gesture listeners are what distinguish the user from the app:

```tsx
el.addEventListener('scroll', handleScrollChange)
el.addEventListener('wheel', handleWheel, { passive: true })       // deltaY < 0 → detach
el.addEventListener('touchstart', handleTouchStart, { passive: true })
el.addEventListener('touchmove', handleTouchMove, { passive: true }) // moved down → detach
```

Also detach for ArrowUp, PageUp, Home, and Shift+Space when the transcript itself
has keyboard focus. Do not intercept those keys in the composer or other nested
controls. Track the last touch Y; increasing Y means an upward content scroll.
Clean up native listeners on unmount. React event handlers are an equivalent option.

**Follow intent and visibility are different facts.** Never derive the button as
`!isScrollPinnedRef.current`. A detached reader may be at the end after content
shrinks, the window grows, or an upward gesture hits a non-scrollable transcript.
Conversely, content can grow while detached without any scroll event. Recompute
visibility after layout changes; see the companion scroll reference.

Do not re-pin just because a queued programmatic scroll event reports "at bottom".
Require a downward movement reaching the end, an explicit jump action, or a new
submission. This prevents a tiny upward gesture from being immediately undone.

Supporting behaviors:

- **Re-pin on send.** Set `isScrollPinnedRef.current = true` when the user submits — they expect to see their own message.
- **Offer a way back.** Show a "jump to latest" button whenever `showScrollDown` is true; clicking it re-pins and scrolls smoothly.
- **Choose the visibility tolerance deliberately.** Use a small rounding tolerance when the button should appear as soon as content is offscreen. A larger "near bottom" threshold may hide the button by product choice, but must not re-enable follow after an upward gesture.

Related: [`scroll-instant-during-stream`](scroll-instant-during-stream.md)
