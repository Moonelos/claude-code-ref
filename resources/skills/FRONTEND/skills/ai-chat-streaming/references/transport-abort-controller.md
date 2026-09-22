---
title: Own the Stream With an AbortController Ref
impact: HIGH
impactDescription: stops orphaned streams writing into unmounted or superseded state
tags: transport, abort, cleanup, react, effects
---

## Own the Stream With an AbortController Ref

A chat stream outlives a render. Closing the panel, navigating, or sending a second question while the first is in flight leaves a reader looping and calling `setState` on a component that has moved on — two answers interleave into one bubble, or React warns about updates after unmount.

**Correct:**

```tsx
const abortControllerRef = useRef<AbortController | null>(null)

// unmount cleanup
useEffect(() => () => abortControllerRef.current?.abort(), [])

const sendQuestion = useCallback(async (question: string) => {
  if (isLoadingRef.current) return        // ref, not state: guards within one tick

  abortControllerRef.current?.abort()     // supersede any in-flight turn
  const controller = new AbortController()
  abortControllerRef.current = controller

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    // ...consume the stream...
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    // real failure → error bubble
  } finally {
    if (abortControllerRef.current === controller) {
      abortControllerRef.current = null     // don't clear a newer controller
    }
    isLoadingRef.current = false
  }
}, [/* deps */])
```

Points that matter:

- **Guard re-entry with a ref, not state.** `isLoading` state has not updated yet when a double Enter fires in the same tick.
- **Swallow `AbortError`.** An abort is a user action, not a failure; rendering an error bubble for it is noise.
- **Compare identity before clearing.** `if (abortControllerRef.current === controller)` prevents a finishing old turn from nulling the new turn's controller.
- **Reset the streaming buffer in `finally`**, so a cancelled turn does not leave a stale caret blinking under a dead message.
- **Expose cancel to the user.** A visible Stop button during a turn is the difference between a stuck UI and a responsive one.

Related: [`state-explicit-phase-machine`](state-explicit-phase-machine.md)
