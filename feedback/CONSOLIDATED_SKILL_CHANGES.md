# Consolidated skill changes — Python skills

Merged from the 8 feedback files in `feedback/`. They are two reviews each of four codebases, all run against copies of `resources/skills/PYTHON`:

| Tag | Codebase | Source files |
|---|---|---|
| **OPS** | Gresham `1008-automation` (ticket-monitor, lseg-worker, resolution-worker, submission-prep) | `SKILL_GUIDELINE_RECOMMENDATIONS.md`, `SKILL_IMPROVEMENT_RECOMMENDATIONS.md` |
| **CTL** | Gresham `Control` (orchestrator, worker, ctc_database) | `SKILL_GUIDELINE_RECOMMENDATIONS copy.md`, `SKILL_RECOMMENDATIONS_FROM_CODEBASE_REVIEW.md` |
| **IM** | Gresham `ControlForIM` (orchestrator, worker, im_client, platform_migrations) | `skill-guideline-review copy.md`, `skill-recommendations.md` |
| **DA** | Deep-Analyst (ingestion, investigation_agent) | `skill-guideline-review.md`, `skill-improvement-recommendations.md` |

How this file was built:

- Duplicates are merged into one rule. The **Raised by** tag shows how many codebases independently hit the problem, which is the strongest signal of priority.
- **Dropped:** items the reviewers marked "already covered / no new rule", items they considered and rejected, repo-specific code defects, and evidence paths. The evidence stays in the original files; see the list at the end.
- Conflicting recommendations are resolved inline, or listed under **§0 Decisions needed** when the choice is yours.
- **Verified 2026-09-27:** the key skill text targeted below still exists in `resources/skills/PYTHON`, so nothing here is already implemented. Examples: `settings-py.md:74` "Include concise `description=`", `ai.md:193` "Every GenAI task has `llm.py`", `engine-and-session.md:20` module-level engine, `boundaries.md:43` "at least two of these", otel `SKILL.md:87` rule 9, `shared_library.md:152` `set_status_on_exception=False`, `naming.md:210` "Do not scatter string literals", `models-and-base.md:23` `column_0_name`, `secrets-py.md:216` `global _cached_secrets`, `repo-layout.md:50` "legitimately varies".

Priority: **H** / **M** / **L**.

---

## 0. Decisions needed before editing

| # | Question | Options raised | Recommendation |
|---|---|---|---|
| D1 | Where do language-level rules live (data containers, enums, `assert`, `Any`, constructors, constants)? | New skill `python-code-conventions` (OPS, IM), or a reference `python-service-architecture/references/code-conventions.md` (CTL, DA) | **New small skill (~200 lines)**. It must trigger for any Python edit, including libs, scripts and Lambdas that never load the architecture skill. The architecture skill gets a one-line pointer. |
| D2 | Env var binding in `BaseSettings` | `case_sensitive=False` and no aliases (IM, CTL), or `alias_generator=str.upper, case_sensitive=True` (DA) | **`case_sensitive=False`, no aliases.** Add `alias=` only when the env name really differs. Mention `alias_generator` only for platforms that require case-sensitive names. Existing services change only as an explicit migration. |
| D3 | Shared YAML settings loader: extract it to a lib, or keep it per service? | Extract when copied (OPS B6, IM 3.10.6), or keep it per deployable because the guardrail is right (CTL ×2) | **Extract when ≥2 services copy it verbatim *and* the copies have drifted, or a natural shared config lib already exists.** Otherwise per-service is fine. Either way, the service owns its `Settings` *schema*. |
| D4 | Async test style | Native `async def` tests via the plugin (IM), or `asyncio.run` per test when no plugin exists (OPS F8) | **Native `async def` tests with the plugin the repo already has** (anyio or pytest-asyncio). Forbid a nested `run()` + `asyncio.run` per test body. Allow `asyncio.run` only for process-level e2e of `main()`. |
| D5 | Exception-detail setting (otel rule 9) | Graded `safe`/`full`, safe in prod, ask when PII (OPS), or one typed boolean never derived from the env name (DA) | **One typed setting whose value is set per environment in YAML**, never computed from `ENVIRONMENT_NAME` in code. The prod baseline is the safe projection. Ask when the service handles personal or financial data and no policy is stated. Remove "Do not ask." |
| D6 | Flat vs nested settings | Nested when cohesive (OPS), or flat with prefixes (CTL) | **Preserve the deployed shape.** New services start flat. Nest when related fields are consumed and validated together. No field-count threshold, and no unconditional "ask". |

---

## 1. Cross-cutting: how the skills are organized

### 1.1 Every rule has exactly one owner file — **H** · OPS, IM, DA, CTL
State each normative rule once, in the file that owns the topic. Everywhere else, write one line: "See `<file>#<section>`." Paraphrases drift, and agents can't tell which one is authoritative. The worst repeats:
- `log_full_exception_trace`: about 18 times across 10 otel files.
- flat-first growth: 7 places.
- the settings ownership test (YAML / env / secret): about 6 times.
- "no root `messaging/`": 4 times.
- adapter subpackage promotion: 3 times.
- test classification and markers: 3–4 places.
- the absolute-imports rule: stated twice, and already enforced by TID252.

### 1.2 Resolve contradictions — **H** · all four
Agents that meet conflicting instructions pick one arbitrarily, and the codebases show both choices being made.

| Contradiction | Resolution |
|---|---|
| settings `SKILL.md:240` / `env-example.md:84` "exactly three sections" vs `env-example.md:49-120` five-section template | Keep **three** (REQUIRED / OVERRIDABLE / OPTIONAL) and delete the five-section template. Allow named sub-sections inside REQUIRED (secrets, command-scoped for one-shot jobs). Omit empty sections. |
| `env-example.md`: "OVERRIDABLE lists every key of the YAML baseline" vs "no exhaustive overrides dump" | Keep "useful overrides only". |
| settings `SKILL.md:236` "`ENVIRONMENT_NAME` never has a YAML default" vs `config-yaml.md:194,207,220` YAML examples set it | Remove it from the examples. |
| settings: host/port are env-only vs `config-yaml.md`/`settings-py.md` put `app_host`/`app_port` in YAML with defaults | Remove them from the examples, or carve out "container bind address" explicitly. Also rule once on OTLP/collector endpoints. |
| settings `SKILL.md:67-69` "one authoritative home" vs `config-yaml.md:83-85,156` "otherwise use a Pydantic field default" | Delete the fallback sentences (see §3.3). |
| otel `shared_library.md:152` `set_status_on_exception=False` vs `conventions/errors.md:52-54` "leave default" | See §7.2. |
| otel `structlog.md:89` binds `service.name` at import vs `shared_library.md:184` forbids it | Fix the `structlog.md` example. |
| otel `structlog.md:53` `exception.stacktrace` vs the shared lib's `exception` field | Pick one name. |
| db `engine-and-session.md:20` module-level `engine` vs arch "bootstrap constructs handles" | Delete the import-time example (§6.1). |
| db `models-and-base.md` file-per-table vs arch flat-first | "Split when a table gains relationships or behaviour." |
| db `repositories-and-queries.md:29-33` "Bootstrap constructs `UserRepository(session)` behind a port" vs arch "a fixed DB often needs no Protocol", and vs per-UoW sessions | "Bootstrap constructs session and UoW factories" (§6.2). |
| arch `boundaries.md:43` port admission test (every DB passes it) vs the adjacent "a fixed DB often needs no second Protocol" | §4.4. |
| arch `SKILL.md:81-86` "no root business-capability packages" vs `CLAUDE.md` #5 | "Business capabilities are organized *inside* `application/` and `domain/`. No root-level peers of the technical boundaries." |
| arch `ai.md:54` `tools.py` holding a few tools vs audit "one exposed tool per module" | arch owns it: "A few cohesive tools may share `tools.py`; split to `tools/<tool>.py` when tools gain their own schemas." The audit cites it. |
| audit "inject a capability, not a raw client" vs `ai.md:249-263` bootstrap passing raw models to `build_agent` | "Application actions receive capability implementations. Raw handles go only into genai/adapter constructors." |
| audit script forbids `opentelemetry` in `application/` vs `boundaries.md:203` "application may call a narrow telemetry helper" | §4.10. Make the script agree. |
| arch `api-and-workers.md` "use `api/routers/` even with one module" vs "no one-file subpackages" | Allow `api/routes.py` until a second router exists. |
| arch `modularization.md` 300–350 lines vs `ai.md` 300–350 vs `CLAUDE.md` ~300 | One number, in one place (the code-conventions skill or `modularization.md`); the others point to it. |
| pytest `SKILL.md:195` "reject tests of framework behaviour" vs the value of pinned-framework characterization tests | Add a "framework characterization" profile (§9.13). |
| arch `testing.md`: "member-qualified support package" + "omit `tests/__init__.py`" + importlib mode + "no global pythonpath" + "don't promote to root" + "don't import another deployable's helpers" | These can't all be satisfied together. Replace with the recipe in §9.1. |
| otel `SKILL.md` scope: "don't touch siblings for symmetry" vs "route repeated contracts to shared_library" | §7.10. |
| settings `settings-py.md:140-141` `PositiveFloat` for timeouts vs `FiniteFloat` for arithmetic | §3.6. |
| settings flat scaffold `case_sensitive=True` + aliases vs nested scaffold `case_sensitive=False` | D2. |

### 1.3 Audits are report-only by default — **M** · OPS, DA, CTL
- In `python-service-architecture-audit/SKILL.md:139-177`, the default becomes: report the findings with a recommended route.
- Write `FEEDBACK.md`, open an OpenSpec proposal or implement fixes **only when the user asks for repair**.
- Remove "Do not stop at a chat-only report…" and "Do not ask for redundant repair confirmation".
- Remove "and repair confirmed boundary violations" from `agents/openai.yaml`.

### 1.4 Enforce with tooling, not prose — **H** · all four
For every rule a linter can check, enable the linter and state the rule nowhere else. See §10.1 for the rule set.

### 1.5 Skill length and dead references — **M** · DA, IM, CTL
- **otel:** about 12–13k lines. Audit mode loads about 2k lines before any GenAI reference. Target a `SKILL.md` of ≤150 lines with a rule index that points to owner files.
  - Move `SKILL.md:76-86` (Langfuse/GenAI projection) into `tracing/genai/content_capture.md`.
  - Cut the deprecation hedging (`:62-68`).
  - Remove `SKILL.md:61`, which refers to `opentelemetry/` and `architecture/02_metrics_design_cheatsheet.md`; neither exists.
  - Add a **"Minimum viable instrumentation"** section to Step 2: boundary spans, one error helper, a few outcome metrics, owner logs. Every further layer needs a named consumer.
- **settings:** 1,570 lines. Target a `SKILL.md` of ≤120 lines built around one ownership table (§3.14); references hold only scaffolds.
- **arch:** reduce invariant 9 (absolute imports) to one line. Move invariant 10 (YAML config location) to settings and leave a pointer.
- **repository-setup:**
  - `SKILL.md:126,436,609` name an `observability` skill; the actual skill is `otel-observability`.
  - Verify that `terraform-aws`, `deploy-scripts` and `split-repo-app-releases` resolve wherever the skills are installed.
  - Move anecdotes (`:457-472`) and the rationale essay (`:128-141`) to a reference.
- **otel `scripts/validate_skill.py`** (~2k lines) checks the skill's own prose for literal substrings. Replace it with a small audit of the target code (§7.14).

---

## 2. New: `python-code-conventions` (see D1)

The largest gap: all four reviews found that the recurring defects sit *below* module placement, where no skill owns the rules. Keep it about 200 lines, one bad/good pair per rule. Every rule either maps to a Ruff or mypy check or states a concrete trigger. Proposed outline:

### 2.1 Data containers — **H** · OPS, IM, DA, CTL
| Need | Use |
|---|---|
| Internal value / result / command / policy | `@dataclass(frozen=True, slots=True)`; add `kw_only=True` for >3 fields, any `bool` field, or adjacent fields of the same type |
| Collections inside a frozen value | `tuple[...]`, `frozenset[...]`, `Mapping[...]`; never `list`/`dict`/`set` |
| Untrusted, persisted, wire or LLM-facing data | Pydantic `BaseModel`, `ConfigDict(frozen=True, extra="forbid")`, declared once per member as a named base (e.g. `StrictModel`); don't copy the base into several modules |
| Fixed-key JSON that must stay a dict (OTel carrier, SDK kwargs, framework state channels) | `TypedDict` |
| Undecoded JSON at the edge | `pydantic.JsonValue` / `Mapping[str, object]`, narrowed immediately |

- Use Pydantic at trust boundaries, not for every internal result "for consistency".
- Decode legacy or versioned formats once at the boundary and pass a stable typed value inward.
- Mutable dataclasses are only for explicit state holders, with a one-line comment saying who mutates them.
- **Exceptions:** tiny tagged-union members (`Active(remaining_seconds)`); `Point(x, y)`; `slots=True` where descriptor or inheritance patterns break it.

### 2.2 Keyword construction — **H** · OPS, IM, DA, CTL
- Wide dataclasses are `kw_only=True` and are always constructed by keyword.
- Never pass bare `True`/`False`/`None`, or a non-self-describing number, positionally (Ruff `FBT003`).
- Keyword-only constructors (`def __init__(self, *, ...)`) are the default.
- Map wide rows or provider responses into DTOs with keywords, so each source visibly matches its destination.

