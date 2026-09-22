---
title: Normalize Agent Markdown Before Rendering, in Both Phases
impact: HIGH
impactDescription: prevents tables and lists rendering as raw text mid-stream
tags: render, markdown, normalization, tables, streaming
---

## Normalize Agent Markdown Before Rendering, in Both Phases

Agent output is not clean GFM. It glues tables onto the preceding sentence, uses `1)` instead of `1.`, and emits stray indentation. Strict parsers (`markdown-to-jsx` among them) then render a whole table as a paragraph of pipes. Because the fix usually gets applied only on the final message, the table "snaps into place" when the stream ends — another reflow.

Normalize inside the shared renderer so streaming and committed text get identical treatment.

**Correct:**

```tsx
const TABLE_ROW = /^\s*\|.*\|\s*$/

function isTableDelimiterRow(line: string): boolean {
  return /^\s*\|?[\s|:-]+\|?\s*$/.test(line) && line.includes('-')
}

// markdown-to-jsx only parses a table when its header row starts a block —
// the preceding line must be blank. Agent output frequently glues a table
// straight onto the sentence above it. Insert the missing blank line.
function ensureTableBlankLines(text: string): string {
  const lines = text.split('\n')
  const out: string[] = []
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const prev = out[out.length - 1] ?? ''
    const isHeaderRow =
      TABLE_ROW.test(line) && isTableDelimiterRow(lines[i + 1] ?? '')
    if (isHeaderRow && prev.trim() !== '' && !TABLE_ROW.test(prev)) out.push('')
    out.push(line)
  }
  return out.join('\n')
}

export function normalizeMarkdown(text: string): string {
  return ensureTableBlankLines(text.replace(/^(\s*\d+)\)\s+/gm, '$1. '))
}
```

Keep normalization **pure and idempotent**. It runs on every delta, so it must not depend on stream position and must produce the same result for a prefix that it will for the full text — otherwise the layout shifts as later tokens arrive.

Normalization is formatting, not sanitization. Do not mix a few ad-hoc tag checks into this function and call the output safe. Keep raw HTML disabled by default and apply the complete element, attribute, URL, and remote-media policy from [`security-untrusted-content`](security-untrusted-content.md) at the renderer boundary.

Related: [`render-same-renderer-both-phases`](render-same-renderer-both-phases.md)
