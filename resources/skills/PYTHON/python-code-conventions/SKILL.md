---
name: python-code-conventions
description: >-
  Language-level conventions for writing, editing, or reviewing any Python
  source: services/, libs/, scripts, and Lambdas. Covers data containers
  (dataclass, Pydantic, TypedDict), keyword construction, StrEnum/Literal
  vocabularies, bool/None outcome contracts, Any/cast/type-ignore, assert,
  magic values, constructors and wrappers, duplicate helpers, imports and
  __init__/__all__, docstrings, error and async idioms, and function/module
  size signals. Use it for every Python change or code review, even a small
  one, and alongside any other Python skill. Architecture, settings,
  persistence, logging, observability and testing specifics live in
  python-service-architecture, python-settings-config, python-sqlmodel-alembic,
  python-logging, otel-observability and pytest.
---

# Python Code Conventions

Rules below module placement: how a value, type, function or module is written. Each rule names the Ruff or mypy check that enforces it, or a concrete review trigger. `python-repository-setup` owns the lint and type configuration that enables these checks. When a check fires, fix the code or add `# noqa: <CODE> <reason>`; never loosen a threshold to pass. Where code lives is `python-service-architecture`'s job; general principles (no `utils`, no speculative abstraction) come from the project `CLAUDE.md`.

Bad/good pairs for every rule are in `references/examples.md` under the same headings; each section below links its pair. Read it when writing new code of that kind or when a reviewer disputes a finding.

## Data containers

| Need | Use |
|---|---|
| Internal value, result, command, policy | `@dataclass(frozen=True, slots=True)`; add `kw_only=True` for >3 fields, any `bool` field, or adjacent fields of the same type |
| Collections inside a frozen value | `tuple[...]` and `frozenset[...]`; for mappings, expose `Mapping[...]` backed by an immutable copy when immutability matters. A `Mapping` annotation alone does not freeze a `dict`. |
| Untrusted, persisted, wire or LLM-facing data | Pydantic, on one named base per member (`StrictModel` with `ConfigDict(frozen=True, extra="forbid")`), not copied into several modules |
| Fixed-key JSON that must stay a dict (OTel carrier, SDK kwargs, framework state) | `TypedDict` |
| Undecoded JSON at the edge | `pydantic.JsonValue` or `Mapping[str, object]`, narrowed immediately |

- Pydantic belongs at trust boundaries, not on every internal result "for consistency". Decode legacy or versioned formats once at the boundary and pass a stable typed value inward.
- A mutable dataclass is only for an explicit state holder, with a one-line comment naming who mutates it.
- Pydantic fields use a bare annotation (`x: int` required, `x: int = 5` defaulted). Write `Field(...)` only for a constraint, an alias that differs from what the source binds, `default_factory`/`discriminator`/`exclude`/`repr=False`, SQLModel column mapping, or a `description` that is consumed (LLM/tool schema, public OpenAPI) or adds what the name, type and default don't (unit, format, scope, what `None` does). Never a description that restates the name. Settings fields follow the same rule; their types, validators and env contract are `python-settings-config`'s.
- Exceptions: tiny tagged-union members (`Active(remaining_seconds)`), `Point(x, y)`, and no `slots=True` where descriptors or inheritance break it.

