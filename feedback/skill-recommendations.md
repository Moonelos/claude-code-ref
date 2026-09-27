# Skill Improvement Recommendations

Evidence-based proposals for improving the Python development skills in
`.agents/skills/`. The findings come from a full read of `libs/` (6 packages)
and `services/` (orchestrator, worker, platform_migrations), which together hold
about 21.6k lines of source and tests. Every rule below is tied to patterns that
actually occur in this codebase.

The skills reviewed are `pytest`, `python-logging`, `python-repository-setup`,
`python-service-architecture`, `python-service-architecture-audit`,
`python-settings-config` and `python-sqlmodel-alembic`. `CLAUDE.md` is loaded in
every session, so it is treated as existing coverage too.

This document proposes changes to the **skills**. Code paths are cited as
evidence for reusable rules, not as a defect list to fix.

---

## How to read this document

Each recommendation uses this shape:

- **Target skill**, **Status**, **Priority**, where Status is one of:
  - *Missing*: no skill says this.
  - *Partial*: a skill says it vaguely, or a skill example contradicts it.
  - *Rewrite*: the current rule is harmful or leads to worse code.
  - *Remove*: the current content should be deleted.
  - *Standardize*: a good practice exists in the code but no skill documents it.
- **Rule**: the text proposed for the skill.
- **Why**, **Evidence**, **Good / Bad**, **Exceptions**.

Evidence counts come from `grep` across `libs/*/src` and `services/*/src`
unless the text says tests.

---

## 0. Summary

### Highest-leverage changes

| # | Change | Target | Priority |
|---|---|---|---|
| 1 | Replace "Include concise `description=` text on fields" with a rule that `Field(...)` must add information | `python-settings-config` | High |
| 2 | Create a small **code-conventions** skill for language-level rules that no skill owns today (data containers, closed value sets, `assert`, constructors, constants, loggers) | new skill | High |
| 3 | Dataclasses with more than 3 fields are `kw_only=True` and always constructed by keyword | new skill | High |
| 4 | Define each closed value set (states, record types, error codes) once as a `StrEnum` or `Literal` alias | new skill + `python-sqlmodel-alembic` | High |
| 5 | Give each service one exception base with a `code`, split into rejection vs unavailable, and handle every port failure at a named boundary | `python-service-architecture` | High |
| 6 | Write one transaction-scope helper instead of per-method `try/begin/except` wrappers | `python-sqlmodel-alembic` | High |
| 7 | Read the clock only in `bootstrap/`; `application/` and `db/` receive `now` or a `Clock` | `python-service-architecture` | High |
| 8 | FastAPI routes get services through typed `Depends` providers, not `request.app.state` plus `cast` | `python-service-architecture` | High |
| 9 | Standardize native async tests (anyio plugin is already installed) and shared integration fixtures | `pytest` | High |
| 10 | Encode `CLAUDE.md` limits in Ruff (`C901`, `S101`, `PT`, `ASYNC`, ...) | `python-repository-setup` | High |
| 11 | Remove self-contradictions and dead references inside the skills | several | High |

### Existing coverage the code already follows well

These practices are already in a skill and the code follows them, so they need
no new rule: absolute imports (TID252), inward dependencies checked by contract
tests, `raise ... from`, structured event names, `SecretStr` secrets split from
settings, `AwareDatetime` and UTC, `extra="forbid"` boundary models, lease
fencing with `SKIP LOCKED`, autospecced mocks, loud failure for missing
integration infrastructure, and Docker version pinning.

Section 11 lists good patterns that exist in the code but that **no** skill
documents yet.

---

## 1. Where language-level rules should live

### 1.1 Create a `python-code-conventions` skill (or a shared reference)

- **Target skill:** new `python-code-conventions`. The alternative is a new
  `python-service-architecture/references/code-conventions.md` that every Python
  skill links to.
- **Status:** Missing · **Priority:** High

**Rule.** Add one short skill, about 200 lines, that owns language-level
conventions: data containers, typing of closed sets, constructors, constants,
module-level loggers, `assert`, exception shape, docstrings. Trigger it for any
edit to Python source under `services/` or `libs/`. The other skills link to it
instead of restating these rules.

**Why.** The most frequent issues found in this codebase do not belong to any
existing skill:

- keyword construction of wide dataclasses;
- stringly-typed states;
- `assert` in production code;
- tuple-packed attributes;
- inline `getLogger`;
- repeated literals.

`python-service-architecture` is about *where* code lives, and `CLAUDE.md` is
generic. Without an owner, agents fall back on whatever local style they see.
That is how the 76 dataclasses ended up with 0 uses of `kw_only`.

**Evidence.** Sections 2–5 below. Every item there was found in at least two
of the three code areas (libs, orchestrator, worker), which shows a
repository-wide habit rather than a single author's style.

**Exceptions.** Keep the skill short and example-driven. Do not duplicate
`CLAUDE.md`'s ten principles; cite them and add the concrete Python mechanics.
Sections 2–6 give the proposed content. Appendix A has the outline.

---

## 2. Data modeling and typing

### 2.1 Wide dataclasses are keyword-only

- **Target:** `python-code-conventions` · **Status:** Missing · **Priority:** High

**Rule.** Declare `@dataclass(frozen=True, kw_only=True)` for any dataclass
with more than 3 fields, and construct such values with keyword arguments only.
Positional construction is acceptable for 1–3 field values whose order is
self-evident, such as `Point(x, y)` or `Reservation(token)`.

**Why.** With positional construction, readers must count arguments, and
same-typed fields (`str`, `UUID`, `datetime | None`) can be swapped silently
without the type checker noticing. Tests copy these constructors, which
multiplies the risk.

**Evidence.**
- 76 `@dataclass` declarations, 0 with `kw_only`.
- `services/worker/src/worker/db/repositories/work.py:164` builds `OwnedWork(`
  from about 22 positional values.
- `services/worker/src/worker/bootstrap/executor.py:43` calls
  `ExecutionPolicy(...)` with 13 positional arguments.
- `services/orchestrator/src/orchestrator/domain/discovery_policy.py:63` has
  `ClaimDecision("failed", observation.attempts, "incompatible_selection", now, None, None)`.
- `db/repositories/recovery.py:55-68` builds `RecoveryObservation(` from 12
  positional values.
- Tests copy the positional `OwnedWork(...)` into 8 worker unit files.

**Bad**
```python
return ClaimDecision("failed", observation.attempts, "incompatible_selection", now, None, None)
```
**Good**
```python
@dataclass(frozen=True, kw_only=True)
class ClaimDecision:
    status: ClaimStatus
    attempts: int
    error_code: str | None = None
    decided_at: datetime
    next_attempt_at: datetime | None = None
    lease_token: UUID | None = None

return ClaimDecision(
    status=ClaimStatus.FAILED,
    attempts=observation.attempts,
    error_code="incompatible_selection",
    decided_at=now,
)
```

**Exceptions.** Tiny tagged-union members such as `Active(remaining_seconds)`.
A dataclass mirroring an external positional protocol.

---

### 2.2 Define each closed value set exactly once

- **Target:** `python-code-conventions`, with a persistence addendum in
  `python-sqlmodel-alembic` (see 7.5)
- **Status:** Partial. `python-settings-config` covers `Literal` for settings
  only, and the architecture skill says "Prefer an enum, literal, or value
  object over a `constants.py`" without saying to define it once.
- **Priority:** High

**Rule.**
- Model a lifecycle state, record type, mode or error-code family as one
  `StrEnum`, or one `type X = Literal[...]` alias, owned by `domain/`, or by
  the shared library when several services persist it.
- Type every parameter, field and transition table with it.
- Name derived subsets as constants beside the type, for example
  `TERMINAL_STATES: frozenset[State]`.
- Compare against members, never string literals.
- Choose `StrEnum` when code needs members, iteration or a DB CHECK generated
  from the values. Choose a `Literal` alias for small mode switches that are
  only compared.

**Why.** Each repeated set is a place a new state can be forgotten, and the
type checker cannot tell `"retry_wait"` from a typo.

**Evidence.**
- Worker states are bare `str` (`ports/work_store.py:51` `state: str`), while
  phases are a `Literal`. `cast(Phase | None, row.resume_phase)` appears at
  `db/repositories/work.py:183`.
- `TERMINAL_STATES = ("completed", "failed", "delivery_unknown")` at
  `orchestrator/domain/retention.py:8` is repeated inline at
  `domain/reporting.py:140`.
- `("reconciliation_pending", "reconciling")` appears twice in
  `db/repositories/retention.py`.
- `RecordType` is a `StrEnum` (`domain/discovery.py:9`), yet
  `cursors.py:37` re-declares `Literal["HOLD", "TRAN"]`, and code compares
  `record.record_type == "TRAN"`.
- `Literal["value_date", "delivery_date"]` is declared 3 times in the worker.
- In `libs/platform_db`, every status column is `str` and the CHECK
  constraints list the values again as raw SQL (`investigations.py:31`).
- `libs/im_client/queries.py:166` checks `operator not in {"EQ", "GTE", "LTE"}`
  at runtime.

**Good**
```python
class InvestigationState(StrEnum):
    PENDING = "pending"
    PREPARING = "preparing"
    COMPLETED = "completed"
    FAILED = "failed"
    DELIVERY_UNKNOWN = "delivery_unknown"

TERMINAL_STATES = frozenset({
    InvestigationState.COMPLETED,
    InvestigationState.FAILED,
    InvestigationState.DELIVERY_UNKNOWN,
})
```