### 2.3 Closed vocabularies are types, declared once — **H** · OPS, IM, DA, CTL
- A status, phase, mode, record type, error-code family, tool name or metric-label set is declared **once**:
  - as a `StrEnum` when code needs members, iteration, branching, a DB CHECK or boundary crossing;
  - as `type X = Literal[...]` only for small compare-only mode switches or schema-only fields.
- Type every attribute, parameter, return value, model field and column with it.
- Compare against members, never string literals. Use `.value` only at serialization edges.
- Name derived subsets beside the type (`TERMINAL_STATES: frozenset[State]`). Derive runtime sets with `get_args()` or enum iteration, never by retyping the values.
- Never classify by substring. Never use sentinel strings such as `"_NONE"`; use `None` or a member.
- Return a `NamedTuple` or dataclass, not `tuple[str, str]`.
- **Exceptions:**
  - Alembic revisions keep frozen copies.
  - A public wire enum may stay separate when the external contract must not follow internal renames. Map it explicitly, with a comment.
  - Pass-through external values may stay `str`.

### 2.4 Outcome contracts: no bare `bool` or ambiguous `None` — **H** · OPS, CTL
- A public or port method that returns `bool` or `X | None` either documents the falsy meaning in one docstring line, or returns a named outcome (a `StrEnum` or a small result dataclass).
- Always use the named outcome when the falsy case has more than one cause (lost lease vs. already applied).
- A wrapper never turns an exception into `None` when `T` can itself be `None`.
- Don't expose half-actions with boolean mode flags whose `| None` result callers interpret differently.
- **Exception:** question-named predicates (`is_due()`).

### 2.5 Type escape hatches: narrow, don't silence — **H** · OPS, IM, DA, CTL
- `Any` is only for truly dynamic values: raw SDK returns (narrowed in the same function), `**kwargs` pass-through, framework-imposed type parameters, and JSONB columns.
- Use `object` for heterogeneous input you narrow, so mypy enforces the narrowing.
- Type model handles as `BaseChatModel` or a narrow Protocol, and agents/graphs as `Runnable` / `CompiledStateGraph`.
- Narrow with `isinstance`, `TypeIs` or a lookup table, never with `cast` or `# type: ignore`. For example, a `dict[str, Environment]` lookup removes `return raw  # type: ignore[return-value]`.
- Every remaining `# type: ignore[code]` names its code, and has a reason when the reason isn't obvious.
- When the same cast/ignore pair appears more than twice, wrap it once in a typed helper owned by the type's package (e.g. typed `Table` handles).
- Never write `cast(Any, …)`. Never `cast` to recover a type from a string-keyed container; store typed attributes instead.
- No `getattr(obj, "attr", default)` on project-owned types: declare the attribute on the Protocol or base class. Reserve reflective access for untyped third-party payloads, inside one translation function per payload.

### 2.6 No `assert`, `object.__setattr__` or duck probing in production — **H** · OPS, IM, DA, CTL
- `assert` never guards a condition that can be false at runtime (lookup results, optional deps, loaded state), because `-O` strips it. Raise a named error, or make the type non-optional.
- Enforced by Ruff `S101`, with tests excluded.
- `assert_never()` in exhaustive `match` is fine.
- Never bypass `frozen=True` with `object.__setattr__`.
- Helpers that always raise are annotated `-> NoReturn`.

### 2.7 A dict with a fixed key set is a record — **H** · OPS, IM
- Don't use `dict[str, Any]` as an internal result or accumulator.
- Helpers return values. They don't receive a dict to mutate by string key.
- When code already holds typed values, construct the model with keywords. Use `model_validate` / `model_validate_json` only for data crossing a trust boundary. Never assemble a dict, `pop` keys, then validate it.
- Once data is validated into a model, pass the model on. Don't convert it back to a dict.

### 2.8 Name recurring types and constraints once — **M** · OPS, IM, DA, CTL
- A structural type or constraint that recurs in ≥2–3 places gets one name at its semantic owner: `type TraceCarrier = dict[str, str]`, `Confidence = Annotated[float, Field(ge=0, le=1)]`, `type Sha256Hex = Annotated[str, Field(pattern=...)]`.
- Use one parameter name per concept.
- Never put these in a generic `types.py` or `common.py`.
- Limits that legitimately differ per field stay inline. Don't alias a type used once.
- New aliases use the PEP 695 `type X = ...` statement, and new generics `def f[T](...)`.

### 2.9 Magic values and constants — **M** · IM, CTL, OPS
- Give a literal an `UPPER_CASE` name when it appears twice or its meaning isn't obvious (sizes, timeouts, sentinel dates, lease names, jitter bounds, retryable status sets). Precompile regexes.
- If the value could differ per deployment or need tuning, it is a **setting**, not a constant.
- An invariant number is a `Final` constant with a unit suffix and a one-line *why*.
- Durations and sizes end in their unit (`_seconds`, `_ms`, `_bytes`, `_chars`, `_tokens`) unless the type carries the unit.
- Don't branch on a substring of a deployment-owned value such as a model ID. Use a setting (`supports_temperature`) or one keyed table.
- **Exceptions:** `0`, `1`, `""`, `fastapi.status` names, one-off test data.

### 2.10 Constructors and wrappers — **M** · IM, CTL, OPS, DA
- Assign one attribute per line in `__init__`. Attribute name = parameter name; collaborators get a leading `_`. Use a `@dataclass` if `__init__` only stores arguments.
- Don't expose collaborators as public mutable attributes that tests overwrite.
- Group settings-derived scalars that one owner always consumes together into a frozen policy dataclass validated in `__post_init__`. Don't create a one-field wrapper while sibling scalars stay loose.
- Replace a boolean flag that selects different object shapes or methods with two functions.
- **Delete pass-through wrappers:** a class or function whose body only forwards to another callable with the same meaning. That includes bootstrap "handlers" repeating a service signature, application functions that only call `store.x()`, and a class storing N fields only to call a free function with the same N arguments. A wrapper earns its place when it translates types or errors, adds policy, or narrows a wide API.
- Never recover structured data by regex from text you rendered yourself; pass the structure.

### 2.11 Search before writing a helper; identical semantics have one owner — **H** · DA, CTL, OPS
- Before writing a private helper, search the member for an existing one and import it.
- Code with identical semantics has one owner. Typical cases: hashing/canonicalization, closed vocabularies, deadline arithmetic, provider error-code classification, trust-boundary rendering, DSN/URL rewriting.
- Two copies that differ by accident are a bug. Similar-looking code with different meaning stays separate, with a comment explaining why.
- Before extracting shared validation, compare failure codes and accepted inputs; similar syntax isn't enough.

### 2.12 Imports, `__init__`, `__all__` — **M** · OPS, IM, DA, CTL
- Imports go at module top. A function-local import needs a comment: optional heavy dependency, cycle, or import-time cost.
- Use `TYPE_CHECKING` only for type-only stub packages or real cycles.
- A cycle between service packages is a design defect: move the shared type inward.
- **Services:**
  - every package directory has an `__init__.py` (Ruff `INP001`);
  - service `__init__.py` files are empty, with no composition logic and no re-exports;
  - no `__all__` in leaf modules.
- **Libraries:**
  - re-export only from package `__init__` with a sorted `__all__` (`RUF022`);
  - every type in a public signature is exported;
  - pick one export point per package;
  - never list imported-from-elsewhere names.
- `observability/__init__.py` must not eagerly import optional (GenAI) dependencies.
- `from __future__ import annotations`: one convention per repo; on 3.13+ don't add it.

### 2.13 Docstrings and comments — **M** · OPS, IM
- Every module has a one-line docstring stating its responsibility.
- Public classes and exceptions get a one-line contract. For exceptions, say when they are raised.
- A function docstring is required only when the contract isn't visible from the signature: falsy/`None` meaning, side effects, ordering, idempotency, units, or the *why* of a surprising choice. Never restate parameters.
- Comments explain *why*. No banners, no commented-out code.
- DA and CTL found density already healthy, so codify the existing pattern; don't add a quota.

### 2.14 Error-handling and async idioms
Language-level parts only. The architecture parts live in §4.11 and §4.12.
- **Minimal `try` blocks:** a `try` contains only the call whose failure the `except` handles. Don't raise `ValueError` inside a `try` just to catch it a few lines later. Never catch `KeyError`/`TypeError` around parsing, because that turns bugs into domain failures. — **M** · IM, CTL
- **`raise X from exc`** by default. Use `from None` only when the cause may carry secret input (and the new error carries a sanitized projection), or for expected client-facing 4xx translations where the cause adds nothing. — **L** · IM, OPS, DA
- `except Exception` doesn't catch `CancelledError` on ≥3.8. Write a `CancelledError` arm only when it does something different. An `except BaseException` / `CancelledError` arm always ends with a bare `raise`. — **M** · DA, IM
- Exception names end in `Error` (Ruff `N818`). Carry context as typed attributes, not message text. Define a class only when a caller handles it differently or it crosses a port. — **L** · CTL, DA
- **Match/`assert_never`** for exhaustive dispatch over closed unions/enums; two-way branches stay `if`. — **L** · OPS (DA considered it unnecessary; keep it optional)
- Run independent awaits concurrently (`TaskGroup`) only when neither's failure changes whether the other runs and there's no rate-limit interaction. Otherwise keep them sequential, with a comment. — **L** · IM
- Don't declare `async def` or use `asyncio.Lock` where nothing suspends. Prefer `asyncio.Event` to polling with `sleep`. — **L** · DA

### 2.15 Size signals — **M** · OPS, DA, CTL
- Complexity ≤10 is enforced by Ruff `C90`.
- Length (~40 lines) and nesting are *review signals*, because Ruff can't measure them.
- A function over ~60 lines must be split, or the PR must say why.
- A long function in `db/` or `bootstrap/` signals misplaced business logic, not just length.
- Composition roots that only wire objects are exempt from the length signal but not from mixing concerns (§4.6).
- Before extracting from a long function, trace its inputs, decisions, effects, cleanup and output. Extract only a separable decision, resource lifecycle or reusable transformation. Don't create one-call helpers to hit a number.

---

## 3. `python-settings-config`

### 3.1 `Field(...)` only when it adds behavior or information — **H** · all 8 reviews
Replace:
- `SKILL.md:247-248` ("Use `Field(..., description=...)` for required values…");
- `settings-py.md:62-63,74,78-79` ("Include concise `description=` text on fields", "Use `Field(...)` only when the app cannot provide a safe default");
- `secrets-py.md:113`;
- the `ENVIRONMENT_NAME` "Declare it with `Field(...)`" line.

Rewrite every scaffold. Apply the general form to plain Pydantic models in `python-service-architecture/references/boundaries.md` (or code-conventions).

