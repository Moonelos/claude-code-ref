---
title: Pass the SSE Body Through the Route Handler Unbuffered
impact: CRITICAL
impactDescription: the difference between a live stream and the whole answer arriving at once
tags: transport, sse, nextjs, proxy, headers
---

## Pass the SSE Body Through the Route Handler Unbuffered

When a Next.js route handler proxies an upstream agent, anything that reads the body before returning it — `await upstream.text()`, `await upstream.json()`, re-encoding through a `TransformStream` that awaits completion — collapses the stream. The user waits, then the full answer appears instantly. No client-side fix compensates for this; check the route first when a "stream" does not stream.

**Incorrect:**

```ts
const upstream = await fetch(gatewayURL, { method: 'POST', headers, body })
const text = await upstream.text()          // drains the stream
return new Response(text, { headers: { 'Content-Type': 'text/event-stream' } })
```

**Correct:**

```ts
export async function POST(request: NextRequest) {
  const upstream = await fetch(gatewayURL, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal: request.signal,                 // client disconnect cancels upstream
  })

  if (!upstream.ok) {
    const detail = await upstream.text().catch(() => '')
    console.error(`agent gateway error [${upstream.status}]:`, detail.slice(0, 500))
    return NextResponse.json(
      { error: 'AI service temporarily unavailable' },
      { status: upstream.status >= 500 ? 502 : upstream.status },
    )
  }

  const contentType = upstream.headers.get('content-type') ?? ''
  if (contentType.includes('text/event-stream') && upstream.body) {
    return new Response(upstream.body, {       // the ReadableStream, untouched
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        // Chat is user-specific. Prevent storage and intermediary transforms.
        'Cache-Control': 'private, no-store, no-transform',
        // Honored by nginx when response buffering is enabled there.
        'X-Accel-Buffering': 'no',
      },
    })
  }

  return NextResponse.json(await upstream.json().catch(() => ({})))
}
```

Checklist:

- Current Next.js `POST` Route Handlers are not cached by default; do not cargo-cult `dynamic = 'force-dynamic'`. If the project pins another Next.js version or enables different cache features, verify that version's route-handler contract.
- Return `upstream.body` directly; never `text()`/`json()` it on the streaming path.
- For user-specific chat, prefer `Cache-Control: private, no-store, no-transform`. Configure buffering at the actual CDN/proxy too; `X-Accel-Buffering: no` is nginx-specific and is not a portable guarantee.
- Forward `request.signal` so an aborted client tears down the upstream call.
- Send `Accept: text/event-stream` on the client fetch and branch on the response's `content-type`, so a non-streaming fallback still works.
- Never forward upstream error text to the UI; log the status and render a generic message.

Related: [`transport-buffer-partial-lines`](transport-buffer-partial-lines.md), [`transport-terminal-error-frame`](transport-terminal-error-frame.md)
