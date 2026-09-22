---
title: Render Streaming and Final Text Through the Same Renderer
impact: CRITICAL
impactDescription: eliminates the visible reflow when a stream completes
tags: render, markdown, streaming, reflow, chat
---

## Render Streaming and Final Text Through the Same Renderer

The most common AI chat defect: partial text is rendered as plain text (or `whitespace-pre-wrap`) while streaming, then re-rendered through a markdown pipeline once the turn completes. At the completion frame the entire answer reflows — headings resize, lists re-indent, tables appear, code blocks re-highlight, images re-request. Users read this as the answer "reloading".

Pipe both phases through one function. Markdown renderers tolerate half-formed input; an unclosed `**` or a partial table renders as literal text for one frame and resolves itself on the next delta.

**Incorrect (plain text while streaming, markdown at the end):**

```tsx
{isStreaming ? (
  <div className="whitespace-pre-wrap">{streamingText}</div>
) : (
  <Markdown options={markdownOptions}>{message.content}</Markdown>
)}
```

**Correct (one renderer, both phases):**

```tsx
// format-message.tsx — the single entry point for any assistant text
export function formatMessage(text: string): React.ReactNode {
  return (
    <Box className="space-y-1 text-sm leading-relaxed [overflow-wrap:anywhere]">
      <Markdown options={messageMarkdownOptions}>
        {normalizeMarkdown(text)}
      </Markdown>
    </Box>
  )
}

// streaming bubble
<Box className="text-sm leading-relaxed">
  {formatMessage(streamingText)}
  <span className="bg-primary ml-0.5 inline-block h-4 w-0.5 animate-pulse" />
</Box>

// committed bubble — identical call
<Box className="text-sm leading-relaxed">{formatMessage(msg.content)}</Box>
```

The caret is the only difference between the two phases, and it is a sibling element, so removing it does not touch the answer's layout.

If the renderer is genuinely too expensive to run per delta, throttle *the renderer input* (re-render markdown at most every ~80ms) rather than switching renderers — the output stays identical.

Related: [`render-stable-bubble-identity`](render-stable-bubble-identity.md), [`render-normalize-markdown-once`](render-normalize-markdown-once.md)
