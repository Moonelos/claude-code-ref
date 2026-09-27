# Skill Improvement Recommendations

Evidence-based proposals for improving the agent skills in `.agents/skills/`, derived
from a review of `libs/` and `services/` (~37k lines of source, ~36k lines of tests,
8 workspace members).

This document is about **the skills**, not about the code. Code excerpts are cited only
as evidence that a skill rule is missing, unclear, contradicted, or already producing a
good result worth locking in. Fixing the individual code sites is out of scope.

Skills reviewed:

| Skill | Short name used below |
| --- | --- |
| `python-service-architecture` | **arch** |
| `python-service-architecture-audit` | **audit** |
| `python-settings-config` | **settings** |
| `python-sqlmodel-alembic` | **db** |
| `otel-observability` | **otel** |
| `pytest` | **pytest** |
| `python-repository-setup` | **repo** |

Each proposal lists **Target skill**, **Rule**, **Why**, **Evidence**, examples where
useful, **Exceptions**, and **Priority**. Coverage status is one of *missing*,
*partial* (rule exists but is too narrow or too vague), or *contradicted* (the skill
currently steers agents the wrong way).

---

## 0. Summary

### What the codebase tells us about the skills

1. **The skills are strong on placement and weak below the module level.** The code
   follows the layering rules well: there are no `utils`/`common` modules, 0 relative
   imports, 0 direct OpenTelemetry imports in `application/`, 173 of 190 dataclasses are
   frozen, and 435 functions use keyword-only arguments. The recurring problems are all
   in areas no skill owns: how to model a value, how to type a status, how to represent
   an outcome, how to write async cleanup, and where a business decision goes once it
   is inside a repository.
2. **Several skill rules produce the problems directly.**
   - The settings skill mandates `description=` on every field, which produces
     descriptions that restate the field name.
   - The DB skill says per-service DB plumbing "legitimately varies", which produced 4
     byte-identical copies of `engine.py` and `session.py` and 2 divergent `server_time`
     semantics.
   - The pytest guidance forbids both cross-member helper imports and promoting shared
     helpers. The result is 3 verbatim copies of the integration DB harness and 1
     drifted copy.
   - The otel skill demands constants for every name and a log "while the span is still
     active". The result is 78–181 constants per service and retroactive "failure-only"
     spans.
3. **Where the skills are silent, each service invents its own answer.** There are 3
   persistence-port styles, 3 stale-write result conventions, 3 exception-logging
   mechanisms, 4 names for the same strict Pydantic base, and 4 incompatible
   `mark_error` signatures.
4. **The skills are long and repetitive.** The env-only vs. YAML ownership test is
   restated about 6 times in the settings skill (~1,570 lines total). The audit skill
   restates `arch/boundaries.md`. Repetition costs context and has not stopped the
   actual failure modes.

### Top priorities

| # | Proposal | Target | Priority |
| --- | --- | --- | --- |
| 1 | Replace the mandatory `description=` rule with the "`Field(...)` only when it adds information" rule (B1) | settings | High |
| 2 | Add a small `python-code-style` skill for below-module idioms: data modelling, enums end to end, outcome types, `assert`, type escapes (Part A) | new | High |
| 3 | Define one canonical unit-of-work / persistence-port shape and fix the DB skill's transaction-ownership gap (C1, D4) | arch + db | High |
| 4 | "Repositories apply decisions; they don't make them" (C2) | arch + db | High |
| 5 | Add an async and resource-management reference: `to_thread`, SDK timeouts, `BaseException` cleanup, loop failure policy (C6, C7) | arch | High |
| 6 | Work-queue patterns for Postgres: single-statement claim, lease fencing, no I/O under locks (D1–D3) | db | High |
| 7 | Replace "duplication legitimately varies" / "propose a later extraction" with a concrete extraction trigger (C8) | arch + db + otel | High |
| 8 | Fix otel ceremony drivers: one boundary helper per unit of work, a constants carve-out, a production-safe default for exception detail (E1–E3) | otel | High |
| 9 | Give pytest a workable shared-test-support recipe (F1, F2) | pytest + arch | High |
| 10 | Remove the internal contradictions listed in Part H | all | High |

---

## Part A — Proposed new skill: `python-code-style`

### A0. Why a new skill rather than more rules in existing ones

- **Target:** new skill `python-code-style`. `arch` gets a one-line pointer to it for
  anything below module placement. `CLAUDE.md` stays as the short principle list and
  links here for the checkable versions.
- **Why:**
  - `CLAUDE.md` items 1, 3, 6 and 7 are the only general Python guidance. They are
    principles, not rules an agent can apply consistently.
  - The architecture skills mention typing only at port boundaries: "Avoid weak
    contracts such as `dict[str, Any]`" (`arch/references/boundaries.md`, "Contract
    ownership"), and "broad `Any`" in `audit`.
  - Everything in A1–A10 fell through those gaps.
  - Adding these rules to `arch` would bloat a skill whose job is placement. A focused
    skill (~200 lines) is cheaper to load.
- **Guardrail for the new skill itself:** every rule should either map to a Ruff or
  mypy check, or state a concrete trigger. Avoid "prefer clean code" prose.
- **Priority:** High.

### A1. Data-modelling decision table

- **Target:** python-code-style (new). Also a one-line cross-reference in `settings`.
- **Rule:**

  | Need | Use |
  | --- | --- |
  | Internal value / result / command | `@dataclass(frozen=True, slots=True)`; add `kw_only=True` when there are more than ~3 fields, any `bool` field, or adjacent fields of the same type |
  | Collections inside a frozen value | `tuple[...]` / `frozenset[...]` / `Mapping[...]`, never `list`/`dict`/`set` |
  | Validating untrusted/external input (settings, JSON documents, LLM structured output, HTTP bodies) | Pydantic `BaseModel` with `ConfigDict(extra="forbid", frozen=True)` |
  | Fixed-key JSON that must stay a dict (e.g. OTel carrier, SDK kwargs) | `TypedDict` |
  | Undecoded JSON at the edge | `Mapping[str, object]`, narrowed immediately |

- **Why:** the default is already right (frozen dataclasses dominate, and Pydantic is
  mostly confined to settings, secrets and schemas). But it is unwritten, so the gaps
  are inconsistent:
  - 23 `list`/`dict`/`set` fields sit inside frozen dataclasses, which makes them
    shallowly mutable and unhashable.
  - Only 10 of 190 dataclasses use `slots=True`, and none use `kw_only`.
  - There are 0 `TypedDict` uses, alongside 120 `dict[str, Any]` annotations.
- **Evidence:**
  - `lseg_worker/domain/run.py:50,91,121` has `submission_otel_context: dict[str, str]` in
    frozen dataclasses.
  - `edm_client/client.py:66` has `DiscoveryPage.rows: list[DiscoveryRow]`.
  - `lseg_worker/application/case_posting.py:39` has
    `diagnostics: dict[str, Any] = field(default_factory=dict)` in a frozen dataclass.
- **Good:**
  ```python
  @dataclass(frozen=True, slots=True, kw_only=True)
  class DiscoveryPage:
      rows: tuple[DiscoveryRow, ...]
      next_cursor: str | None
  ```
- **Bad:**
  ```python
  @dataclass(frozen=True)
  class DiscoveryPage:
      rows: list[DiscoveryRow]   # "frozen" but rows.append() works
  ```
- **Exceptions:**
  - Performance-sensitive builders may use a mutable, non-frozen dataclass locally, as
    long as it does not cross a function boundary.
  - `slots=True` is incompatible with some descriptor or inheritance patterns. Skip it
    there, with no comment needed.
- **Priority:** Medium.

### A2. A closed vocabulary with an enum is typed as that enum end to end

- **Target:** python-code-style (new). Also `db`, for column typing (see D9).
- **Rule:** when a `StrEnum` exists for a closed set, every attribute, parameter,
  return type, and model field that carries it uses the enum type. Compare against
  members (`SessionState.HITL`), never string literals. Use `.value` only at
  serialization edges (SQL text, JSON, logs). Do not create a parallel
  `Literal["A", "B"]` for a set that already has an enum.
- **Why:** a typo in `"RESOLVD"` type-checks today. The enums exist but deliver none of
  their safety.
- **Evidence:**
  - `libs/db_models/src/db_models/enums.py` defines 10 StrEnums, but the model columns
    are typed `str`. For example, `models/inbound_email.py:197` has
    `processing_status: str = Field(default=InboundProcessingStatus.UNCLASSIFIED.value, ...)`.
  - There are about 15 literal comparisons, e.g.
    `db-migrate/.../workflow_recovery.py:123` has
    `email.processing_status not in {"COMPLETED", "HITL"}`, and
    `resolution-worker/.../exhausted_responses.py:32` has `== "RESPONSE_PENDING"`.
  - `ticket_monitor/domain/email.py:66` types an authentication `reason: str` that is a
    closed code set.
- **Coverage:** partial. `arch/boundaries.md` says "Prefer an enum, literal, or value
  object over a `constants.py` module", but not that the enum must be used where the
  value is stored or compared.
- **Exceptions:** raw SQL text and Alembic migrations use literal values by necessity.
- **Priority:** High.

### A3. Name recurring structural types once

- **Target:** python-code-style (new). The trace-carrier specifics go in `otel`.
- **Rule:** give a structural type that recurs in two or more modules one name at its
  semantic owner: a `type` alias, `NewType`, `Annotated` alias, or `StrEnum`. Use one
  parameter name for the same concept. Use the PEP 695 `type X = ...` statement for new
  aliases on 3.12+.
- **Why:** the same concept is spelled many ways, which hides that it is one thing and
  lets the variants drift.
- **Evidence:**
  - The W3C trace carrier appears 79 times as `dict[str, str]` under 8 parameter names:
    `source_otel_context` (42), `otel_context` (11), `next_otel_context` (9),
    `source_trace_context` (7), `carrier` (6), and others.
  - `Literal["UNCONFIRMED", "OUT_OF_SCOPE", "DUPLICATE"]` is copied into 4 files:
    `db_models/documents.py:163`, `genai/.../schemas.py:36`,
    `domain/response_understanding/contracts.py:70`, and
    `domain/response_rubric/comments.py:18`.
  - `confidence: float = Field(ge=0.0, le=1.0)` appears 13 times.
- **Good:**
  ```python
  type TraceCarrier = dict[str, str]
  Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
  ```
- **Exceptions:** do not alias a type used once; an alias with one use is indirection.
- **Priority:** Medium.

### A4. A dict with a fixed key set is a record; helpers return values instead of filling a dict

- **Target:** python-code-style (new).
- **Rule:**
  - Do not use `dict[str, Any]` as an internal result or accumulator. Use a frozen
    dataclass, or a `TypedDict` if it must stay JSON-shaped.
  - Helpers return values. They do not receive a dict to mutate by string key.
  - Keep `dict[str, Any]` / `Mapping[str, object]` for undecoded JSON at the edge, and
    parse it into a typed shape immediately.
- **Why:** mutated dict accumulators hide the output contract and defeat mypy strict,
  which the repo already pays for.
- **Evidence:**
  - `db-migrate/.../workflow_recovery.py:46-58` builds
    `result: dict[str, Any] = {"email_id": ..., "actions": [], "ambiguities": [], "applied": False}`.
    It then passes `result` into `_coverage_recovery(..., result: dict[str, Any], ...)`
    (line 121), which appends to it.
  - There are 15 `error: dict[str, str]` parameters and fields, including one on a port
    (`resolution-worker/ports/response_work.py:58`).