**Exceptions.** Alembic revisions keep their own frozen copies (see 7.8). Wire
values from an external API that the application passes through without
interpreting may stay `str`.

---

### 2.3 Untrusted JSON is `JsonValue`; `Any` is only for raw SDK edges

- **Target:** `python-code-conventions` · **Status:** Missing · **Priority:** Medium

**Rule.**
- Type unvalidated wire or JSONB data as `pydantic.JsonValue`, `object` or a
  `TypedDict`.
- Once data has been validated into a model, pass the model on. Do not convert
  it back to `dict[str, Any]`.
- Allow `Any` only where a third-party SDK returns `Any`, and narrow it within
  the same function.

**Why.** `Any` switches off `mypy --strict` exactly where malformed input
arrives.

**Evidence.**
- `policy_config` and the worker's `evidence.py` use
  `TypeAdapter(dict[str, JsonValue])`: a good precedent.
- `im_client` returns `-> Any` from `request()`/`query()` and exposes
  `parse_page(payload: Any, ...)`.
- `orchestrator/domain/cursors.py:53-61` validates into `QueryPosition`, then
  returns `dict(document["payload"])`, which throws the typed model away.
- About 12 JSONB columns in `platform_db` are typed `dict[str, Any]`.

**Exceptions.** JSONB model columns may stay `dict[str, JsonValue]` when their
shape is owned by a codec (see 7.6).

---

### 2.4 No `assert`, `object.__setattr__` or `getattr` duck-typing in production code

- **Target:** `python-code-conventions`, enforced by Ruff `S101` (see 9.1)
- **Status:** Missing · **Priority:** High

**Rule.**
- Do not use `assert` under `src/` for invariants or type narrowing. Make the
  field non-optional in the type, or raise a specific exception.
- Never bypass `frozen=True` with `object.__setattr__`. Derive the value in a
  method, a `computed_field`, or a separate resolved model.
- Do not probe for optional methods with `getattr(obj, "name", None)`. Type the
  dependency, and make test fakes implement the full protocol.

**Why.** `python -O` removes asserts. The other two patterns hide the real
contract from both readers and the type checker.

**Evidence.**
- There are 11 `assert` statements in `src`, for example
  `worker/db/repositories/work.py:162`
  `assert row.lease_token is not None and ...`,
  `orchestrator/adapters/im_discovery.py:50`, and
  `worker/bootstrap/supervisor.py:52`.
- `worker/config/settings.py:239` has
  `object.__setattr__(self, "admission_min_inflight", minimum)`.
- `worker/application/admission/gate.py:51` has
  `changed = getattr(self.controller, "pending_changed", None)`, which exists
  only because a test fake lacks the method.

**Exceptions.** `assert_never()` in exhaustive `match` statements is encouraged.
Asserts are fine in tests.

---

### 2.5 Frozen means deeply immutable; secrets are typed, not just hidden

- **Target:** `python-code-conventions` · **Status:** Missing · **Priority:** Low

**Rule.**
- Frozen value objects hold `tuple`/`frozenset`/`Mapping`, not `list`/`dict`.
- To change a Pydantic domain model, build a new instance with
  `model_copy(update=...)`; do not mutate it in place.
- A credential inside a library dataclass is `SecretStr`. `field(repr=False)`
  is the minimum only when adding pydantic to the library is unjustified.

**Evidence.**
- `im_client/queries.py:69` has a frozen `QueryPage` with
  `rows: list[dict[str, Any]]`.
- `worker/application/prepare.py:28` does `snapshot.evidence = evidence` and
  `snapshot.limitations.append(...)`.
- `im_client/client.py:28` has `client_secret: str = field(repr=False)`.

---

### 2.6 Use the Python 3.13 `type` statement for aliases

- **Target:** `python-code-conventions` · **Status:** Missing · **Priority:** Low

**Rule.** Write `type CooldownState = Active | Inactive | Unavailable`, not a
bare assignment or `TypeAlias`, for new aliases.

**Evidence.** `provider_admission/cooldown_signal.py:30` uses a bare assignment.
The Alembic `script.py.mako` still emits `Union[...]` (see 7.9).

---

## 3. Pydantic models and settings

### 3.1 `Field(...)` only when it adds information: rewrite the settings rule

- **Target:** `python-settings-config` (`SKILL.md` core conventions and
  `references/settings-py.md` "Field Conventions"), and the Pydantic section of
  `python-code-conventions`
- **Status:** Rewrite · **Priority:** High

**Current text causing the problem.**
- `settings-py.md:74`: "Include concise `description=` text on fields."
- `SKILL.md:247`: "Use `Field(..., description="...")` for required values and
  `Field(default=..., description="...")` only for sensible, safe defaults."
- Every scaffold models this with, for example,
  `app_port: PositiveInt = Field(default=8080, description="Server bind port.")`.

**Proposed rule.**

> Use `Field(...)` only when it provides meaningful metadata or behavior: a
> constraint, an alias that differs from the field name, a `default_factory`,
> `repr=False`/`exclude`, or a `description` that adds information the name
> and type do not already convey. Useful information includes units, expected
> format, allowed range rationale, when a value is required, what happens when
> it is omitted, and whether it is sent to an external system. Do not
> mechanically wrap ordinary fields in `Field(...)`. Prefer
> `timeout_seconds: PositiveFloat = 15.0` over
> `Field(default=15.0, description="Timeout seconds.")`.

**Why.** The skill's instruction directly produced about 80 descriptions that
restate the field name. They add noise to the settings class, then propagate
into `.env.example` comments (`# Im base url.`), where they read as
documentation but carry none. The few meaningful descriptions get lost among
them.

**Evidence.**
- `orchestrator/config/settings.py`: about 35 of 40 descriptions restate the
  name, for example `im_client_id: str = Field(alias="IM_CLIENT_ID", description="Im client id.")`
  and `db_pool_size ... description="Db pool size."`.
- The worker settings are the same, about 45 of 51.
- Good counter-examples in the same file:
  ```python
  im_source_scope: str = Field(
      alias="IM_SOURCE_SCOPE",
      description="Identity of this IM connection; scopes rate limiting and "
      "investigation de-duplication, never sent to IM.",
  )
  cognito_resource_server_id: str | None = Field(
      default=None, alias="COGNITO_RESOURCE_SERVER_ID", min_length=1,
      description="Cognito custom-scope namespace; omit only for unprefixed local tokens.",
  )
  ```

**Bad**
```python
lease_seconds: PositiveInt = Field(default=120, alias="LEASE_SECONDS", description="Lease seconds.")
```
**Good**
```python
lease_seconds: PositiveInt = 120
reconciliation_deadline_seconds: PositiveInt = Field(
    default=300,
    description="Wall-clock budget for one reconciliation generation, across all attempts.",
)
```

**Exceptions.**
- A generated configuration reference that renders `description` for
  operators may justify short descriptions everywhere. In that case make it an
  explicit, stated repository decision, and still require the description to
  say more than the name.
- `Field(...)` as a required marker is unnecessary: an annotation with no
  default is already required.

Also update the three scaffolds in `settings-py.md` to follow the new rule, so
the examples model it.

---

### 3.2 Drop env aliases that only upper-case the field name

- **Target:** `python-settings-config` (`settings-py.md` "Field Conventions",
  `secrets-py.md`) · **Status:** Rewrite · **Priority:** Medium

**Current text.** "Use SCREAMING_SNAKE_CASE aliases for env vars" and "set
`populate_by_name=True` whenever fields have env-var aliases".

**Proposed rule.** Keep `case_sensitive=False`, the pydantic-settings default,
and let field names map to env vars: `db_pool_size` reads `DB_POOL_SIZE`. Add
`alias`/`validation_alias` only when the env name differs from the field name,
for example a legacy name, an SDK-owned variable, or a compatibility alias.
With no aliases, YAML keys and field names match, and `populate_by_name` is no
longer needed.

**Why.**
- About 90 aliases across the two settings classes carry no information.
- The alias requirement forces `populate_by_name=True`, and the skill spends a
  paragraph in three places explaining that trap.
- Removing them deletes the trap along with the noise.

**Evidence.**
- `orchestrator/config/settings.py` has an alias on every field.
- `sources.py` must look up both `"ENVIRONMENT_NAME"` and `"environment_name"`.

**Exceptions.**
- Keep `case_sensitive=True` plus aliases only when a platform really requires
  case-sensitive names.
- The env-contract test may compare `field_name.upper()` instead of aliases.
- This changes no deployed variable names, so it is a safe refactor.

---

### 3.3 One authoritative home per default

- **Target:** `python-settings-config` · **Status:** Partial. The skill forbids
  duplicating env-only values into YAML, but is silent on Python defaults
  duplicating YAML. · **Priority:** Medium

**Rule.** Under the YAML pattern, a YAML-owned policy value has exactly one
authoritative literal, in `config/base.yaml` or the environment file. Pick one
of these two approaches and state it in the skill:
- **(a)** The Python field has no default, and the YAML source always supplies
  it.
- **(b)** Keep a Python default, and have a contract test assert it equals
  `base.yaml`.

In both cases, the commented `.env.example` OVERRIDABLE values must be
verified by the contract test, not typed by hand.

**Evidence.** `DB_POOL_SIZE = 5` appears in `orchestrator/config/settings.py:59`,
`config/base.yaml:3` and `.env.example:43`, three literals kept in sync by
hand.

---

### 3.4 Settings validation: constraints on types first, `model_validator` for relations

