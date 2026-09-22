---
title: Let the Assistant Bubble Grow Without Reflowing Its Container
impact: MEDIUM
impactDescription: keeps text from rewrapping as the message widens during a stream
tags: render, layout, flexbox, cls, chat
---

## Let the Assistant Bubble Grow Without Reflowing Its Container

A bubble sized to its content changes width as tokens arrive: the first word makes a narrow pill, the next sentence widens it, and every already-rendered line rewraps. Combined with a long code block or table, an unconstrained flex child also blows out the panel and introduces a horizontal scrollbar.

Assistant bubbles should claim their final width immediately; only user bubbles hug their content.

**Incorrect:**

```tsx
<Stack direction="column" className="max-w-[80%] gap-1">
  {formatMessage(text)}   {/* width tracks content → rewraps each delta */}
</Stack>
```

**Correct:**

```tsx
<Stack
  direction="column"
  className={cn(
    'gap-1',
    msg.role === 'user' ? 'max-w-[80%]' : 'min-w-0 flex-1',
  )}
>
  <Box className="rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed break-words">
    {formatMessage(msg.content)}
  </Box>
</Stack>
```

- `flex-1` makes the assistant bubble full width from the first token, so nothing rewraps as it fills.
- `min-w-0` is required — without it a flex child refuses to shrink below its content's intrinsic width and a wide table pushes the panel sideways.
- `break-words` plus `[overflow-wrap:anywhere]` on the markdown wrapper handles unbroken tokens like long URLs or ids.
- Wide blocks get their own scroller rather than scrolling the panel: `<Box className="overflow-x-auto">` around tables and `overflow-hidden` on `pre`.

Related: [`render-stable-media`](render-stable-media.md), [`scroll-pinned-ref-not-state`](scroll-pinned-ref-not-state.md)