> Declare fields with a bare annotation: `x: int` is required, `x: int = 5` has a default. In Pydantic v2 an annotation without a default is already required, so never write `Field(...)` or `Field(default=...)` with no other argument.
>
> Use `Field(...)` only when it carries **behavior** or **information**:
> - a constraint (`gt`, `ge`, `min_length`, `pattern`, `strict`, `allow_inf_nan`);
> - an alias that differs from what the source binds automatically;
> - `default_factory`, `discriminator`, or `exclude`/`repr=False`;
> - SQLModel column mapping;
> - a `description` that is **consumed**, or that **adds information** the name, type and default don't.
>
> A description is consumed when it becomes schema text a reader sees: LLM structured-output and tool schemas, public OpenAPI. Information worth adding: the unit (if it isn't in the name), the accepted format, the scope ("rows claimed per poll"), what omission or `null` does, a cross-field relationship, why a bound exists, and whether the value is sent externally.
>
> Never write a description that restates the field name. Put units in the name (`timeout_seconds`). Put a rationale longer than one line in a `#` comment above the field. Document the env contract once, in `.env.example`, not in both places.

- **Good:** `pool_size: PositiveInt`; `otlp_endpoint: AnyHttpUrl | None = Field(default=None, description="Telemetry is disabled when unset.")`.
- **Bad:** `pool_size: PositiveInt = Field(description="Pool size.")`; `enabled: bool = Field(default=False, description="Whether enabled.")`.
- **Exceptions:**
  - **LLM/tool schemas:** description is behaviour. State once per schema module whether field descriptions or the prompt carry the semantics. Describe server-side clamps to the model.
  - **SQLModel columns** (`sa_column`, keys, server defaults).
  - A **generated config reference** that renders descriptions, when it is an explicit repo decision. Descriptions must still say more than the name.
  - Don't remove existing env aliases as a drive-by cleanup (see D2).

### 3.2 Env aliases — **M** · IM, CTL, DA
See D2. Use `case_sensitive=False` with no per-field `alias=` equal to `NAME.upper()`. That removes the `populate_by_name` trap and dual-key lookups (`values.get("ENVIRONMENT_NAME") or values.get("environment_name")`). The env-contract test may compare `field_name.upper()`.

### 3.3 One authoritative home per value; no shadow defaults — **H** · OPS, IM, DA, CTL
- A YAML-owned field has **no Python default**, so a missing key, file or mount fails validation naming the field.
  - DA verified 12 of 38 duplicated defaults had already drifted (e.g. a 120 vs 240 turn timeout).
  - If a class default is kept deliberately, a contract test asserts it equals every committed baseline.
- A configured YAML directory with no file for the selected environment **raises**; it never silently drops the YAML source.
- **No shadow defaults downstream:** a value owned by YAML or env must not reappear as a literal or a default on a dataclass, constructor, prompt builder, library function or port. Policy objects built from settings have required, keyword-only fields.
- When moving a value into YAML, grep for its literal and remove the shadow copies.
- An environment YAML file contains only keys whose value differs from `base.yaml`.
- `.env.example` OVERRIDABLE values are verified by the contract test, not typed by hand.
- Delete the fallback sentences in `config-yaml.md:83-85,156`.
- **Exceptions:** a shared library's own config object (it has no YAML); test-only factories.

### 3.4 YAML policy allowlist: use it only with a consumer — **H** · CTL (×2), DA, OPS
- Root `Settings` keeps `extra="ignore"`, because `.env` is shared with unrelated variables. That makes YAML typos silent, so:
  - **(a)** a YAML source rejects non-policy keys at startup against an allowlist (`PolicyYamlSource` + `POLICY_FIELDS`); **or**
  - **(b)** a contract test compares the merged YAML keys, for every environment, with `Settings.model_fields`, with a small explicit exclusion set for env-only inputs.
- Don't keep a hand-maintained allowlist that nothing consumes; derive it from model fields where possible.
- Nested section models use `extra="forbid", frozen=True` from one named base per service. Today the scaffolds use `extra="ignore"` on sections (`settings-py.md:240,286,423`); fix them.

### 3.5 Cross-field validation: types first, small non-mutating validators — **H** · OPS, IM, CTL (×2), DA
- Single-field rules go in the type or `Field` (`PositiveInt`, `Field(ge=2)`, `StringConstraints`), never in a model validator. Don't validate one invariant twice.
- Use `@model_validator(mode="after")` only for relationships between fields and for environment-dependent requirements. Validate before constructing clients.
- Keep one validator per concern (`_validate_nats_timing`, `_validate_llm_budgets`), each under about 10 checks, with messages naming both fields or env vars.
- Test each meaningful invalid combination and the valid boundary.
- **Never mutate `self`**, especially on a frozen model. Declare `field: T | None = None` and resolve the effective value in a property or in the bootstrap mapping.
- A `before` validator may normalize raw input only when that normalization is part of the contract.
- Don't build the same policy object once for validation and again for use. Validate the policy once, in its own `__post_init__`, where bootstrap builds it.

### 3.6 Reusable constrained types; finite numbers — **H** · CTL, OPS, IM, DA
- Durations, intervals, ratios and multipliers reject `inf`/`nan`; `PositiveFloat` accepts `inf` (verified). Define aliases once beside `Settings`:
  ```python
  PositiveSeconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]
  Ratio           = Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)]
  NonEmptyStr     = Annotated[str, Field(min_length=1)]
  ```
- Merge the conflicting `PositiveFloat` / `FiniteFloat` rows (`settings-py.md:140-141`).
- Put value-shape checks in the type (`AfterValidator`), not in a one-field `field_validator`.
- Prefer Pydantic's own types to validators: `AwareDatetime` rather than a `tzinfo` check, `EmailStr`, `SecretStr = Field(min_length=16)`.
- The same concept has the same type across services.
- Add an upper bound only for a real limit, and name it. Choose bounds from library semantics: `max_overflow=0` is valid.
- An intended "infinite = disabled" is `X | None`, with the `None` meaning documented.

### 3.7 Secrets hygiene — **H** · CTL (×2), DA, OPS, IM
- Every `Secrets` model sets `hide_input_in_errors=True`. So does `Settings` whenever a field can carry credential-adjacent input.
- A loader that converts `ValidationError` raises with **`from None`**. `errors(include_input=False)` only cleans your message; the chained `__cause__` still prints `input_value=...` (verified by DA).
- Any value containing a credential, including a DSN with a password, is `SecretStr`, parsed after `.get_secret_value()`. Never `AnyUrl`/`PostgresDsn`, whose repr shows the password (verified).
- Credential-free URL settings use a validated alias that rejects an embedded password.
- Required secrets are `Annotated[SecretStr, Field(min_length=1)]`, so an empty env var fails.
- Secrets outside Pydantic stay `SecretStr` or use `field(repr=False)`. Unwrapping helpers are typed `SecretStr | None`, never `object`. Unwrap only in adapters or bootstrap.
- **Test with a sentinel payload:** missing, malformed and cross-field secret failures must not show the payload in the raised error, `str(exc.__cause__)`, `repr`, JSON, or startup logs.
- Checklist to add:
  - errors name the variable, not the value (`type(exc).__name__`);
  - a pair validator for credentials that must arrive together;
  - reject static keys when deployed;
  - per-process secret models with least privilege.
- **Carve-outs:**
  - `Secrets` holds only credential-bearing values; `environment_name` and timeouts belong in `Settings`, even in a one-module runner.
  - A single-process job with one or two secrets may keep `SecretStr` fields on `Settings`. Use a separate `secrets.py` when processes need different secret sets or a remote provider.
- Decide the DSN-in-JSON case (`DATABASE_SECRET={"dsn": ...}`) explicitly against the "don't wrap a scalar in a one-field JSON object" rule, and show it as a worked example.
- Never hand-parse `.env`.

### 3.8 Settings stay in `config/` and `bootstrap/` — **H** · OPS, IM, DA, CTL
- Only `config/`, `bootstrap/` and `main.py` import `Settings`/`Secrets`. Construct them **once**, in the composition root, and pass them down.
- Bootstrap maps them into small frozen, action- or adapter-owned policy dataclasses (`XxxPolicy`, `NatsConsumerSettings`), one named mapping function each.
  - Convert Pydantic types (`AnyUrl`, `ByteSize`, `SecretStr`) into plain values there, once.
  - Never pass the whole `Settings` object into adapters, domain code, application code or libraries.
- A test that needs `Settings.model_construct()` to skip fields signals a missing slice.
- Never store `Secrets` on `app.state`; inject the specific credential into the adapter that needs it.
- Replace the scaffold's `lru_cache get_settings()` + `# type: ignore[call-arg]` with `load_settings()`. It translates `ValidationError` into a typed `ConfigurationError` naming the source and fields, with no raw input. Show the accepted `Settings()  # type: ignore[call-arg]` form once if it remains.

### 3.9 Auxiliary entry points reuse the service settings — **M** · CTL, OPS
- Probes, admin CLIs and diagnostics build from the service's `load_settings()`/`load_secrets()` and add only their own fields, extending the secrets model or adding a sibling one.
- They do not re-read env vars, create a second `BaseSettings` mixing secrets and settings, or resolve `.env` relative to the working directory.
- A separate one-shot deployable with three or fewer inputs may parse an injected `Mapping[str, str]`, but still documents and masks its inputs.

### 3.10 OPTIONAL may hold diagnostic knobs with Python defaults — **M** · CTL
OPTIONAL may hold:
- (a) platform-supplied runtime identity;
- (b) escape hatches;
- (c) diagnostic or observability switches whose Python default is safe everywhere: content capture, exception detail, export interval, a release version with an `"unknown"` fallback.

Anything that changes business behaviour (limits, retries, timeouts, prefixes) stays YAML policy with no Python default. Replace the over-rigid "safe default ⇒ YAML".

### 3.11 URL types normalize — **M** · CTL
Pydantic URL types add a trailing `/`. For identifiers compared verbatim (JWT issuer, audience, registered callbacks), use `str` with a `pattern`, or normalize once in bootstrap. Join base-URL paths in exactly one helper, not `rstrip('/')` per call site.

### 3.12 Single-value `Literal` setting is a constant — **L** · OPS
A setting typed `Literal[<one value>]` isn't configurable. Move it to a constant beside its owner and remove it from YAML. The exception is a temporary pin, with a comment naming its removal condition.

### 3.13 Tests for settings — **M** · IM, DA, CTL
- Unit tests constructing `Settings` clear the env vars the model reads, pass `_env_file=None`, and point the config-dir variable at a fixture/`tmp_path`. Use one shared `runtime_env` autouse fixture per service.
- Tests that read the committed baseline belong under `contract/`.
- The `.env.example` contract test compares **values** as well as names against the YAML baselines. It also checks the root `.env.example` against each service's shared keys, and checks that comments are not just the field name restated.
- Cover validators, cross-field invariants, derived values, redaction and the document↔model contract. Don't assert literal defaults one by one, and don't test that pydantic-settings reads env vars.

### 3.14 Restructure and clean up the skill — **H/M** · OPS, IM, DA, CTL
- **Ownership table.** Replace the prose in `SKILL.md:65-119,204-278` with one table of ≤15 rows. Columns: *value kind → owner (code / YAML / env-only / secret) → Python declaration → `.env.example` section → test*. The references keep only scaffolds (§1.1, §1.5).
- **Remote-secrets scaffold** (`secrets-py.md:162-221`): remove the ABC `SecretsProvider`, the stub remote provider raising `NotImplementedError`, the factory and `global _cached_secrets`. Show a plain `load_secrets(settings) -> Secrets`, loaded once in bootstrap. Add a Protocol only when a second backend exists.
- **The `or raise_missing_environment_name()` trick** (`settings-py.md:404-412`): replace it with an explicit `if value is None: raise ...`.
- **`SKILL.md:15-22` forces migrating env-only projects to YAML** during any config refactor. Change to: "propose the migration; don't perform it unless asked."
- **`SKILL.md:156-182` mandates a `config/base.yaml` + `config/services/<svc>.<env>.yaml` layout.** Add: "Preserve an existing YAML layout; propose migration separately."
- **Don't create empty override-layer files**; the loader treats them as optional.
- **`.env.example`:**
  - Comment a variable only when its name, type and value don't already say what it is, its unit, or what omission does.
  - Show the value resolved for `ENVIRONMENT_NAME=local` and say so in the section header.
- **"Validate during FastAPI startup"** becomes "validate at process start, before accepting traffic or consuming messages."
- **Document the process-env-only variant** (`del dotenv_settings, file_secret_settings` when the launcher supplies `.env`). Settings and secrets must match. — L
- **Standardize** `env_ignore_empty=True`, with a comment, when Compose passes unset variables as `""`.
- **Standardize** rejecting legacy env vars with a migration message.
- **Generalize** the `asyncio.to_thread` note for sync secret SDKs by linking to §4.12.

---

## 4. `python-service-architecture`

### 4.1 Remove file mandates; keep ownership rules (GenAI) — **H** · OPS, IM, DA, CTL
Rewrite invariant 4, `ai.md:3-6,183-193,191-286` and `boundaries.md:322`:
> Keep model construction, prompts, schemas, tools and behaviour-changing middleware under `genai/<task>/`.
> - Build the model in a factory function. A task-level `llm.py` exists only when it binds something task-specific (structured output, tools, task-only parameters).
> - Provider construction policy (timeouts, disabled SDK retries, client validation, callbacks) lives once, in `genai/shared/<provider>.py::build_chat_model(options)`.
> - Name other modules after what they contain (`runner.py`, `embedder.py`).
> - No module whose body is only a re-export.
> - Reuse a sibling task's factory through `genai/shared/`, never by reaching into the sibling.
> - Responsibilities that must stay *separable*: construction, prompt+version, output schema, invocation/translation. They may share a module until one grows independent weight.

Also:
- Shorten the ~95-line factory section to rules: no import-time handles, no global settings, pass the settings slice, type the handles.
- When prompt, schema or tools depend on runtime context, bootstrap injects the static ingredients into an assembler class in `genai/<task>/agent.py`. Bootstrap never defines closures containing GenAI assembly or parsing logic.
- Evidence: 7-line re-export `llm.py` files, and three factories differing only in temperature.

### 4.2 Type the skill's own examples — **H** · DA, CTL
`ai.md:210,229` (`build_model`, `build_agent`) are untyped, and agents fill in `Any` to satisfy mypy strict. Type them as `-> BaseChatModel`, `model: BaseChatModel`, `tools: Sequence[BaseTool]`, `-> CompiledStateGraph` (or a narrow Protocol).

### 4.3 Other GenAI additions (`ai.md`)
- **Prompts are built from the constants they describe:** limits, tool names, delimiters (or a test asserts they match). Every `prompts.py` exports `PROMPT_VERSION`; show an example. — **H** · DA
- **Keep `@tool` closures thin:** validate, call one collaborator, return. Bookkeeping goes in module functions. Tool builders return `BaseTool`. `agent.py` only sets up the agent; invocation and outcome assembly belong in the capability adapter. — **M** · DA
- **`ContextVar`s as the tool channel,** only when the framework offers no explicit context channel. Declare them at module level in the owning GenAI module, never in bootstrap. Bind them all in one context manager inside `invoke()`. Readers fail loudly when nothing is bound. — **M** · CTL
- **Agents as workflows:** the domain owns pure state-transition functions, GenAI middleware decides *when* to call them, and the application owns pre-flight, idempotency and the outcome contract. Don't invent pass-through orchestration to satisfy "no workflow in genai/". — **M** · DA
- **Relax** "deterministic fallback selection is forbidden in GenAI": GenAI may return a typed incomplete/degraded result as part of the port contract, and the application decides what it means. — **M** · CTL
- **Mark `core/context.py` as conditional** in the ordinary GenAI tree. — **L** · CTL, DA
- **Cut the expanded multi-agent tree** (`ai.md:74-136`, which contradicts flat-first) to about 5 lines. — **M** · DA
- **Say explicitly that genai→application imports are allowed** for tools that call a use case. — **L** · DA
- **Standardize the good GenAI patterns:**
  - a versioned prompt constant;
  - data sent as a separate untrusted user message;
  - a `strict=True, extra="forbid"` output schema with a semantic validator;
  - SDK retries disabled so one call is one audited attempt;
  - per-record partial salvage;
  - two-step error translation: framework → GenAI-private → port.

  — **H** · IM, CTL

### 4.4 Ports: when they earn their cost — **H** · OPS, IM, DA, CTL
- **Replace the "at least two of three" admission test** (`boundaries.md:43-50`), which any I/O passes. The new question: *introduce a Protocol only when a test substitutes it or a second implementation exists today.*
- **Persistence:** a database always "qualifies", so state that the persistence port exists to give application code a unit-of-work boundary and a testable contract. Add a repository/UoW Protocol when application state-transition logic is unit-tested with fakes. Skip it for thin CRUD pass-through. Use the shapes in §6.2, never a Protocol per repository class.
- **Root `ports/`** holds only contracts that `application/` imports.
  - A contract between two implementation boundaries (a genai tool that needs a DB reader) lives next to its **consumer**.
  - A Protocol that only decouples an outer component from a collaborator is declared next to its single consumer.
  - A private Protocol narrowing a third-party SDK surface for fakes belongs in the adapter module; that's legitimate, and it isn't a port.
- **Port contract hygiene:**
  - signatures never use `Any`, `object`, `Mapping[str, Any]` or framework method names (`ainvoke`, `astream`, `adelete_thread`);
  - return types are named types;
  - a streaming port yields a closed union of typed business events;
  - ports contain no helpers, no I/O and no configuration defaults;
  - Protocols declare methods, not collaborator attributes;
  - a required collaborator has no `None` default;
  - a port module doesn't re-export domain types.
- **Don't mirror library types.** A port-owned type that mirrors a technology-neutral contract-library type one-for-one isn't isolation: import it. Mirror only when the meaning differs, and say how in the docstring. Apply one decision per library.
- Application actions depend on sibling actions concretely, not through a Protocol.
- Replace the invented example at `boundaries.md:86-95` with a real one: base, transient and permanent errors, a typed input, a one-method Protocol.

### 4.5 Repositories apply decisions; they don't make them — **H** · OPS, IM
A repository method implementing a state transition:
1. reads and locks the rows;
2. maps them to a typed *observation* (a frozen kw-only dataclass);
3. calls a pure domain decision function;
4. writes the returned *decision*.

Repositories don't choose statuses, error codes, retry delays, HITL reasons or user-visible text.
- Pass the decision function as a `Callable` alias; add a Protocol only when needed.
- Review triggers: a repository method over ~40 lines, or more than two branches on business state.
- **Exception:** SQL predicates that *are* the eligibility rule for a claim stay in SQL. Name them as shared predicates (§6.9).
- Put decision invariants in the decision object's `__post_init__`.

### 4.6 Bootstrap: structure the composition root — **H** · OPS, IM, DA, CTL
- Bootstrap constructs and wires. It doesn't define closures that run DB queries or business steps; each supervised operation is an application action. Bootstrap runs no SQL itself: readiness calls a port method.
- **Split once past ~80 lines** into `_build_<capability>(settings, resources) -> <frozen bundle>` functions of about 40 lines each. Split only at stable resource or capability seams. Don't add a factory per constructor or a generic registry. A service with fewer than ~10 collaborators keeps one flat function.
- **One lifecycle idiom:** `@asynccontextmanager async def runtime(settings, secrets) -> AsyncIterator[Runtime]` owning a single `AsyncExitStack`.
  - `build_*` functions are pure construction; `run()` only orchestrates and maps outcomes to exit codes.
  - Register each process-wide teardown exactly once.
  - Resources kept only for disposal live in the exit stack.
  - Never reach into `_private` fields; expose `start()`/`aclose()`.
- Build each concrete adapter once and share it. Keep gauge initialization and business-validation checks out of wiring.
- A composition function taking more than ~6 positional collaborators takes a container.
- Put run-completion summaries and log projections in `observability/`.
- **The runtime container** holds only what the process boundary uses, with no fields for tests to inspect.
- **Test seams:**
  - substitute doubles at **one** seam, by passing fakes into the composition function, or through keyword parameters defaulting to the production constructors;
  - don't add `factory=`/`launcher=`/`hooks=`/`clock=None` to every layer;
  - a factories object must be typed without `Any`/`Callable[..., X]`.
- Diagnostics and maintenance entry points reuse bootstrap factories rather than importing concrete adapters.

### 4.7 Constructor contracts — **H** · CTL, OPS
A production class's required collaborators and limits are required parameters. No `X | None = None` with a built-in fallback, magic-number default or "legacy" branch just so tests or old callers can omit them. Defaults are allowed only for:
- effect seams (clock, sleep, random, uuid) whose default *is* the real effect;
- genuinely optional, settings-documented features.

### 4.8 Use-case shape — **M** · CTL
An application action is a class named with an imperative verb phrase. It has:
- keyword-only dependencies: ports, a UoW factory, typed policy objects, and effect seams;
- **one** public `async def execute(*, ...) -> <FrozenResult>`;
- failures raised as action- or port-owned exceptions.

Use a plain module function when there are no dependencies. Add a short template to `templates.md`.

### 4.9 Nondeterminism: typed callables, read only at the root — **H** · IM, CTL, OPS
- `domain/`, `application/` and `db/` never call `datetime.now()`, `time.time()`, `random.*` or `uuid4()` directly.
- Inject keyword-only typed callables whose defaults are the real effect, with the same names everywhere:
  - `clock: Callable[[], datetime]`
  - `monotonic: Callable[[], float]`
  - `sleep: Callable[[float], Awaitable[None]]`
  - `uniform: Callable[[float, float], float]`
  - `id_factory: Callable[[], UUID]`
- Drop the "clock is a port" suggestion (`boundaries.md:52-53`); a Protocol `Clock` is unnecessary.
- Never default a clock inside a function body (`now or datetime.now(UTC)`).
- For lease predicates, prefer database-owned time (§6.10).

### 4.10 Telemetry in application code — **H** · DA, CTL, OPS
Replace `boundaries.md:203-205`:
> The use case returns a result or summary (counts, outcome, stop reason). The *caller* (supervisor, handler, wrapper) records span attributes, metrics and logs from it.
> - Application code may use the service's own `observability/` vocabulary and one-line helpers (`with phase_span("x"):`).
> - It never imports `opentelemetry` types, receives a `Tracer`, builds attribute dicts inline, mutates telemetry accumulators, or calls a telemetry function from each return path.
> - When an adapter must report per-attempt facts, inject a typed callback (`record_outcome: Callable[[Outcome], None]`).
> - If telemetry exceeds roughly a fifth of a use case's lines, move it into a decorator or context helper.
> - Keep the sequence of outcome decisions (acknowledge, state transition) visible. Extract repeated telemetry/error projection into a small helper owned by the same boundary, but never hide ack or transition order in a generic decorator.

Exception: counts discovered inside framework callbacks may use a context-local accumulator.

### 4.11 New reference: `references/errors.md` — **H** · all four
Today no skill owns error design. The otel `errors.md` keeps only the telemetry projection and links here. Route it from invariant 6 and `api-and-workers.md`.
- **Allowed shapes of a broad `except Exception`/`BaseException`:**
  1. mark and re-raise;
  2. clean up and re-raise (prefer `finally` or a context manager; bound cleanup that can hang);
  3. translate to a port-owned error `from exc` at an adapter boundary;
  4. a true process boundary (request handler, message handler, worker loop) that logs once and applies a declared outcome;
  5. a **recorded fallback**: a warning with `exc_info` and `error.type`, or a handled-failure recorder, plus a metric for degraded capabilities;
  6. a best-effort shutdown or flush step that logs at warning.

  An `except` that doesn't re-raise must catch specific types or record the failure. `except …: pass` needs a why-comment. Never silently return `()`/`None`/`False`.
- **Never label an unknown exception as a specific cause** ("database_unavailable", "dependency outage"), because programming errors then look like outages. Deliberate degradation catches a narrow **owned** failure type and makes the fallback explicit in the result, with a reason code. Never use a broad built-in such as `ValueError` as the signal.
- Lower layers raise with context rather than log-and-reraise.
- **Translate once; never self-chain:** code that already raised a port error re-raises it unchanged (`except PortError: raise` before the broad arm). Don't raise a port error inside a `try` whose broad `except` translates, and don't raise a generic exception inside a `try` whose `except` catches only a narrower type. Each port owns distinct error classes; aliasing another port's errors corrupts `error.type`.
- **Classification bases:** when retry or terminal policy depends on transient vs. permanent, define a small pair of bases once, where the policy lives: `DependencyUnavailableError(error_code, retry_metadata)` and `DependencyRejectedError(error_code)`.
  - Port errors subclass them. Application code catches the bases, not tuples of every port error.
  - Every attribute read from an exception is declared on the base; never `getattr(exc, "error_code", default)`.
  - Rewrite audit `SKILL.md:55-56` ("no universal adapter hierarchy") so it doesn't read as a ban on this.
  - Never raise built-in `ValueError`/`LookupError`/`RuntimeError` for an expected business outcome or an integrity fault.
- **Exception → public error: one exhaustive table in `api/`,** keyed by exception type (resolved along the MRO) or a closed `StrEnum`. A test asserts every member is mapped.
  - Business exceptions state *what happened*. They don't carry `public_message`/`status_code`/`retryable`.
  - No `getattr(exc, "code")` resolution, no synthetic exceptions to reach the mapper, no path branching in global handlers, and one helper builds the envelope.
  - Routers don't try/except just to re-raise.
  - A code persisted in durable state is a `StrEnum` in `domain/`.
  - Promote the good existing pattern: a closed allowlist, `problem+json`, never copy exception text, log only ≥500 at the handler, `Cache-Control: no-store`, `Retry-After`.
- **Every failure a port can raise has a named handling boundary:** an API `exception_handler`, or a loop boundary that logs once and backs off (or exits with a documented reason). An unhandled port failure becomes a 500 or kills a supervisor.
- **Uncertain outcomes for external writes:** for a write that isn't provably safe to replay, distinguish confirmed success, confirmed rejection and **unknown**. A timeout or connection loss after dispatch is unknown. Persist enough identity to reconcile against an authoritative read or idempotency key before writing again, and test that the uncertain path never blindly replays. Simpler retries are fine with a verified idempotency key. — **H** · IM

### 4.12 New reference: `references/async-and-lifecycle.md` — **H** · all four
Nothing covers asyncio mechanics today; the only guidance is "the supervisor owns asyncio tasks, stop events, graceful shutdown". Route it from SKILL.md for any service with async I/O.
1. **No blocking I/O on the event loop.**
   - Remote-I/O ports are `async`. Adapters wrapping sync SDKs (boto3, openpyxl, file IO) call each blocking operation through `await asyncio.to_thread(...)` on a private sync method, or use an async client.
   - Don't offload cheap pure computation or tiny `Path` calls.
   - A one-shot CLI may block before `asyncio.run`.
   - Bulk downloads use bounded concurrency (a `Semaphore` throttle).
2. **SDK clients are built once** (adapter constructor or bootstrap), injected, and closed by their owner's lifecycle. Adapters never create or close injected `httpx`/Redis clients. boto3 low-level clients are thread-safe; the default session isn't. Never call `boto3.client()` inside a `to_thread` function.
3. **Every SDK client gets explicit timeouts and retries** (`botocore Config(connect_timeout, read_timeout, retries)`). An outer `asyncio.timeout` around `to_thread` cancels the await, not the thread.
4. **A deadline bounds every phase:** pool acquisition, `statement_timeout = min(configured, remaining)`, and provider calls (`asyncio.timeout_at`). Keep one `remaining(deadline)` helper per member.
5. **Exactly one retry owner per physical call.** Under middleware or application retry, set SDK retries to 0, with a comment. Delete an inner retry loop that bootstrap always configures to one attempt. The retry policy object owns its `retry_on` set. Library retry loops take injectable `sleep`/`clock`, expose attempts through a callback or result, and honour `Retry-After`.
6. **Acquire several resources with `AsyncExitStack`,** or open each inside the `try` that closes it.
   - Factories return async context managers, not `launch()`/`close()` pairs.
   - Close several resources with `gather(..., return_exceptions=True)` and report every failure.
   - Never drive `__enter__`/`__exit__` by hand.
   - Every acquired client, session, browser, workbook or **streaming response body** has an owner, and is closed on success and failure.
7. **Cleanup must survive cancellation:** use `try/finally`, or `except BaseException: cleanup(); raise`. Never `except Exception` for resource cleanup.
8. **Structured concurrency:**
   - Sibling tasks started by one operation live in a lexical scope. Use `asyncio.TaskGroup` for fail-together fan-out (Python ≥3.11).
   - First-completed races use `create_task`/`wait` with a `finally` that cancels and awaits every remaining task, preserving the original failure. Use one service-owned `gather_or_cancel` helper instead of re-implementing cancel-then-gather.
   - Store or await every `create_task` result. Background tasks go in a set with a done-callback that logs failures.
   - Supervisors that signal a stop event and wait for a graceful exit should **not** become a `TaskGroup`, which cancels immediately. Say so in the text.
9. **Cancellation-safe idioms:**
   - In async generators, wrap only the `await` in a timeout, never the `yield`.
   - After `gather(return_exceptions=True)`, re-raise any `CancelledError` found in the results.
   - Use `asyncio.shield` with a why-comment when cancellation could orphan a half-built resource.
10. **Health probes** have a timeout and log the failure reason on state transitions.

### 4.13 Long-running loops — **H** · OPS, IM, CTL
Extend `api-and-workers.md` "Long-running worker":
- Each loop is an object with `async def run(self, stop: asyncio.Event)` that calls a **public** single-iteration method (`tick()`/`poll_once()`). That method calls an application action and records the returned result. One owner creates all loop tasks.
- **Every loop declares exactly one failure policy:**
  - **contain/isolate:** catch around the iteration, log once with `exc_info`, back off (backoff from settings), continue; or
  - **crash/fail-fast:** log once and re-raise, letting liveness fail.

  A loop that must survive infrastructure failures catches the service's `Unavailable` branch *inside* the loop.
- One shared stop-aware sleep:
  ```python
  async def wait_or_stop(stop: asyncio.Event, seconds: float) -> bool:
      """Return True when stop was requested before the timeout."""
      try:
          async with asyncio.timeout(seconds):
              await stop.wait()
      except TimeoutError:
          return False
      return True
  ```
- When a supervisor runs more than two cycles with the same span/metric/log/failure shape, route them through one `run_cycle(name, operation)` helper. Each cycle receives its one action, not the whole runtime.
- Shutdown: stop `Event` → `asyncio.timeout(grace)` → cancel → `gather(return_exceptions=True)`.
- Pause, admission and batch-until-done decisions belong in domain or application objects, not in the loop body.
- **Broker adapters map outcomes; they don't own retry policy.** The adapter maps a typed application outcome to ack/nak/term plus a delay, and the delay policy is a domain function (IM/CTL). Add to the audit semantic checklist.
- **Exception:** a one-off process (CLI, job) has no supervisor; it exits non-zero.

### 4.14 FastAPI — **H/M** · IM, DA, CTL
- **Typed dependencies (H).**
  - Store the typed `Runtime` on `app.state` once, and expose one accessor `get_runtime(request) -> Runtime`.
  - Routes receive services via `Annotated[X, Depends(provider)]` from `api/dependencies.py`.
  - Routes never touch `request.app.state`, never `cast` it, never look up attributes by string, and never re-validate what bootstrap validated.
  - Group transport policy scalars into a typed object (`SsePolicy`).
  - Tests use `app.dependency_overrides`.
- **`api/` never imports `bootstrap/` (H).** `api/` declares the narrow Protocol it needs (`ApiRuntime`), and bootstrap satisfies it. The same applies to `adapters/`, `db/` and `genai/`.
- **Thin routers (M):**
  - every route declares a typed `response_model`, with no `dict[str, Any]` and no `extra="allow"`;
  - status codes use `fastapi.status` names;
  - query and path params are validated with `Query(gt=0, le=...)`/`Annotated`, not `if` statements;
  - configured limits, cursor decoding and continuation checks are application policy.
- **Request bodies use `extra="forbid"` (M);** response models keep the default.
- **Per-route authorization** uses route dependencies (`Security(require_scope(...))`), not method/path tables in middleware. (M)
- **Relax `api/schemas/` (L).** Reuse an application model when it is deliberately the public contract (frozen, `extra="forbid"`). Create `api/schemas/` only when the HTTP shape differs. The canonical tree lists roles, not required filenames (`api/problems.py`, `api/sse.py` are fine). Keep domain types out of `api/schemas`, and don't re-export them there.
- **Streaming use cases (M).** The application runs the whole execution and returns a typed stream of business events, including the terminal outcome. `api/sse.py` only encodes, sends heartbeats and turns disconnects into cancellation.

### 4.15 Boundaries: validate external structure — **H** · OPS, DA
- At a JSON, queue, HTTP or SDK boundary, verify the shape and types of required nested fields before building a domain value. Convert malformed input to a stable boundary error.
- Never `str(value)` an arbitrary provider value to satisfy a string contract.
- Preserve deliberate handling of documented alternate envelopes and test events.
- Validation happens at construction only: `model_copy(update=...)` **does not revalidate** (verified). Use it only for already-validated values that can't violate a cross-field invariant. Rebuild with `model_validate` for untrusted input, arithmetic that may cross bounds, or updates to related fields.

### 4.16 Duplication and extraction triggers — **H** · OPS, IM, CTL, DA
Replace the permissive wording ("propose a later extraction", "legitimately varies", "may move to a library") in:
- arch `SKILL.md` discovery step 7;
- `shared-libraries.md`;
- db `repo-layout.md`;
- the otel scope rules;
- the audit's shared-capability review.

With:
> - A module identical (apart from package name) in **≥3 deployables**, or **two copies that have diverged semantically**, is a finding that must be resolved: extract it, or comment in each copy why the semantics differ.
> - An identical non-business helper in ≥2 services whose natural library is *already a dependency of both* moves there now; this doesn't require a new library.
> - Until extraction, a new copy matches existing public signatures exactly.
> - A library's config input is a concrete frozen dataclass the library owns, not a Protocol of properties.
> - An implicit shared storage layout (a prefix one service writes and another purges) is a contract with one owner.
> - Before finishing, grep the other members for identical function names.

Keep the counter-rule: code that differs in meaning, lifecycle or dependencies stays local. Settings loaders: see D3.

### 4.17 Shared libraries — **M** · OPS, IM, DA, CTL
- Shared vocabulary (enums, JSON document contracts, value types) lives in a module importable **without SQLAlchemy/SQLModel**. Domain and ports never import the ORM package root. The schema lib may own these contracts but never runs queries or reads session state.
- A service extends a library type only through documented public hooks. If a subclass needs `self._private` state, the library is missing an extension point. A callback override never swallows `super()` exceptions.
- Library independence is guarded by an import-boundary contract test: no `os`, no `pydantic_settings`, no service imports.
- Add an exception to "avoid mutable module-global state": process-singleton SDK state behind idempotent configure/shutdown and a test reset hook.
- Temporary re-exports have a removal trigger: remove them in the same change once in-repo consumers migrate. An in-repo re-export shim with only internal consumers is a violation.

### 4.18 Removing a capability removes its generality — **H** · CTL
When a capability is removed, delete in the same change:
- the parameters, branches, `**kwargs` pass-throughs, HTTP verbs, shims and error mappings it justified;
- its domain-record fields and read paths;
- dead helpers and stale e2e/live expectations.

Keep DB columns until a contract migration drops them. Before finishing, search for single-value parameters and test-only call paths. Add this to `modularization.md` "Migration sequence" and to `CLAUDE.md` #9.

### 4.19 Adapter layout additions — **M** · DA, CTL
- `db/` owns all SQL, including DDL, bootstrap SQL and staging loads.
- Delete production modules only tests use.
- Don't name production packages `fixtures/`.
- Every module belongs to a layer or capability package; no top-level miscellaneous module.

### 4.20 Deduplicate the skill itself — **M** · IM, DA, CTL
- State each placement rule once, in `boundaries.md`; see §1.1.
- The 22-bullet "Dependency audit" (`boundaries.md:307-337`) lives only in the audit skill.
- Remove the repeated `modularization.md:74-89` review questions.
- Keep `core/` guidance once.
- `ai.md:166-189` module-size advice points to the single source.
- "External naming": give a concrete check (identical service name across pyproject, package, container and `service.name`) or remove it.
- Spend the saved space on the code-level API and worker rules above.

---

## 5. `python-service-architecture-audit`

### 5.1 Make the script catch what it can — **M** · OPS, DA, CTL
It reported 0 violations on most services while real issues existed. Every check cites the owning rule by ID. Treat script failures as *candidates to confirm*, not verdicts. Print "static checks passed; semantic audit pending".

New checks (review notices unless noted):
- **Imports:**
  - `application`/`domain` → `config` imports (and add `config` to the forbidden set);
  - `api`/`adapters`/`db`/`genai` → `bootstrap` imports;
  - `INTERNAL_FORBIDDEN["observability"] = {"application"}` plus entries for `api`, `adapters` and `observability`;
  - resolve §4.10 so the OTel-in-application check agrees with the architecture skill.
- **Ports:**
  - signatures containing `Any`/`object`/`Mapping[str, Any]` or framework-verb names;
  - `ports/<m>.py` not imported by any `application/` module;
  - I/O calls in `ports/`;
  - Protocols with exactly one implementation that lives in `application/`.
- **Code smells:**
  - `assert` in `src/`;
  - `getattr(<exc>, …)` inside `except`;
  - `X | None = None` constructor parameters in `application/`/`genai/`;
  - `datetime.now`/`uuid4`/`random.` in `domain/`/`application/` outside default arguments;
  - exception classes carrying `public_message`/`status_code`/`retryable`.
- **Structure:**
  - `text(`/`.execute(`/`psycopg` outside `db/`, including in `bootstrap/`;
  - functions over ~60 lines in `bootstrap/`, and repository methods over N lines/complexity;
  - `adapters/<x>/` with exactly one non-`__init__` module;
  - `__init__.py` defining classes or functions (services);
  - `observability/__init__.py` importing `langchain*`;
  - modules whose body is only imports plus `__all__`;
  - identical `genai/*/llm.py` bodies;
  - `model: Any` / `-> Any` in `genai/`.
- **Duplication:**
  - modules byte-identical across workspace members;
  - duplicate private function names across modules;
  - a string literal in ≥3 modules.
- **Transport fields:** add `traceparent`, `trace_carrier`, `stream_seq` and `delivery_attempt`.
- **Wording:** "relative import crosses an implicit boundary" becomes "relative import (forbidden)".

### 5.2 Reference, don't restate — **M** · OPS, DA, IM
The audit's "Semantic audit" bullets restate `boundaries.md`, GenAI tool rules and observability placement. Keep only the procedure, and reference arch sections by name or ID. Add "port failure with no handler" (§4.11) and "pass-through wrappers" (§2.10) to the checklist.

### 5.3 Report-only default
See §1.3.

### 5.4 Persistent fitness tests — **M** · IM, CTL, DA
Recommend a persistent architecture-fitness test (import-boundary checks with a shared AST inspector that has its own mutation/sensitivity tests), not only the one-shot script.

---

## 6. `python-sqlmodel-alembic`

### 6.1 Fix the engine and examples — **H** · OPS, IM, DA, CTL
- **Delete the module-level `engine = build_engine(settings.database_url)`** (`engine-and-session.md:20,38-39,85`).
  - Show `build_engine(url, *, pool_size, ...)` called in `bootstrap/runtime.py`, with `engine.dispose` registered on the `AsyncExitStack` immediately.
  - `session.py` exposes `build_session_factory(engine)` and imports no global engine.
- **Pool sizes** come from settings; the builder has no literals and validates sizes. Use `max_overflow=0` when pool capacity is an intended concurrency cap or the database is external.
- **One-shot processes** (CLIs, probes, diagnostics) build a pool-of-1 or `NullPool` engine and dispose it in `finally`. This is an exception to "never create an engine per call".
- **Type the repository examples:** `self._session`, typed returns.
- **`TableBase.created_at: datetime | None` with `nullable=False`** makes callers `assert row.created_at is not None`. Explain the trade-off (the value is `None` only before flush), or use a non-optional type with `init=False`.
- **`onupdate=`** fires on ORM flushes and Core `update()`. State the real gap: raw `text()` SQL and migration backfills.
- "Async only" gets an exception for the sync `Connection` inside `run_sync`.
- Recommend the `sqlalchemy[asyncio]` extra over the greenlet advice, or state that it applies to every member importing `sqlalchemy.ext.asyncio`.
- Make "Prefer SQLModel's `AsyncSession`" conditional (use it when returning model instances); Core-shaped repositories gain nothing from `.exec()`.
- Keep one query style per repository (`session.exec` vs `execute`, `col()`).

### 6.2 Transaction ownership / unit of work — **H** · all four
Add "Transactions and the unit of work" to `engine-and-session.md` and a bullet in `SKILL.md`. The skill's `get_session` never begins or commits, so every service reinvented this.
- **Repositories never call `commit`/`begin`/`rollback`.** They may `flush()`.
- **Exactly one owner draws the transaction,** chosen by who needs atomicity:
  1. **One port call = one transaction:** a `...Store` holds the session factory and opens a transaction per method, and composes repositories inside it. A thin `db/*_transactions.py` coordinator may import `AsyncSession` for this; it doesn't implement queries or policy.
  2. **The application needs several operations atomically:** a UoW async context manager exposes repositories and `commit()`, rolls back on exception, and always closes the session. Open the session in `__aenter__`, not `__init__`.
- **One `unit_of_work` / `transaction(factory)` helper** per service (in a shared lib when ≥2 services have it) opens `sessions.begin()` and translates driver failures. It replaces repeated `try / begin / except SQLAlchemyError / raise XFailure from` in every method. Include one read-only variant. Code must not bypass the helper with an ad-hoc `async with factory() as s, s.begin()`.
- When ≥2 UoWs differ only in repositories and error type, share a private base.
- **No forwarding stores:** don't add a class whose methods only open a session and forward to a same-named repository method. Don't use callable "repository factory" Protocols.
- Bootstrap constructs *factories* (session factory, `lambda: UoW(sessions)`); repositories are built per transaction.
- Durable "run started" markers get their own committed transaction. Plain reads may autobegin.
- Repositories don't construct sibling repositories. A query several repositories need (a fenced ownership read) is a shared module-level function taking a session.

### 6.3 DB failure contract — **H** · CTL, OPS
- Every public DB-adapter method returns a port type or raises a port-owned exception:
  - **Unavailable** (`SQLAlchemyError`, `OSError`, `TimeoutError`): retryable;
  - **Integrity/corrupt state:** a named error, never `RuntimeError`.
- Translate at the outermost DB boundary: UoW commit/exit, or the method that opens its own session. Code outside `db/` never needs `except Exception` to detect a DB failure. `CancelledError` passes through untouched.
- **`IntegrityError`:**
  - for idempotent inserts, prefer `INSERT … ON CONFLICT DO NOTHING RETURNING`, then select the existing row;
  - when catching, match the **named constraint** and re-raise anything else generically, so a CHECK/NOT NULL violation is never reported as a duplicate.

### 6.4 Where SQL lives — **H** · all four
- Replace "`repositories/` is the *only* code that imports `AsyncSession`/`text()`" (`SKILL.md:88-99`) with:
  > Only the service's `db/` package (and shared DB libraries) imports these. Ordinary entity reads and writes go in repositories. A cohesive operation (UoW/coordinator, lease manager, advisory lock, retention pass, schema probe, external read-only DB) may live in a precisely named `db/` module. Application, domain and ports never run SQL.
- Make the `repositories/ → queries/*.sql` diagram optional.
- Don't require an application port per table.
- Direct psycopg is valid for PostgreSQL-specific privilege, cursor or policy work.
- **Replace the `.sql`-file rule** ("multi-join/aggregate SQL goes in `.sql`"):
  > Keep a query beside its method when filters, joins, locking, projection and bound parameters read clearly together in SQLAlchemy. That's especially true for queries that compose, vary, or reuse shared predicates and clock helpers. Move **long, static** reporting/DBA-reviewed SQL to a packaged `.sql` resource. Load it once via a resource helper (not file I/O at import time), and verify it ships in the wheel. Choose by readability and ownership, never by join count.

### 6.5 Work queues: claim, lease, fence — **H** · OPS, IM, CTL
Add a "Work claiming and leases" section. Every OPS service is a Postgres-backed queue.
- **Claim in one statement:** `UPDATE … WHERE id IN (SELECT id … WHERE <due predicate> ORDER BY … LIMIT :n FOR UPDATE SKIP LOCKED) RETURNING <needed cols>`. Re-sort in Python, because `RETURNING` has no order guarantee. Loop per candidate only when a parent must be locked first; lock parents in bulk, in sorted order.
- Write a fresh `lease_token`/`lease_until`.
- **Every later write is fenced:** filter on expected state, lease owner/token **and** `lease_until > now()`, with `RETURNING id`. Report "no row" as **one** typed outcome (`WriteOutcome.STALE`) used consistently across the repo; an exception is fine if a stale write is truly exceptional, but pick one.
- **State transitions are guarded compare-and-set updates:** one `UPDATE … WHERE <current-state guard> RETURNING`, never read-modify-write in Python. Guard every column the decision depended on (`IS NULL` for nullable ones). After a Core UPDATE, re-read with `populate_existing=True` or use `RETURNING`.
- **No external I/O while holding locks:** claim → commit → external call → fenced write in a new transaction. If holding the lock *is* the point:
  - bound the batch and the external timeout;
  - set `idle_in_transaction_session_timeout`;
  - comment the invariant the lock protects.
- **Lock ordering and timeouts:**
  - lock the aggregate root before its children, and multiple rows in PK order;
  - prefer `pg_try_advisory_xact_lock`; use a session-level lock only when it must outlive a transaction, and then on a dedicated connection;
  - use a transaction-scoped advisory lock when uniqueness is logical rather than enforced by an index;
  - a transaction that waits on `FOR UPDATE` without `SKIP LOCKED` sets `SET LOCAL lock_timeout`.
- Keep the "eligible work" predicate in one shared named SQL expression used by claiming and demand counting.
- Design a partial index for every claim or scan predicate (`postgresql_where`).
- Code that depends on READ COMMITTED semantics says so in a comment.

### 6.6 Per-transaction limits and external read-only databases — **H** · CTL, DA
- **Per-transaction limits:**
  - Every query against a DB the service doesn't own, and every batch or maintenance statement against one it does, runs in an explicit transaction that first sets `set_config('statement_timeout', :v, true)` (plus `lock_timeout` for writes), with a bound parameter.
  - Implement it once per DB package (`apply_transaction_limits`), with an explicit unit and rounding up.
  - Own OLTP DBs get a role- or engine-level default, so no query is unbounded.
  - Put invariant session settings (search_path, read-only default, `prepare_threshold=0` behind PgBouncer) in the pool `configure` callback or connection `options`, not per query.
- **External read-only DBs** (new `references/external-read-databases.md`):
  1. a least-privilege read-only role, verified by a runnable acceptance check;
  2. `SET TRANSACTION READ ONLY` plus local limits;
  3. results bounded in SQL (`LIMIT n+1` to detect truncation, or keyset);
  4. `text()`/Core mapped into frozen dataclasses, no ORM;
  5. `max_overflow=0` and an acquisition timeout;
  6. one `…SourceUnavailableError`.
- **Untrusted / LLM-authored SQL** (defence in depth, all required):
  1. AST allowlist before pool checkout;
  2. a reader role with `default_transaction_read_only=on`, a pinned `search_path`, and grants only on `security_barrier` views;
  3. transaction-local timeouts, never session-level `SET`;
  4. `SELECT * FROM (<q>) LIMIT max_rows+1`;
  5. `fetchmany` capping rows and bytes;
  6. retry transient errors only, never `QueryCanceled`;
  7. validate once and pass the validated plan down.
  Don't route trusted internal queries through this path. Cross-link from `ai.md`.

### 6.7 Raw SQL safety — **H** · CTL, DA, IM
- Values are always bound, including `IN` (`bindparam(expanding=True)` / `= ANY(:arr)`). Never hand-escape.
- Identifiers go through one validated quoting function in a *public* module of the DB package (`psycopg.sql.Identifier`, dialect quoting, or a trusted allowlist). DDL identifiers and passwords use `format('%I','%L')`.
- An f-string is allowed only for a module constant or an already-validated int, with a comment.
- For composed optional filters, one builder returns `(clauses, params)` and owns all placeholder numbering. Use `$n` only where externally authored SQL must round-trip exactly.
- Build CHECK constraints and partial-index predicates from the owning `StrEnum` via `column.in_()`, never by string concatenation.
- Never execute SQL text taken from outside the repo under an application role.
- Inside a transaction, never run cleanup SQL in `finally`; rely on rollback or `ON COMMIT DROP`.

### 6.8 Efficient reads and bulk writes — **M** · OPS, IM, CTL, DA
- Select only the columns the result needs, especially for hot claim, scan, status and list queries over wide rows (large JSONB/text). Apply the DB-side page bound before building objects. A detail operation legitimately loads everything.
- Process a page of N items with a bounded number of queries per page, not per item: `IN`/`= ANY` lookups into a dict, one query per hop for graph traversal.
- Build counters and indexes once, not inside loops (no quadratic `sum(x == v for x in rows)` per value).
- Validate paginated accumulation incrementally (`seen_keys` set), not by rescanning the full prefix.
- Do pagination and "latest per key" in SQL with keyset predicates, not by deserializing everything.
- A bulk state or FK change is one `UPDATE … WHERE id IN (…)`, not a load-modify-flush loop.
- Bulk upsert uses `insert().on_conflict_do_update(...)`. Derive chunk size from the 65,535 bind-param limit (`65535 // n_columns`), not a magic number.
- A projection "rebuilt every run" must delete rows this run didn't produce; an upsert alone isn't a rebuild.
- Repository ports accept collections when callers would otherwise loop; return early on empty input.
- A per-row loop inside a transaction is acceptable only when bounded by configuration and each row depends on the previous one; state the bound.
- Add an operation-count regression test only for a demonstrated hot path. Assert a bound or scaling shape, not a universal one-statement target.
- Map rows through typed accessors, not `row: Any` with string keys.

### 6.9 Column vocabularies, JSON codecs and shared transitions — **H/M** · OPS, IM, CTL, DA
- **(H)** A status column is annotated with its `StrEnum` (living in the shared models package), stored as `Text`, and guarded by a named CHECK generated from the enum. Reads return members.
  - Domain enums convert in exactly one pair of functions per repository module; never pass a domain enum straight into a column expression.
  - A predicate reused by a partial index and by queries (`index_where`) is defined once next to the model.
- **(M)** Each typed JSON column and each wire format gets one encode/decode pair (`TypeDecorator` or helpers) with one fixed `model_dump` mode. No ad-hoc `model_dump`/`model_validate` in repositories.
- **(M)** Name the serialization contract at every storage or wire boundary: `model_dump(mode="json")` or one contract serializer, and validate again on read. Choose `exclude_none` and key order deliberately.
- **(M)** One canonical-JSON / fingerprint function per member: `model_dump(mode="json")`, then `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, with **no `default=str`**.
- **(M)** A multi-column state transition (revision counter, sync status, lease reset) is one update-values builder next to the model. Share predicates and transitions; repositories stay per service.
- **(M)** Pick one column-access style per repository package, and export typed `Table` handles once.

### 6.10 One database-clock helper — **M** · OPS
- Compute leases and deadlines in SQL with the DB clock through one helper module (`now()`, `now_plus(seconds)`).
- Pick `now()` (transaction start) or `statement_timestamp()` (statement start), document the choice, and keep it identical across services.
- Fetch `SELECT now()` only when application code needs the value itself; don't open a transaction just to read the clock.

### 6.11 Retention and bulk maintenance — **M** · CTL
Scheduled deletes and updates:
- are bounded per statement (`DELETE … WHERE id IN (SELECT … ORDER BY ts, id LIMIT n) RETURNING id`) and commit per batch;
- set local timeouts;
- delete children before parents, or rely on `ON DELETE CASCADE`, never both;
- guard rows still referenced by pending work;
- use `pg_try_advisory_lock` for multi-replica jobs, and invalidate the connection if unlock fails;
- are backed by a partial index the delete implies.

### 6.12 Migrations — **M** · IM, CTL
Document these, each already working in some repo:
- Serialize migration runs with a named `pg_advisory_lock` and bounded `lock_timeout`, plus a test that two runners can't overlap.
- The runner exposes `upgrade`, `check` and `sql`, with `compare_type` and `compare_server_default` on.
- Check the data before tightening constraints: query violations and fail with example keys and an operator instruction.
- Every `downgrade()` is an exact inverse, or raises deliberately with an operator-facing reason, and refuses data loss.
- Drop a backfill `server_default` after the backfill unless the model declares it permanently.
- Migrations never import live model constants; they inline frozen copies.
- **Naming:**
  - Fix `"uq": "uq_%(table_name)s_%(column_0_name)s"` to `column_0_N_name`; choose it before the first migration.
  - Let the convention name every PK/FK/UQ/CK/IX, and use `op.f()`. Hand-name only what it can't express, or name every constraint explicitly in `__table_args__`.
- Update `script.py.mako` to house style (PEP 604 unions, `collections.abc`, typed `revision`/`down_revision`).
- Use one SQLAlchemy type per concept (`sa.Uuid()`, `sa.func.now()`).
- Revision ids follow `YYYYMMDD_NNNN_<slug>`.
- **Tests:**
  - Assert a single head via `ScriptDirectory.from_config(cfg).get_heads()`; never count files.
  - A DB-free test asserts the code's schema-revision constant equals `get_current_head()`; tests reference that constant, never a literal id.
  - Call Alembic `command.*` from async tests via `asyncio.to_thread`.
- After a feature removal, file a contract (drop) migration for the next release, and remove unused dialect variants.

### 6.13 Schema ownership and prototype mode — **H** · DA
- Every schema object has one owning deployable and one versioned history. Disjoint owners get separate `version_table_schema`s. Cross-owner dependencies (views over another owner's tables) are declared, and their ordering enforced by the deploy graph.
- `create_all()` and hand-rolled initializers are allowed only in a declared **rebuild-only prototype mode**, stated in the module docstring. Its exit criteria: a second DDL owner, or the first persistent environment. One-shot initializers take an advisory lock.
- A consumer's column contract over a shared schema is derived from the shared metadata, not re-typed. Contract tests compare **types**, not only names.

### 6.14 Stack routing — **H** · DA
The skill assumes SQLModel + Alembic; DA uses raw psycopg and no Alembic.
- At minimum add a routing line: "If the service uses psycopg directly (including LangGraph `AsyncPostgresSaver`), follow `references/psycopg.md`."
- Optionally rename the skill to `python-postgres-data-access`, with references for SQLModel/SQLAlchemy async, psycopg/psycopg_pool, Alembic, and roles/read paths.
- Generalize the pool guidance to `psycopg_pool`: construct pools unopened in bootstrap, from settings, with an explicit `max_waiting` and acquisition timeout.

### 6.15 Disposable test databases — **M** · CTL, DA, IM
- The integration fixture reads a variable separate from `DATABASE_URL` (`INTEGRATION_<DB>_DATABASE_URL`) and refuses non-disposable names (non-loopback hosts, no `test_` prefix).
- It **fails rather than skips** in CI profiles (a `requires_env` marker); fix `schema-verification.md:97` "skip when unset".
- Each service's fixtures drop only the schemas it owns.
- The testing docs use a URL that passes the guard.

---

## 7. `otel-observability`

### 7.1 Exception-detail rule — **H** · OPS, DA, CTL
See D5 for the policy.
- `conventions/errors.md` is the single owner; replace the other ~17 statements with a link.
- Phrase it as a call-site rule: "Call sites never build `exception.*` fields; pass `exc_info=exc` and nothing else. The shared processor applies the setting."
- Hand-built stack traces drop the message and the `__cause__` chain.
- The shared library must not bake in an environment policy.

### 7.2 `set_status_on_exception` — **H** · CTL, DA
This has already caused a defect: spans left UNSET, which error-biased sampling then drops.
- In `errors.md`: "Ad-hoc spans pass only `record_exception=False`. Only a generic helper that itself catches `BaseException`, sets `ERROR` and `error.type`, and re-raises may disable `set_status_on_exception`. A narrow `except SpecificError` doesn't make disabling it safe."
- Remove the conflicting sentence from `shared_library.md:152`.
- **Cancellation semantics for span helpers:**
  - handle `BaseException`;
  - cancellation during shutdown records `app.outcome=cancelled` without `ERROR`;
  - a timeout-caused cancellation records `ERROR` with `error.type=TimeoutError`.

### 7.3 Snippets call the shared helper — **H** · DA
- The ~15 `except Exception as exc:` snippets use `with start_span(...)` (which marks and re-raises).
- Show the hand-written `set_status` + `error.type` form once, labelled "only inside framework callbacks where a context manager can't be used".
- Remove the redundant `except CancelledError: raise` arms (`streaming_and_agent_span.md:79-89,226,284`).

### 7.4 Telemetry failure isolation and intrusion budget — **H** · DA, OPS
- **Isolation:**
  - Don't wrap OpenTelemetry *API* calls in try/except; the API is specified not to throw.
  - Guard app-owned telemetry code at most once, at the framework-callback or close boundary, with one `telemetry_failed` warning carrying `exc_info`. Never `except Exception: return`.
  - Instrumentation wrappers record the failure and re-raise; business code decides whether to contain it.
  - Telemetry may observe an outcome but never chooses or mutates it, and never enforces business behaviour such as cancellation.
- **Budget:**
  - Business functions contain at most one-line telemetry constructs (≈3 lines per call site).
  - One helper per unit-of-work boundary (`with work_boundary(name, failure_event=...)`) closes span error + error log + metric on every exit path, never N manual close calls.
  - Replace `if telemetry is not None` with a no-op implementation.
  - Completion logs carry the outcome plus ≤~8 independently queried fields; the rest are span attributes.

### 7.5 Constants: only for shared names — **M** · OPS, CTL, IM
Replace `naming.md:210` "Do not scatter string literals":
> Span, metric and event names, and attribute keys shared across signals, emitters or tests, are constants in the conventions module. Semconv keys may be literals. A log-only field key used by one module may be a literal. Keep the conventions module as the vocabulary, not a mirror of every key. Review large modules for single-use entries (no numeric cap).

The reviewers counted 78–181 constants per service.

### 7.6 Testing telemetry — **H** · CTL, DA
Rewrite `references/testing.md`:
- Module-level tracers and instruments are the default (they're proxies).
- Tests install one session-scoped global `TracerProvider(InMemorySpanExporter)` and `MeterProvider(InMemoryMetricReader, views=<production views>)` in `conftest.py`, and clear the exporter per test.
- Metric assertions filter by a unique attribute or compare before/after values (cumulative temporality).
- Never monkeypatch instruments or `trace.get_tracer`. Assert production names, units and attribute keys.
- Yield a typed `TelemetryCapture` dataclass (tracer provider, span exporter, meter provider, metric reader), not a bare exporter or a 4-tuple, from the member's support package.
- Fix the undefined `tracer` / `data_points` fixtures and the `Any`-typed helpers.
- Test code that owns global provider registration in a subprocess.
- Add a pointer from pytest.

### 7.7 Metrics — **H/M** · CTL, DA
- **(H) State gauges:**
  - Current state held in an object is an `ObservableGauge` whose callback reads it, registered once at the composition root.
  - A sync `Gauge.set()` only for a value computed at one well-defined point, with exactly one writer.
  - Each counter event has one owning call site.
  - Zero baselines only for instruments with a live writer in that process.
  - One metric name has exactly one producing service; grep before adding.
- **(M)** One measurement goes to one instrument. Before adding a counter, list the instruments that already count the event (including a histogram's `_count`). Each new instrument or attribute names the query, dashboard or alert it serves.
- **(M)** Declare histogram buckets at creation with `explicit_bucket_boundaries_advisory`. Use the central `View` registry only for third-party instruments. Every histogram that can exceed ~5 s or counts tokens/rows declares boundaries.
- **(M)** New instruments use `app.<domain>.<noun>` with a UCUM unit and no `_total` or unit suffix. Renaming an existing name is an explicit migration (dual-emit, then remove).
- **(M)** A recorder function only when an instrument is recorded from ≥2 call sites or needs normalization (`metrics/genai.md:33`).
- **(M)** Put instruments in the service's existing metrics module, not the mandated `genai_metrics.py`/`agent_counters.py`. Provider setup lives in bootstrap or the shared lib; instruments live with their capability once a module passes ~15.
- **(M)** Mark each `gen_ai.*` row in `metrics/genai.md` as stable, development or app-defined; move non-spec rows to `app.gen_ai.*`.

### 7.8 One attribute vocabulary — **M** · CTL, DA, IM
- Outcome is always `app.outcome` and classification always `error.type`, on spans *and* app metrics; no `status`/`result`/`error_code` synonyms. Metric labels use the same keys as span attributes.
- `error.type` is one of: the exception class name (via one shared `error_type_of(exc)`), a provider status/code, or the service's documented closed error-code enum. Unclassified is `_OTHER`.
- A business failure taxonomy goes in a separate attribute (`app.failure.class`). Fix `errors.md:170-171` versus `:145/:166`.
- Drop the `_NONE`-on-success rule or explain it; it's unused.
- Provider error-code extraction and transient classification exist once, in the shared library.
- Never build attribute, metric or log keys from runtime values (no f-string keys); use a bounded attribute *value*.
- Keep one short key/value-set table per service in the `observability/` module docstring.
- Log event names and label keys come from one enum per service, checked by a regex test. Pick one event-name style and make the skill's examples use it.

### 7.9 Logging rules — **M** · CTL, OPS
- The first positional argument of a log call is a snake_case past-tense event name, never a sentence with values. Derive the OTel `event_name` mechanically; don't keep two names per event.
- One call-site logging API per repo (stdlib `extra=` or structlog kwargs), recorded in the shared lib's docstring.
- A function that logs a summary *and* re-raises omits `exc_info`; the handling boundary logs it.
- **Loops:** count every failure, but log only on state transitions (healthy→failing with `exc_info`, failing→recovered with count and duration). A condition exported as a gauge is alerted from the metric.
- Replace the default `job_started`/`job_completed` plus warning-per-recovered-failure (`business_events.md:18,21`) with: `job_failed` (owner) plus one terminal business event.
- Don't create a retroactive span just to host a failure log that happened before any unit-of-work span existed.
- **Structlog / allowlist:**
  - An allowlist processor fails in tests on unknown keys, or emits a dropped-fields marker; it never silently discards authored fields.
  - Route the root stdlib logger through the same `ProcessorFormatter`.

### 7.10 Scope and consistency across siblings — **H** · OPS
Replace the tension in `SKILL.md` scope with: "When adding observability and sibling services already have `observability/`, read their public helper signatures first and reuse them verbatim. Helper API consistency is in scope even when editing siblings isn't." Four services had four incompatible `mark_error` signatures.

### 7.11 One redaction module — **H (security)** · CTL, OPS
One redaction module (patterns plus a recursive `mask(value)`) is owned by the shared observability library and imported by both the log processor and the GenAI content serializer. Each sink has a canary test (`api_key=`, Bearer, AWS key).

### 7.12 Fix the samples — **M** · OPS, DA
In `structlog.md`:
- `get_settings()` is called at module import;
- `exception.message = str(exc)` is set before redaction;
- redaction is left as a comment;
- `service.name` vs the flat `service_name` needs one ruling;
- the worker-runtime example uses sync `signal.signal` plus a global flag; replace it with the asyncio stop-event shape (§4.13).

### 7.13 Smaller rules — **M/L** · CTL, OPS
- **(M) Spans are write-only:** never read attributes back. `gen_ai.usage.*` goes only on model-call (and agent) spans; roll-ups use `app.*`.
- **(L) No spans as events:** emit a log plus a counter. Don't copy `http.*` attributes onto internal spans.
- **(M) Parent vs link:** a one-line table in rule 12. Outbox publish → link; queue redelivery → link plus `app.message.attempt`; synchronous in-process call → parent.
- **(L–M)** Start the root span only after the claim returns work, and count empty polls instead. Don't filter empty-poll spans at the exporter.
- **(M)** Per-item spans carry no positional or debug attributes unless a named investigation needs them. Before adding any signal, name the operational question and the expected volume.
- **(M)** `shared_library.md:132-141,209-218` lifecycle requirements: implement only the invariants a current consumer exercises; with one bootstrap call, "configure once; raise on a second call" is enough.

### 7.14 Replace the prose validator with a code audit — **M** · DA
A script of about 150 lines that flags:
- a broad `except` that neither re-raises nor logs;
- `"exception.` literals outside the processor;
- `record_exception(` and `add_event(`;
- f-string attribute keys;
- invalid `error.type` values;
- redundant `CancelledError` arms;
- try/except around OTel API calls.

---

## 8. `python-logging`

- **Allowlist reconciliation — H · IM.** If a formatter uses an allowlist, review each new event's authored fields against it, and verify the serialized record contains the fields needed to answer the event's question. Either register the field with an agreed name and type, or omit it at the call site. Tests parse representative output, including retry and failure paths. Keep redaction before serialization. See also §7.9.
- **Silent degradation leaves a trace — M · IM.** When code catches and continues with a fallback, it catches the narrowest type and emits one warning with bounded `error.type`, or carries a why-comment if logging would be pure noise. Add this to `errors-and-security.md`.
- **Module-level logger — L · IM.** Use `logger = logging.getLogger(__name__)` once below the imports; never call `getLogger` inline at each call site.
- **Canary test — L · IM, DA.** Add a concrete "secret never appears in logs" test to `testing-and-verification.md`.
- **Standardize — M · IM.** Allow-listed fields plus a formatter that validates the event-name pattern.

---

## 9. `pytest` (+ `python-service-architecture/references/testing.md`)

### 9.1 Importable shared test support — **H** · all four
Replace the unsatisfiable rule set (§1.2) with one declared mechanism:
- When a double, builder or harness appears in **≥2–3 modules** of a member, or subclasses a third-party type or implements a production port, extract it:
  - Reusable *instances* (exporter, manual clock, engine, fake runtime) become fixtures in the narrowest `conftest.py`.
  - Reusable *types* go in a member-qualified support package: `services/<svc>/tests/<svc>_testing/`, importable via per-member `pythonpath` plus the matching `mypy_path`, **or** an installed dev-only package. State which one the repo uses, and never rely on bare module names.
  - Disposable-infrastructure lifecycle identical across members (DB URL guard, reset, migrate, dispose) goes in one workspace test-support package or pytest plugin.
- **Forbidden:**
  - fixtures returning a module (`sys.modules[__name__]`);
  - fixtures returning a class or function just so tests can reach it;
  - `type(fixture().attr)`;
  - importing another deployable's test helpers.
- Paths resolve from `__file__`; env vars are read inside fixtures, not at import.
- Counterweight to "fixtures hide scenarios": setup carrying no scenario facts *should* be a fixture once repeated.
- Configure test paths per member, not as a root `pythonpath` list of every member (repository-setup).

### 9.2 Doubles must be correct — **H** · DA, CTL, IM
- **UoW fakes are transactional:** writes become visible only on `commit()`, and exiting without commit discards them. Assert on the committed store; counting commits isn't a substitute.
- **No assertions inside doubles.** Doubles record, and the test asserts afterwards. An `assert` inside a double, called by production code under `except Exception`, passes vacuously. To reject unexpected input, raise `UnexpectedCall(BaseException)`.
- Fakes record what they received, in order, without sorting, deduping or canonicalizing.
- **Scripted models, tools and runners raise** `AssertionError("unscripted call N to <name>")` when exhausted; they never repeat the last response.
- Every harness or builder parameter is used; delete unused helpers.
- Prefer small typed recording fakes (`fake.decisions == [...]`) over `call_args`/`await_args` archaeology. Never echo `call_args` back into the expected value.
- Default to zero `unittest.mock`. Use `httpx.MockTransport` for HTTP and `create_autospec(Port, instance=True)` over `patch`. No spec-less `Mock`/`AsyncMock` for ports.
- One fake per port per member. Move fakes over ~100 lines, or used by more than one module, to a `fakes` support module.

### 9.3 Bounded waits and deterministic time — **H** · CTL, DA, IM
- Every `await` on an event, queue, task or future in a test is wrapped in `asyncio.timeout(...)` (≤1 s for unit tests).
- Poll only through one bounded helper (`await wait_until(pred, timeout=1)`); `while cond: await asyncio.sleep(0)` is forbidden. Don't count event-loop yields.
- For "nothing happens" assertions, drive a deterministic step (manual clock plus `tick()`). If a real broker makes that impossible, name the window as a constant and keep the test in the integration profile.
- Test builders default to minimal time budgets (≤0.1 s). A unit test over ~1 s is a defect; check `--durations`.
- Prove order-independence by forcing an adversarial completion order (release per-item `Event`s in reverse), not with random sleeps.
- Drive timeouts with an injected clock; never `sleep(2 × timeout)`.
- Unit tests never sleep in real time.
- Identify real-infrastructure resources with `uuid4()`, not timestamps.

### 9.4 Mechanical quality-gate checklist — **H** · CTL, IM, DA
Add a greppable checklist below the prose gate (`SKILL.md:186-207`). Reject:
- a bare `.wait()`, or `await task`, without a timeout;
- `while …: await asyncio.sleep(0)`;
- `assert` inside a double;
- an asserted value no code path under test writes, or asserts on a local literal, the environment (`datetime.now().year`), or `is not None` on factories that can't return `None`;
- an expected value computed with the production expression;
- `pytest.raises((A, B))`, unless the contract really is a union (say so). Use `match=` or an attribute check identifying the reason; in parametrized rejection tests, every case needs a reason oracle;
- a spec-less `Mock`/`AsyncMock` for a port;
- `SimpleNamespace` for a typed collaborator or constructible library type;
- `cast(Any, …)`, `object.__new__(Subject)`, or `# type: ignore` to force a double to fit;
- private `._x` access or calls, unless the test is an explicit white-box contract that says so;
- non-trivial parameter tables without `pytest.param(..., id=...)`, parameters unused, or the body branching on a parameter (split success and failure);
- a compound `assert x is not None and x.y == …` (narrow on its own line).

### 9.5 One behaviour per test — **M** · DA, IM
- A test asserts one behaviour's oracle. Business outcome, emitted telemetry and framework graph shape go in separate tests that share the harness, not the assertions.
- A name joining independent outcomes with `_and_` signals a split; sequential protocols are exempt.
- Use exact values for deterministic results.
- Prefer one high-level wiring test plus narrow behavioural tests over repeating a matrix at every layer.
- This refines "assert the complete semantic outcome" and isn't a one-assert-per-test rule.

### 9.6 Typed fixtures and builders — **M** · DA, OPS, IM, CTL
- Fixtures and builders return concrete types, never `Any`.
- Replace tuple fixtures with frozen dataclasses.
- Keyword builders per important domain type (`owned_work(**overrides)` with defaults), built through real constructors, using `dataclasses.replace` / `model_copy`; never `Model(**values)  # type: ignore`.
- Integration seeding uses typed row builders, not inline `INSERT` SQL (unless the SQL is under test).
- Tests build settings with a typed helper or `model_validate`, not env mutation plus `# type: ignore[call-arg]`. Application tests shouldn't need `Settings` at all (§3.8).
- **Doubles type-check against the port Protocol:** include test support in mypy, or add `_: Port = Fake()`. Remove the conditional "when the repository type-checks tests".

### 9.7 Missing-seam thresholds — **M** · CTL, OPS, DA
Stop and propose a production seam, instead of adding patches, when a test:
- needs more than three `monkeypatch.setattr` calls on one module, or patches in more than one module;
- patches `_private` names, instrument globals, `trace.get_tracer`, or `asyncio`/`httpx` attributes;
- raises an exception to abort production code midway;
- uses `SimpleNamespace` for a typed runtime.

Patching public module-level factories in one module is tolerated when production changes aren't authorized.

Seam shapes to propose:
- settings→policy as a pure function;
- a composition root accepting constructed resources or builder callables;
- a public `tick()` on loops;
- caches observed through factory-call counts;
- an adapter taking a connection factory instead of hard-coding `connect()`.

One in-process wiring smoke test per service may keep a few patches.

### 9.8 Async tests — **H** · IM, DA, OPS
- See D4.
- Show concrete async-fixture options, including `pytest_asyncio.fixture(scope="session", loop_scope="session")`.
- Use a module-level `pytestmark`, not per-test markers.

### 9.9 Workers and DB-as-queue tests — **M** · OPS, CTL
`workers.md` is Celery/RQ-centric. Move that detail into a subsection or the examples file, and add framework-neutral asyncio guidance:
- an ordered effect log that proves "commit before ack";
- a public `tick()`;
- a bounded drain.

Add a DB-queue section:
- two concurrent claimers never get the same row;
- a stale lease owner's write is rejected;
- an expired lease becomes claimable;
- retry exhaustion reaches the terminal state;
- claim order.

Add an uncertain-write oracle: the uncertain path never replays the side effect (§4.11).

### 9.10 Structured log events as oracles — **M** · OPS, CTL
Replace the ambiguous "exact log prose" line: a structured event name plus its meaningful fields is a valid oracle when the event is an operational contract. Capture with the library helper (`structlog.testing.capture_logs`) and one mechanism. Never match prose (`"… failed" in caplog.text`).

### 9.11 Split ownership of the two testing docs — **H** · IM, DA, CTL
- Arch `testing.md` owns placement, profile classification, markers, CI selection and the support-package mechanism.
- `pytest` owns test design, doubles, assertions, async and flakiness.
- Each keeps a single pointer to the other and deletes duplicate paragraphs; today neither points to the other.
- Add **architecture fitness** tests to the classification table, and register a `contract` marker.
- Settings validation tests are unit; shipped YAML and `.env.example` tests are contract.
- Add a pointer to otel `testing.md` for telemetry tests.

### 9.12 Fix examples — **M** · IM, DA
- `examples-integration.md` uses a sync `Session`. Add the async equivalent: an `AsyncConnection` with an outer transaction, `AsyncSession(bind=conn, join_transaction_mode="create_savepoint")`, and rollback. Keep the caveat that this doesn't isolate second connections or workers.
- Add a canonical `ScriptedToolChatModel(BaseChatModel)` to the LangChain examples:
  - `bind_tools` returns `self` and records the tools and `tool_choice`;
  - it mints fresh message and tool-call IDs per call;
  - it raises when the script is exhausted;
  - it records the messages it saw;
  - mutable fields use `Field(default_factory=list)`.

  State that `GenericFakeChatModel` doesn't support `bind_tools`.

### 9.13 Profiles and hygiene — **M/L** · DA, IM, OPS, CTL
- **(M)** Add a `contract/framework/` **characterization** profile for third-party behaviour the app depends on. Each test is named after the assumption it protects and runs a minimal synthetic graph; one test pins the locked versions. Rerun on every dependency bump. Unit tests then don't re-assert framework shape.
- **(H)** When behaviour is removed or renamed, update every profile (integration, e2e, live) in the same change. The hermetic job runs `pytest --collect-only` over all profiles. Delete per-module `pytest.skip` fallbacks once a fail-fast `requires_env` hook exists.
- **(M)** Don't reimplement production control flow in tests.
- **(M)** Compose/config contract tests assert structural facts, not substrings of shell commands. A SQL-text assertion in a unit test is acceptable only if an integration test proves the effect.
- **(M)** Integration fixtures: one engine fixture per member. Prefer unique schema or tenant namespaces over table wipes, and any wipe first asserts a test database. Tests never read `os.environ` directly. Migration tests get one throwaway-DB fixture and one subprocess helper with a timeout.
- **(L)** Delete spike and prototype code from the collected suite once the decision is recorded. Keep scripts with a `main()` outside `tests/`.
- **(L)** Label ceremony rules as heuristics: the "compact matrix" is a suite-design step, and "one state-changing setup action per fixture" becomes "one cohesive setup concern".
- **(L)** Prompt tests: one reviewed snapshot per prompt, paired with the version constant. Other tests check invariants with whitespace-normalized matching.
- **Good defaults to state:**
  - redaction canaries;
  - prove "import is inert" in a subprocess;
  - the live profile shape (`pytestmark = pytest.mark.live`, fail when env is missing, bounded assertions);
  - markers derived from directory in the root `conftest.py`, with `--strict-markers --import-mode=importlib`.

---

## 10. `python-repository-setup`

### 10.1 Lint and type baseline that enforces the written rules — **H** · all four
The template selects only `E4,E7,E9,F,I,UP,B,TID252`, so none of CLAUDE.md's thresholds is checked. Proposed, with a one-line rationale per family in the template:
```toml
[tool.ruff.lint]
select = ["E4","E7","E9","F","I","UP","B","TID252",
          "C90",            # complexity <= 10
          "PLR0912","PLR0915",
          "S101",           # no assert in src
          "BLE",            # blind except; use `# noqa: BLE001 <reason>` at real boundaries
          "ASYNC","DTZ","T20","TRY400","N818","FBT003","INP",
          "PIE","RET","SIM","C4","PERF","PGH","FURB","ERA","RUF"]  # RUF022: sorted __all__
