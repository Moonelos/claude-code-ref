---
title: Keep the Same Element Identity Across the Stream/Commit Handoff
impact: CRITICAL
impactDescription: prevents remount flashes, image re-fetches, and lost scroll position
tags: render, reconciliation, keys, remount, chat
---

## Keep the Same Element Identity Across the Stream/Commit Handoff

Even with one renderer ([`render-same-renderer-both-phases`](render-same-renderer-both-phases.md)), swapping `<StreamingBubble>` for `<MessageBubble>` unmounts the whole subtree. React tears down the DOM and rebuilds it: `<img>` elements re-request their source (the visible "image reloads" flash), syntax highlighters re-run, CSS enter-animations replay, and any in-flight text selection is lost.

Give the streaming turn and the committed message the same position and the same key so React reconciles in place.

**Incorrect (two different components in two different slots):**

```tsx
{messages.map((m, i) => <MessageBubble key={i} msg={m} />)}
{isStreaming && <StreamingBubble text={streamingText} />}
// on completion: StreamingBubble unmounts, a new MessageBubble mounts → flash
```

**Correct (one component, one key, driven by a phase prop):**

```tsx
const rendered = useMemo(() => {
  // While provisional text is visible, suppress its persisted counterpart.
  const items = messages
    .filter((m) => !turn.text || m.turnId !== turn.turnId)
    .map((m) => ({ ...m, streaming: false }))
  if (turn.text) {
    items.push({
      id: turn.turnId,         // stable across retries and stream → commit
      role: 'assistant',
      content: turn.text,
      streaming: turn.phase !== 'completed',
    })
  }
  return items
}, [messages, turn])

{rendered.map((m) => (
  <MessageBubble key={m.id} msg={m} streaming={m.streaming} />
))}
```

Two supporting requirements:

- **Key by a stable id, never by array index.** Index keys shift when history is prepended by "load older messages", remounting every bubble.
- **Keep the chrome identical.** The avatar, bubble padding, border radius, and max-width must not change between phases, or the text rewraps at the handoff even without a remount.

Related: [`render-single-source-of-truth`](render-single-source-of-truth.md), [`render-stable-media`](render-stable-media.md)
