# Collection Index Template

The root `README.md` is the canonical landing page for the notes collection. It tells readers what
the collection covers, how it is organized, and where to start.

Adapt this template to scale: a small flat collection can list its notes directly in the root
README. Use section indexes and two-level navigation only when real content directories exist.
Do not create directories or extra learning paths just to match this example.

For badge hex codes and logo names, see `../badges.md`.

---

## Template

```markdown
# {Topic} Notes

> {One-line tagline describing the scope — practical, not academic.}

[![Badge1](https://img.shields.io/badge/Label-version-COLOR.svg?logo=name&logoColor=white)](URL)
[![Badge2](https://img.shields.io/badge/Label-version-COLOR.svg?logo=name&logoColor=white)](URL)

---

## Start here

| If you want to… | Start with | Working outcome |
|---|---|---|
| {Reader goal} | [{First useful entry}]({path}.md) | {Visible result or concrete capability} |
| {Reader goal} | [{First useful entry}]({path}.md) | {Visible result or concrete capability} |

---

## Contents

| Area | Covers | Start here |
|---|---|---|
| **{Area name}** | {Questions this area helps answer} | [{Start or explore label}]({area}/README.md) |
| **{Area name}** | {Concrete capabilities covered here} | [{Start or explore label}]({area}/README.md) |
| **{Area name}** | {Systems, trade-offs, or workflows covered here} | [{Start or explore label}]({area}/README.md) |

The landing page stops at section-level navigation. Each linked section index owns its detailed
list of guides; learning paths below may link directly to selected guides.

---

## Learning paths

> **Not sure where to start?** Pick the path that matches your goal.

### Path Name

**For**: {reader starting point and goal}

**Assumed knowledge**: {explicit general skills; link to needed prerequisite bridges}

**First useful milestone**: {entry and concrete result, with a reason for necessary prerequisites}

**Understanding checkpoint**: {new scenario the reader can explain, with a worked solution}

1. [Do: Topic](path/to/file.md) — produces the first visible result
2. [Understand: Topic](path/to/file.md) — explains why that result works; may revisit entry 1 explicitly
3. [Harden: Topic](path/to/file.md) — adds the first production requirement, only if needed

**Stop here if**: {the baseline already meets the reader's need}. Continue to {next path/note} when {specific production or specialist requirement appears}.

---

## What's changing

> Checked {YYYY-MM-DD}. The notes teach {version baseline}; these items affect choices beyond it.

| Item | Status | Why it matters to you | Covered in | Source |
|---|---|---|---|---|
| {Feature or practice} | GA / PREVIEW / DEPRECATED / EMERGING | {Decision or example it changes} | [{note}]({path}.md) or "not yet" | [{source}]({url}) |

---

[Glossary](GLOSSARY.md): every term used in these notes, with a link to where it is taught.
```

---

## Key rules

- Put **Start here** immediately after the introduction and route common reader goals to a useful
  first result
- Follow it with **Contents** organized around reader intent, not directory shape
- For collections with content directories, use landing page → section index → individual notes
- In larger collections, the landing page lists areas and section indexes own detailed guide listings
- Learning paths may link directly to the few leaf notes that form the route
- Use compact grouped Area / Covers / Start here tables that render in ordinary Markdown viewers
- Keep card titles and descriptions parallel, concise, and free of decorative emoji
- Add a small `Repository layout` tree only when contributors genuinely need it; it is secondary,
  never the primary navigation
- Choose named paths that serve the actual audience goals; do not force a path count
- Aim for an early concrete result; entry two is a diagnostic target, not a universal limit
- Paths teach prerequisites before relying on them, establish a concrete model, then deepen and harden; label revisits
- One named path is for a first-time reader and reaches a complete useful outcome before production deep dives or references
- Each path states its audience, working result, and stop point
- Omit the `*Last updated*` line unless the user requests it — it goes stale immediately
- Include **What's changing** for an evolving subject, with a checked date on the section itself
  rather than on the whole page; drop it for a stable or version-pinned subject
- Link `GLOSSARY.md` once, after the paths; it is a lookup aid, not an entry point