[tool.ruff.lint.mccabe]
max-complexity = 10
[tool.ruff.lint.per-file-ignores]
"**/tests/**" = ["S101", "INP"]
"**/bootstrap/runtime.py" = ["PLR0915"]   # linear wiring; split rule in arch §4.6
```
- Consider `ANN401` (with per-file ignores for true adapters), `FBT001` and `PLR2004` (tests excluded).
- **Mark `TID252` mandatory** whenever arch invariant 9 applies.
- **Don't** enable `PLR0913` (keyword-only DI constructors legitimately exceed it) or `EM`/`TRY003` (hundreds of hits for little value).
- State that Ruff can't measure function length or nesting, so those remain review signals.
- Introduce the rules with a baseline: fix the code or add `noqa` with a reason; never weaken thresholds to pass.
- **mypy:**
  - `plugins = ["pydantic.mypy"]` whenever pydantic is used;
  - `warn_unreachable = true`;
  - `enable_error_code = ["ignore-without-code", "redundant-expr", "possibly-undefined"]`;
  - type-check `tests/**/support` and conftest files.
- **Stubs policy:** use `boto3-stubs`/`types-*`, or **one** `[[tool.mypy.overrides]] ignore_missing_imports` block; never per-import `# type: ignore[import-untyped]`.