[Examples](references/examples.md#data-containers).

## Keyword construction

Ruff `FBT003` (optionally `FBT001`). Wide dataclasses are `kw_only=True` and built by keyword. Never pass bare `True`/`False`/`None` or an unexplained number positionally. Constructors are keyword-only (`def __init__(self, *, ...)`) by default. Map wide rows and provider responses into DTOs by keyword so each source visibly matches its destination.

[Examples](references/examples.md#keyword-construction).

## Closed vocabularies

Trigger: a string literal compared with, assigned to, or substring-matched against a status, phase, mode, record type, error-code family, tool name or metric-label value.

- Declare it once: a `StrEnum` when code needs members, iteration, branching, a DB CHECK or a boundary crossing; `type X = Literal[...]` only for small compare-only switches or schema-only fields.
- Type every attribute, parameter, return, model field and column with it. Compare against members; `.value` only at serialization edges.
- Name derived subsets beside the type (`TERMINAL_STATES: frozenset[JobState]`). Derive runtime sets by enum iteration or `get_args()`, never by retyping values.
- No substring classification, no sentinel strings (`"_NONE"`): use `None` or a member. Return a `NamedTuple` or dataclass, not `tuple[str, str]`.
- Exceptions: Alembic revisions keep frozen copies; a public wire enum may stay separate from the internal one, mapped explicitly with a comment; pass-through external values may stay `str`.

[Examples](references/examples.md#closed-vocabularies).

## Outcome contracts

Trigger: a public or port method returning `bool` or `X | None`. It documents the falsy meaning in one docstring line, or returns a named outcome (`StrEnum` or small result dataclass); always the named outcome when the falsy case has more than one cause. A wrapper never turns an exception into `None` when `T` can itself be `None`. No half-actions behind boolean mode flags whose `| None` result callers read differently. Exception: question-named predicates (`is_due()`).

[Examples](references/examples.md#outcome-contracts).

## Type escape hatches

mypy `--strict` plus `enable_error_code = ["ignore-without-code"]`; Ruff `PGH003`, optionally `ANN401`.

- `Any` only for truly dynamic values: raw SDK returns narrowed in the same function, `**kwargs` pass-through, framework-imposed type parameters, JSONB columns. Use `object` for heterogeneous input you narrow.
- Type model handles as `BaseChatModel` or a narrow Protocol, agents and graphs as `Runnable`/`CompiledStateGraph`.
- Narrow with `isinstance`, `TypeIs` or a lookup table, not `cast` or `# type: ignore`. Never `cast(Any, ...)`, and never `cast` to recover a type from a string-keyed container: store typed attributes.
- Every remaining ignore names its code, with a reason when not obvious. The same cast/ignore pair more than twice becomes one typed helper owned by the type's package.
- No `getattr(obj, "attr", default)` on project-owned types: declare the attribute on the Protocol or base. Reflection is for untyped third-party payloads, inside one translation function per payload.

[Examples](references/examples.md#type-escape-hatches).

## No assert in production

Ruff `S101`, tests excluded. `assert` never guards a condition that can be false at runtime (lookups, optional dependencies, loaded state), because `python -O` strips it: raise a named error or make the type non-optional. `assert_never()` in an exhaustive `match` is fine. Never bypass `frozen=True` with `object.__setattr__`, and never `hasattr`-probe project-owned types. Helpers that always raise return `NoReturn`.

[Examples](references/examples.md#no-assert-in-production).

## Fixed-key dicts are records

Trigger: `dict[str, Any]` as an internal result or accumulator; a helper that receives a dict to mutate by string key; a dict assembled, `pop`ped, then validated; a validated model dumped back to a dict to pass inward. Helpers return values. Code that already holds typed values constructs the model by keyword; `model_validate`/`model_validate_json` is only for data crossing a trust boundary.

[Examples](references/examples.md#fixed-key-dicts-are-records).

## Named types and constraints

Trigger: the same structural type or constraint in two or three places. Name it once at its semantic owner, never in a generic `types.py` or `common.py`. One parameter name per concept. Limits that legitimately differ per field stay inline; don't alias a type used once. New aliases use `type X = ...`, new generics `def f[T](...)` (Ruff `UP040`, `UP047`).

[Examples](references/examples.md#named-types-and-constraints).

## Magic values and constants

Trigger: a literal that appears twice or whose meaning isn't obvious (sizes, timeouts, sentinel dates, lease names, jitter bounds, retryable status sets); optionally Ruff `PLR2004` outside tests. Name it `UPPER_CASE` with a one-line *why*; precompile regexes. A value that could differ per deployment or need tuning is a setting (`python-settings-config`), not a constant. Durations and sizes end in their unit (`_seconds`, `_ms`, `_bytes`, `_chars`, `_tokens`) unless the type carries it. Don't branch on a substring of a deployment-owned value such as a model ID; use a setting (`supports_temperature`) or one keyed table. Exceptions: `0`, `1`, `""`, `fastapi.status` names, one-off test data.

[Examples](references/examples.md#magic-values-and-constants).

## Constructors and wrappers

Trigger: a class or function whose body only forwards to another callable with the same meaning, or an `__init__` that only stores arguments (review only: Ruff `B903` is preview-only and not enabled).

- `__init__` assigns one attribute per line; attribute name equals parameter name; collaborators get a leading `_`. If `__init__` only stores arguments, use a `@dataclass`. Don't expose collaborators as public mutable attributes for tests to overwrite.
- Settings-derived scalars one owner always consumes together become a frozen policy dataclass validated in `__post_init__`; no one-field wrapper while siblings stay loose (where bootstrap maps settings into it: `../python-service-architecture/references/boundaries.md#bootstrap`).
- A boolean flag that selects different object shapes or methods becomes two functions.
- Delete pass-through wrappers: bootstrap "handlers" repeating a service signature, a class storing N fields only to call a function with the same N. A wrapper earns its place by translating types or errors, adding policy, or narrowing a wide API. For application action boundaries, see `python-service-architecture` (fallback: `../python-service-architecture/references/boundaries.md#action-boundaries-a-deliberate-cost`).
- Never regex structured data back out of text you rendered yourself; pass the structure.

[Examples](references/examples.md#constructors-and-wrappers).

## One owner per semantics

Trigger: writing a private helper. First search the member for an existing one and import it. Identical semantics have one owner: hashing and canonicalization, vocabularies, deadline arithmetic, provider error-code classification, trust-boundary rendering, DSN/URL rewriting. Two copies that differ by accident are a bug. Similar-looking code with different meaning stays separate, with a comment saying why. Before extracting shared validation, compare failure codes and accepted inputs, not just syntax. Extraction across deployables follows `python-service-architecture`.

[Examples](references/examples.md#one-owner-per-semantics).

## Imports and package markers

- Imports at module top (Ruff `PLC0415`, enabled in the templates). A function-local import carries a comment: optional heavy dependency, cycle, or import-time cost. `TYPE_CHECKING` only for type-only stub packages or real cycles. A cycle between service packages is a design defect: move the shared type inward.
- Services: every package directory has an `__init__.py` (Ruff `INP001`); service `__init__.py` files are empty (no composition, no re-exports); no `__all__` in leaf modules.
- Libraries: re-export only from the package `__init__`, with a sorted `__all__` (Ruff `RUF022`); export every type in a public signature; one export point per package; never list names imported from elsewhere. An `__init__` never eagerly imports optional dependencies (e.g. GenAI extras of an observability package).
- `from __future__ import annotations`: one convention per repo; on 3.14+ (deferred annotations, PEP 649/749) don't add it.

[Examples](references/examples.md#imports-and-package-markers).

## Docstrings and comments

Trigger: a module without a docstring, a public class or exception without a contract line, a docstring that restates parameters. Every module except an intentionally empty service `__init__.py` has a one-line docstring stating its responsibility. Public classes get a one-line contract; exceptions say when they are raised. A function docstring is required only when the contract isn't visible from the signature: falsy/`None` meaning, side effects, ordering, idempotency, units, or the *why* of a surprising choice. Comments explain *why*. No banners, no commented-out code (Ruff `ERA001`). No density quota: match the existing healthy pattern.

[Examples](references/examples.md#docstrings-and-comments).

## Error and async idioms

Language-level idioms only. Error design (broad-except shapes, port errors) is owned by `../python-service-architecture/references/errors.md` and public error mapping by `../python-service-architecture/references/api-and-workers.md`; asyncio lifecycle, cancellation and structured concurrency by `../python-service-architecture/references/async-and-lifecycle.md`.

- A `try` holds only the call whose failure the `except` handles. Don't raise inside a `try` just to catch it lines later. Never catch `KeyError`/`TypeError` around parsing: that turns bugs into domain failures.
- `raise X from exc` by default (Ruff `B904`). `from None` only when the cause may carry secret input (the new error carries a sanitized projection) or for expected client-facing 4xx translations where the cause adds nothing.
- `except Exception` doesn't catch `CancelledError`. Write a `CancelledError` arm only when it does something different; any `except BaseException`/`CancelledError` arm ends with a bare `raise`.
- Exception names end in `Error` (Ruff `N818`). Carry context as typed attributes, not message text. Define a class only when a caller handles it differently or it crosses a port.
- Optional: `match` with `assert_never` for exhaustive dispatch over closed unions and enums; two-way branches stay `if`.
- Run independent awaits concurrently (`TaskGroup`) only when neither's failure changes whether the other runs and no rate limit interacts; otherwise keep them sequential, with a comment.
- No `async def` or `asyncio.Lock` where nothing suspends (review only: Ruff `RUF029` is preview-only and not enabled). Prefer `asyncio.Event` to polling with `sleep` (Ruff `ASYNC110`).

[Examples](references/examples.md#error-and-async-idioms).

## Size signals

This section owns the size numbers; other skills and `CLAUDE.md` point here.

| Signal | Threshold | Enforced by |
|---|---|---|
| Cyclomatic complexity | ≤10 | Ruff `C901` (`C90`, `max-complexity = 10`), backed by `PLR0912`/`PLR0915` |
| Function length | ~40 lines is a review signal; over ~60, split or the PR says why | Review (Ruff can't measure length) |
| Nesting depth | ≤3 | Review |
| Module length | ~300–350 lines: review for multiple responsibilities; never split only to hit a count | Review |

- A long function in `db/` or `bootstrap/` signals misplaced business logic, not just length.
- Composition roots that only wire objects are exempt from the length signal, not from mixing concerns. The bootstrap split rule is owned by `python-service-architecture` (fallback `../python-service-architecture/references/boundaries.md`, `bootstrap/`).
- Before extracting from a long function, trace its inputs, decisions, effects, cleanup and output. Extract only a separable decision, resource lifecycle or reusable transformation. No one-call helpers to hit a number.

## Related skills

- `python-service-architecture`: module placement, bootstrap, errors, async lifecycle; test placement in `../python-service-architecture/references/testing.md`.
- `python-settings-config`: settings fields, env contract, secrets.
- `python-sqlmodel-alembic`: models, sessions, repositories, migrations.
- `python-logging`, `otel-observability`: log events and telemetry.
- `pytest`: test design.
- `python-repository-setup`: the Ruff and mypy configuration that enables the checks named here.
