# CLAUDE.md changes (§11)

Project `CLAUDE.md` files live in each project, not in this repo. Replace items #1, #3, #4, #5, #6, #7 and #9 of the "Code Style" list with the block below. Items #2, #8 and #10 are unchanged. The size numbers in #1 match `python-code-conventions` → "Size signals"; if they ever change, change them there first.

## What each item replaces

- **#1** replaces "Prefer functions under ~40 lines, cyclomatic complexity ≤ 10, and nesting depth ≤ 3. Treat these as review signals…": complexity is now tool-enforced, the >~60 line rule is added, and composition roots point to the architecture skill's bootstrap split rule instead of carrying a number.
- **#3** adds that a `bool`/`None` return on a public or port method is never self-explanatory.
- **#4** replaces "Around 300 lines…" with a pointer; the module-size number lives only in `python-code-conventions`.
- **#5** replaces "Organize primarily by business capability… `billing/`, `ingestion/`…", which contradicted the architecture skill's "no root business-capability packages".
- **#6** removes "Type-hint public interfaces and important internal boundaries" (mypy strict) and "Avoid mutable default arguments" (Ruff B006); adds one sentence on `Any`.
- **#7** removes "Do not use bare `except`" (Ruff E722); adds the non-re-raising `except`, one exhaustive error table, and no-`assert` rules.
- **#9** replaces the duplication sentence with the one-owner rule and adds "delete leftovers when removing a capability".
- **Removals** (tool-enforced, stated nowhere else): "type-hint public interfaces" (mypy strict), "avoid mutable default arguments" (B006), "no bare `except`" (E722). Keep "no `utils`" and "no speculative abstraction" here; the architecture skill defers to CLAUDE.md for them.

## Paste-ready block

```markdown
1. **Keep functions focused and readable.**
   Cyclomatic complexity ≤ 10 is enforced by Ruff C901. ~40 lines and nesting
   depth ≤ 3 are review signals; past ~60 lines, split the function or say why
   in the PR. Composition roots that only wire objects are exempt from the
   length signal but not from mixing concerns; the bootstrap split rule lives in
   the python-service-architecture skill. Use guard clauses and early returns
   when they make control flow clearer.

3. **Write comments that add information.**
   Public APIs should document their contract when it is not already obvious
   from the name, signature, and types. A `bool` or `None` return on a public or
   port method is never self-explanatory: document what the falsy value means,
   or return a named outcome. Comment why a decision exists, not what the code
   visibly does. Remove commented-out code and decorative banners.

4. **Keep modules cohesive.**
   When a module passes the size signal in the python-code-conventions skill
   (Size signals), review whether it contains multiple responsibilities and
   should become a package. Do not split files solely to satisfy a line count.

5. **Organize business capabilities inside the technical boundaries.**
   Business capabilities are organized inside application/ and domain/. No
   root-level peers of the technical boundaries. Give capability packages
   precise names (`billing/`, `ingestion/`, `pricing/`), never catch-all
   modules such as `utils.py`, `helpers.py`, or `common.py`.

6. **Use explicit interfaces.**
   Prefer keyword-only arguments when they improve clarity. Introduce a
   dataclass or parameter object when the values form a cohesive concept—not
   merely because an arbitrary argument count was exceeded. Use `*args` and
   `**kwargs` only for genuinely generic adapters or wrappers. Use `Any` only
   for truly dynamic values and narrow it immediately; prefer `object` plus
   `isinstance` or a typed lookup over `cast` or `# type: ignore`.

7. **Represent failures explicitly.**
   Raise specific exceptions for exceptional conditions. Do not silently
   suppress errors or use ambiguous sentinel values. `None` is acceptable for a
   legitimate optional result when expressed in the return type. An `except`
   that doesn't re-raise must catch specific types or record the failure. Map
   exceptions to public errors through one exhaustive table, never
   `getattr(exc, "code")`. No `assert` for runtime checks.

9. **Avoid speculative abstraction.**
   Prefer clear duplication over an abstraction whose shape is still changing.
   Code with identical semantics has one owner; search before writing a helper.
   When removing a capability, delete its leftovers. Do not add plugin,
   factory, or configuration layers for a single concrete use.
```