### 10.2 Declare every direct import — **M** · IM
- Every directly imported package is declared by the member that imports it; a transitive install isn't a declaration.
- Coverage `source` lists every workspace import package.

### 10.3 Package markers — **L** · CTL
See §2.12. Enable `INP001` and drop the `explicit_package_bases` workaround.

### 10.4 Clean the asset — **L** · IM
- Delete `assets/workspace-template/.ruff_cache/`; it's committed.
- Delete `otel-observability/scripts/__pycache__/`.
- Exclude caches from assets.

### 10.5 Cross-reference fixes
See §1.5.

---

## 11. `CLAUDE.md` (resources/skills/CLAUDE.md, and repo copies)

**M** · DA, CTL, OPS, IM
- **Remove clauses the tooling already enforces:** "type-hint public interfaces" (mypy strict), "avoid mutable default arguments" (B006), "no bare `except`" (E722).
- **#1 (size):** "CC ≤10 is enforced by ruff C901; ~40 lines and nesting ≤3 are review signals. Composition roots that only wire may be longer but split by subsystem past ~80 lines."
- **#3 (docs):** say plainly that a `bool`/`None` return on a public or port method is never self-explanatory.
- **#4 (module size):** keep the number only in one skill file, and point to it.
- **#5:** fix the business-capability contradiction (§1.2).
- **#6:** add one sentence on `Any` (§2.5).
- **#7 (errors):** add "An `except` that doesn't re-raise must catch specific types or record the failure. Map exceptions to public errors through one exhaustive table, never `getattr(exc, "code")`. No `assert` for runtime checks."
- **#9 (duplication):** "Prefer clear duplication over an abstraction whose shape is still changing. Code with identical semantics has one owner; search before writing a helper. When removing a capability, delete its leftovers." (§2.11, §4.18)
- Keep the general rules (no `utils`, no speculative abstraction) in CLAUDE.md, delete them from the arch skill, and have the skill say "General code-style rules come from CLAUDE.md."