- **Target:** `python-settings-config`
- **Status:** Standardize (cross-field validation) plus Partial (constraints)
- **Priority:** Medium

**Rule.**
- Express single-field rules in the type: `PositiveInt`,
  `Annotated[str, StringConstraints(min_length=1)]`, `Field(le=...)`,
  `list[NonEmptyStr]` with `min_length=1`.
- Reserve `model_validator(mode="after")` for relationships between fields.
- Keep each message naming both fields.
- Never mutate `self` in a validator. Derived values go in a method or a
  `computed_field`.

**Why.** The existing `validate_limits` validators are a strong pattern that
the skill only mentions in passing ("Validate cross-field invariants at
startup"). They should be shown. The per-item emptiness loop belongs in the
type.

**Evidence.**
- Good: `orchestrator/config/settings.py:175-194`, for example
  `if self.heartbeat_seconds * 2 >= self.lease_seconds: raise ValueError(...)`.
- Misplaced in the same validator:
  `if not self.cognito_client_ids or any(not value.strip() for value in ...)`.
- `worker/config/settings.py:239` mutates `self` (see 2.4).

---

### 3.5 Map settings to domain policy objects once; build `Settings` once

- **Target:** `python-settings-config` and `python-service-architecture`
  (bootstrap section) · **Status:** Missing · **Priority:** Medium

**Rule.**
- Construct `Settings` and `Secrets` once in the composition root and pass
  them down.
- Each settings-to-policy mapping, for example `AdmissionProfile` or
  `ExecutionPolicy`, is one named function or method, used by both validation
  and bootstrap.
- Never store `Secrets` on framework state such as `app.state`. Inject the
  specific credential into the adapter that needs it.

**Evidence.**
- `Settings()` is constructed 4 times in the orchestrator (`main.py:9`,
  `bootstrap/app.py:28`, `app.py:91`, `bootstrap/recovery.py:21`).
- `bootstrap/app.py:36` has `app.state.secrets = secrets`.
- The 17-field `AdmissionProfile(...)` is built in both
  `worker/config/settings.py:240`, for validation, and
  `bootstrap/supervisor.py:53`.

---

### 3.6 Keep `Secrets` credential-only, even in single-purpose runners

- **Target:** `python-settings-config` · **Status:** Partial · **Priority:** Low

**Rule.** `Secrets` holds only credential-bearing values. `environment_name`,
timeouts and lock durations belong in `Settings`, even in a one-module
migration runner.

**Evidence.** `platform_migrations/config.py:9-17` puts `environment_name` and
`migration_lock_timeout_seconds` in `Secrets`, while the services keep that
split.

---

### 3.7 Settings tests isolate the process environment

- **Target:** `python-settings-config` (Change Checklist) and `pytest`
- **Status:** Missing · **Priority:** Medium

**Rule.** Settings tests must:
- clear every env var the model reads, using `monkeypatch.delenv`;
- construct with `_env_file=None`, or point to a temp file;
- point the config-dir override at a fixture directory.

Share one `runtime_env` fixture per service. Do not copy it into each test
module.

**Evidence.** The worker's `test_settings.py:13` clears overrides and passes
`_env_file=None`. The orchestrator's copy calls `Settings()`, so a developer's
`.env` can leak into the result.

---

### 3.8 Build models from typed values with keyword arguments; `model_validate` is for untrusted input

- **Target:** `python-code-conventions` (Pydantic section)
- **Status:** Missing · **Priority:** Medium

**Rule.** When application code already holds typed values, construct the
model with keyword arguments so mypy checks the field names. Use
`model_validate` and `model_validate_json` for data crossing a trust boundary.
Do not assemble a `dict`, `pop` keys and then validate it.

**Evidence.**
- `orchestrator/domain/reporting.py:164-202` builds
  `result: dict[str, Any]`, pops keys, then calls
  `ReportItem.model_validate(result)`.
- `db/repositories/queries.py:84` calls
  `RequestSummary.model_validate({"request_id": str(row.id), ...`.
- `routers/queries.py:31` does `body.model_dump(...)` and then
  `QuerySelection.model_validate(...)`.

---

### 3.9 Reusable `Annotated` types for repeated constraints

- **Target:** `python-code-conventions` (Pydantic section)
- **Status:** Missing · **Priority:** Low

**Rule.** When the same constraint or validator appears on two or more
models, define one `Annotated` alias or small helper next to the owning domain
type. Examples: `RecordKey = Annotated[str, StringConstraints(min_length=1, max_length=200)]`,
or an "exactly one of" check.

**Evidence.**
- `max_length=200` for record keys appears 5 times.
- `sum(value is not None for value in (...)) != 1` appears 3 times
  (`api/schemas/investigations.py:36`, `:84`, `domain/cursors.py:41`).
- The record-key de-duplication validator is copied twice.

**Exceptions.** Do not introduce a validator library for a single use (see
`CLAUDE.md` rule 9).

---

### 3.10 Fix contradictions and complexity inside `python-settings-config`

- **Target:** `python-settings-config` · **Status:** Rewrite/Remove · **Priority:** High

1. **The YAML examples break the skill's own rules.**
   - `config-yaml.md:194` shows `environment_name: local` in YAML, but
     `SKILL.md:236` says `ENVIRONMENT_NAME` must "never have a YAML or Python
     default".
   - The same examples put `app_host` and `app_port` in YAML, while
     `SKILL.md:80-85` classifies ports as deployment topology.
   - Fix: remove those keys from the examples. Agents copy examples more
     faithfully than prose.
2. **There are two incompatible `.env.example` structures.**
   - `SKILL.md:240` and `env-example.md:84` require "exactly three sections"
     (REQUIRED/OVERRIDABLE/OPTIONAL).
   - `env-example.md:49-120` prescribes a five-section layout and ships a full
     template for it.
   - Fix: keep the three-section contract the repository actually uses, and
     delete the five-section template.
3. **The scaffold uses a clever control-flow trick.**
   - `settings-py.md:407` uses
     `env_settings().get(...) or dotenv_settings().get(...) or raise_missing_environment_name()`.
     A raising function hidden in an `or` chain is exactly the "clever"
     pattern the repository wants to avoid.
   - Replace it with an explicit `if value is None: raise ...`.
4. **The remote-secrets example has mutable global state.**
   - It uses `global _cached_secrets` (`secrets-py.md:212-220`) and an ABC,
     plus a `_fetch_scalar` that does `del source; raise NotImplementedError`.
   - Replace this with: load secrets once in bootstrap and pass them
     explicitly. Use a `Protocol` or plain function per provider, and no
     module-level cache.
5. **The skill repeats itself.** The ownership contract (YAML vs env-only vs
   secret, GenAI coordinates, "resource vs namespace", "location vs API
   path") is restated in `SKILL.md`, `config-yaml.md`, `settings-py.md` and
   `env-example.md`. Keep the full statement in `SKILL.md`, and replace the
   copies with one-line links. This cuts about 25% of the skill and removes
   the risk that the copies drift apart.
6. **Shared source code is duplicated per service.** The skill shows
   `settings_customise_sources` and discovery as per-service code, and the
   repository copied it: `orchestrator/config/sources.py` and
   `worker/config/sources.py` differ only in the service name, `*_CONFIG_DIR`
   and `OBSOLETE_SETTINGS`. Add: "In a workspace with two or more services
   using the YAML pattern, the YAML source and discovery live in the shared
   config library, parameterized by service name. Services keep only their
   `Settings` class." Here, `libs/policy_config` is the natural owner.

---

## 4. Classes, functions and constants

### 4.1 Constructors: one attribute per line, names match parameters, collaborators private

- **Target:** `python-code-conventions` · **Status:** Missing · **Priority:** Medium

**Rule.**
- In `__init__`, assign one attribute per line.
- Keep the attribute name equal to the parameter name, with a leading
  underscore for collaborators.
- Prefer a `@dataclass` when `__init__` only stores arguments.
- Do not expose injected collaborators as public mutable attributes that tests
  overwrite after construction. Tests pass fakes to the constructor.

**Why.** Tuple-packed assignment hides renames, and it makes it hard to see
which argument became which attribute.

**Evidence.**
- Tuple-packed assignment appears in about 20 constructors across all three
  areas.
- `im_client/client.py:46-52`:
  `self.policy, self.margin, self.clock, self.sleep = (policy or RetryPolicy(), refresh_margin_seconds, monotonic, ...)`.
  Here `refresh_margin_seconds` becomes `margin` and `monotonic` becomes
  `clock`.
- `worker/application/execution.py:60`:
  `self.store, self.source, self.sender, self.reader = store, source, sender, reader`.
- Tests overwrite public attributes, for example `im.observer = recorder` and
  `im.clock = lambda: clock[0]` (`im_client/tests/unit/test_client.py:77`,
  `:317`).

**Bad**
```python
self.http, self.base_url, self.credentials = http, base_url.rstrip("/"), credentials
```
**Good**
```python
self._http = http
self._base_url = base_url.rstrip("/")
self._credentials = credentials
```

---

### 4.2 Delete pass-through wrappers

- **Target:** `python-service-architecture` (`boundaries.md`, "Avoid utility
  gravity"), plus the audit skill checklist
- **Status:** Partial. `CLAUDE.md` rule 9 warns against speculative
  abstraction, but nothing names this concrete shape. · **Priority:** High

**Rule.** Do not add a class or function whose body only forwards its
arguments to another callable with the same meaning. Specifically:
- a "handler" in `bootstrap/` that repeats a service's signature;
- an `application/` function that only calls `store.x(...)`;
- a class that stores N fields only to call a free function taking the same N
  arguments.

The caller should use the target directly. A wrapper earns its place when it
translates types or errors, adds policy, or narrows a wide API.

**Evidence.**
- `orchestrator/bootstrap/queries.py:11-32` (`QueryHandler`) and
  `bootstrap/submissions.py:10-28` repeat every argument.
- `application/retain.py:15` `plan_retention` returns `retention_plan(...)`.
- `application/discover.py:68-90` only forwards to `store.commit_page`.
- `worker/genai/break_analysis/analyzer.py:135`: `BreakAnalysisAnalyzer`
  stores 8 fields to call `analyze(...)`.
- `worker/evidence.py:80`: the `PreparationEvidenceCodec` methods call free
  functions one-to-one.

**Exceptions.** A temporary compatibility shim during a migration, marked as
transitional (the architecture skill already allows this).

---

### 4.3 Name magic values; separate constants from settings

- **Target:** `python-code-conventions`
- **Status:** Partial. The architecture skill covers where constants live, not
  when a literal needs a name. · **Priority:** Medium

**Rule.**
- Give a literal a module-level `UPPER_CASE` name when it appears twice, or
  when its meaning is not obvious from the call site (sizes, timeouts, sentinel
  dates, lease names, jitter bounds).
- If the value could reasonably differ between deployments, or needs tuning
  under load, it is a setting instead.
- Precompile regexes as module constants.

**Evidence.**
- `{429, 500, 502, 503, 504}` appears twice in `im_client/client.py`.
- `32768` appears in `orchestrator/domain/cursors.py:62` and
  `api/schemas/investigations.py:32`.
- Redis clients use `socket_timeout=5, socket_connect_timeout=5` in both
  services' `bootstrap/runtime.py`.
- `"retention"` is used as a lease name 3 times.
- `trace[:16000]` in `application_logging/logging.py:133`.
- Inline `re.search(...)` next to precompiled patterns in the same module.
- `asyncio.sleep(1)` and `uniform(0.8, 1.2)` in worker loops.

**Exceptions.** `0`, `1`, `""`, obvious HTTP status codes written with
`fastapi.status` names, and one-off test data.

---

### 4.4 Module-level logger

- **Target:** `python-logging` (`implementation.md`) · **Status:** Missing · **Priority:** Low

**Rule.** Declare `logger = logging.getLogger(__name__)` once, below the
imports, and log through it. Do not call `logging.getLogger(__name__)` inline
at each log site.

**Evidence.** There are 22 inline `logging.getLogger(__name__).<level>(...)`
calls across `src`, and no module uses a module-level logger.

---

### 4.5 Imports at module top

- **Target:** `python-code-conventions` · **Status:** Missing · **Priority:** Low

**Rule.** Put imports at module top. Use a function-local import only for a
documented cycle, an optional heavy dependency, or import-time cost, and add a
one-line comment saying which.

**Evidence.**
- `im_client/retry.py:81` imports `timedelta` inside a `try`.
- `worker/genai/break_analysis/model.py:6` aliases the port's `AnalysisFailure`
  as `ModelFailure`, which suggests a separate exception type that does not
  exist.
- Several tests import inside test bodies.

---

## 5. Errors and failure handling

### 5.1 One exception base per service or library, carrying a stable `code`

- **Target:** `python-service-architecture` (`boundaries.md`, "Errors and
  constants follow ownership")
- **Status:** Partial. The skill defines *where* errors live, not their
  *shape*. · **Priority:** High

**Rule.**
- Each service and each library defines one base exception. Subclasses carry
  a stable machine-readable `code`, which is a `StrEnum` member or module
  constant.
- Split the base into two branches:
  - **rejection**: caller input or business state; maps to 4xx, or to "do not
    retry";
  - **unavailable**: infrastructure; maps to 5xx/503, or to "retry with
    backoff".
- Never raise built-in `ValueError`, `LookupError` or `RuntimeError` for an
  expected business outcome.
- Never raise a rejection for an infrastructure failure.
- Give each exception a one-line docstring saying when it is raised.

**Why.** The code has good chaining habits but no shared shape:
- some failures are `ValueError` subclasses and some are bare `Exception`;
- codes are passed as message strings;
- built-ins stand in for domain outcomes, so handlers cannot tell a bug from a
  business result.

**Evidence.**
- Good: `ImFailure(code)` with `Deferred`/`DeliveryUnknown` subclasses in
  `im_client/retry.py:11-38`, and `RecoveryRejected(code)`.
- Inconsistent: provider_admission's `QuotaDeferred(Exception)` and
  `ImpossibleReservation(Exception): pass` are raised with no message.
- Orchestrator: `InvalidCursor(ValueError)` versus `QueryFailure(Exception)`.
  The same docstring, "The durable capability could not complete its
  transaction.", is copied 4 times.
- Built-ins as outcomes:
  - `application/queries.py:29` `raise LookupError()`, mapped to 404 in two
    routes;
  - `worker/db/repositories/exchanges.py:38`
    `raise ValueError("Model attempt budget exhausted")`;
  - `orchestrator/adapters/ecs_identity.py:20` raises the domain
    `RecoveryRejected` when an ECS metadata call fails.

**Good**
```python
class OrchestratorError(Exception):
    """Base for failures the orchestrator reports by code."""
    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code)
        self.code = code

class Rejected(OrchestratorError):
    """The request or current business state does not permit the action; do not retry."""

class Unavailable(OrchestratorError):
    """A dependency failed; the action may succeed on retry."""
```

**Exceptions.** Keep this small: two branches plus the few specific subclasses
handlers actually distinguish. Do not build a deep taxonomy for symmetry.

---

### 5.2 Every failure a port can raise has a named handling boundary

- **Target:** `python-service-architecture` (`api-and-workers.md`), and the
  audit checklist
- **Status:** Missing · **Priority:** High

**Rule.** For each exception type declared in `ports/`, the skill requires
one named place that decides its outcome:
- in an API: an app-level `exception_handler`;
- in a worker loop: the loop boundary, which logs once, backs off and
  continues, or deliberately exits with a documented reason.

The audit skill should list "port failure with no handler" as a violation.

**Why.** An unhandled port failure turns into a generic 500 or kills a
supervisor task. Both are hard to see in review, because the exception is
defined and raised correctly.

**Evidence.**
- `QueryFailure` and `SubmissionFailure` (`db/query_transactions.py:33`,
  `db/submission_transactions.py:30`) are never caught, so they become 500s.
- `DiscoveryStoreFailure` is not caught by `discover_page`, which catches only
  `DiscoveryFailure`, so it ends the discovery supervisor.
- `WorkStoreFailure` and `AuditFailure` are never caught in the worker `src`.
  One DB failure inside a `work_loop` or lease heartbeat stops
  `asyncio.wait(FIRST_COMPLETED)` and the whole worker exits.

---

### 5.3 Minimal `try` blocks; no builtin exceptions as internal control flow

- **Target:** `python-code-conventions` · **Status:** Missing · **Priority:** Medium

**Rule.**
- A `try` block contains only the call whose failure the `except` clause is
  meant to handle.
- Validate with explicit checks or a Pydantic model rather than raising
  `ValueError` inside the `try` and catching it a few lines later.
- Never catch `KeyError` or `TypeError` around parsing. They are usually bugs,
  and catching them converts bugs into domain failures.

**Evidence.**
- `im_client/client.py:118-126`: `raise ValueError("Malformed token response")`
  inside a `try` that ends with
  `except (httpx.HTTPError, ValueError, KeyError, TypeError)`.
- The same pattern appears at `queries.py:206-223` and
  `orchestrator/db/repositories/discovery.py:75-80`.
- `worker/application/execution.py:222`: `except ValueError: intent = None`
  turns any `ValueError` into `invalid_comment_mapping`.

---

### 5.4 A swallowed or degraded exception leaves a trace

- **Target:** `python-logging` (`errors-and-security.md`)
- **Status:** Partial. The skill covers terminal records and recovered
  retries, not silent degradation. · **Priority:** Medium

**Rule.** When code catches an exception and continues with a fallback value,
such as `return False` or `count = None`, it must:
- catch the narrowest type;
- emit one `warning` event with the bounded `error.type`, or carry a
  why-comment when logging would be pure noise, for example a probe that runs
  every second.

A bare `except ...: pass` needs a comment saying why ignoring the failure is
correct.

**Evidence.**
- `worker/application/admission/signals.py:66` has `except Exception:` with no
  log.
- `im_client/retry.py:56` has `except ValueError: pass`.
- Good: `im_client/client.py:88-90` swallows `QuotaDeferred` with a
  why-comment and a warning.

---

### 5.5 Re-raise cancellation; keep `raise ... from`

- **Target:** `python-code-conventions` (short statement) · **Status:** Standardize · **Priority:** Low

**Rule.**
- Always translate exceptions with `raise X(...) from error`, or `from None`
  when hiding the cause is intended.
- An `except asyncio.CancelledError` or `except BaseException` block must end
  with a bare `raise`.

**Evidence.** Every one of the 12 translations in libs, and all of those in the
services, already chain with `from`.
`worker/genai/break_analysis/analyzer.py:120` records an audit on cancellation,
then re-raises. Documenting this keeps it that way.

---

## 6. Async, lifecycle, time and FastAPI

### 6.1 Read the clock only at the composition root

- **Target:** `python-service-architecture` (`boundaries.md`, application
  section)
- **Status:** Partial. The skill lists "clock used in business decisions" as a
  port example, and `pytest` says "inject clocks", but nothing says where the
  clock may be read. · **Priority:** High

**Rule.**
- `domain/`, `application/` and `db/` never call `datetime.now()`,
  `time.time()` or `random.*` directly.
- They receive `now: datetime`, or a `Clock = Callable[[], datetime]` for
  code that reads time more than once, plus a random source when needed.
- `bootstrap/` binds the real implementations.
- Monotonic time for deadlines follows the same rule.

**Why.** Deterministic core, from `CLAUDE.md` rule 8. The code is halfway
there, and the inconsistency is what confuses agents.

**Evidence.**
- `datetime.now(UTC)` is called 18 times in the worker `src`, 8 of them in
  `db/transactions.py`.
- `application/reconcile.py:21` correctly accepts
  `clock: Callable[[], datetime]`.
- The orchestrator mixes three styles: `now=lambda: datetime.now(UTC)` in
  discovery, `now=datetime.now(UTC)` in recovery, and direct calls in
  `application/queries.py:54` and `db/repositories/queries.py:182`.
- `im_client` injects `monotonic` but calls `datetime.now(UTC)` directly.

---

### 6.2 One supervision idiom and one stop-aware sleep

- **Target:** `python-service-architecture` (`api-and-workers.md`,
  "Long-running worker") · **Status:** Missing · **Priority:** Medium

**Rule.**
- Supervise long-running loops with `asyncio.TaskGroup`, plus a bounded drain
  on shutdown (`asyncio.timeout(settings.shutdown_seconds)`).
- A loop that must survive infrastructure failures catches the service's
  `Unavailable` branch *inside* the loop (see 5.2), so the TaskGroup is not
  torn down.
- Implement "sleep until the next tick or until stop is requested" once:
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

**Evidence.**
- `worker/bootstrap/supervisor.py:118` uses `create_task` +
  `asyncio.wait(FIRST_COMPLETED)` + manual cancel/gather, while
  `bootstrap/leases.py:27` uses `TaskGroup`.
- The `try: await asyncio.wait_for(stop.wait(), timeout=...) except TimeoutError: pass`
  idiom is repeated 6 times across both services.

**Exceptions.** `asyncio.wait(FIRST_COMPLETED)` is acceptable when a
supervisor must react to the *first* task to finish without cancelling its
siblings. Document the reason in a comment.

---

### 6.3 Remote calls: injected client, deadline, size cap

- **Target:** `python-service-architecture` (`boundaries.md`, adapters)
- **Status:** Standardize · **Priority:** Medium

**Rule.**
- Adapters receive their `httpx.AsyncClient` or Redis client from bootstrap
  and never create or close it.
- Every remote call runs under an explicit deadline (`asyncio.timeout`).
- Responses of unbounded size are streamed with a byte cap.
- Blocking SDK calls go through `asyncio.to_thread`. When cancellation could
  orphan a half-built resource, use `asyncio.shield` with a why-comment.

**Evidence (good).**
- `im_client/client.py`: an injected `http`, `async with asyncio.timeout(remaining)`,
  and single-flight token refresh with an `asyncio.Lock`.
- `orchestrator/adapters/cognito_jwks_verifier.py:97-103` streams the JWKS
  response with a size cap.
- `worker/genai/break_analysis/lazy.py:24`:
  `# Caller cancellation cannot orphan a client being built by a worker thread.`

---

### 6.4 Run independent awaits concurrently when it costs no readability

- **Target:** `python-code-conventions` (async section) · **Status:** Missing · **Priority:** Low

**Rule.** When two awaits are independent and neither's failure changes
whether the other should run, use `asyncio.TaskGroup` (or `gather` for exactly
two simple calls). Keep them sequential when ordering, rate limiting or
partial-failure semantics matter, and say so in a comment.

**Evidence.** `im_client/queries.py:235-236` awaits the HOLD lookup and then
the TRAN lookup, sequentially.

---

### 6.5 FastAPI: typed dependencies instead of `app.state`

- **Target:** `python-service-architecture` (`api-and-workers.md`,
  "FastAPI / HTTP API") · **Status:** Missing · **Priority:** High

**Rule.**
- Routes receive application services through
  `Annotated[QueryService, Depends(get_query_service)]` providers defined in
  `api/dependencies.py`.
- Providers read the runtime container once. Routes never touch
  `request.app.state` and never `cast` it.
- Tests override providers with `app.dependency_overrides`.

**Evidence.**
- There are 7 `request.app.state` reads in routers, for example
  `routers/queries.py:24` `settings = request.app.state.settings`.
- `api/dependencies.py:24` does
  `await cast(TokenVerifier, request.app.state.verifier).verify(...)`.
- Tests patch the state directly: `app.state.verifier = LocalIdentity()`
  (`tests/integration/test_investigation_api.py:41`).

---

### 6.6 FastAPI: response models, status names, parameter constraints, thin routers

- **Target:** `python-service-architecture` (`api-and-workers.md`)
- **Status:** Partial. "Routers must not contain business branching" exists
  but is too abstract to stop limit checks and cursor decoding. · **Priority:** Medium

**Rule.**
- Every route declares a typed `response_model` and returns that model. No
  `dict[str, Any]`, and no `extra="allow"` on response models.
- Status codes use `fastapi.status` names.
- Validate query and path parameters with `Query(gt=0, le=...)` and
  `Annotated` constraints, not `if` statements.
- Configured limits, cursor decoding and continuation-compatibility checks are
  application policy. The route passes raw input to one application call.
- Keep domain types out of `api/schemas`. Do not re-export them with
  `import X as X`.

**Evidence.**
- `routers/queries.py:24-30` has
  `if page_size > settings.max_page_size: raise HTTPException(422, "page_size_limit")`.
- `routers/submissions.py:35-46` decodes the continuation cursor inside the
  route.
- `/status` and the poll route return `dict[str, Any]`.
- `ReportsResponse` has `extra="allow"`.
- `api/schemas/investigations.py:7-13` re-exports domain models as schemas.

---

## 7. Database, repositories and migrations (`python-sqlmodel-alembic`)

### 7.1 Fix the engine and repository examples

- **Target:** `python-sqlmodel-alembic` (`engine-and-session.md`,
  `repositories-and-queries.md`, `models-and-base.md`)
- **Status:** Rewrite · **Priority:** High

1. **Remove the module-level engine.** `engine-and-session.md:20` has
   `engine = build_engine(settings.database_url)`, and `session.py` imports
   it. This contradicts the architecture skill ("Do not import global settings
   or construct ... runtime handles at module import time") and the
   repository's actual design, where `postgres_runtime.build_engine(...)` is
   called from bootstrap. Show `build_engine(url, *, pool_size, ...)` called
   in `bootstrap/runtime.py` and disposed in the runtime context.
2. **Type the repository examples.** `self.session = session` and
   `async def get_monthly_report(self, month_start, month_end):` have no return
   type. Use `self._session` and a typed result, so agents do not copy
   untyped, public-attribute code into a `mypy --strict` repository.
3. **Stop teaching a type that lies about nullability.** `TableBase` declares
   `created_at: datetime | None = Field(default=None, sa_column=Column(..., nullable=False, server_default=func.now()))`
   (`models-and-base.md:45`), and the repository copied it into all 6 models.
   Explain the trade-off: the value is `None` only before flush. Either keep
   the type and document why, or use a non-optional type with
   `sa_column_kwargs`/`init=False`. Callers must not have to write
   `assert row.created_at is not None` (`db/repositories/discovery.py:69`).

---

### 7.2 One transaction-scope helper per service

- **Target:** `python-sqlmodel-alembic` (`engine-and-session.md`, session
  section) · **Status:** Missing · **Priority:** High

**Rule.** Open a unit of work and translate driver failures in one helper, and
make every store method use it. Do not repeat
`try / async with sessions.begin() / except SQLAlchemyError / raise XFailure(...) from error`
in each method. Repositories take a session and never commit. The
transaction owner decides the commit.

**Good**
```python
@asynccontextmanager
async def unit_of_work(
    sessions: async_sessionmaker[AsyncSession], *, failure: Callable[[], Exception]
) -> AsyncIterator[AsyncSession]:
    try:
        async with sessions.begin() as session:
            yield session
    except SQLAlchemyError as error:
        raise failure() from error


async def claim(self, *, limit: int, now: datetime) -> list[OwnedWork]:
    async with unit_of_work(self._sessions, failure=self._unavailable) as session:
        return await WorkRepository(session).claim(limit=limit, now=now)
```

**Evidence.**
- `worker/db/transactions.py` has 9 methods with the identical `try/begin/except`
  shape, and `db/exchange_audit.py` has 3 more.
- The orchestrator has 5 `*_transactions.py` modules with the same shape.
- Since this is repeated across two services, the helper belongs in
  `libs/postgres_runtime` (see 8.3).

---

### 7.3 Observe, decide, persist: document the repository–domain split

- **Target:** `python-sqlmodel-alembic` (`repositories-and-queries.md`) and
  `python-service-architecture` · **Status:** Standardize, with one correction · **Priority:** Medium

**Rule.**
- A repository method that implements a state transition:
  1. reads and locks the rows it needs;
  2. maps them to a typed *observation*, a frozen keyword-only dataclass;
  3. passes the observation to a pure domain decision function;
  4. writes the returned *decision*.
- Repositories do not choose statuses, error codes or messages.
- Pass the decision function as a parameter typed with a `Callable` alias.
  Add a `Protocol` only when the callable needs more than its signature to be
  understood, or when several implementations exist.

**Why.** This is the codebase's best design idea: domain decisions can be unit
tested without a database. But the current shape adds one callable
`Protocol` per policy with exactly one implementation, threaded through three
layers.

**Evidence.**
- Good:
  - `worker/ports/work_store.py:19` `WorkerRecoveryDecider`;
  - `domain/reconciliation.py:42` puts decision invariants in `__post_init__`;
  - `orchestrator/application/retain.py:22` has
    `store.sweep(token, now=now, plan=plan, expire=expire_active, purge=purge_eligible)`.
- Heavy: `orchestrator/ports/discovery.py:48-57` defines
  `class ClaimPolicy(Protocol): def __call__(self, observation: ClaimObservation) -> ClaimDecision: ...`,
  and the same for `AdmissionPolicy` and `CompletionPolicy`.
- Violations: `orchestrator/db/repositories/queries.py:74-101` derives
  `failed_key` from error codes and reads untyped
  `row.selection.get("record_keys")`.

---

### 7.4 Queue-like tables: claim, lease and fence

- **Target:** `python-sqlmodel-alembic` (new section in
  `repositories-and-queries.md`) · **Status:** Standardize · **Priority:** Medium

**Rule.** When a table is used as a work queue, document this pattern as the
reference:
- claim with `with_for_update(skip_locked=True)` and a bounded `LIMIT`;
- write a fresh `lease_token` and `lease_expires_at`;
- start every later write from a *fenced* read, `WHERE id = ... AND lease_token = ... AND lease_expires_at > now FOR UPDATE`,
  and treat "no row" as lost ownership;
- take a transaction-scoped advisory lock when uniqueness is logical rather
  than enforced by an index;
- keep the SQL predicate for "eligible work" in one shared module used by both
  claiming and demand counting.

**Evidence.**
- `worker/db/repositories/work.py:98` (`SKIP LOCKED`), `:106` (advisory lock),
  `:190` (fenced `owned_row`).
- `worker/db/work_predicates.py` is shared by claim and demand.
- The orchestrator does the same in `db/repositories/discovery.py:64`.

---

### 7.5 Generate status predicates from the enum, never by string concatenation

- **Target:** `python-sqlmodel-alembic` (`models-and-base.md`)
- **Status:** Missing · **Priority:** Medium

**Rule.**
- Build CHECK constraints and partial-index predicates from the owning
  `StrEnum`, using `column.in_(...)` or a helper that renders bound literals.
- Keep long SQL predicates wrapped at the line limit.
- Never build SQL by joining string fragments, even from constants, because
  the pattern gets copied onto user input.

**Evidence.**
- `platform_db/models/api_requests.py:18-20` and `investigations.py:21-23` use
  `text("status IN (" + ",".join(f"'{status}'" ...) + ")")`.
- `investigations.py:31` and `:43` are single-line CHECK strings listing the
  states again.

---

### 7.6 Repositories do not construct other repositories; one codec per persisted JSON shape

- **Target:** `python-sqlmodel-alembic` (`repositories-and-queries.md`)
- **Status:** Missing · **Priority:** Medium

**Rule.**
- Put a query that several repositories need, such as a fenced ownership read,
  in a shared module-level query function that takes a session. Do not
  instantiate a sibling repository inside a repository method.
- Each persisted JSON sub-document and each external wire format has one
  encode/decode function pair, reused by adapters and repositories.

**Evidence.**
- `worker/db/repositories/exchanges.py:34` and `preparation.py:19` call
  `WorkRepository(self.session).owned_row(...)`.
- The `delivery_ambiguity` dict is built in 3 places (`work.py:141`, `:357`,
  `reconciliation.py:24`).
- IM record parsing is duplicated between `adapters/im_records.py:53` and
  `db/preparation_codec.py:72`.
- The IM comment payload is built in two places.

---

### 7.7 Batch per page: no per-row query loops, no quadratic scans

- **Target:** `python-sqlmodel-alembic` (`repositories-and-queries.md`; the
  current N+1 guidance covers relationships only)
- **Status:** Partial · **Priority:** Medium

**Rule.**
- When processing a page of N items, issue a bounded number of queries per
  page, not per item. Load lookups with `IN (...)` into a dict, then loop in
  memory.
- Build counters or indexes once, not inside the loop.
- Keep one query style per repository (`session.exec` for ORM selects,
  `session.execute` for `text()`), and use `col()` consistently.

**Evidence.**
- `orchestrator/db/repositories/discovery.py:181-187` loops over up to 500
  rows, and `_insert_or_attach` issues 2–5 queries each.
- `db/repositories/queries.py:168`:
  `sum(row.record_key == value for row in rows) > 1` runs for every value.

---

### 7.8 Migrations: document the good practices the repository already follows

- **Target:** `python-sqlmodel-alembic` (`alembic-migrations.md`)
- **Status:** Standardize, adding to existing material · **Priority:** Medium

Add these rules, each backed by code that already works:

1. **Serialize migration runs.** The runner takes a named
   `pg_advisory_lock` with a bounded `lock_timeout`, and a test proves two
   runners cannot overlap (`platform_migrations/alembic/env.py:29-37`,
   `tests/integration/test_migration_lock.py:34`).
2. **The runner exposes `upgrade`, `check` and `sql`** (`main.py:18`), with
   `compare_type` and `compare_server_default` on.
3. **Check the data before tightening constraints.** Before adding a unique or
   check constraint over existing rows, query for violations and fail with up
   to N example keys and an operator instruction
   (`versions/0004_active_request_fingerprint.py:21-48`).
4. **Every `downgrade()` either reverses the change or raises** with an
   operator-facing reason, and refuses when data would be lost (`0002:123`,
   `0005:47`). This extends the skill's baseline-only guidance to every
   revision.
5. **A backfill `server_default` is dropped after the backfill**, unless the
   model declares the same default permanently (`0003:24-44`).
6. **Migrations never import live model constants.** They inline a frozen
   copy of every predicate or state list (`0002:19`).

---

### 7.9 Migrations: fix naming drift, template style, and revision pinning

- **Target:** `python-sqlmodel-alembic` · **Status:** Partial · **Priority:** Medium

**Rule.**
- Let the metadata naming convention name every PK, FK, UQ, CK and IX, and
  use `op.f()` in revisions. Hand-name an object only when the convention
  cannot express it, and follow the same pattern when you do.
- Update `script.py.mako` to the house style: PEP 604 unions,
  `collections.abc.Sequence`, typed `revision`/`down_revision`.
- Use one SQLAlchemy type per concept: `sa.Uuid()` vs
  `postgresql.UUID(as_uuid=True)`, `sa.func.now()` vs `sa.text("now()")`.
- Add a DB-free unit test asserting the code's schema-revision constant equals
  `ScriptDirectory.get_current_head()`. Tests reference that constant, never a
  literal revision id.

**Evidence.**
- Hand-named `uq_request_client_idempotency`, `ix_request_schedule` and
  `uq_investigation_record_owner` sit next to `op.f("pk_api_requests")`.
- `0005` has no typed header, and the mako template still emits
  `Union[...]`.
- Tests hard-code `"0005_source_record_type"`, while `SCHEMA_REVISION` is
  exported by `platform_db`.

---

## 8. Architecture skill content: what to cut, soften or add

### 8.1 Reduce repetition in `python-service-architecture`

- **Target:** `python-service-architecture` · **Status:** Rewrite · **Priority:** Medium

**Problem.** "Flat-first" growth is explained in full in `SKILL.md` (invariant
5), `boundaries.md` (twice), `ai.md`, `shared-libraries.md`, `testing.md` and
`api-and-workers.md`. "No root `messaging/`" appears 4 times. Adapter
provider-subpackage promotion is explained 3 times. Across 1,800 lines, an
agent spends most of its reading budget on placement and none on how to write
the code inside a module.

**Proposal.** State each placement rule once, in `boundaries.md`, and link to
it from the other files. Use the saved space for the code-level API and worker
rules in sections 6.2, 6.5 and 6.6.

---

### 8.2 Soften mandatory GenAI file splits

- **Target:** `python-service-architecture` (`ai.md`, `SKILL.md` invariant 4)
- **Status:** Rewrite · **Priority:** Medium

**Problem.** The current rules include:
- "Every GenAI task has `llm.py`";
- "Every application-facing GenAI capability keeps its port implementation
  separate; do not collapse these responsibilities merely to reduce `.py`
  count".

Together they push agents toward a fixed file set, even when one module would
do.

**Evidence.** `worker/genai/break_analysis/` has 9 modules:
- `analyzer.py` stores 8 fields to call a free function (see 4.2);
- `model.py` exists to alias the port exception;
- `lazy.py` and `bedrock.py` each wrap the model client.

**Proposal.**
- Keep `genai/` as the mandatory root, and keep "no module-global model
  handle, no settings imported at import time".
- Replace the fixed file list with the responsibilities that must stay
  *separable*: construction, prompt and version, output schema,
  invocation/translation.
- Say they may share a module until one grows independent weight, in line
  with the flat-first rule the skill already states.

---

### 8.3 Shared plumbing: name what should be extracted

- **Target:** `python-service-architecture` (`shared-libraries.md`), and the
  audit's shared-capability review · **Status:** Partial · **Priority:** Medium

**Rule.** Add concrete signals. Code repeated across two or more services
whose meaning, lifecycle and dependencies match is a library candidate. These
are the examples in this repository:
- the YAML settings source and discovery (see 3.10.6);
- the unit-of-work helper (see 7.2);
- the stop-aware sleep (see 6.2).

Keep the counter-rule: similar code with different semantics stays local.

**Evidence.** `orchestrator/config/sources.py` and `worker/config/sources.py`
are near-identical. `*_transactions.py` in the orchestrator and
`db/transactions.py` in the worker share the same shape.

---

### 8.4 Ports expose operations, and a port type must change something

- **Target:** `python-service-architecture` (`boundaries.md`, "When a port
  earns its cost") · **Status:** Partial · **Priority:** Low

**Rule.**
- A `Protocol` declares methods, not collaborator attributes such as
  `store: WorkStore` or `policy: ExecutionPolicy`.
- A port-owned value type that mirrors a library type one-for-one is not
  isolation. Re-export or alias the library type, or state in the port's
  docstring what the redefinition protects against.
- Every module belongs to a layer or capability package. No top-level
  miscellaneous module sits outside the layers.

**Evidence.**
- `worker/application/scheduler.py:15`: `WorkActions(Protocol)` exposes
  `store` and `policy`, and the scheduler reaches into
  `executor.policy.batch.max_records`.
- `worker/ports/cooldown.py` redefines `Active`/`Inactive`/`Unavailable`,
  identical to `provider_admission`'s.
- `worker/evidence.py` sits at the package root and is imported by 3 layers.

---

### 8.5 Library public API: export every type in a public signature

- **Target:** `python-service-architecture` (`shared-libraries.md`, "Public
  API and compatibility") · **Status:** Partial · **Priority:** Low

**Rule.**
- Every type that appears in a public signature is in `__init__.__all__`.
- Choose one export point per package, and do not re-export the same names
  from both the package and a subpackage.
- Keep `__all__` sorted.
- Consumers and tests import from the package root.
- Guard the library-independence rule with an import-boundary contract test.

**Evidence.**
- `provider_admission.CooldownState` is returned publicly but not exported.
- Tests import `im_client.queries.SourceQueries` and `parse_page` directly.
- `platform_db/__init__.py` and `platform_db/models/__init__.py` both
  re-export the same models.
- Good: `libs/postgres_runtime/tests/contract/test_runtime.py:30-41` walks the
  AST to forbid service, `os` and `pydantic_settings` imports.

---

### 8.6 Fix dead skill references

- **Target:** `python-service-architecture`,
  `python-service-architecture-audit`, `python-repository-setup`
- **Status:** Remove/Rewrite · **Priority:** High (cheap, and it misleads agents)

These skills refer to skills that are not installed:
- `otel-observability`, in `python-service-architecture/SKILL.md:172`,
  `boundaries.md:221`, `shared-libraries.md:119`, and the audit skill line 112
  (`otel-observability/references/setup/shared_library.md`);
- `observability`, in `python-repository-setup/SKILL.md:126` and `:609`;
- `split-repo-app-releases`, in `python-repository-setup/SKILL.md:602`.

The observability references should point at `python-logging`, since this
repository's shared library is `application_logging`. Otherwise, remove them.

---

## 9. Tooling (`python-repository-setup`)

### 9.1 Encode `CLAUDE.md` in Ruff

- **Target:** `python-repository-setup` (root `pyproject.toml` template)
- **Status:** Rewrite. The current `select` is minimal. · **Priority:** High

**Rule.** Replace
`select = ["E4", "E7", "E9", "F", "I", "UP", "B", "TID252"]` with a set that
enforces the written conventions. Explain each addition next to it:

```toml
[tool.ruff.lint]
select = [
  "E4", "E7", "E9", "F", "I", "UP", "B", "TID252",
  "C90",   # CLAUDE.md: cyclomatic complexity <= 10
  "S101",  # no assert in production code (see 2.4)
  "BLE",   # no blind `except Exception`
  "ASYNC", # blocking calls and timeout misuse in async code
  "DTZ",   # naive datetimes
  "PT",    # pytest style: raises(match=), parametrize tuples, fixtures
  "RUF",   # mutable class defaults, unused noqa, ambiguous characters
  "C4", "PIE", "SIM",  # simple readability fixes; drop SIM if it proves noisy
]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.per-file-ignores]
"**/tests/**" = ["S101"]
```

**Why.** `CLAUDE.md` asks for complexity ≤ 10 and explicit failure handling.
The repository has 11 production `assert`s and functions of 90–105 lines
(`worker/db/repositories/work.py:70` `claim`, `bootstrap/supervisor.py:31`
`run`) that a complexity gate would have flagged. Rules that are not
enforced drift.

**Exceptions.** Introduce this with a baseline: fix the code or add a
per-line `noqa` with a reason. Do not weaken the thresholds to pass. Check
`BLE` against the one intentional broad catch that re-raises
(`except BaseException: ...; raise`), which Ruff allows.

---

### 9.2 Declare every direct import; derive coverage from the members

- **Target:** `python-repository-setup` · **Status:** Partial · **Priority:** Medium

**Rule.**
- Every package imported directly is declared by the member that imports it,
  or by the root dev group for root `tests/`.
- A transitive install is not a declaration.
- Add untyped third-party imports to a mypy override once, rather than
  scattering `# type: ignore[import-untyped]`.
- Coverage `source` lists every workspace import package.

**Evidence.**
- `dotenv` is imported in 5 files but `python-dotenv` is declared nowhere.
- The orchestrator imports `starlette` while declaring only `fastapi`.
- There are 6 `# type: ignore[import-untyped]` for `asyncpg`.
- The coverage `source` omits `platform_migrations`, `postgres_runtime`,
  `provider_admission` and `policy_config`.

---

### 9.3 Clean the template asset

- **Target:** `python-repository-setup` · **Status:** Remove · **Priority:** Low

`assets/workspace-template/.ruff_cache/` is committed inside the skill asset.
Delete it, and exclude caches from the asset.

---

## 10. Testing (`pytest` and `python-service-architecture/references/testing.md`)

### 10.1 Remove the overlap between the two testing skills

- **Target:** `pytest` and `python-service-architecture` · **Status:** Rewrite · **Priority:** High

**Problem.** Both skills define:
- execution profiles (unit/contract/integration/e2e/live);
- marker policy;
- fixture ownership, and "never import conftest";
- "fail rather than silently skip".

They word these differently. `pytest` also repeats its fixture and async rules
between `SKILL.md` and `core-principles.md`.

**Proposal.**
- `python-service-architecture/references/testing.md` owns **placement**:
  directory tree, profile classification, where fixtures and support modules
  live.
- `pytest` owns **how to write the test**: oracles, doubles, fixtures'
  internals, async mechanics, flakiness.
- Each links to the other instead of restating it.

---

### 10.2 Choose one async test style: native `async def` tests via the anyio plugin

- **Target:** `pytest` (`core-principles.md`, "Async discipline")
- **Status:** Partial. The skill says "pick one owner" but does not recommend
  one, and the repository ended up with a workaround. · **Priority:** High

**Rule.** Write async tests as `async def test_...` with async fixtures. In
this repository, use the anyio pytest plugin with
`anyio_backend = "asyncio"`:
- it is already installed transitively (anyio 4.15.1 registers the
  `pytest11` entry point);
- it only needs to be declared in the root dev group.

Do not wrap test bodies in a nested `async def run()` plus `asyncio.run(run())`.

**Why.** The workaround adds an indentation level and splits assertions
between inside and outside `run()`. Most importantly, it rules out async
fixtures, which is why setup is copied into every test (see 10.3).

**Evidence.** 161 `asyncio.run` calls in 72 of 104 test files, 0
`pytest.mark.asyncio`/`anyio`, and only 4 `@pytest.fixture` definitions in the
whole repository.

**Bad**
```python
def test_x() -> None:
    async def run() -> None:
        engine = create_async_engine(url)
        try: ...
        finally:
            await engine.dispose()
    asyncio.run(run())
```
**Good**
```python
async def test_x(engine: AsyncEngine) -> None:
    ...
```

**Exceptions.** Tests that deliberately start a fresh event loop, such as
process-level e2e tests of `main()`, may call `asyncio.run` directly.

---

### 10.3 Shared integration fixtures and one disposable-database guard

- **Target:** `pytest` (`integration-boundaries.md`) and
  `python-service-architecture/references/testing.md` (fixture placement)
- **Status:** Partial · **Priority:** High

**Rule.**
- Each service's `tests/integration/conftest.py` provides fixtures for the
  database URL, engine, session factory and Redis client. Tests never read
  `os.environ` directly.
- One guard in the root `conftest.py` applies to every integration and e2e
  profile. It refuses non-loopback hosts and database names without the
  `test_` prefix.
- The testing docs use a URL that passes the guard.
- Migration tests get one throwaway-database fixture and one subprocess helper
  with a timeout.

**Evidence.**
- The `INTEGRATION_DATABASE_URL` read-and-`pytest.fail` preamble is repeated
  69 times.
- `test_work_eligibility.py:69` uses `os.environ[...]` and gets a `KeyError`
  instead of the helpful message.
- The guard exists only in `services/worker/tests/conftest.py:9-22`, and
  `docs/guides/testing.md:52` documents a URL that fails it.
- `CREATE/DROP DATABASE` appears in 5 migration test files.
- `process.communicate()` has no timeout in `test_migration_lock.py:30`.

---

### 10.4 Keyword test-data builders; subjects built through real constructors

- **Target:** `pytest` (`core-principles.md`, "Use doubles deliberately" and
  "Fixtures reveal ownership and cost") · **Status:** Partial · **Priority:** Medium

**Rule.**
- Provide one builder per important domain type, for example
  `def owned_work(**overrides: Unpack[OwnedWorkFields]) -> OwnedWork`, in a
  support module beside its consumers. It constructs by keyword with sensible
  defaults.
- Build the subject under test through its public constructor.
- Forbid `object.__new__(Subject)`, `SimpleNamespace` stand-ins for typed
  collaborators, spec-less `AsyncMock()`, and `# type: ignore` used to force a
  double to fit. These hide exactly the contract drift that typed fakes catch.

**Evidence.**
- `OwnedWork(` is built positionally in 8 worker test files, and
  `ExecutionPolicy(...)` with 13 positional values.
- `worker/tests/unit/test_retry_deferral.py:30-34` has
  `subject = object.__new__(WorkExecutor)` and
  `subject.policy = SimpleNamespace(...)  # type: ignore[assignment]`.
- `RecoveryRequest(**values)  # type: ignore[arg-type]` appears twice.

---

### 10.5 Prefer recording fakes to call-argument archaeology

- **Target:** `pytest` (`core-principles.md`)
- **Status:** Partial. The skill says "Assert calls only when the interaction
  itself is a contract", but gives no example of the alternative. · **Priority:** Medium

**Rule.**
- When the effect under test is "the store received decision X", use a small
  typed fake that records decisions, and assert on
  `fake.decisions == [...]`.
- Avoid assertions like
  `mock.await_args_list[1].kwargs["decision"].state == "completed"`.
- Do not call private members (`Repository._candidate`) or read private
  attributes (`engine.pool._max_overflow`) unless the test is an explicit
  white-box contract, and its name or docstring says so.

**Evidence.**
- There are 36 `call_args`/`await_args` digs in 11 files, for example
  `worker/tests/unit/test_delivery_reconciliation.py:160`.
- `DiscoveryRepository._candidate(` is called 4 times in a contract test.
- `libs/postgres_runtime/tests/contract/test_runtime.py:20-22` reads private
  pool attributes.

---

### 10.6 Fix the async-stack mismatch in `pytest` examples

- **Target:** `pytest` (`examples-integration.md`) · **Status:** Rewrite · **Priority:** Medium

The only integration example uses a sync `sqlalchemy.orm.Session`, while
`python-sqlmodel-alembic` forbids sync sessions. Add the async equivalent:

- an `AsyncConnection` with an outer transaction;
- `AsyncSession(bind=connection, join_transaction_mode="create_savepoint")`;
- teardown by rollback.

Keep the existing caveat that this does not isolate second connections or
workers. That caveat is why this repository uses unique IDs or per-test
databases for worker tests.

---

### 10.7 Small test-style rules worth making explicit

- **Target:** `pytest` (`core-principles.md`) · **Status:** Missing · **Priority:** Low

- `pytest.raises` includes `match=`, or asserts on the exception's `code`
  attribute. Only 34 of 99 uses do today.
- Use `pytest.param(..., id="...")` for non-trivial cases, and never branch on
  a parameter inside the test body (`if confirmed: ... else: with pytest.raises`).
  Split success and failure into separate tests.
- Unit tests do not sleep in real time (`asyncio.sleep(1)` appears in a unit
  test at `worker/tests/unit/test_delivery_reconciliation.py:171`). Inject the
  sleep, or use an `Event`.
- Put scripts with a `main()` (evaluation, local runtime) outside `tests/`, or
  under a directory excluded from collection.

---

## 11. Good patterns to standardize (currently undocumented)

These practices are in the code and working, but no skill describes them. An
agent writing a new service would not reproduce them. Each gets a short
paragraph and one example in the target skill.

| Pattern | Evidence | Target skill | Priority |
|---|---|---|---|
| Frozen decision objects whose invariants live in `__post_init__`; the domain returns decisions and persistence applies them | `worker/domain/reconciliation.py:42`, `domain/admission.py:127` `decide(...)` | `python-code-conventions` + architecture (see 7.3) | High |
| Keyword-only public signatures (`def __init__(self, *, http, base_url, ...)`) | about 10 lib signatures, most orchestrator functions | `python-code-conventions` | Medium |
| Union-of-results for expected failure instead of exceptions (`Active \| Inactive \| Unavailable`, fail-open) | `provider_admission/cooldown_signal.py:30-44` | `python-code-conventions` | Medium |
| Architecture fitness tests with a shared AST inspector that has its own sensitivity tests | `tests/contract/architecture.py`, `test_architecture_inspection.py:25`, per-service `test_dependencies_point_inward` | `python-service-architecture-audit` (a persistent version of the script) | Medium |
| `.env.example` ↔ `Settings` contract test | `orchestrator/tests/contract/test_environment_contract.py` | `python-settings-config` (already recommended; cite as the reference implementation) | Low |
| Library independence contract test (no `os`, `pydantic_settings` or service imports) | `libs/postgres_runtime/tests/contract/test_runtime.py:30-41`, `policy_config` canary env var | `python-service-architecture` (`shared-libraries.md`) | Medium |
| GenAI: versioned prompt constant, data sent as a separate untrusted user message, `strict=True, extra="forbid"` output schema with a semantic `model_validator`, SDK retries disabled so one call is one audited attempt, per-record partial salvage | `worker/genai/break_analysis/prompt.py:6`, `schema.py:14`, `llm.py:37` | `python-service-architecture` (`ai.md`) | High |
| Canary-based security tests ("the secret never appears in logs") | `application_logging/tests/.../test_logging.py:15-25` | `python-logging` (`testing-and-verification.md` mentions canaries; add the concrete test) | Low |
| Allow-listed log fields plus a formatter that validates the event-name pattern | `application_logging/logging.py:18-40` | `python-logging` (`implementation.md`) | Medium |
| Transport-level fakes for HTTP (`httpx.MockTransport`) and `create_autospec(Port, instance=True)` instead of `patch` (0 `patch(` in the repository) | `im_client/tests/unit/test_client.py`, 63 `create_autospec` | `pytest` (`core-principles.md`) | Medium |
| Markers derived from test directory in root `conftest.py`, `--strict-markers --import-mode=importlib` | `conftest.py:6-10` | `python-service-architecture/references/testing.md` | Low |
| Comment density: one-line intent docstring per module, why-comments only, no banners | pervasive; for example `im_client/queries.py:109-113` | `python-code-conventions` (see A.9) | Medium |

---

## 12. Recommendations considered and rejected

These came up in the review but are deliberately **not** proposed:

- **A column-factory helper for repeated SQLModel columns.**
  `Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))`
  appears about 15 times. The repetition is visible and grep-able, whereas a
  factory hides the column definition that Alembic autogenerate and reviewers
  need to see. Revisit only if column policy starts to change, such as a new
  precision.
- **Mandating `asyncio.gather` for every pair of independent awaits.** Rule
  6.4 limits this to cases with no rate-limit or partial-failure interaction.
- **Generating `.env.example` from the settings model.** Hand-written files
  checked by a contract test give better comments. The test should also check
  that comments are not just the field name restated.
- **Lowering the 300-line module review signal.** Every large module found,
  such as `work.py` at 384 lines, has a responsibility-based reason to split.
  The line count is not the reason.

---

## Appendix A: Proposed outline for `python-code-conventions`

```text
---
name: python-code-conventions
description: Language-level conventions for Python source in services/ and libs/:
  data containers, typing of closed value sets, constructors, constants, errors,
  async idioms, comments. Use for any Python edit or review; architecture, settings,
  persistence, logging and testing specifics live in their own skills.
---
1. Scope and relationship to CLAUDE.md
   (cite its principles, add mechanics only)
2. Data containers
   - frozen dataclass for internal values; Pydantic at trust boundaries;
     TypedDict only for untyped JSON you don't own (2.1, 2.5, 3.8)
   - kw_only for >3 fields; keyword construction
3. Closed value sets: StrEnum vs Literal, defined once, named subsets (2.2)
4. Typing: JsonValue vs Any, `type` aliases, Callable alias vs Protocol,
   assert_never (2.3, 2.6, 7.3)
5. Constructors and attributes: one per line, names match,
   private collaborators (4.1)
6. Pydantic: Field only when informative, keyword construction,
   Annotated reusable constraints, no mutation in validators (3.1, 3.8, 3.9)
7. Errors: base + code + rejection/unavailable, minimal try, from-chaining,
   CancelledError re-raise, no assert / __setattr__ / getattr probing
   (2.4, 5.1, 5.3, 5.5)
8. Constants and magic values (4.3)
9. Async idioms: TaskGroup, wait_or_stop, deadlines, to_thread, shield (6.2–6.4)
10. Time: never read the clock outside bootstrap (6.1)
11. Imports and module-level logger (4.4, 4.5)
12. Comments and docstrings (below)
13. Review checklist (one line per rule, for agents to self-check)
```

**A.9 Comments and docstrings, as a proposed rule (Medium).**
- Every module starts with a one-line docstring stating its purpose.
- Public classes and exceptions have a one-line contract docstring. For
  exceptions, say when they are raised.
- Decision functions whose rules are not obvious from the code (for example
  admission and claim decision tables) document the rule, not the mechanics.
- Comments explain *why*, including evidence such as incident or probe
  results.
- No banners, and no commented-out code.

The evidence shows the codebase mostly does this already (for example
`im_client/queries.py:109-113` "Broad-date string recordKey queries timed out in
DDD probes…"). The gaps are public classes in libs (about 12 without
docstrings), 4 orchestrator `*_transactions.py` modules, and the worker's
`ports/*.py`, where the meaning of `transition(...) -> bool` is undocumented.
