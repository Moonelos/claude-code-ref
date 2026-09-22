---
title: Give Streamed Images, Charts, and Code Blocks Stable Identity
impact: HIGH
impactDescription: stops images re-fetching and charts re-animating on every delta
tags: render, images, charts, memo, streaming
---

## Give Streamed Images, Charts, and Code Blocks Stable Identity

Every delta re-renders the markdown tree. Any node that is expensive or stateful — an `<img>`, a chart component, a highlighted code block, an iframe — is rebuilt on each token unless its identity is stable. Symptoms: images flash white or show a loading placeholder repeatedly, charts replay their entry animation, code blocks flicker as the highlighter re-runs.

**Incorrect (new component identity every delta):**

```tsx
img: {
  component: ({ src, alt }) => <img src={src} alt={alt} />, // inline arrow: new type each render
}
```

Defining override components inline inside the render body gives them a new function identity on every render, which forces a remount even when props are unchanged.

**Correct (module-level components, memoized, keyed by content):**

```tsx
// module scope — one stable component type for the app's lifetime
const MarkdownImage = React.memo(function MarkdownImage({
  src,
  alt,
}: { src?: string; alt?: string }) {
  if (!src) return null
  return <img src={src} alt={alt ?? ''} loading="lazy" decoding="async" />
})

export const messageMarkdownOptions = {
  overrides: {
    img: { component: MarkdownImage },
    pre: { component: CodeBlock },   // also module-level + memo
  },
}
```

Additional guards:

- **Reserve the box.** Set explicit `width`/`height` or an `aspect-ratio` on media so a late-loading image does not shove the transcript down mid-stream.
- **Don't render an image from a half-streamed URL.** `![x](https://cdn/ima` is a valid markdown image with a broken src; it fires a failed request and paints a broken-image icon. Skip rendering `img` when the source is inside the last line of an actively streaming message, or only commit media once the enclosing block is closed.
- **Memoize by content, not by position.** `React.memo` on the code block keyed off the code string keeps the highlighter from re-running while later paragraphs stream in.

Related: [`render-same-renderer-both-phases`](render-same-renderer-both-phases.md), [`render-reserve-layout`](render-reserve-layout.md)
