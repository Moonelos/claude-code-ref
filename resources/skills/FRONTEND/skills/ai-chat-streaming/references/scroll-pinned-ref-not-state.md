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
const SCROLL_BOTTOM_THRESHOLD = 100   // "near enough" to keep the button hidden
const SCROLL_REENGAGE_THRESHOLD = 4   // must be truly at the bottom to re-pin

const detachAutoScroll = useCallback(() => {
  isScrollPinnedRef.current = false
}, [])

const handleScrollChange = useCallback(() => {
  const el = scrollAreaRef.current
  if (!el) return
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  const isNearBottom = distanceFromBottom < SCROLL_BOTTOM_THRESHOLD
  const isAtBottom = distanceFromBottom <= SCROLL_REENGAGE_THRESHOLD
  const isScrollingUp = el.scrollTop < previousScrollTopRef.current - 1

  previousScrollTopRef.current = el.scrollTop

  if (isAtBottom) isScrollPinnedRef.current = true
  else if (isScrollingUp || !isNearBottom) detachAutoScroll()

  setShowScrollDown(!isNearBottom)          // the only state this writes
}, [detachAutoScroll])
```

Listen for intent directly, not just for the resulting scroll position — programmatic scrolling also fires `scroll`, so gesture listeners are what distinguish the user from the app:

```tsx
el.addEventListener('scroll', handleScrollChange)
el.addEventListener('wheel', handleWheel, { passive: true })       // deltaY < 0 → detach
el.addEventListener('touchstart', handleTouchStart, { passive: true })
el.addEventListener('touchmove', handleTouchMove, { passive: true }) // moved down → detach
```

Supporting behaviors:

- **Re-pin on send.** Set `isScrollPinnedRef.current = true` when the user submits — they expect to see their own message.
- **Offer a way back.** Show a "jump to latest" button whenever `showScrollDown` is true; clicking it re-pins and scrolls smoothly.
- **Two asymmetric thresholds.** A generous threshold hides the jump button near the bottom; a tight one re-pins only at the true bottom, so a small upward nudge is not undone.

Related: [`scroll-instant-during-stream`](scroll-instant-during-stream.md)