---

## 12. Suggested implementation order

1. **Remove causes first** (small edits, directly causal):
   - §3.1 `Field` rule and scaffolds;
   - §3.3 no YAML shadow defaults;
   - §3.7 secret-safe errors;
   - §4.1–4.2 GenAI file mandate and typed examples;
   - §6.1 engine example;
   - §6.4 SQL location and `.sql` rules;
   - §7.1–7.3 otel rule 9, `set_status_on_exception`, snippets;
   - §9.1 test-support recipe;
   - the §1.2 contradictions table.
2. **Make decisions D1–D6.**
3. **Add the missing homes:**
   - `python-code-conventions` (§2);
   - arch `errors.md` (§4.11) and `async-and-lifecycle.md` (§4.12);
   - db transactions/UoW, failure contract, work queues, limits (§6.2–6.6).
4. **Tooling** (§10.1), then the audit-script checks (§5.1, §7.14).
5. **Restructure for single ownership:** settings ownership table (§3.14), otel slimming (§1.5), testing split (§9.11), arch dedupe (§4.20), CLAUDE.md (§11).
6. **Remaining M/L items.**

---

## Not carried forward

- **"Already covered, no new rule":** dependency direction and port naming; bootstrap lifecycle and per-operation sessions; `SecretStr` split and startup validation; bounded cardinality and content-gated GenAI capture; absolute imports; no `utils`; real integration boundaries and deterministic tests; tests asserting behaviour over private calls; typed boundary contracts; injected clock/sleep in HTTP clients.
- **Rejected by a reviewer:**
  - a column-factory helper for repeated SQLModel columns;
  - mandating `gather` for every independent await pair;
  - generating `.env.example` from the model;
  - lowering the 300-line module signal;
  - a `Final` mandate;
  - a comment-density quota;
  - a blanket "deduplicate settings loaders" (softened into D3);
  - a blanket integration test per adapter method;
  - `EM`/`TRY003`/`PLR0913`.
- **Repo-specific:** the concrete code defects (CTL Appendix B, DA "real defects"), evidence paths and counts, "otel-observability not installed" dead links (true only in one repo's `.agents/skills`), and the `offset` audit notices, which need semantic review.
