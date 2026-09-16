# Section Index Template

Every content directory gets a `README.md`. Section indexes are **intentionally minimal** — just enough to
orient the reader within that section. Don't repeat the landing page's area overview.

---

## Template

```markdown
# {Section Title}

> {One-line description of what this section covers.}

[![Tech](https://img.shields.io/badge/Tech-version-COLOR.svg)](URL)

---

## Contents

| File | Role | Topic | Reader outcome |
|------|------|-------|----------------|
| [01_name.md](01_name.md) | Foundation | Topic | What the reader can explain or decide afterward |
| [02_name.md](02_name.md) | Implementation | Topic | What the reader can build or verify afterward |

---

## Learning path

**Working result by entry 2**: {the smallest runnable result or concrete worked outcome}.

1. **Do: Topic** — produces the first visible result
2. **Understand: Topic** — explains why it works; name this explicitly if it revisits entry 1
3. **Harden: Topic** — adds the first production requirement, only when needed

**Stop here if**: {the baseline meets the reader's need}. Continue when {specific hardening, scale, or operational requirement appears}.

---

## Prerequisites

- Basic understanding of X
- [Other Section](../path/README.md)
```

The reading order is a learning contract, not a mirror of every file in the directory. Every path reaches a runnable result or concrete worked outcome within its first two entries and follows **do → understand → harden**. Keep reference-only or specialist notes in Contents and route to them only when their requirement becomes relevant.
