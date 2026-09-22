---
title: Treat Model Output and Remote Media as Untrusted Content
impact: CRITICAL
impactDescription: prevents streamed Markdown from becoming script execution, credential leakage, or tracking
tags: security, markdown, xss, links, images, privacy
---

## Treat Model Output and Remote Media as Untrusted Content

Model output, tool results, citations, and retrieved documents are untrusted input even when the model is instructed to be safe. Streaming does not change the trust boundary: partial and committed text must pass through the same restrictive rendering policy.

Use these defaults:

- Keep raw HTML disabled in the Markdown parser. If a product requirement enables HTML, sanitize the parsed tree with a maintained allowlist-based sanitizer configured for the actual renderer.
- Allow only required elements and attributes. Do not rely on removing `<script>` alone; event attributes, SVG, styles, iframes, and URL-bearing attributes create additional attack surface.
- Apply one URL policy to links, images, and other resources. Resolve relative URLs only against an intentional trusted base; allow approved schemes; reject credentials, control characters, and ambiguous encodings.
- Open external links with `rel="noopener noreferrer"` when using a new browsing context. Make the destination visible and never turn model text into privileged application navigation without validation.
- Treat remote images as network requests that disclose the user's IP, referrer, and viewing time. Proxy approved media, require user action, or use an allowlist according to the product's privacy model. Never forward session credentials to model-provided origins.
- Do not execute model-produced HTML, JavaScript, CSS, SVG, Mermaid directives, or chart/plugin configuration as code. Parse rich artifacts into a narrow validated data schema and render them with trusted components.
- Enforce limits on message size, nesting, table dimensions, code highlighting, image count, and URL length so hostile or accidental output cannot freeze the main thread.

Sanitization happens at the renderer boundary, after formatting normalization and before creating DOM nodes. Test the configured parser and sanitizer together; library defaults and plugins can change the effective policy.

Related: [`render-normalize-markdown-once`](render-normalize-markdown-once.md), [`test-stream-contract`](test-stream-contract.md)
