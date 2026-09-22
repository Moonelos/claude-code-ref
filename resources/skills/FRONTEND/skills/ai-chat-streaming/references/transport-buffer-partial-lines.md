---
title: Buffer Partial Lines When Decoding the SSE Stream
impact: CRITICAL
impactDescription: prevents dropped tokens and JSON parse failures at chunk boundaries
tags: transport, sse, decoding, textdecoder, parsing
---

## Buffer Partial Lines When Decoding the SSE Stream

Network chunks do not align to SSE frames. A `reader.read()` can return `data: {"delta":"hel` with the rest arriving next tick. Code that splits each chunk independently silently drops that frame — the classic "some words are missing from the stream" bug. A multi-byte UTF-8 character split across chunks produces a replacement character unless the decoder is told more is coming.

**Incorrect:**

```ts
const { value } = await reader.read()
const text = new TextDecoder().decode(value)     // no stream: true
for (const line of text.split('\n')) processLine(line)  // last line may be partial
```

**Correct foundation (byte decoding only):**

```ts
const reader = response.body!.getReader()
const decoder = new TextDecoder()

try {
  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    // Feed decoded text to a real SSE parser. Do not assume chunks, lines,
    // data fields, and application events have the same boundaries.
    sseParser.push(decoder.decode(value, { stream: true }))
  }

  sseParser.push(decoder.decode())                         // flush UTF-8 decoder
  sseParser.finish()
} finally {
  reader.releaseLock()
}
```

A correct SSE parser handles an optional UTF-8 BOM, `\r\n`, `\n`, and lone `\r`; ignores comment lines; accumulates repeated `data:` fields joined with `\n`; tracks `event`, `id`, and `retry`; and dispatches only on the blank-line terminator. Prefer a small, maintained SSE parser over reproducing the algorithm inline.

Separate transport parsing from application validation. Unknown event types may be ignored for forward compatibility, but malformed JSON or a known event with an invalid schema is a protocol error—not a silently dropped token. Validate parsed payloads before dispatching them to the reducer. EOF without the application's explicit terminal event is an uncertain ending even if the SSE syntax itself was valid.

Related: [`transport-sse-proxy-headers`](transport-sse-proxy-headers.md)