- **Coverage:** partial. `arch/boundaries.md` covers only port contracts.
- **Priority:** High.

### A5. Outcome contracts: no bare `bool` or ambiguous `None`

- **Target:** python-code-style (new). The port-specific part goes in `arch/boundaries.md`
  "Contract ownership".
- **Rule:** a public function or port method that returns `bool` or `X | None` must
  either:
  - document what the falsy result means, in one docstring line; or
  - return a named outcome instead (a `StrEnum` or small result dataclass).

  Prefer the named outcome whenever the falsy case has more than one cause (e.g. "lost
  lease" vs. "already applied"). Wrappers must not turn an exception into `None` when
  `T` can itself be `None`.
- **Why:**
  - 111 of 113 Protocol methods under `*/ports/` have no docstring. That includes 21 of
    the 22 that return `bool` and 12 that return `X | None`.
  - Callers cannot tell a stale lease from a no-op.
  - The same concept (a stale write) is reported three ways across services (see D2).
- **Evidence:**
  - `resolution-worker/ports/response_work.py:53-63`: `fail(...) -> bool` has 8
    keyword-only parameters and no docstring.
  - `ports/response_work.py:118` has `commit(...) -> RubricCommitResult | None`.
  - `submission_prep/observability/phases.py:30-55`: `observed_phase(...) -> T | None`
    swallows an exception and returns `None`.
  - **Good counterpart:** `lseg_worker` returns `MutationOutcome.STALE`, and
    `due_operations.py` returns `(summary, failure: BaseException | None)` explicitly.
- **Coverage:** partial. `CLAUDE.md` #3 says to document "when it is not already
  obvious". Agents do not treat `bool` as non-obvious, so the skill should say plainly:
  a `bool`/`None` return on a public or port method is never self-explanatory.
- **Good:**
  ```python
  class WriteOutcome(StrEnum):
      APPLIED = "applied"
      STALE = "stale"          # lease lost or state moved on; caller must not retry

  async def fail(self, *, claim: ClaimedResponse, error: WorkError, policy: RetryPolicy) -> WriteOutcome: ...
  ```
- **Bad:**
  ```python
  async def fail(self, *, claim, owner, error: dict[str, str], retryable: bool,
                 max_attempts: int, retry_delay_seconds: float, hitl_owner: str) -> bool: ...
  ```
  This also illustrates the parameter-object clause of `CLAUDE.md` #6:
  `max_attempts`, `retry_delay_seconds` and `hitl_owner` are one retry policy.
- **Exceptions:** predicates named as questions (`is_due()`, `has_capacity()`) are
  self-documenting.
- **Priority:** High.

### A6. Type escape hatches: narrow, don't silence

- **Target:** python-code-style (new). The pydantic-settings `Settings()` case goes in
  `settings`.
- **Rule:**
  - Narrow with `isinstance`, `TypeIs`, or a lookup table. Do not use `cast()` or
    `# type: ignore` to narrow.
  - Every remaining `# type: ignore[code]` names its error code and has a short reason
    if the reason isn't obvious.
  - Use `Any` only in genuinely generic adapters and in third-party callback
    signatures.
- **Evidence:**
  - 13 `# type: ignore`, 15 `cast()`, and 304 `Any` in source.
  - The same ignore is copied into 4 settings modules:
    ```python
    raw = os.environ.get(ENVIRONMENT_VARIABLE)
    if raw not in RECOGNISED_ENVIRONMENTS:
        raise ConfigurationError(...)
    return raw  # type: ignore[return-value]
    ```
    A `dict[str, Environment]` lookup narrows without the ignore.
  - `resolution-worker/.../propagation.py:365-367` has `mapping = row` followed by
    `# type: ignore[arg-type]`.
- **Exceptions:** `Settings()  # type: ignore[call-arg]` is a known pydantic-settings
  limitation. The settings skill should show the accepted form once, so agents stop
  improvising.
- **Priority:** Medium.

### A7. `assert` is not a runtime check

- **Target:** python-code-style (new). Also a one-liner in `CLAUDE.md` #7 and in the
  `db` repository guidance.
- **Rule:** production code never uses `assert` for a condition that can be false at
  runtime (a DB lookup result, an optional dependency, loaded state). Raise a named
  error instead. `assert` is acceptable for tests, and for type narrowing of a value
  that is unreachable by construction when a comment says why.
- **Why:** asserts are stripped under `-O`, so the failure becomes a distant
  `AttributeError`.
- **Evidence:** 29 production asserts, 19 of them under `db/`:
  - `resolution-worker/.../retention.py:80-82`: `assert state.run_id is not None`, …
  - `propagation.py:162,197,238,273`: `assert batch is not None` after a lookup.
  - `resolution_worker/bootstrap/supervisor.py:98` uses `assert recover is not None` to
    guard an optional collaborator.
- **Coverage:** missing everywhere.
- **Tooling:** Ruff `S101` with `per-file-ignores` for `tests/**`, which flags 29 sites
  today (see G1).
- **Priority:** High. It is cheap and prevents a class of silent failures.

### A8. Dispatch over closed unions with `match` + `assert_never`

- **Target:** python-code-style (new).
- **Rule:** when branching on every variant of a closed union or enum, use `match`
  with a final `case _: assert_never(x)`, so a new variant fails type checking.
- **Evidence:** 0 `match` statements and 0 `assert_never` in the codebase, yet unions
  are consumed exhaustively:
  - `lseg_worker/application/case_creation.py:164-166` dispatches on
    `type PortalOutcome = A | B | C` with `isinstance`.
  - `propagation.py:152-190` runs a 5-arm `elif` chain over `PropagationOutcome`.
- **Exceptions:** two-way branches and partial handling ("only care about X") stay as
  `if`.
- **Priority:** Low–Medium.

### A9. Call-site clarity for booleans and positional values

- **Target:** python-code-style (new).
- **Rule:** never pass a bare `True`/`False`/`None` positionally. A dataclass with any
  `bool` field is `kw_only=True`.
- **Evidence:** definitions are clean (0 positional `bool` parameters), but call sites
  are not. `ticket_monitor/domain/authentication.py:16-22` has:
  ```python
  return AuthenticationEvidence(False, "sender_not_allowed", sender_domain, False)
  return AuthenticationEvidence(True, "authenticated", sender_domain, True)
  ```
  Ruff `FBT003` flags 20 such sites.
- **Coverage:** partial. `CLAUDE.md` #6 covers definitions only.
- **Priority:** Low.

### A10. Size signals that actually fire

- **Target:** python-code-style (new), plus `audit`.
- **Rule:**
  - Express the function-size signal in both lines (~40) and statements. Treat a
    function over ~60 lines as a mandatory review prompt: either split it or state why
    in the PR.
  - A long function in `db/` or `bootstrap/` specifically signals misplaced business
    logic (see C2, C5), not just length.
  - Pick one convention for `from __future__ import annotations` on 3.13; it is present
    in 242 of 323 modules today.
- **Why:** Ruff's `PLR0915` counts statements, so expression-heavy functions pass it.
  There are 98 functions over 40 lines and 35 over 60, including:
  - `resolution_worker/bootstrap/runtime.py:96 runtime`: 163 lines.
  - `ticket_monitor/adapters/aws/sqs_consumer.py:113 _process`: 146 lines, nesting 5.
  - `resolution-worker/.../rubric.py:137 commit`: 110 lines, cyclomatic complexity 24.

  47 of the 97 long functions are in `db/`.
- **Coverage:** partial. `CLAUDE.md` #1 has the numbers. `arch/modularization.md` says
  "Around 300–350 lines", while `CLAUDE.md` says "Around 300"; align them.
- **Priority:** Medium.

### A11. Docstrings: codify the good pattern that already exists

- **Target:** python-code-style (new), replacing the vague "document when not obvious".
- **Rule:**
  - Every module has a one-line docstring stating its responsibility.
  - A function docstring is required only when the contract is not visible from the
    signature: falsy/None meaning, side effects, ordering or idempotency guarantees,
    units, or a *why* for a surprising choice. Never restate parameter names or types.
- **Evidence:**
  - All 323 modules already have one-line docstrings (median 1 line).
  - The best function docstrings explain why. `edm_client/models.py:84-91`: "Unparseable
    is `None` rather than an exception because the caller's next question is always
    'does this row fall inside the window?'".
  - `submission_prep/db/server_time.py` explains why it avoids a `SELECT now()` round
    trip.
- **Coverage:** partial. `CLAUDE.md` #3.
- **Priority:** Medium.

---

## Part B — `python-settings-config`

### B1. Use `Field(...)` only when it adds information (the proposed convention)

- **Target:** settings: `SKILL.md` "Core Conventions" and
  `references/settings-py.md` "Field Conventions". Also applies to Pydantic models
  generally (python-code-style A1).
- **Verdict:** **adopt**, with an explicit exception for LLM structured-output schemas.
- **Rule (proposed wording):**
  > Use `Field(...)` only when it adds behavior or information: a constraint (`ge`,
  > `max_length`, …), an alias, a `default_factory`, or a description that states
  > something the name and type do not. Examples of such descriptions:
  > - units, when they are not in the name;
  > - the expected format;
  > - what omission or `null` means;
  > - a cross-field relationship;
  > - why a bound exists.
  >
  > Write a required field as a bare annotation (`queue_url: AnyHttpUrl`), not
  > `Field(...)`, unless it also needs an alias. Never write a description that
  > restates the field name. Put units in the field name (`timeout_seconds`) rather
  > than in a description. Put a rationale longer than one line in a `#` comment above
  > the field.
  >
  > **Exception:** in schemas sent to an LLM as structured output, descriptions are
  > part of the prompt. Describe every field whose meaning is not obvious to a reader
  > who has only the schema.
- **Why:** the current rule is mechanical and produces noise.
  - `references/settings-py.md:74`: "Include concise `description=` text on fields."
  - `SKILL.md`: "Use `Field(..., description="...")` for required values".
  - The skill's own scaffolds model restating text:
    `app_port: PositiveInt = Field(default=8080, description="Server bind port.")`.

  Nothing in the repo reads these descriptions: there is no `model_json_schema` use and
  no generated docs. Where descriptions would have runtime effect, in LLM schemas, the
  repo has none.
- **Evidence (from an AST scan of 424 `Field(` uses in source):**
  - 64 carry only a description (or a default plus a description). 58 of them are in
    one file, `submission-prep/config/settings.py`.
  - The same `DatabaseSettings`/`TelemetrySettings` classes in resolution-worker and
    ticket-monitor have no descriptions, so the rule is also applied inconsistently.
  - About 24 of the 64 (~37%) restate the name.
- **Bad (from the repo):**
  ```python
  pool_size: PositiveInt = Field(description="Connections kept open.")
  page_size: PositiveInt = Field(description="Rows requested per page.")
  verify_tls: bool = Field(description="Whether server certificates are verified.")
  log_level: LogLevel = Field(description="Lowest severity emitted.")
  ```
- **Good (from the repo):**
  ```python
  max_attempts: PositiveInt = Field(description="Total attempts, including the first.")
  endpoint_url: AnyHttpUrl | None = Field(
      default=None, description="null selects AWS S3 through the SDK default."
  )
  submit: bool = Field(description="Fail-safe live-side-effect switch; omitted always means preview.")
  span_queue_size: PositiveInt = Field(description="Spans above this are dropped silently.")
  ```
- **Missing counterpart in LLM schemas:**
  `resolution-worker/genai/response_understanding/schemas.py:28-39` has
  `confidence: float = Field(ge=0.0, le=1.0)` with no description telling the model
  what confidence means.
- **Also fix:**
  - `settings-py.md:78` ("Use `Field(...)` only when the app cannot provide a safe
    default") and `SKILL.md` ("Declare it with `Field(...)`" for `ENVIRONMENT_NAME`) both
    push `Field(...)` where a bare annotation, or `Field(alias=...)`, is enough.
  - Rewrite every scaffold in `settings-py.md` so descriptions appear only where they
    add information.
- **Exceptions:** SQLModel columns need `Field(sa_column=...)`; that is behavior, not
  noise, and is out of scope for this rule.
- **Priority:** High.

### B2. Strict section models: `extra="forbid", frozen=True`, one named base

- **Target:** settings, `references/settings-py.md`.
- **Rule:** in the YAML pattern, the root `Settings` and every section model set
  `extra="forbid", frozen=True`. Define the base once per service, with one canonical
  name (e.g. `ConfigSection`). If a shared settings library exists (B6), it owns the
  base.
- **Why:** `forbid` turns a misspelled YAML key into a startup error. Without it, the
  typo is silently ignored and the class default wins. The skill's scaffolds use
  `extra="ignore"` (`settings-py.md`, e.g. lines 240, 286 and 423), which defeats that.
- **Evidence:**
  - The repo already made the better choice everywhere, under 4 names: `ConfigSection`,
    `Section`, `StrictModel`, `ImmutableDocument`.
  - `submission-prep/.../settings.py:151` explains that forbid "makes a misspelled key
    inside a nested map fail".
- **Coverage:** contradicted (the scaffolds use `ignore`).
- **Exceptions:** the root `BaseSettings` must tolerate unrelated process-env variables.
  pydantic-settings already ignores those when no prefix matches, so `forbid` is safe
  on sections. On the root, `forbid` is right when every source is scoped.
- **Priority:** High.

### B3. YAML-owned fields have no Python default

- **Target:** settings, `SKILL.md` "Configuration Ownership Contract".
- **Rule:** in the YAML pattern, a field whose value is YAML policy has no Python
  default. A missing YAML key must fail validation, not silently fall back to a second
  copy of the value in code.
- **Why:** two homes for one value drift, and the drift is invisible.
- **Evidence:** `lseg-worker/.../settings.py:213-214` has
  `global_slo_seconds: PositiveInt = 604800`, while `config/services/lseg-worker.yaml:38`
  sets `1209600`. The class default is stale and would be used silently if the key were
  removed. `WorkerSettings` defaults duplicate YAML the same way.
- **Coverage:** partial. `config-yaml.md` says "Reject duplicate YAML ownership when a
  value belongs at only one layer" but does not mention class defaults.
- **Also:** environment files restate base values; `dev.yaml`, `staging.yaml` and
  `prod.yaml` each repeat the four `edm.*_path` values from `base.yaml:12-15`. The rule
  "an environment file contains only keys whose value differs from `base.yaml`" belongs
  in `config-yaml.md`.
- **Priority:** High.

### B4. A single-value `Literal` setting is a code constant

- **Target:** settings, "Code invariant" bullet.
- **Rule:** a setting typed `Literal[<one value>]` is not configurable. Move it to a
  constant beside its owner and remove it from YAML.
- **Evidence:**
  - `lseg-worker/.../settings.py:152,158`: `affected_users: Literal["Multiple Users"]`,
    `description_resource: Literal["case-description.txt"]`.
  - resolution-worker: `max_chasers: Literal[2]`, `claim_limit: Literal[1]`.
  - lseg-worker: `database_tracing_enabled: Literal[False]`.
- **Coverage:** covered in principle ("Keep it in code, not in settings merely to make
  it adjustable"), but it needs this concrete detection example.
- **Exceptions:** a temporary pin during a migration, with a comment naming the
  removal condition.
- **Priority:** Low.

### B5. Reusable constrained types and consistent typing across services

- **Target:** settings, "Preferred Pydantic Types".
- **Rule:**
  - Define a constrained scalar used in two or more fields once, as an `Annotated`
    alias beside its owner (`NonEmptyText`, `AwsRegion`, `Confidence`).
  - The same YAML key or concept in two services has the same type.
  - Add an upper bound only when it guards a real limit (an API maximum, a column
    width, a cost ceiling), and name the limit in a comment or the constant name.
  - Use the listed specific type (`EmailStr`) instead of hand-rolled validators.
- **Evidence:**
  - `max_attempts` is `PositiveInt` in lseg, `Field(ge=1, le=100)` in resolution, and
    `Field(ge=1, le=5)` in ticket-monitor.
  - Email addresses are validated 3 ways: `EmailStr`, a hand-written `ContactAddress`,
    and a regex `EmailAddress`.
  - `claim_limit: int = Field(ge=1, le=500)` has an unexplained bound.
  - `Field(min_length=1)` appears 11 times where `NonEmptyText` already exists.
  - **Good:** `NonEmptyText`, `AwsRegion` and `TimezoneName` as `Annotated[...,
    AfterValidator(...)]` in `submission-prep/.../settings.py:66`.
- **Coverage:** partial (the preferred-types table exists, but nothing about reuse,
  bounds, or cross-service consistency).
- **Priority:** Medium.

### B6. Settings *schema* is service-owned; the settings *loader* is not

- **Target:** settings (new section), and `arch/references/shared-libraries.md`, which
  currently says "Deployment settings and loaders remain service-owned".
- **Rule:** each service owns its `Settings` schema. The mechanics that two or more
  services copy verbatim belong in one workspace library. Services pass their service
  name and config-dir variable to it. Those mechanics are:
  - the layered-YAML loader (discover dir, read layers, deep-merge);
  - the `ConfigurationError` type and the `ValidationError` → `ConfigurationError`
    wrapper;
  - the `startup_failed` writer;
  - shared value types (region, log level, exception detail).
- **Why:** the copies have already drifted in a way that can crash some services and
  not others.
- **Evidence:**
  - `_read_layers`, `_merge`, `_discover_config_dir`, `get_settings` and
    `ConfigurationError` are near-identical in 4 services. `ConfigurationError`
    subclasses `Exception` in submission-prep but `RuntimeError` elsewhere.
    submission-prep uses `YamlConfigSettingsSource`; the other three hand-roll a merge.
  - Each service keeps its own list of top-level keys it will ignore
    (`_REPO_TOP_LEVEL_KEYS` / `_SERVICE_KEYS`), and the lists differ. Adding a shared
    key to `base.yaml` breaks only the services whose list lacks it.
- **Coverage:** contradicted (shared-libraries.md makes loaders service-owned).
- **Exceptions:** keep it local when only one service uses YAML, or when a service's
  merge semantics genuinely differ (then say how in a comment).
- **Priority:** High.

### B7. Secrets: reinforce one rule, add one carve-out

- **Target:** settings, `references/secrets-py.md`.
- **Reinforce:** "Do not wrap a scalar in a one-field JSON object"
  (`secrets-py.md`, ~lines 52-54). All four services wrap the DSN as
  `DATABASE_SECRET={"dsn": ...}`. Either the rule is wrong for DSNs (if the stored
  secret is shared with other tooling that expects JSON) or agents ignored it. Decide,
  and state the DSN case explicitly as a worked example.
- **Add — diagnostic CLIs:** a diagnostic or maintenance entry point that needs extra
  secrets extends the service's secrets model or adds a sibling secrets model. It does
  not create a second `BaseSettings` mixing `SecretStr` with settings, and never
  resolves `.env` relative to the working directory.
  - Evidence: `ticket_monitor/diagnostics/mailbox_settings.py:23-45` does all three
    things the skill forbids. It is a second `BaseSettings`, holds a `SecretStr` on
    settings, and falls back to `Path("services/ticket-monitor/.env")`. The skill has no
    diagnostic-CLI section, so the agent improvised.
- **Standardize these good patterns:**
  - Unwrap `SecretStr` only in adapters or bootstrap (`*/db/engine.py:13`,
    `playwright_portal.py:195`).
  - Name the variable, never the value, in errors (`lseg/secrets.py:149-151` uses
    `type(exc).__name__`).
  - Use a pair validator when credentials must arrive together (`lseg/secrets.py:40-46`).
  - Reject static keys when deployed (`lseg/secrets.py:100-107`).

  Add these as a checklist; they are not in the skill today. ticket-monitor's secrets
  module lacks both the provider error wrapping and the pair validator, which is what
  a checklist would have caught.
- **Priority:** Medium.

### B8. Document the process-env-only variant

- **Target:** settings, "Pattern Decision".
- **Rule:** allow dropping the `.env` source from `settings_customise_sources`. This is
  valid when `.env` is supplied by the process launcher (`uv run --env-file`, Compose
  `env_file`) and secrets also read only the process environment. State that the two
  must match.
- **Evidence:** every settings module does `del dotenv_settings, file_secret_settings`.
  That is a deliberate, consistent design, but the skill's mandated precedence ("kwargs,
  env, `.env`, YAML, defaults") doesn't describe it.
- **Priority:** Low.

### B9. Editorial fixes to the settings skill (contradictions and repetition)

See Part H, items H1–H4. Priority: High, because agents follow whichever sentence they
read last.

---

## Part C — `python-service-architecture` (+ `python-service-architecture-audit`)

### C1. One canonical persistence-port / unit-of-work shape

- **Target:** `arch/references/boundaries.md` ("When a port earns its cost") and
  `db/references/repositories-and-queries.md`. State it once, in `db`, and have `arch`
  link to it.
- **Rule (proposed):** pick the shape by who draws the transaction boundary.
  1. **One port call = one transaction.** Application code receives a `...Store` that
     holds the session factory and opens a transaction per method. The method contains
     the query logic itself, or delegates to a repository that adds real value.
  2. **Application needs several operations atomically.** The port exposes
     `transaction() -> AbstractAsyncContextManager[XxxRepository]`, where `XxxRepository`
     is a Protocol of the operations.

  Do not add a class whose methods only open a session and forward to a repository
  method of the same name. Do not use callable "repository factory" Protocols.
- **Why:** every service invented its own shape, and one of them is pure ceremony.
- **Evidence:**
  - lseg-worker and submission-prep use store classes that only forward.
    `lseg-worker/db/submission_store.py` (207 lines) is mostly:
    ```python
    async with transaction(self._factory) as session:
        return await SubmissionRepository(session).mark_submitting(...)
    ```
  - ticket-monitor uses `AdmissionRepositoryFactory(Protocol): def __call__(self) -> AdmissionRepositoryContext`
    (`ports/repositories.py:101`), plus a same-named port and concrete class
    `InboundEmailRepository`.
  - resolution-worker uses `BatchFinalizationTransactions.transaction()` (shape 2),
    with 10 `Database*Transactions`/`*Store` classes.
- **Coverage:** missing. `boundaries.md` only says "A fixed database … often does not
  need a second Protocol above it", while its own port admission test (next item) says
  every DB qualifies.
- **Also fix the port admission test.** "Introduce a port when at least two of these
  are true: remote/nondeterministic…; failure modes materially affect business
  behavior…" is satisfied by every database, which contradicts the sentence above.
  Add: "A database always meets criteria 1–2; the persistence port exists to give
  application code a unit-of-work boundary and a testable contract. Use the shapes
  above, not a Protocol per repository class."
- **Priority:** High.

### C2. Repositories apply decisions; they don't make them

- **Target:** `arch/references/boundaries.md` (a new "Persistence adapters" paragraph
  next to the queue-consumer rule) and `db/references/repositories-and-queries.md`.
- **Rule:** a repository loads, locks, persists, and maps rows. It applies a decision
  the caller has already made. The decision is:
  - which status to set;
  - whether an entity is eligible;
  - retry delays;
  - HITL reasons;
  - user-visible text.

  That decision comes from a pure domain function that takes the loaded rows and
  returns the transition. When one repository method must lock, decide, and write
  atomically, it calls that domain function between the load and the write. It does
  not inline the rule.

  Review triggers: a repository method over ~40 lines, or one with more than two
  branches on business state.
- **Why:** this is where the longest and most complex functions in the repo live.
  Business rules there can only be tested against a real database, and the
  application "actions" become one-line forwards, which is exactly the drift the
  audit skill looks for but cannot detect statically.
- **Evidence:**
  - `resolution-worker/.../application/batch_finalization.py:16`: the whole action is
    `async with self._work.transaction() as repository: return await repository.finalize(batch_id)`.
    The completion rule lives in `db/repositories/batch_finalization.py:91 _batch_can_complete`.
  - `db/repositories/rubric.py:137 commit`: 110 lines, CC 24. It contains
    `state not in {"RESOLVED", "HITL"}`, `timedelta(seconds=1)`, and the literal
    `"RESPONSE_ROW_REVIEW"`.
  - `ticket-monitor/.../inbound.py:647-667 _freeze_for_review` builds user-facing text
    and decides the HITL owner:
    ```python
    comment = (f"[{batch.frozen_at:%d/%m}] [REF_LSEG:{ticket_id}] "
               "Escalated to human, agent processing failure.")
    desired = DesiredSourceWrite(OWNER=hitl_owner, STATUS="Open", COMMENT_AI=comment)
    ```
- **Coverage:** partial. The audit flags delegate-only actions as a "review prompt".
  `boundaries.md` says queue consumers "do not implement classification or state
  rules", but nothing says the same about repositories.
- **Exceptions:** SQL predicates that *are* the eligibility rule for a claim (e.g. "due
  and unleased") must stay in SQL for correctness under concurrency. Name them as
  shared predicates (D11) and test them with integration tests.
- **Priority:** High.

### C3. `application/` and `domain/` never import `config/`; use action-owned policy objects

- **Target:** `arch/references/boundaries.md` ("Folder responsibilities" →
  `application/`), and `audit/scripts/audit_service.py`.
- **Rule:** `application/` and `domain/` never import the service's `config` package.
  Bootstrap maps `Settings` into a frozen, action-owned `XxxPolicy` dataclass holding
  only the fields that action uses. Keep the mapping in small `_xxx_policy(settings)`
  builders.
- **Why:**
  - Injecting the whole `Settings` object couples every action to every configuration
    key.
  - Test construction then needs the full YAML tree: 224 `Settings()  # type:
    ignore[call-arg]` in tests.
  - It makes the action's real inputs invisible.
- **Evidence:**
  - Problem: `lseg-worker/application/case_posting.py:45` has
    `def __init__(self, *, settings: Settings, posts: PostStore, run_id: str)` and reads
    `self._settings.post_claim.max_attempts`.
  - Problem: `submission-prep/domain/desired_write.py:6` imports `Settings`. Seven
    application modules import `config.settings`.
  - **Good (standardize):** resolution-worker's `PropagationPolicy` and
    `RubricProcessingPolicy`, and ticket-monitor's `ProcessingPolicy`, all built in
    bootstrap.
- **Coverage:** partial and vague. "They must not read global settings" allows an
  injected `Settings`. The audit script's forbidden-import set omits `config`, so it
  reported 0 findings.
- **Priority:** High.

### C4. Port contract hygiene

- **Target:** `arch/references/boundaries.md` "Contract ownership".
- **Rule additions:**
  - A port's return type is a named type, never `object` or `Any`.
  - A required collaborator has no `None` default.
  - Ports hold no configuration defaults. Environment-varying values arrive as
    parameters or policy.
  - A port module does not re-export domain types via `__all__`; callers import types
    from their owner.
  - Application actions depend on sibling actions concretely, not through a Protocol,
    unless the sibling crosses an I/O boundary.
- **Evidence:**
  - `resolution-worker/ports/chaser_work.py:64`:
    `PropagationVerifier.verify_before_post(...) -> object`. Its only implementation is
    an application class, injected as `propagation_verifier: PropagationVerifier | None = None`.
  - `ports/response_work.py:99-101 RubricCadenceDelays` has defaults `86400`/`79200`
    that duplicate `settings.rubric.*_delay_seconds`.
  - `ports/response_understanding.py:19` is a re-export hub with a one-off `...Port`
    suffix.
- **Coverage:** partial (ports for in-process logic are discouraged; the rest is
  missing).
- **Priority:** Medium.

### C5. Bootstrap constructs; it doesn't do work

- **Target:** `arch/references/boundaries.md` `bootstrap/` section, and
  `api-and-workers.md`.
- **Rule:**
  - Bootstrap builds objects and wires them. It does not define closures that run DB
    queries or business steps. Each supervised operation is an application action.
  - Split `runtime()` into small construction helpers so it reads as a wiring list.
  - Put outcome and log projections (run-completion summaries) in `observability/`.
  - Composition functions accept their constructors (engine builder, client factories,
    tracer provider) as keyword parameters that default to the production ones. That
    gives tests a seam without monkeypatching (see F3).
  - Diagnostics and maintenance entry points reuse bootstrap factories instead of
    importing concrete adapters and repositories directly.
- **Evidence:**
  - `resolution_worker/bootstrap/runtime.py:96`: 163 lines. Its closure
    `recover_exhausted()` (line 154) calls a repository function directly, bypassing
    `application/`, and it has the magic value `lease_seconds=60` (line 252).
  - `lseg_worker/bootstrap/run.py:101 _complete_run`: 97 lines, CC 16, about 40 log
    fields. It uses `if summary.exit_code == 1` although `domain/run.py:13` defines
    `EXIT_ATTENTION = 1`.
  - Bootstrap tests patch module globals: up to 8 names across 2 modules in one test
    (`submission-prep/tests/unit/bootstrap/test_entrypoint.py:125-132`).
  - **Good:** `ticket_monitor/bootstrap/classification.py:11 build_model_classifier` is
    documented as "shared by the runtime and the diagnostic scanner". By contrast, 8
    diagnostics import concrete adapters directly.
- **Coverage:** partial. `boundaries.md` bans "Repository queries" in bootstrap and says
  "Split a large runtime by construction concern", but closures and diagnostics aren't
  addressed.
- **Priority:** Medium.

### C6. Supervised loops declare a failure policy; one cycle wrapper

- **Target:** `arch/references/api-and-workers.md` (supervisor section), and
  `otel/references/tracing/worker_runtime.md` (shutdown example).
- **Rule:**
  - Every supervised loop declares exactly one failure policy:
    - **contain:** log once, back off (backoff values from settings), continue; or
    - **crash:** log once, re-raise, and let liveness fail.
  - No loop body runs without one of the two.
  - When a supervisor runs more than two cycles with the same span/metric/log/failure
    shape, run them through one `run_cycle(name, operation)` helper. Each cycle
    receives the one action it runs, not the whole runtime container.
  - Replace the sync `signal.signal` + global-flag example in `worker_runtime.md` with
    the asyncio shape the services actually use: a stop `Event`,
    `asyncio.timeout(grace)`, then cancel, then `gather(return_exceptions=True)`, or
    FastAPI lifespan.
- **Evidence:**
  - `ticket_monitor/bootstrap/supervisor.py`: the ingestion loop contains (`:86-106`)
    and the classification loop crashes (`:112-133`).
  - `_recovery_loop` (`:64-69`, and `resolution_worker/bootstrap/supervisor.py:98-104`)
    has **no** `try`, so one exception kills it without a log.
  - The retention loop hard-codes `60.0`/`900.0` backoff.
  - `resolution_worker/bootstrap/supervisor.py` is 596 lines, with 8 `_run_*_cycle`
    functions repeating the same span + metric + try + failure-record + outcome + log
    shape, each taking the `Runtime` container.
  - **Good (standardize):** grace-then-cancel shutdown (`resolution supervisor:132-143`)
    and `_interruptible_wait`, which is duplicated in 2 services.
- **Coverage:** partial. "The supervisor owns `asyncio` tasks, stop events, graceful
  shutdown, and task health" names the owner but gives no mechanics, and the only
  example is sync.
- **Exceptions:** a one-off process (CLI, job) has no supervisor and just exits
  non-zero.
- **Priority:** High.

### C7. New reference: `arch/references/async-and-resources.md`

- **Target:** `arch` (new reference, routed from SKILL.md for any service with async
  I/O).
- **Why:** no skill covers async mechanics. The only related lines are
  "deterministic shutdown" (`boundaries.md`) and a trace-context note about
  `to_thread` in `worker_runtime.md`.
- **Rules:**
  1. **Sync SDKs run only through `asyncio.to_thread` in the adapter.** This covers
     boto3, openpyxl, and blocking file IO. Keep the sync body a private method.
     - *Good (standardize):* all 17 boto3 call sites already do this, e.g.
       `resolution_worker/adapters/aws/ses_email_sender.py:36`.
  2. **Every SDK client gets explicit timeouts and retries**, e.g.
     `botocore.config.Config(connect_timeout=..., read_timeout=..., retries=...)`.
     An outer `asyncio.timeout` around `to_thread` cancels the await but not the
     thread.
     - *Evidence:* `ticket_monitor/adapters/aws/clients.py:22-35` builds clients with no
       `Config`.
  3. **Cleanup-on-failure must survive cancellation.** Use `try/finally` with an
     ownership flag, or `except BaseException: cleanup(); raise`. Never use
     `except Exception` for resource cleanup, because `CancelledError` is a
     `BaseException`.
     - *Evidence:* `lseg_worker/db/repositories/advisory_lock.py:41-52` closes the
       connection only under `except Exception`.
     - *Evidence:* `adapters/playwright_portal.py:147-179 launch()` cleans up context,
       browser and driver only under `except Exception`, which leaks a Chromium
       process on cancellation. It also closes only one of context/browser when both
       exist.
  4. **Per-unit resources are async context managers.** Factories return
     `@asynccontextmanager` / `AsyncExitStack`-managed resources, not
     `launch()`/`close()` pairs that callers must remember.
     - *Good:* `lseg_worker/bootstrap/runtime.py:79-92` uses
       `AsyncExitStack.push_async_callback`; `edm_client/client.py:84-146` uses an
       `_owns_client` flag and `__aenter__`/`aclose`.
     - *Bad:* `due_operations.py:162-225` is a ~70-line nested `try/finally` threading a
       mutable `step` string, at nesting depth 5.
  5. **Health probes have a timeout and log the failure reason.** Compare
     `ticket_monitor/bootstrap/health.py:52-55` (`except Exception: return False, ...`,
     no timeout, no log) with the resolution-worker probe, which uses `asyncio.timeout`.
  6. **Library retry loops are observable.** They take injectable `sleep` and `clock`
     (good: `edm_client/session.py:109-147`) and expose attempts through a callback or
     result, so the consuming service emits the warning and metric. The library never
     configures logging. Honour `Retry-After` on 429.
- **Priority:** High.

### C8. Replace "propose a later extraction" with a trigger that fires

- **Target:**
  - `arch/SKILL.md` discovery step 7;
  - `arch/references/shared-libraries.md`;
  - `db/references/repo-layout.md`;
  - `otel/SKILL.md` (scope rules);
  - `audit` (shared-capability review).
- **Rule:**
  - When a module is identical (apart from package name) in three or more deployables,
    or two copies have diverged semantically, treat it as an **Improvement finding
    that must be resolved**. Either extract it, or add a comment in each copy stating
    why the semantics differ.
  - Until extraction happens, a new copy must match the existing public signatures
    exactly, so the eventual extraction is mechanical.
  - A library's configuration input is a concrete frozen dataclass the library owns.
    It is not a Protocol of properties that every consumer re-implements.
- **Why:** the current wording is permissive to the point of inertia.
  - `arch` SKILL.md step 7: "Read-only comparison does not expand the edit scope;
    propose a later extraction".
  - `boundaries.md`: "may move to an internal observability library".
  - `db/repo-layout.md`: "that legitimately varies per service".
  - `otel` SKILL.md: "do not touch sibling services merely for symmetry".

  Each is reasonable alone. Together they produced:
  - `engine.py`/`session.py` identical in 4 services;
  - `server_time.now` meaning `func.now()` in three services but
    `func.statement_timestamp` in ticket-monitor, which is **different semantics for
    the same lease columns**;
  - 4 × ~1,100-line `observability/` packages with 4 incompatible `mark_error`
    signatures;
  - 4 copies of `secrets.py`, `ConfigurationError`, and the `startup_failed` writer;
  - two identical 18-field EDM config dataclasses, because `libs/edm_client/ports.py:54`
    exposes `EdmConfig` only as a Protocol of 18 properties.
- **Exceptions:** keep code local when the copies differ in operational meaning,
  lifecycle, or dependencies. This is the skill's existing test, and it remains
  correct; it just needs to produce a decision.
- **Priority:** High.

### C9. Import policy: `TYPE_CHECKING`, local imports, `api` → `bootstrap`

- **Target:** `arch/references/boundaries.md` ("Absolute imports only" section).
- **Rule:**
  - Use `TYPE_CHECKING` only for type-only stub packages (e.g. `mypy_boto3_*`) or
    unavoidable ORM relationship cycles.
  - A function-local import needs a comment (an optional heavy dependency, or an
    import-time side effect).
  - A cycle between service packages is a design defect. Move the shared type inward;
    for example, the API layer defines a Protocol for the runtime surface it needs
    instead of importing `bootstrap.runtime.Runtime`.
- **Evidence:**
  - `resolution-worker/api/dependencies.py:9-10` imports `bootstrap.runtime.Runtime`
    under `TYPE_CHECKING`; ticket-monitor imports it at runtime.
  - `lseg_worker/observability/redaction.py:13,16-17,49` imports the same symbol three
    ways: top level, under `TYPE_CHECKING`, and function-local.
- **Coverage:** missing.
- **Priority:** Low–Medium.

### C10. Shared vocabulary lives outside the ORM package

- **Target:** `arch/references/shared-libraries.md` and `db/references/repo-layout.md`.
- **Rule:** enums, JSON document contracts, and value types shared across services live
  in a module importable without SQLAlchemy/SQLModel (e.g. `db_models.vocabulary`, or
  a separate dependency-light package). Domain and ports import that module, never the
  ORM package root. The schema library may own these contracts, but it must not run
  queries or read session state.
- **Evidence:**
  - Domain and ports import `db_models` about 30 times; `from db_models import X` pulls
    in SQLModel through `__init__.py`.
  - `libs/db_models/.../source_projection_audit.py:43` runs `SELECT … FOR UPDATE` and
    stashes data in `session.info`. Every service's `session.py` hand-copies the drain
    loop.
- **Coverage:** contradicted in two directions. `repo-layout.md` says the lib holds
  "*only* `base.py` and `models/`", which is too strict for enums and document
  contracts. `shared-libraries.md` correctly bans sessions and queries.
- **Priority:** Medium.

### C11. Errors: where broad catches are allowed, and how to chain

- **Target:** `arch/references/boundaries.md` ("Errors and constants follow
  ownership") for placement. `otel/references/conventions/errors.md` for span/log
  treatment.
- **Rule:** `except Exception` is allowed only in these places:
  - an adapter boundary that translates to the port's error `from exc`;
  - a loop or unit-of-work owner that logs once and applies its declared policy (C6);
  - a best-effort shutdown or flush step, which logs at warning.

  `except ...: pass` is never allowed.

  Use `raise ... from exc` by default. Use `from None` only when the cause may carry
  secrets **and** the new error carries a sanitized projection; say so in a comment.

  Prefer separate `except` clauses over `except Exception` followed by an `isinstance`
  chain.
- **Evidence:**
  - About 80 broad catches.
  - Good translation: `ticket_monitor/genai/email_classification/classifier.py:41-54`
    maps to transient, invalid and permanent errors `from exc`, but through an
    `isinstance` chain.
  - Silent: `lseg_worker/observability/tracing.py:92-107` has four consecutive
    `try: ... except Exception: pass` blocks in shutdown.
  - `playwright_portal.py:196-199` has `except TimeoutError: pass`.
  - Chaining is inconsistent: 84 `from exc` vs 8 `from None`.
    `playwright_portal.py:204-205` uses `from None`, then re-attaches the stack
    manually into the payload.
- **Coverage:** partial. Translation at adapters is covered; suppression, shutdown and
  `from None` are not. `CLAUDE.md` #7 states the principle.
- **Priority:** High.

### C12. Make the audit script catch what it can

- **Target:** `audit/scripts/audit_service.py` and `audit/SKILL.md`.
- **Why:** it reported **0 violations and 0 notices on all 4 services** while patterns
  C2, C3, C5, C9 and C10 exist. The skill says a clean run "does not reduce … the
  semantic work", but agents treat it as a pass.
- **Add checks (as review notices, not violations):**
  - `application`/`domain` → `config` imports;
  - `api` → `bootstrap` imports;
  - repository methods over N lines or complexity N;
  - `assert` statements in `src/`;
  - modules byte-identical across workspace members;
  - Protocols with exactly one implementation that lives in `application/`.
- **Also:** have the report print "static checks passed; semantic audit pending", so
  "0 findings" never reads like a verdict.
- **Priority:** Medium.

---

## Part D — `python-sqlmodel-alembic`

The DB skill is solid on schema, metadata, migrations and verification, and the repo
follows it well there (see Part I). Its gaps are all on the runtime side: transactions,
concurrency and work queues. Every app service here is a Postgres-backed work queue.

### D1. Claim work in one statement

- **Target:** `db/references/repositories-and-queries.md`, in a new "Work claiming and
  leases" section.
- **Rule:** claim a batch with one statement:
  ```sql
  UPDATE t SET lease_owner = :owner, lease_until = now() + :lease
  WHERE id IN (SELECT id FROM t WHERE <due predicate>
               ORDER BY <priority> LIMIT :n FOR UPDATE SKIP LOCKED)
  RETURNING <needed columns>
  ```
  Re-sort the returned rows in Python, because `RETURNING` has no order guarantee.
  Loop per candidate only when a parent row must be locked first. In that case, lock
  the parents in bulk, in sorted id order.
- **Evidence:**
  - **Good (standardize):** `submission-prep/.../sessions.py:262-282`:
    ```python
    update(ResolutionSession)
        .where(col(ResolutionSession.id).in_(due.scalar_subquery()))
        .values(lease_owner=owner, lease_until=server_time.now_plus(lease_seconds))
        .returning(ResolutionSession)
    # RETURNING has no ordering guarantee; restore the claim order callers see.
    ```
    The same shape is in `resolution-worker/.../chasers.py`, `rubric.py` and
    `responses.py`, across 14+ `claim_*` methods in 4 services.
  - **Counter-example:** `ticket-monitor/.../inbound.py:143-187` runs up to 3 statements
    per candidate over `max(16, limit*4)` candidates. `lseg-worker/.../posts.py:60-89`
    loops similarly.
- **Coverage:** missing; the skill has no locking, lease, or queue guidance.
- **Priority:** High.

### D2. Lease-fenced writes and one stale-write outcome

- **Target:** `db`, same new section.
- **Rule:** every write that follows a claim filters on the expected state, the lease
  owner, **and** `lease_until > now()`, and uses `RETURNING id`. Report "no row
  updated" as one typed outcome (e.g. `WriteOutcome.STALE`, per A5), consistent across
  the repository.
- **Evidence:** three conventions for the same fact:
  - `submission-prep/.../sessions.py:247-260` raises `StaleSessionOwnershipError`, and
    does not check `lease_until`;
  - `lseg-worker/.../posts.py:319-331` returns `MutationOutcome.STALE` and does check
    expiry;
  - `resolution-worker/ports/response_work.py:44-50` returns a bare `bool`.
- **Exceptions:** an exception is acceptable when a stale write is truly exceptional
  for that caller. Choose one convention per repository and document it.
- **Priority:** High.

### D3. No external I/O while a transaction holds locks

- **Target:** `db/references/engine-and-session.md`.
- **Rule:** never await a network, LLM, browser, or object-store call inside a
  transaction that holds row locks. The sequence is:
  1. claim, then commit;
  2. make the external call;
  3. do a fenced write in a new transaction.

  Don't open a transaction just to read the clock (see D6).
- **Evidence:**
  - **Good (standardize):** `resolution-worker/application/response/processing.py:55-87`
    claims in transaction 1, calls the LLM outside any transaction, and writes the
    result in a fenced transaction 2.
  - The same code opens a whole transaction just for `database_now()` (lines 76-77).
- **Coverage:** partial. "Never hold one `AsyncSession` open across multiple unrelated
  units of work" addresses session scope, not lock hold time.
- **Priority:** High.

### D4. Say who begins and commits the transaction

- **Target:** `db/references/engine-and-session.md` and
  `repositories-and-queries.md`.
- **Rule:**
  - Provide one `transaction(factory)` async context manager (session plus
    `session.begin()`) and one read-only variant.
  - The unit-of-work owner from C1 is the only caller.
  - Repositories take a session and never begin or commit.
  - Code must not bypass the helper with an ad-hoc `async with factory() as s,
    s.begin()`, because that skips helper behavior such as evidence draining.
- **Why:** the skill defines `session.py` as the "per-unit-of-work session", but its
  `get_session` example never begins or commits. Nothing says who owns commit.
- **Evidence:** `resolution-worker/.../retention.py:54` bypasses the shared helper and
  so skips the evidence drain that `transaction()` performs.
- **Coverage:** missing and self-contradictory.
- **Priority:** High.

### D5. Translate integrity errors precisely

- **Target:** `db/references/repositories-and-queries.md`.
- **Rule:**
  - For idempotent inserts, prefer `INSERT … ON CONFLICT DO NOTHING RETURNING`, then
    select the existing row.
  - When catching `IntegrityError`, match the **named constraint** and re-raise
    anything else as the store's generic error. A CHECK or NOT NULL violation must not
    be reported as a duplicate.
- **Evidence:**
  - Good: `submission-prep/db/admission_store.py:64-89` matches
    `constraint_name == "uq_active_exception"` and confirms the winning row.
  - Good: `ticket-monitor/.../admission.py:79-87` uses `on_conflict_do_nothing`.
  - Too broad: `lseg-worker/db/submission_store.py:155-158` maps any `IntegrityError` to
    `DuplicateTicketIdentity`.
- **Coverage:** partial (translation is generic in `arch`; the DB skill never mentions
  constraint names or `ON CONFLICT`).
- **Priority:** Medium.

### D6. One database-clock helper

- **Target:** `db`.
- **Rule:**
  - Compute leases and deadlines inside SQL with the database clock, through one
    helper module (`now()`, `now_plus(seconds)`).
  - Pick one function and document the choice. `now()` is transaction start time;
    `statement_timestamp()` is statement start time.
  - Fetch `SELECT now()` separately only when application code needs the value itself.
- **Evidence:**
  - 4 `server_time.py` copies with two different semantics (see C8).
  - `func.make_interval(...)` is inlined in `rubric.py:109`, `responses.py:90` and
    `inbound.py:173`, while other code uses `now_plus()`.
  - `database_now()` round trips are called 49 times.
  - **Good (standardize):** `submission_prep/db/server_time.py` documents why it avoids
    the round trip.
- **Priority:** Medium.

### D7. Select what you need; bulk-update instead of ORM loops

- **Target:** `db/references/repositories-and-queries.md`. This extends the existing
  eager-loading paragraph, which is irrelevant here because the repo uses no
  `Relationship` loading.
- **Rule:**
  - Hot claim and scan queries select or return only the columns the result DTO needs,
    and especially avoid large JSONB columns.
  - A bulk state or FK change is one `UPDATE … WHERE id IN (…)`, not a load-modify-flush
    loop.
  - Map rows through typed accessors, not `row: Any` with string keys.
- **Evidence:**
  - Good: `responses.py:93-101` returns 7 columns.
  - `ticket-monitor/.../inbound.py:171` has `.returning(InboundEmail)`, including JSONB
    `response_envelope`.
  - `submission-prep/.../batches.py:47-70` loads whole sessions to set one FK.
  - `rubric.py:520-540` maps from `row: Any`.
- **Priority:** Medium.

### D8. Lock ordering and lock timeouts

- **Target:** `db`, "Work claiming and leases" section.
- **Rule:**
  - Lock an aggregate root before its children.
  - Lock multiple rows in sorted id order.
  - Prefer `pg_try_advisory_xact_lock` over session-level advisory locks, unless the
    lock must outlive a transaction (and then it needs a dedicated connection).
  - A transaction that waits on `FOR UPDATE` without `SKIP LOCKED` sets
    `SET LOCAL lock_timeout`.
- **Evidence:**
  - **Good (standardize):** parent-then-child locking at `inbound.py:602-639`; sorted
    `FOR UPDATE` at `hitl_notifications.py:155-190`; a keyed transaction-scoped lock at
    `hitl_notifications.py:83`; a process-wide lock on a dedicated connection at
    `advisory_lock.py:40-53`.
  - Only `retention.py:292-297` sets `lock_timeout`.
- **Priority:** Medium.

### D9. Type status columns with their enum; derive CHECK constraints from it

- **Target:** `db/references/models-and-base.md`.
- **Rule:** a status column is annotated with its `StrEnum` type, stored as `Text`, and
  guarded by a named CHECK constraint generated from the enum values. Reads return
  enum members (per A2).
- **Evidence:**
  - **Good (standardize):** `resolution_session.py:27-43` generates named CHECK
    constraints from `StrEnum` values.
  - The annotation, however, is `str` (see A2). Half the pattern is done.
- **Priority:** High (paired with A2).

### D10. One codec per typed JSON column

- **Target:** `db/references/models-and-base.md`.
- **Rule:** a JSONB column holding a Pydantic document gets one encode/decode pair, a
  `TypeDecorator` or a pair of repository helpers, with one fixed `model_dump` mode.
  Repositories do not call `model_dump`/`model_validate` ad hoc.
- **Evidence:**
  - JSON columns are typed `dict[str, Any]` (`resolution_session.py:263-292`).
  - There are about 50 scattered dump/validate calls with inconsistent modes:
    `desired.model_dump()` at `lseg/.../submissions.py:313`,
    `model_dump(mode="json")` at `rubric.py:329`, and `exclude_none=True` about 10 times.
- **Priority:** Medium.

### D11. Share multi-column transitions and predicates, not repositories

- **Target:** `db/references/repositories-and-queries.md` and `repo-layout.md`.
- **Rule:**
  - A state transition that must keep several columns consistent (revision counter,
    sync status, lease reset) is one update-values builder next to the model, used by
    every service.
  - A predicate used by many claims ("due and unleased") is one named SQL expression.
  - Repositories stay per service.
- **Evidence:**
  - "Supersede the desired source write" (`desired_source_revision + 1` plus resetting
    about 8 `source_*` fields) is written out 8 times in 5 services.
  - The due/unleased predicate appears under 5 names, plus 35 inline
    `or_(… is_(None), … <= now())`, across 12 files.
- **Priority:** Medium.

### D12. Minor additions

- Design a partial index for every claim or scan predicate (`postgresql_where`). The
  repo already does this (`idx_sessions_*_claim`), and the skill should say so. Priority:
  Low.
- One-shot CLIs and diagnostics that build their own engine use `NullPool` and dispose
  it on exit. Today the skill covers only the long-running singleton. Priority: Low.

### D13. Corrections to existing DB skill text

See Part H, items H5–H10.

---

## Part E — `otel-observability`

The otel skill is thorough, and the repo follows much of it: a conventions module per
service, application code calling service helpers instead of OpenTelemetry, and an
allowlisted log renderer. The problems below come from rules that are overbroad, or
that interact to produce ceremony.

### E1. Rewrite the mandatory `log_full_exception_trace = true` rule

- **Target:** `otel/SKILL.md` (rule 9).
- **Current text:** "Always declare one typed `log_full_exception_trace` … with a
  default of `true`. Do not ask for confirmation."
- **Problem:**
  - For a regulated, PII-bearing domain, full exception detail by default is the wrong
    default, and "do not ask" removes the chance to correct it.
  - The repo deliberately uses a graded `exception_detail: Literal["safe", "full"]`, with
    `safe` in `config/prod.yaml`, which a boolean cannot express.
- **Rule (proposed):** "Declare one typed exception-detail setting. Default it to the
  safe projection in production-like environments and to full detail locally. Ask when
  the service handles personal or financial data and the user has not stated a policy."
- **Priority:** High.

### E2. One boundary helper per unit of work; a telemetry budget per call site

- **Target:** `otel/references/conventions/errors.md` and
  `references/logging/business_events.md`.
- **Rule:**
  - Wrap the span-error + error-log + metric triple in one helper per unit-of-work
    boundary, e.g. `with work_boundary(name, failure_event=...)`.
  - A business call site should need at most about 3 lines of telemetry.
  - Completion logs carry the outcome and at most about 8 independently queried fields.
    The rest is span attributes, not log fields. That enforces the skill's own
    statement: "Emitting a log at every step of a traced pipeline recreates the trace
    in a worse format" (`structlog.md`).
- **Evidence:**
  - `ticket_monitor/adapters/aws/sqs_consumer.py:113-258` repeats four near-identical
    `mark_error` + `log.error(EVENT, **{FIELD_OPERATION: ..., FIELD_ERROR_TYPE: ...,
    FIELD_EXCEPTION: sanitize_exception(...)})` blocks. Two differ only in
    `safe_message`.
  - `resolution_worker/bootstrap/supervisor.py` repeats the same pattern in 10
    `_run_*_cycle` functions.
  - `lseg_worker/bootstrap/run.py:127-190`: `run_completed` logs about 35 fields,
    mirroring span attributes and metrics.
- **Priority:** High.

### E3. Constants: required for cross-signal names, optional for local log keys

- **Target:** `otel/references/conventions/naming.md`.
- **Current text:** "Do not scatter string literals. Put convention names in one
  module."
- **Rule (proposed):**
  - Span names, metric names, event names, and attribute keys shared across signals
    are constants in the conventions module.
  - A log field key used only in logs, by one module, may be a literal.
  - Keep the conventions module as the vocabulary, not as a mirror of every key.
- **Evidence:** 78–181 `FIELD_`/`EVENT_`/`ATTR_` constants per service
  (`observability/conventions.py`, imported `as names`). Call sites become
  `**{names.FIELD_X: ...}` dict splats.
- **Keep (good pattern):** the module itself, and the rule that application code never
  imports OpenTelemetry directly (0 violations).
- **Priority:** Medium.

### E4. Don't fabricate spans to satisfy "log while the span is active"

- **Target:** `otel/references/conventions/errors.md`.
- **Current text:** "the configured exception detail is emitted once, as a named
  structured log, while the span is still active".
- **Add:** "A failure that occurs before any unit-of-work span exists logs without span
  correlation. Do not create a retroactive span just to host the log."
- **Evidence:** `ticket_monitor/observability/tracing.py:173-207 failure_only_span`
  builds a span *after* the failure so the one log has something to correlate to.
- **Priority:** Medium.

### E5. Specify cancellation semantics for span helpers

- **Target:** `otel/references/conventions/errors.md`.
- **Rule:**
  - Custom span context managers handle `BaseException`, not just `Exception`.
  - Cancellation during shutdown records `app.outcome=cancelled` without `ERROR`.
  - A cancellation caused by a timeout records `ERROR` with `error.type=TimeoutError`.
- **Evidence:** `lseg_worker/observability/tracing.py:117-128` and the equivalent in
  resolution-worker combine `set_status_on_exception=False` with `except Exception`, so
  a `CancelledError` leaves the span UNSET. The skill says to leave
  `set_status_on_exception` at its default, and names `CancelledError` only as an
  `error.type` value.
- **Priority:** Medium.

### E6. Match sibling helper signatures even before extraction

- **Target:** `otel/SKILL.md` (scope rules). Paired with C8.
- **Current tension:** "One service at a time… do not touch sibling services merely for
  symmetry" vs. "Repeated operational contracts route to `shared_library.md` without an
  explicit extraction request".
- **Rule:** "When adding observability to a service and sibling services already have
  `observability/`, read their public helper signatures first and reuse them verbatim.
  Consistency of the helper API is in scope even when editing siblings is not."
- **Evidence:** three different helper APIs for the same job:
  - `mark_error(span, error_type: str)` in lseg, `mark_error(span, exc)` in
    ticket-monitor, and `set_work_error` in resolution-worker;
  - `traced(tracer, name)` vs `traced(name)`;
  - `sanitize_exception()`, `safe_exception_detail()`, and `exc_info=` handled by a
    processor.
- **Priority:** High.

### E7. Allowlisted log renderers must not drop fields silently

- **Target:** `otel/references/logging/structlog.md`.
- **Rule:**
  - An allowlist processor must fail in tests on unknown keys, or emit a
    dropped-fields marker. It must not silently discard them.
  - Route the root stdlib logger through the same `ProcessorFormatter`, so botocore,
    httpx and SQLAlchemy warnings become JSON too.
- **Evidence:** `resolution_worker/observability/logging.py:128-133` does
  `{k: v for k, v in fields.items() if k in _SAFE_FIELDS}`. That is a strong PII guard,
  but it would also drop `exc_info` if a caller followed the skill's own pattern. Only
  the uvicorn stdlib loggers are routed.
- **Priority:** Medium.

### E8. Don't open root spans for empty polls

- **Target:** `otel/references/tracing/worker_runtime.md`.
- **Rule:** start the root span only after the claim returns work. Record empty polls as
  a counter. Don't filter them out at the exporter, because that orphans child DB spans.
- **Evidence:** `resolution_worker/observability/tracing.py:53-75` defines
  `DropIdleCycleExporter`, which filters empty-poll spans at export time.
- **Priority:** Low–Medium.

### E9. Fix the skill's own samples

- **Target:** `otel/references/logging/structlog.md`.
- **Problems:**
  - The sample calls `get_settings()` at module import, which is an import-time side
    effect.
  - It sets `exception.message = str(exc)` before the redaction policy runs.
  - It leaves redaction as a comment ("Apply the service's credential/token
    redactor…"). Agents then wrote their own redactor, and the credential regexes are
    copied into `exception_sanitizer.py` and `edm_client/errors.py`.
  - It treats `service.name` as "effectively mandatory" in logs, while the repo
    deliberately uses the flat key `service_name`. `naming.md` already concedes flat
    log keys; make the two consistent.
- **Priority:** Medium.

### E10. Observability wrappers never swallow

- **Target:** `otel/references/conventions/errors.md`.
- **Rule:** an instrumentation wrapper records the failure and re-raises. Business code
  decides whether to contain it, and returns an explicit result (A5).
- **Evidence:** `submission_prep/observability/phases.py:30-55` catches, logs, and
  returns `None`.
- **Priority:** Medium.

---

## Part F — `pytest` (+ `arch/references/testing.md`)

The test suite has good foundations:

- about 1,000 tests;
- only 5 files import `unittest.mock`;
- a real Postgres with a real Alembic upgrade per scenario;
- a destructive-reset guard;
- behavior-named tests;
- `--strict-markers` and `--import-mode=importlib`.

The issues below cluster around shared test infrastructure and typing, where the skill
text is contradictory or silent.

### F1. Cross-member test infrastructure gets a home

- **Target:** `arch/references/testing.md` and `pytest/references/integration-boundaries.md`.
- **Rule:**
  - Put disposable-infrastructure lifecycle that is identical across members (DB
    URL guard, schema reset, migrate to head, engine disposal) in one workspace
    test-support package or pytest plugin, e.g. `libs/testing_postgres`. Declare it
    as a dev dependency. Do not copy it into each member's conftest.
  - Resolve paths from `__file__`, never from the working directory.
  - Read environment variables inside fixtures, not at import.
- **Why:** two rules combine into a dead end:
  - `testing.md`: "Do not promote it to root merely to avoid a local duplicate";
  - `testing.md`: a service test "must not import another deployable's private package
    or test helpers".
- **Evidence:**
  - `lseg-worker`, `submission-prep` and `resolution-worker` have near-verbatim
    76–90-line integration conftests, down to the same docstrings.
  - ticket-monitor's copy drifted: `DATABASE_URL = os.environ.get(...)` is read at
    import, and `Config("services/db-migrate/alembic.ini")` is relative to the working
    directory.
- **Priority:** High.

### F2. A support-module import recipe that works

- **Target:** `arch/references/testing.md` (with `repo` for the pytest config).
- **Problem:** the skill says "use an unambiguous member-qualified test-support
  package", "omit `tests/__init__.py`", "prefer importlib mode", and "do not add
  several member `tests/` directories to a global `pythonpath`". Under importlib mode
  without `__init__.py`, the only way to import a helper is `pythonpath`, so agents did
  exactly what was forbidden:
  - `pyproject.toml:89-96` puts four `services/*/tests` directories on the path;
  - modules are hand-prefixed (`ticket_monitor_db_fixtures.py`) and some collide-prone
    ones are not (`db_operations.py`);
  - one service imports another's helper: lseg-worker's `test_settings.py:13` imports
    `runtime_contract_cases` from submission-prep's tests.
- **Rule:** prescribe one concrete recipe:
  - support code lives in `services/<svc>/tests/<svc>_testing/__init__.py`, importable
    as `<svc>_testing`, with only that member's `tests/` on the path (set per member);
  - **or** the support code is a dev-only installable package.
- **Priority:** High.

### F3. When patching bootstrap is tolerated

- **Target:** `pytest/references/core-principles.md`. Pairs with C5.
- **Rule:**
  - Prefer the injectable-constructor seam (C5).
  - When the seam is missing and the task doesn't authorize production changes,
    patching **public** module-level factories in **one** module is tolerated.
  - Patching `_private` names, or names in more than one module, means you should
    report the missing seam instead of adding more patches.
- **Why:** `testing.md` prescribes "injected constructors", while SKILL.md says "a
  request for tests does not by itself authorize production refactors". Neither says
  what to do in between.
- **Evidence:**
  - The most-patched targets: `runtime_module` (22), `worker_module` (19),
    `run_root` (17).
  - `resolution-worker/tests/unit/bootstrap/test_resolution_worker_runtime.py:151-155`
    patches private `_raw_email_store_config`.
- **Priority:** Medium.

### F4. Typed settings builders and typed fakes

- **Target:** `pytest/references/core-principles.md`. Settings construction also goes
  in `settings`.
- **Rule:**
  - Tests build settings with a typed helper (`settings_for_tests(**overrides)` or
    `Settings.model_validate({...})`), not environment mutation plus
    `# type: ignore[call-arg]`.
  - Application tests should not need `Settings` at all once policy objects exist (C3).
  - Fakes must type-check against the port Protocol, with no `arg-type` ignore.
  - `SimpleNamespace` / `cast(Any, ...)` stand-ins are allowed only for third-party
    objects outside the repo's type surface.
- **Evidence:**
  - 224 `Settings()  # type: ignore[call-arg]`, built from a copied YAML tree even for
    pure application tests (`lseg-worker/.../test_due_operations.py:1120-1124`).
  - 52 `arg-type` ignores, e.g. `posts=EmptyPostStore(),  # type: ignore[arg-type]`.
  - 189 `SimpleNamespace` uses, e.g. a nested settings stand-in in
    `ticket-monitor/tests/unit/bootstrap/test_app.py:24-29`.
- **Coverage:** partial. "Prefer an explicit typed fake at an application port" exists,
  but not settings construction or the no-ignore requirement. The repo runs mypy
  strict on tests, so this matters.
- **Priority:** Medium.

### F5. Fake modules and DB row builders

- **Target:** `pytest/references/core-principles.md` and `integration-boundaries.md`.
- **Rule:**
  - When fakes for a port exceed ~100 lines, or serve more than one test module, move
    them to a `fakes` support module beside their consumers. One fake per port per
    member: no three `FakePage` classes.
  - Integration seeding uses named, typed row builders with defaults and keyword
    overrides, not inline `INSERT` SQL, unless the SQL itself is under test.
- **Evidence:**
  - `lseg-worker/.../test_due_operations.py` is 1,500 lines, and lines 50–612 are fakes.
  - lseg-worker has three separate Playwright `FakePage` classes.
  - `ticket-monitor/tests/integration/db/test_inbound_email_repository.py:299` is a
    203-line test, mostly inline `INSERT` with JSON blobs.
- **Priority:** Medium.

### F6. Structured log events are a legitimate oracle; assert them properly

- **Target:** `pytest/SKILL.md` quality gate.
- **Current text:** it rejects tests that lock "exact log prose". For structlog, the
  event name is a stable identifier, not prose.
- **Rule:** "A structured event name plus its meaningful fields is a valid oracle when
  the event is an operational contract (alerts, dashboards). Capture with the logging
  library's helper (e.g. `structlog.testing.capture_logs`). Never echo `call_args` back
  into the expected value."
- **Evidence:** `lseg-worker/tests/integration/db/test_repositories.py:846-849` asserts
  its log call by comparing against values copied from its own `call_args`:
  ```python
  logger.info.assert_called_once_with(
      "source_evidence_superseded",
      session_id=logger.info.call_args.kwargs["session_id"],
      ...
  ```
  Nothing in the suite uses `capture_logs`.
- **Priority:** Medium.

### F7. Database-as-queue tests

- **Target:** `pytest/references/workers.md`.
- **Why:** `workers.md` is Celery/RQ/Kafka-heavy. This repo's workers claim and lease
  rows from Postgres, and only the "Scheduled and periodic work" section applies.
- **Add a short section:**
  - two concurrent claimers never receive the same row;
  - a stale lease owner's write is rejected;
  - an expired lease becomes claimable;
  - retry exhaustion transitions to the terminal state;
  - ordering of claimed rows.

  Move the Celery detail into the examples file.
- **Priority:** Medium.

### F8. Recognize the plugin-free async style

- **Target:** `pytest/references/core-principles.md` (async section).
- **Rule:** "If no async pytest plugin is installed, the convention is sync tests that
  call `asyncio.run` once per test, with async fixtures exposed as runner callables. Do
  not add pytest-asyncio for a single test."
- **Evidence:** 404 `asyncio.run(` calls in tests. The skill assumes a plugin ("When
  AnyIO and pytest-asyncio are both installed…").
- **Priority:** Low.

### F9. Remove prototypes and experiments from the regression suite

- **Target:** `pytest/SKILL.md` quality gate.
- **Rule:** spike and experiment code that doesn't exercise production code is deleted,
  or moved out of the collected suite, once the decision is recorded.
- **Evidence:** `submission-prep/tests/autocommit_prototype.py` holds 80 lines exercised
  by `integration/db/test_connection_policy_experiments.py`.
- **Priority:** Low.

### F10. Label ceremony rules as heuristics

- **Target:** `pytest/SKILL.md` and `core-principles.md`.
- **Change:**
  - "For non-trivial work, record a compact matrix before implementation": make this a
    suite-design step, not a per-test requirement.
  - "Make each fixture perform one state-changing setup action": `run_with_db`
    reasonably resets, migrates and builds an engine as one unit. Reword to "one
    cohesive setup concern".
- **Priority:** Low.

---

## Part G — `python-repository-setup`

### G1. Lint set: mandate what the skill assumes, offer a measured extension

- **Target:** `repo/references/pre-commit.md` (Ruff section).
- **Rule:**
  - Mark `TID252` (no relative imports) as mandatory whenever `arch` invariant 9
    applies. The template includes it, but the repo's config dropped it; the code is
    compliant only by habit.
  - Offer an optional extension set, with per-file ignores for tests:
    - `S101` (assert): 29 hits in source;
    - `FBT003` (positional bool): 20;
    - `PLW0603` (global): 30, all in metrics modules;
    - `BLE001` (blind except): 51, mostly legitimate boundary translation, so use it
      as a review prompt with a `# noqa: BLE001  <reason>` convention.
  - Explicitly **do not** recommend `EM`/`TRY003`: 688 hits of pure churn.
- **Why:** each rule in Part A becomes cheaper to follow when a linter flags it, and
  the measured counts show the cost of adoption.
- **Priority:** Medium.

### G2. Per-member test paths

- **Target:** `repo`. Pairs with F2.
- **Rule:** configure the test path per member, not as a root-level `pythonpath` list
  of every member's `tests/`.
- **Priority:** Medium (as part of F2).

---

## Part H — Existing skill text to rewrite or remove

These are defects in the skills themselves. Each one either contradicts another rule or
steers agents toward noisier code.

| # | Skill / location | Current text (abridged) | Problem | Recommendation |
| --- | --- | --- | --- | --- |
| H1 | settings `settings-py.md:74`; `SKILL.md` Core Conventions; all scaffolds | "Include concise `description=` text on fields"; "Use `Field(..., description=...)` for required values" | Produces descriptions that restate the name (B1) | Replace with B1 |
| H2 | settings `SKILL.md` vs `references/env-example.md` | "exactly three sections: REQUIRED, OVERRIDABLE, OPTIONAL" | The template in `env-example.md` has five sections, and the repo follows five | Pick one taxonomy, and fix the template or the rule |
| H3 | settings `env-example.md` | "OVERRIDABLE lists every key of the YAML policy baseline" vs. "Do not add an exhaustive 'all possible overrides' dump" | Direct contradiction | Keep "useful overrides only"; drop "every key" |
| H4 | settings `config-yaml.md` examples | `environment_name: local`, `app_host`, `app_port` in YAML | Violates the skill's own rules (environment selector never in YAML; hosts/ports env-only), and the repo copied the host/port pattern | Fix the examples |
| H5 | settings (whole skill) | The env-only vs. YAML ownership test restated ~6 times across 5 files | ~1,570 lines; repetition crowds out missing Pydantic-modelling guidance | State the ownership contract once in `SKILL.md`; references link to it |
| H6 | db `engine-and-session.md` | Module-level `engine = build_engine(settings.database_url)`; `from myservice.db.engine import engine` | Import-time global; conflicts with "bootstrap creates engines" and with the repo's `AsyncExitStack` pattern | Show a `build_engine(dsn, settings)` factory entered in bootstrap |
| H7 | db `SKILL.md` | "`repositories/` is the *only* code that imports `AsyncSession`, `text()`…" | Ignores `db/session.py`, advisory locks, and unit-of-work stores | "Only `db/` imports…" |
| H8 | db `SKILL.md` | "Multi-join, aggregation, or reporting SQL goes in its own `.sql` file" | The repo's multi-join claims compose shared Python predicates and clock helpers that a `.sql` file cannot reuse; there are 0 `.sql` files | Restrict to static reporting SQL |
| H9 | db `repo-layout.md` | "Everything from `engine.py` down … legitimately varies per service"; the lib holds "*only* `base.py` and `models/`" | Licenses 4 identical copies; bans enums and document contracts from the schema lib | Replace with C8's trigger and C10's contents rule |
| H10 | db `models-and-base.md` | `onupdate=` is client-side, "not a database trigger" (read as a prohibition) | `onupdate` fires on ORM flushes and Core `update()`, which is every write here | State the real gap: raw `text()` SQL and migration backfills |
| H11 | db `repositories-and-queries.md` | "Bootstrap constructs `UserRepository(session)` and injects it behind an application-owned repository port" | Read literally, it forces a Protocol per repository and contradicts `arch`'s "often does not need a second Protocol"; produced pass-through stores | Replace with C1 |
| H12 | arch `boundaries.md` port admission test | "Introduce a port when at least two of these are true" | Every DB satisfies it; contradicts the adjacent sentence | Add the DB clarification from C1 |
| H13 | arch `boundaries.md` | "must not read global settings" | "Global" lets injected `Settings` pass | "never import `config/`" (C3) |
| H14 | arch `SKILL.md` invariant 4 | "Every GenAI task keeps model construction in an `llm.py` factory; an agent adds an `agent.py` factory" | Mandates files regardless of size; conflicts with invariant 5 (flat-first) | "a model factory function, in `llm.py` once the task has more than one module" |
| H15 | arch `api-and-workers.md` | "Use `api/routers/` … even if it starts with one module" | Contradicts "no one-file subpackages" | Allow `api/routes.py` until a second router exists |
| H16 | arch vs. audit | The audit "Semantic audit" bullets restate `boundaries.md` "Dependency audit", GenAI tool rules, and observability placement | Two sources of truth drift | The audit references `arch` sections by name and keeps only procedure |
| H17 | audit "Route the findings" | Default: write `FEEDBACK.md` and implement fixes, or invoke `openspec-propose`; "Do not ask for redundant repair confirmation" | Heavy and surprising for "review this"; turns an audit into edits | Default to report-only; make repair or proposal an explicit follow-up |
| H18 | arch `modularization.md` vs. `CLAUDE.md` | "Around 300–350 lines" vs. "Around 300 lines"; function thresholds only in `CLAUDE.md` | Inconsistent signals | One set of numbers, stated in python-code-style and referenced |
| H19 | otel `SKILL.md` rule 9 | `log_full_exception_trace` default `true`, "Do not ask" | Unsafe default for regulated data (E1) | Replace with E1 |
| H20 | otel `naming.md` | "Do not scatter string literals" (no carve-out) | ~100+ constants per service (E3) | Replace with E3 |
| H21 | otel `worker_runtime.md` | Sync `signal.signal` + global-flag loop | Doesn't match asyncio services (C6) | Replace with an asyncio stop-event example |
| H22 | otel `SKILL.md` scope | "do not touch sibling services merely for symmetry" + "route to shared_library without an explicit request" | Pull against each other (E6) | Add E6 |
| H23 | pytest `testing.md` | "Do not promote it to root merely to avoid a local duplicate" + "must not import another deployable's … test helpers" + "omit `tests/__init__.py`" + "no global pythonpath" | Unsatisfiable together (F1, F2) | Replace with F1 and F2 |
| H24 | pytest `SKILL.md` quality gate | "exact log prose" | Ambiguous for structured events (F6) | Replace with F6 |

---

## Part I — Good patterns already in the code, to codify explicitly

These are working well, often in only some services. Writing them down makes them the
default instead of an accident.

| Pattern | Where it's done well | Target skill | Currently covered? |
| --- | --- | --- | --- |
| Frozen dataclasses for domain values; Pydantic only for validated external input | 173/190 dataclasses frozen; Pydantic in settings, secrets and schemas | python-code-style (A1) | No |
| Keyword-only parameters for multi-argument functions | 435 functions; 0 positional-bool definitions | python-code-style | Partially (`CLAUDE.md` #6) |
| Modern syntax: `X \| None`, `datetime.UTC`, no `os.path`, PEP 695 aliases and generics | Throughout (39 `datetime.UTC` uses) | python-code-style | No |
| Why-docstrings | `edm_client/models.py:84-91`, `db/server_time.py` | python-code-style (A11) | Partially |
| Reusable `Annotated` validator types | `NonEmptyText`, `AwsRegion`, `TimezoneName` | settings (B5) | Partially |
| Cross-field `model_validator` for timing invariants (lease longer than timeout) | `resolution-worker/.../settings.py:292-318` | settings | No |
| Rejecting legacy env vars with a migration message | `lseg-worker/.../settings.py:336-355` | settings | No |
| `ConfigurationError` carrying reason and key with `include_input=False` | all services | settings (B6) | No |
| Secret hygiene: unwrap only at adapters; errors name variables not values; pair validators | `lseg/secrets.py` | settings (B7) | Partially |
| Action-owned policy dataclasses built in bootstrap | resolution-worker, ticket-monitor | arch (C3) | No |
| Single-statement skip-locked claim with re-sort | submission-prep, resolution-worker | db (D1) | No |
| Claim → commit → external call → fenced write | `resolution-worker/.../processing.py` | db (D3) | No |
| Named-constraint `IntegrityError` matching; `ON CONFLICT DO NOTHING` | `admission_store.py`, `admission.py` | db (D5) | No |
| CHECK constraints generated from `StrEnum`; partial indexes per claim predicate | `resolution_session.py` | db (D9, D12) | No |
| Lock ordering; `pg_try_advisory_xact_lock` | `inbound.py`, `hitl_notifications.py` | db (D8) | No |
| Squashed baseline with a raising `downgrade()`; triggers via `op.execute`; SQL backfills | db-migrate | db | Yes |
| `asyncio.to_thread` around every boto3 call | all 17 sites | arch (C7) | No |
| `AsyncExitStack` composition root; `_owns_client` + `aclose` for injectable clients | `lseg_worker/bootstrap/runtime.py`, `edm_client` | arch (C7) | No |
| Stop event + grace timeout + cancel + gather | `resolution_worker/bootstrap/supervisor.py:132-143` | arch (C6), otel | No |
| Injected `sleep`/`clock`; database-owned time for lease predicates (no freezegun) | `edm_client/session.py`, `domain/source_projection_retry.py` | pytest, db | Partially |
| Conventions module + service helpers; 0 OTel imports in application code | all services | otel | Partially |
| Allowlisted log renderer as a PII guard | resolution, lseg, ticket | otel (E7) | No |
| Destructive-reset guard for integration DB (`INTEGRATION_DATABASE_URL` only) | integration conftests | pytest | Yes |
| Contractual call-order assertion only where order matters (disposal order) | `lseg-worker/tests/unit/bootstrap/test_runtime.py:185` | pytest | Yes |
| Sanitized fixtures with provenance READMEs | `libs/edm_client/tests/fixtures/README.md` | pytest | Yes |

---

## Appendix — Method and measurements

- **Scope:** `libs/` (2) and `services/` (6 members, 4 with application code). Source and
  tests were surveyed separately by concern: settings/Pydantic, persistence,
  architecture, async/errors/observability, tests, and Python idioms.
- **Skills:** each skill's `SKILL.md` and the references relevant to each concern were
  read in full. Coverage claims quote the skill text.
- **Measurements:**
  - AST scans for function length, complexity, and `Field()` argument categories.
  - grep counts for `Any`, `cast`, `type: ignore`, `assert`, `except Exception`,
    `asyncio.run`, `monkeypatch`, `SimpleNamespace`.
  - An isolated Ruff pass with extra rule sets, for G1's counts.
  - `audit_service.py` run on all four services.
- **Verification:** key evidence was re-read at source, including:
  - `submission-prep/config/settings.py:220-224` (descriptions);
  - `db_models/models/inbound_email.py:197` (enum column typed `str`);
  - `workflow_recovery.py:120-128` (dict accumulator and literal comparisons);
  - `advisory_lock.py:38-54` (`except Exception` cleanup);
  - `lseg_worker/observability/tracing.py:90-108` (`except Exception: pass`);
  - `ticket_monitor/domain/authentication.py:14-22` (positional booleans);
  - the `engine.py` diff between services (identical apart from package and docstring).
- **Not in scope:** fixing any of the cited code, the existing
  `SKILL_GUIDELINE_RECOMMENDATIONS.md` (deliberately not consulted), and non-Python
  skills.
