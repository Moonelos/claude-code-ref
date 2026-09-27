# Skill Improvement Recommendations from the `libs/` and `services/` Review

Date: 2026-09-27

**Scope.**
- Code reviewed: all source and test code under `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services`. That is about 17k source lines across 177 files, plus about 19k test lines.
- Skills reviewed:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/otel-observability`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/pytest`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-repository-setup`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture-audit`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-sqlmodel-alembic`
  - the repository `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/CLAUDE.md`
- I did not read the existing `SKILL_GUIDELINE_RECOMMENDATIONS.md`.

**Method.**
- I read the skills in full, or at least the references that apply to this codebase.
- The source code was reviewed along six dimensions:
  - settings/Pydantic
  - persistence
  - observability
  - architecture/DI/errors
  - tests
  - general Python
- Measurements:
  - ruff with an extended rule set, run in isolation through `uvx`
  - AST scans for function length and assertions inside test doubles
  - grep counts
  - the hermetic test suite: 894 passed in 11.65 s
- I rechecked the most consequential claims by hand, including the `set_status_on_exception` contradiction, `PositiveFloat` accepting `inf`, the swallowed claim error, and the minimal ruff baseline.
- No repository files were changed except this one.

**How to read this document.**
- Recommendations are grouped by engineering theme, not by skill. Each one names its **target skill** and reference file.
- Evidence paths are absolute. Line numbers refer to the tree as of commit `2a3e8ff`.
- The code examples illustrate *reusable rules*. They are not a defect list to fix. The few concrete bugs found along the way are collected in [Appendix B](#appendix-b--incidental-defects-found-not-skill-work) so they are not lost.
- Section 12 is a per-skill critique: what to rewrite, merge, or delete.

---

## 0. Summary of the highest-value changes

| # | Change | Target skill | Priority |
|---|---|---|---|
| 1 | Replace "`description=` on every field" with the **meaningful-`Field(...)`** rule (§2.1) | python-settings-config | High |
| 2 | Resolve the **`set_status_on_exception` contradiction**. It already produced spans that are never marked as errors (§9.1) | otel-observability | High |
| 3 | Make telemetry **testable without monkeypatching**: global in-memory providers in `conftest.py`, and no fixtures that contradict module-level instruments (§9.2, §10.4) | otel-observability, pytest | High |
| 4 | Add **transaction ownership / Unit of Work**, a **DB failure contract**, and **per-transaction limits** (§8.1–8.3) | python-sqlmodel-alembic | High |
| 5 | **No shadow defaults**: a value owned by YAML or env must not reappear as a Python default further down the call chain (§4.1) | python-settings-config, python-service-architecture | High |
| 6 | **Constructor contracts**: no `X \| None = None` collaborators, legacy branches or magic-number defaults that exist only for tests (§5.4) | python-service-architecture | High |
| 7 | **Retry-classification base for port errors** instead of hand-maintained exception tuples and `getattr(exc, ...)` (§3.1) | python-service-architecture (+ audit) | High |
| 8 | **Lint and type baseline that actually enforces CLAUDE.md**: C90/PLR09/BLE/S101/ASYNC…, the `pydantic.mypy` plugin, and a stubs policy (§1.2, §6.1) | python-repository-setup | High |
| 9 | **Bounded waits in async tests**, **transactional UoW fakes**, and **no assertions inside doubles** (§10.1–10.3) | pytest | High |
| 10 | Add a small **`code-conventions.md`** reference to own function-level Python rules that currently have no home (§1.1) | python-service-architecture | Medium |

---

## 1. Where rules live, and how they are enforced

### 1.1 Add a function-level code-conventions reference instead of a new skill

- **Target skill:** python-service-architecture. Add a new file, `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/code-conventions.md`. Route it from `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/SKILL.md:48-75` as "Read when writing or reviewing function-level code".
- **Proposed rule:** this reference owns the cross-cutting code-level rules in this document. That means §3 (errors), §4 (constants/vocabularies), §5.4–5.6 (constructor contracts, flags, wrappers), §6 (typing), §7 (async/resources) and §5.8 (post-removal cleanup). Keep it short, one rule per bullet, each with a bad/good pair.
- **Why:** today no skill owns these rules:
  - `CLAUDE.md` is principle-level and repo-local.
  - python-service-architecture is structural.
  - python-repository-setup is tooling.

  So recurring issues fall between them: typing escapes, stringly-typed outcomes, cancellation handling, test-only parameters, leftovers after a feature is removed.
- **Evidence:** every section below. Many findings map to no existing skill text.
- **Exceptions:** a separate `python-code-style` skill is justified only if these rules must apply to code that never loads python-service-architecture, such as standalone scripts or Lambdas.
- **Priority:** Medium.

### 1.2 Make the lint baseline enforce what CLAUDE.md claims

- **Target skill:** python-repository-setup. Change:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-repository-setup/SKILL.md:287-291`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-repository-setup/references/pre-commit.md:108-113`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-repository-setup/assets/workspace-template/pyproject.toml:23-27`
- **Proposed rule:**
  ```toml
  [tool.ruff.lint]
  select = ["E4","E7","E9","F","I","UP","B","TID252",
            "C90","PLR0912","PLR0915","ASYNC","BLE","S101","DTZ","T20",
            "TRY400","N818","FBT003","INP","PIE","RET","SIM","ERA","RUF"]
  [tool.ruff.lint.mccabe]
  max-complexity = 10
  [tool.ruff.lint.per-file-ignores]
  "**/bootstrap/runtime.py" = ["PLR0915"]   # linear wiring; see §5.1 for the split rule
  "**/tests/**" = ["S101", "INP"]
  ```
  Add two sentences to the skill:
  - "Do not enable PLR0913 (argument count). Keyword-only DI constructors legitimately exceed it; review argument count manually."
  - "Ruff cannot measure function length or nesting depth, so those remain review signals."
- **Why:** the baseline selects only `E4, E7, E9, F, I, UP, B, TID252`. None of CLAUDE.md's thresholds is checked (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/CLAUDE.md:6-9`, `:38-42`). The result in this codebase:
  - 44 functions exceed 40 lines; the longest is 220.
  - 5 functions hit C901.
  - 21 `except Exception`.
  - 5 production `assert`s used for type narrowing.
  - 3 exception classes lack the `Error` suffix.

  None of this was flagged.
- **Evidence:**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/pyproject.toml:26-27` (the baseline copied verbatim)
  - C901 hits:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/client.py:84` (CC 14)
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:290` (CC 20)
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:136` (CC 11)
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/llm_client.py:114` (CC 11)
- **Exceptions:** flat Pydantic validators should be *split* (§2.6), not exempted.
- **Priority:** High.

### 1.3 Deduplicate CLAUDE.md against the skills

- **Target:** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/CLAUDE.md`, plus the skill references named below.
- **Proposed changes:**
  - **#1 (function size):** "…Composition roots may be longer when purely linear, but split them by subsystem past ~80 lines (see python-service-architecture). CC ≤ 10 is enforced by ruff C901; length and nesting are review signals."
  - **#4 (module size):** keep the number *only* in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/modularization.md:33-35`. `CLAUDE.md:21-23` says 300 and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/references/ai.md:168-175` says 300–350, so three places state it with different numbers. Replace the others with a pointer.
  - **#5 (business capability):** it conflicts with `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture/SKILL.md:81-86`, which forbids "root business-capability packages". Rewrite both: "Business capabilities are organized *inside* `application/` and `domain/` (e.g. `application/billing/`). Do not create root-level peers of the technical boundaries."
  - **#7 (errors):** extend it per §3.2.
  - **#9 (speculative abstraction):** add "and delete leftovers" per §5.8.
- **Why:** duplicated rules with different wording drift apart, and an agent that reads both gets contradictory instructions.
- **Priority:** Medium.

---

## 2. Pydantic models and `BaseSettings`

### 2.1 Use `Field(...)` only when it adds behavior or information (the proposed rule, evaluated)

- **Verdict:** adopt it. The skill currently instructs agents to do the opposite.
- **Target skill:** python-settings-config. Change:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/references/settings-py.md` ("Field Conventions")
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-settings-config/SKILL.md:247-248`

  Add one line each to python-service-architecture `references/api-and-workers.md` (request/response schemas) and `references/ai.md` (LLM schemas).
- **Proposed rule:**
  > Declare fields with a bare annotation: `x: int` is required, `x: int = 5` has a default. Use `Field(...)` only when it carries **behavior** or **information**:
  > - a constraint (`gt`, `ge`, `min_length`, `pattern`, `strict`, `allow_inf_nan`);
  > - an alias that differs from what the source would bind automatically;
  > - `default_factory`;
  > - SQLModel `sa_column` / `primary_key`;
  > - a `description` that is **consumed** (LLM tool/structured-output schemas, public OpenAPI) **or adds information** the name, type and default do not: the unit, the accepted format, the scope ("rows claimed per poll"), what omission does ("telemetry is disabled when unset"), or a non-obvious semantic ("compared with the token's `client_id`, not `aud`").
  >
  > Never write a description that restates the field name. Never write `Field(...)` or `Field(default=...)` with no other argument: in Pydantic v2 an annotation without a default is already required. Document the env contract once, in `.env.example`, not in both `description=` and the env file.
- **Why:**
  - `SKILL.md:247-248` says: "Use `Field(..., description="...")` for required values and `Field(default=..., description="...")`". `settings-py.md:74` says: "Include concise `description=` text on fields."
  - `settings-py.md:78` says: "Use `Field(...)` only when the app cannot provide a safe default". In Pydantic v2 the `...` is redundant.
  - Every scaffold restates the name, e.g. `app_port … description="Server bind port."`.
  - The two services diverged because of this rule. The worker ignored it: 106 `Field()` calls and 0 descriptions. The orchestrator followed it: 28 of 39 fields have descriptions, and about 17 of those only restate the name. No code renders the settings schema, so nobody consumes these descriptions.
- **Evidence:**
  - Noise: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/config/settings.py`:
    - `:136` `nats_url` → "NATS server URL."
    - `:137` `s3_bucket` → "Object-store bucket."
    - `:169` "CTC tenant token."
    - `:184` "Maximum reports batch size."
    - `:193` "Publisher polling interval."
    - `:214` "JetStream name."
    - `:219` "JWKS cache lifetime."

    The same text is maintained a second time in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/.env.example:32-66`.
  - Informative descriptions (keep):
    - same file `:104` ("Credential-free async URL…")
    - `:145` (client id, not audience)
    - `:155` ("telemetry is disabled when absent")
    - `:196` ("rows claimed by one publisher poll")
    - `:209` ("Statement **and lock** timeout")
  - Consumed descriptions (keep):
    - LLM schemas `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/schemas.py:69`, `:78-83`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/tools/run_sql_query.py:33-36`
  - Pure-behavior `Field`, which is good: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/schemas/investigations.py:27` (`Field(default=1, gt=0, strict=True)`).
- **Bad / good:**
  ```python
  # bad: restates the name, and the alias equals NAME.upper()
  nats_stream: str = Field(alias="NATS_STREAM", min_length=1, description="JetStream name.")
  request_timeout_seconds: float = Field(default=30.0, description="Default outbound request timeout.")

  # good
  nats_stream: str = Field(min_length=1)
  otlp_endpoint: AnyHttpUrl | None = Field(
      default=None, description="OTLP collector; telemetry is disabled when unset."
  )
  ```
- **Exceptions:**
  - LLM-facing and OpenAPI-facing models, where descriptions become schema text the consumer reads. There, a description is expected even when it looks obvious, if it guides the model.
  - SQLModel columns.
- **Priority:** High.

### 2.2 Default to `case_sensitive=False` with no aliases

- **Target skill:** python-settings-config, `references/settings-py.md:63-67` and `SKILL.md:260-262`.
- **Proposed rule:**
  > For new services, use `case_sensitive=False` and no `alias=`, so `LOG_LEVEL` binds `log_level` automatically. Add an alias only when the env name genuinely differs from the field name. This also removes the need for `populate_by_name=True` in the YAML pattern.
  >
  > For existing services this changes the env contract, so treat it as an explicit migration, not a drive-by edit.
- **Why:**
  - Across all 156 settings and secrets fields in both services, `alias == field_name.upper()` in 100% of cases. The aliases exist only because the flat scaffold mandates `case_sensitive=True`.
  - They force a `populate_by_name` workaround and dual-key lookups, e.g. `values.get("ENVIRONMENT_NAME") or values.get("environment_name")` (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:137`).
  - The skill's own nested scaffold already uses `case_sensitive=False` without aliases (`settings-py.md:239`). The skill is inconsistent with itself.
- **Exceptions:** existing deployments, and contract tests that read `model_fields[name].alias` (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/contract/config/test_settings_documents.py:17-18`).
- **Priority:** Medium.

### 2.3 Durations and ratios must be finite: define `Annotated` aliases once

- **Target skill:** python-settings-config, `references/settings-py.md` "Preferred Pydantic Types". Replace rows `:140-141` and add a "Reusable field types" subsection.
- **Proposed rule:**
  > Durations, intervals, ratios and multipliers must reject `inf`/`nan`. Define one module-level alias per shape beside `Settings` and reuse it:
  > ```python
  > PositiveSeconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]
  > Ratio           = Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)]
  > NonEmptyStr     = Annotated[str, Field(min_length=1)]
  > ```
  > When the same constraint set appears on three or more fields, or encodes a domain rule (a credential-free DSN, for example), make it an `Annotated` alias. Put value-shape checks in the type (`AfterValidator`), not in a `field_validator` bound to one field, so every field of that kind gets the check.
- **Why:**
  - The skill recommends `PositiveFloat` for timeouts (`settings-py.md:140`) and, in the next row, `FiniteFloat` for "any float used in arithmetic" (`:141`). The two conflict.
  - `PositiveFloat` accepts `inf`. I verified this in the repo venv: `M(x='inf') → x=inf`. So `LEASE_SECONDS=inf` passes startup validation.
- **Evidence:**
  - Worker `PositiveFloat` durations: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:190-193` (e.g. `:193` `lease_seconds: PositiveFloat`), `:198`, `:204`, `:215`, `:251`, `:254`, `:257`, `:260`.
  - The same file uses `FiniteFloat = Field(..., gt=0)` 28 times for the same concept (e.g. `:216`).
  - A test rejects `nan/inf` only for the `FiniteFloat` fields: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/config/test_settings.py:188-198`.
  - There are 0 `Annotated` aliases for Pydantic types in the repo.
- **Exceptions:**
  - A one-off constraint stays inline.
  - An intentional "infinite = disabled" meaning should be `X | None` with a documented `None`.
- **Priority:** High.

### 2.4 Secret hygiene beyond `SecretStr`

- **Target skill:** python-settings-config, `references/secrets-py.md` "General Conventions", plus the scaffolds at `secrets-py.md:94-111` and `:144-150`.
- **Proposed rule:**
  > - Set `hide_input_in_errors=True` on every `Secrets` model. Also set it on `Settings` whenever a field can carry credential-adjacent input (DSNs, URLs).
  > - Declare required secrets as `Annotated[SecretStr, Field(min_length=1)]`, so an empty env var fails at startup.
  > - Secrets held outside Pydantic (dataclasses, parameter objects) stay `SecretStr` or use `field(repr=False)`.
  > - Type unwrapping helpers as `SecretStr | None`, never `object`.
  > - Re-raise secret-payload parse failures with `from None`.
  > - Settings URLs that must be credential-free use a validated alias (§2.3) that rejects an embedded password. Otherwise the password leaks through `repr(settings)`, which I verified: `AnyUrl` repr shows `user:secret@host`.
- **Why:** the two services diverged:
  - The orchestrator sets `hide_input_in_errors` (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/config/secrets.py:18`).
  - The worker does not (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/secrets.py:13-18`).

  A constrained `SecretStr` echoes the raw value in the `ValidationError` unless `hide_input_in_errors` is set.
- **Evidence:**
  - A plain `str` password in a dataclass with the default repr: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/platform_migrations/src/platform_migrations/database_bootstrap.py:22-25`.
  - Duck-typed unwrapping: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:466-468`.
  - Worker DSN fields with no credential-free check: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:155-156`.
  - The orchestrator has the check, but only as a one-field validator: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/config/settings.py:118-134`.
  - Good pattern: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/connectivity_probe.py:36-40` (`SecretStr` in a dataclass).
- **Priority:** High.

### 2.5 Make the YAML-policy allowlist and contract test part of the scaffold

- **Target skill:** python-settings-config, `references/settings-py.md` (YAML scaffold `:436-469`), `references/config-yaml.md`, and the `SKILL.md:328-332` checklist.
- **Proposed rule:**
  > `extra="ignore"` is necessary because `.env` is shared with unrelated variables, but it makes YAML typos silent. Therefore:
  > - (a) keep an explicit `YAML_POLICY_FIELDS` frozenset in `settings.py`;
  > - (b) give YAML-owned fields **no Python default**, so YAML is their single baseline and a missing key fails at startup;
  > - (c) add a contract test that, for every environment, compares the merged YAML keys to the allowlist, and checks the allowlist is a subset of `Settings.model_fields`.
- **Why:**
  - The skill's YAML scaffold gives YAML-owned fields Python defaults (`app_title="AI Service"`, `request_timeout_seconds=30.0`) that also appear in YAML. That gives a value two authoritative homes, which contradicts its own rule "A value gets one authoritative home" (`SKILL.md:67-69`).
  - The repo already does better, and that should be the template.
- **Evidence (good):**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:30-111` (allowlist)
  - `:182-287` (policy fields without defaults)
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/contract/config/test_settings_documents.py:74-76` (the contract test)
- **Priority:** High.

### 2.6 Keep cross-field validators small, per concern, and non-mutating

- **Target skill:** python-settings-config, `references/settings-py.md:116-123`. Add a "Validation" subsection.
- **Proposed rule:**
  > - Put single-field bounds in the type or `Field` (`ge`, `lt`, `pattern`), never in a model validator.
  > - Split cross-field invariants into several `@model_validator(mode="after")` methods, one per concern (`_validate_nats_timing`, `_validate_aimd`, `_validate_llm_budgets`). Each should stay under about 10 checks, and each error message should name the env vars involved.
  > - Do not assign fields inside a validator to compute a derived default. Declare `field: T | None = None` and resolve the effective value in a property or in the bootstrap mapping.
- **Why:** the worker's single validator is 64 lines with CC 20 (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:289-352`). It:
  - covers eight unrelated subsystems;
  - duplicates a field bound (`:312-313` `if self.min_samples_per_vendor < 2`, which should be `Field(ge=2)`);
  - hides a derived default by mutation (`:291-292`), so the declared default of `min_inflight` (`:226`) is not the effective one.
- **Good example:**
  ```python
  min_inflight: PositiveInt | None = None

  @property
  def effective_min_inflight(self) -> int:
      return self.min_inflight or min(2, self.initial_target)
  ```
- **Exceptions:** a single cohesive set of 3–4 checks can stay together.
- **Priority:** Medium.

### 2.7 Confine `Settings` to `config/` and `bootstrap/`, and map to narrow frozen dataclasses

- **Target skill:** python-settings-config `SKILL.md` "Core Conventions". Cross-link python-service-architecture `references/shared-libraries.md:143-149`.
- **Proposed rule:**
  > Only `config/` and `bootstrap/` import `Settings`/`Secrets`. Bootstrap maps them into small frozen dataclasses owned by each consumer (adapter, use case, library). At that point it converts Pydantic types (`AnyUrl`, `ByteSize`, `SecretStr`) into plain values, **once**, instead of calling `str(url)` at each use site. Never pass the whole `Settings` object into adapters, domain code or libraries.
- **Why:** this is already the codebase's strongest configuration pattern, but the settings skill never states it. The one weak spot is repeated `str(...)` conversion at use sites.
- **Evidence (good):**
  - `NatsConsumerSettings`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/consumer.py:33-43`
  - `TelemetryConfig`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_observability/src/platform_observability/providers.py:46-62`
- **Evidence (weak spot):** `str(...)` conversions at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:166`, `:174`, `:182`, `:193`, `:258-259`.
- **Priority:** Medium.

### 2.8 URL types normalize: know when not to use them

- **Target skill:** python-settings-config, `references/settings-py.md` (a note under the URL rows at `:142`).
- **Proposed rule:**
  > Pydantic URL types normalize values: a bare host gains a trailing `/`. When the value is an identifier compared verbatim (JWT issuer, audience, a callback registered elsewhere), use `str` with a `pattern`, or normalize it once in bootstrap. When it is a base URL, join paths in exactly one helper, not with `rstrip('/')` at each call site.
- **Evidence:** `str(AnyHttpUrl("http://127.0.0.1:8083"))` returns `".../"`. Callers compensate ad hoc:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/adapters/cognito_jwks_verifier.py:30`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/client.py:382`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/connectivity_probe.py:107`
- **Priority:** Medium.

### 2.9 Auxiliary entry points reuse the service settings

- **Target skill:** python-settings-config `SKILL.md:270` (the `os.getenv` rule).
- **Proposed rule:**
  > Probes and admin CLIs of a service build from that service's `get_settings()`/`get_secrets()` and add only their own extra fields. They do not re-read env vars in a hand-written `from_environment()`.
  >
  > A *separate* one-shot deployable with three or fewer inputs may parse an injected `Mapping[str, str]` explicitly, but it still documents them in `.env.example` and still masks secrets.
- **Evidence:**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/connectivity_probe.py:45-60` and `:235` re-read 12 variables, including `NATS_STREAM`, `NATS_CONSUMER` and `NATS_SUBJECT`. For the worker these are YAML policy, so the probe's contract diverges from the service's.
  - The probe also hard-codes consumer parameters that duplicate YAML (§4.1).
- **Priority:** Medium.

### 2.10 Diagnostic/telemetry knobs may live in OPTIONAL with Python defaults

- **Target skill:** python-settings-config, `SKILL.md:240-246` and `references/env-example.md:130-134`.
- **Proposed rule:**
  > OPTIONAL may hold:
  > - (a) runtime identity supplied by the platform;
  > - (b) escape hatches;
  > - (c) diagnostic or observability switches whose Python default is safe in every environment and which are not application policy: content capture, full exception traces, the export interval, and a release version with an `"unknown"` fallback.
  >
  > Anything that changes business behavior (limits, retries, timeouts, prefixes) stays YAML policy with no Python default.
- **Why:** the rule "A value with a safe default is YAML policy, not an optional variable" is over-rigid. Applied literally, it would push OTel knobs into four YAML files. Both services, and their contract tests, already do the pragmatic thing:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:175-180`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/.env.example:136-144`
- **Priority:** Medium.

### 2.11 Request bodies forbid unknown keys consistently

- **Target skill:** python-service-architecture, `references/api-and-workers.md` (FastAPI section).
- **Proposed rule:**
  > Public request models use `model_config = ConfigDict(extra="forbid")`. Response models keep the default.
- **Evidence:**
  - `InvestigateRequest` forbids extras: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/schemas/investigations.py:14-15`.
  - These do not:
    - `QueryStatusRequest` (`:57-68`)
    - `FetchReportsRequest` (`:102-113`)
    - `ResetConfigurationRequest` (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/schemas/config.py:6-9`)

    The last one is destructive: a request with `{"purge_manual": true}` (a typo of the real key) resets without purging.
- **Priority:** Medium.

---

## 3. Errors and failure contracts

### 3.1 A small retry-classification base for port errors

- **Target skill:** python-service-architecture, `references/boundaries.md` ("Errors and constants follow ownership", around `:255-259`). Also rewrite `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture-audit/SKILL.md:55-56`.
- **Proposed rule:**
  > When the application's retry or terminal policy depends on a transient/permanent distinction, define that classification **once**, where the policy lives (`domain/` or `application/errors.py`), as a small pair of bases:
  > ```python
  > class DependencyUnavailableError(Exception):
  >     def __init__(self, message: str, *, error_code: str, retry_metadata: RetryMetadata | None = None): ...
  > class DependencyRejectedError(Exception):
  >     def __init__(self, message: str, *, error_code: str): ...
  > ```
  > Port-owned errors subclass these bases. Their meaning stays with the port; only the retry semantics are shared. Application code catches the bases, not an allow-list of every port error. Every attribute read from an exception is declared on the base. Never use `getattr(exc, "error_code", default)`.
  >
  > This is not a "universal adapter hierarchy". Adapters still translate their own SDK errors.
- **Why:** the audit skill says to translate failures "without a universal adapter hierarchy or central translator", and `boundaries.md` forbids shared error collections. Together they push authors toward N unrelated `RuntimeError` subclasses, and then the application has to enumerate them all.
- **Evidence:**
  - Hand-maintained tuples: `_TRANSIENT_FAILURES` (10 classes) and `_PERMANENT_FAILURES` (9 classes) at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/investigate_exception.py:227-249`.
  - `getattr` on error attributes:
    - `investigate_exception.py:110`: `getattr(exc, "error_code", "external_dependency_unavailable")`
    - `investigate_exception.py:319`: `cast(str, getattr(...))`
  - `getattr(…, "retry_metadata", None)`:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/domain/retry.py:123`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/analyst.py:306`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/config_summarization/summarizer.py:54`
  - Identical `__init__(message, *, retry_metadata)` boilerplate in five port files, e.g. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/ports/investigation/exception_source.py:23-25` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/ports/investigation/query_executor.py:22-24`.
  - The same tuple-based pattern in the orchestrator's HTTP handlers: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/exception_handlers.py:50-58`, `:78-80`.
- **Bad / good:**
  ```python
  # bad
  except _TRANSIENT_FAILURES as exc:
      raise TransientInvestigationError(str(exc), error_code=getattr(exc, "error_code", "x"))
  # good
  except DependencyUnavailableError as exc:
      raise TransientInvestigationError(str(exc), error_code=exc.error_code,
                                        retry_metadata=exc.retry_metadata)
  ```
- **Exceptions:** with only one or two ports, catching them explicitly is fine.
- **Priority:** High.

### 3.2 Where `except Exception` is allowed; `assert` and `NoReturn`

- **Target:** `CLAUDE.md` #7 (extend it) and the `code-conventions.md` reference (§1.1). Enforce with BLE001, S101 and TRY400 (§1.2).
- **Proposed rule:**
  > - `except Exception` is allowed only at a **process boundary**: a supervisor iteration, a message handler, cleanup in `finally`, or a telemetry wrapper that re-raises. There it must either log with `exc_info` and map to a declared outcome, or re-raise.
  > - Never label an unknown exception as a specific cause (for example `"database_unavailable"`).
  > - A capability that degrades on failure (returns empty or a default) logs at warning and records a metric. Silently returning `()` is forbidden.
  > - Do not raise a generic exception inside a `try` whose `except` catches only a narrower type.
  > - Do not use `assert` for runtime narrowing in production code. Raise a specific error, or restructure the code so the type narrows.
  > - Helpers that always raise are annotated `-> NoReturn`.
- **Evidence:**
  - Swallowed and mislabeled (verified): `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:152-154`. The code is `except Exception: await message.nak(delay_seconds=30); return "retried", "database_unavailable"`, with no log. A `TypeError` becomes "database unavailable".
  - Silent degradation: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/contextual_analyst.py:135-138` (`except QueryExecutionError: return ()`).
  - Generic raise inside a narrow `try` (verified): `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/max_delivery_advisories.py:106-108`.
  - `assert` for narrowing:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_investigations.py:81`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/fetch_reports.py:106`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/analyst.py:180`
  - Missing `NoReturn`, which forces a dead `raise AssertionError(...)`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/llm_client.py:158`, `:180-191`. The correct form exists at `analyst.py:295`.
  - Acceptable boundary usage: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/reconciliation_supervisor.py:32-33`.
- **Priority:** High.

### 3.3 Every DB adapter method honours the port's failure contract

This topic is covered under persistence in §8.2.

### 3.4 HTTP error mapping in one table

- **Target skill:** python-service-architecture, `references/api-and-workers.md` (FastAPI section).
- **Proposed rule:**
  > - Map errors to HTTP in one place: a table in `api/exception_handlers.py` from error type to `(status, code)`, using the error's own `error_code`.
  > - Routers do not use try/except just to re-raise as `ApiError`.
  > - Build the error envelope with one helper.
  > - Global handlers never branch on the request path.
  > - Declare per-route authorization as route dependencies (`Security(require_scope(...))`), not as method/path tables in middleware.
- **Evidence:**
  - The same `batch_too_large` mapping appears three times: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/routers/investigations.py:82-87`, `:133-138`, `:171-176`.
  - A path branch: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/exception_handlers.py:36`.
  - The envelope is built in three places (`exception_handlers.py:25`, `:40-42`, `:66-71`) and again in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/middleware/authentication.py:29-35`.
  - A path table that duplicates the routers: `authentication.py:20-26`.
- **Priority:** Medium.

---

## 4. Configuration values, constants and closed vocabularies

### 4.1 No shadow defaults for configured values

- **Target skill:**
  - python-settings-config `SKILL.md` "Configuration Ownership Contract" (`:65-119`) and "Change Checklist"
  - python-service-architecture `references/boundaries.md:273-276`
- **Proposed rule:**
  > A value owned by YAML or env must not reappear as a literal, or as a default on a dataclass, constructor, prompt builder or library function, anywhere downstream. Policy objects built from settings have **required**, keyword-only fields, and bootstrap passes the resolved value.
  >
  > When you move a value into YAML, grep for its literal and remove the shadow copies.
  >
  > A genuinely invariant number is a named module-level `Final` constant with a unit suffix and a one-line *why*.
- **Why:** if bootstrap forgets one keyword, the stale literal silently wins. The skill warns about exactly this failure for YAML-versus-env (`config-yaml.md:144-156`) but not for Python defaults further down the call chain.
- **Evidence:** each of these repeats a value from `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/config/services/worker.yaml`:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/retry.py:15-19`: `max_attempts=3`, `base_delay_seconds=0.5`, `max_defer_seconds=3600.0`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/llm_client.py:35-36`, `:198`: `retry_window_seconds=120.0`, `3600.0`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/prompts.py:19-20`: `main_tool_limit=30`, `repair_execution_limit=3`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/analyst.py:69-79`: a hard-coded fallback budget (`35`, `80`, `600`)
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/connectivity_probe.py:177`, `:193-195`: `ack_wait=60`, `max_deliver=6`, `max_ack_pending=2250`. The probe can therefore create a consumer that differs from production.
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/engine.py:16`: `acquisition_timeout_seconds=30`, while YAML says 5.
  - Unnamed literals:
    - `nak(delay_seconds=30)` three times in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:153`, `:160`, `:280`
    - `expires_in * 0.8` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/client.py:285`
    - `age > 300` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/reconcile.py:43`
- **Bad / good:**
  ```python
  # bad
  @dataclass(frozen=True)
  class CtcRetryPolicy:
      max_attempts: int = 3
      max_defer_seconds: float = 3600.0

  # good
  @dataclass(frozen=True, slots=True, kw_only=True)
  class CtcRetryPolicy:
      max_attempts: int
      max_defer_seconds: float

  _TOKEN_REFRESH_RATIO: Final = 0.8  # refresh before expiry to absorb clock skew
  ```
- **Exceptions:** library-owned behavior that no service configures, and test-only factories.
- **Priority:** High.

### 4.2 Closed vocabularies are types, declared once

- **Target:** `code-conventions.md` (§1.1). Cross-link python-service-architecture `references/boundaries.md:275-276` and `references/shared-libraries.md`.
- **Proposed rule:**
  > - Outcomes, statuses, reasons, stop reasons, budget dimensions and metric-label vocabularies that cross a function boundary are a `StrEnum` (when members are used by name) or a `Literal` alias. That includes private return tuples and exception fields.
  > - Declare each one **once**. Derive runtime sets with `typing.get_args(Alias)` or by iterating the enum, never by retyping the values.
  > - Never classify by substring (`"tool" in error.dimension`).
  > - Use `None` or an explicit enum member, never sentinel strings such as `"_NONE"`.
  > - Return a `NamedTuple` or dataclass instead of `tuple[str, str]`.
  > - Timestamps that cross process boundaries reject naive values.
- **Evidence:**
  - `_handle(...) -> tuple[str, str]` returning `"retried"`/`"_NONE"`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:136`, `:154`, `:180`.
  - `"_NONE"` also appears in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/metrics.py:117` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/observability/filtered_requests.py:47`.
  - Parallel allowlist sets `_STOP_REASONS`, `_OUTCOMES`, … in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/genai.py:39-71` duplicate `IncompleteStopReason` in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/domain/incomplete_analysis.py:10-20`.
  - Substring classification: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/analyst.py:274-282`.
  - `Literal["high","medium","low"]` is declared in five places, e.g.:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/investigation_contracts/src/investigation_contracts/analysis.py:9-10`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/domain/analysis.py:6-7`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/fetch_reports.py:19-20`
  - Naive timestamps accepted: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/investigation_contracts/src/investigation_contracts/events.py:116-122`.
  - Good contrast: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/domain/admission_policy.py:46` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/domain/retry.py:12`. The codebase has 23 `StrEnum`s overall.
- **Exceptions:** a deliberate copy across a service boundary when the service must not depend on the package. The copy should still derive its runtime sets from its own alias.
- **Priority:** Medium.

### 4.3 Unit suffixes on every duration and size

- **Target skill:** python-settings-config `SKILL.md` ("Code invariant" bullet) and `code-conventions.md`.
- **Proposed rule:**
  > Every duration or size name ends with its unit (`_seconds`, `_millis`, `_days`, `_chars`, `_tokens`, `_bytes`) unless the type carries the unit (`ByteSize`, `timedelta`). A settings bound that exists for a code reason (`le=4`) references a named constant.
- **Evidence:**
  - Good: every settings duration is unit-suffixed, and `ByteSize` is used for sizes.
  - Gaps:
    - `record_comment_limit` counts characters (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:263`).
    - Unexplained bounds `le=4`/`le=2` (`:267`, `:274`).
- **Priority:** Low.

---

## 5. Service architecture: composition, lifecycle, use cases, ports

### 5.1 Structure the composition root, and use one lifecycle idiom

- **Target skill:** python-service-architecture, `references/boundaries.md` (`bootstrap/` section, `:145-159`).
- **Proposed rule:**
  > - A composition root may be long because it is linear wiring. Once it passes about 80 lines, split it into `_build_<capability>(settings, resources) -> <frozen bundle>` functions (`_build_admission`, `_build_investigation`, `_build_genai`), each under about 40 lines.
  > - Build each concrete adapter once and share it.
  > - Use one lifecycle idiom: `@asynccontextmanager async def runtime(settings, secrets) -> AsyncIterator[Runtime]` owning a single `AsyncExitStack`. Do not hand-roll `build()` + `close()` + `pop_all()`.
  > - Register each process-wide teardown (observability shutdown, for example) exactly once.
  > - Resources kept only for disposal live in the exit stack, not in public runtime fields.
  > - Never reach into a runtime object's `_private` fields from bootstrap. Expose `start()`/`aclose()` instead.
  > - Keep gauge initialization and closures that contain business logic out of wiring.
- **Why:** `boundaries.md:157-159` says to split "by construction concern", but it says nothing about the composition function itself or which lifecycle idiom to use. The two services picked different ones.
- **Evidence:**
  - `_compose_runtime` is 220 lines: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:219-438`. Within it:
    - two S3 stores with copied credential expressions (`:289-295`, `:314-320`);
    - three identical UoW lambdas (`:310`, `:328`, `:352`);
    - gauge setup inside the wiring (`:361-364`);
    - a business closure (`:246-254`).
  - Duplicated resource dataclasses: `runtime.py:85-100` and `:142-153`.
  - Observability shutdown registered twice:
    - worker: `runtime.py:162` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/process.py:29`
    - orchestrator: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/runtime.py:203` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/app.py:56`
  - Good idiom: the orchestrator's `@asynccontextmanager` runtime (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/runtime.py:191-226`). It is spoiled by `value._publisher.close` / `value._publisher_supervisor.start()` at `:221-225`.
- **Exceptions:** a service with fewer than about 10 collaborators keeps one flat function.
- **Priority:** High.

### 5.2 Long-running loops: one owner and a declared failure policy

- **Target skill:** python-service-architecture, `references/api-and-workers.md:78-80` ("Long-running worker").
- **Proposed rule:**
  > - Each loop is an object with `async def run(self, stop: asyncio.Event) -> None`. It calls a **public** single-iteration method (`tick()`, `poll_once()`), which calls an application action and records the returned result.
  > - One owner creates all loop tasks.
  > - Every loop declares its failure policy explicitly:
  >   - **isolate:** catch `Exception` around the iteration, log it with `exc_info`, back off, and continue; or
  >   - **fail fast:** let it propagate and stop the process or mark it not-ready.
  > - Use one shared `wait_for_stop(stop, timeout)` helper.
  > - Pause and admission decisions belong in domain/application objects, not in the loop body.
  > - Batch-until-done business loops belong in `application/`, not in the supervisor.
- **Why:** the skill says only that "the supervisor owns asyncio tasks, stop events, graceful shutdown". As a result, loops in the same service behave differently on error.
- **Evidence:**
  - Isolate: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/reconciliation_supervisor.py:29-35`.
  - Crash the process: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/diagnostic_supervisors.py:121-126` (`AimdSupervisor.run`).
  - Catch and log: `diagnostic_supervisors.py:82-89`.
  - Stop-wait written inline four times (`diagnostic_supervisors.py:75-78`, `:104-109`, `:123-126`; `reconciliation_supervisor.py:36-39`).
  - Start/stop/cancel duplicated in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/supervisor.py:54-97` and `:100-168`.
  - Admission policy mixed into the loop: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/supervisor.py:102-120`.
  - Private iteration method that tests have to call: `diagnostic_supervisors.py:80` (`_poll_once`). Compare the public `tick()` at `:128`.
- **Priority:** High.

### 5.3 Standardize the use-case shape the code already mostly follows

- **Target skill:** python-service-architecture, `references/boundaries.md:175-183` (`application/`), plus one short template in `references/templates.md`.
- **Proposed rule:**
  > An application action is a class named with an imperative verb phrase (`InvestigateException`, `RequestInvestigations`). It has:
  > - keyword-only constructor dependencies: ports, a UoW factory `Callable[[], UoW]`, typed policy objects, and effect seams with real defaults;
  > - **one** public `async def execute(*, ...) -> <FrozenResult>`;
  > - failures raised as action-owned or port-owned exceptions.
  >
  > Use a plain module function when there are no dependencies. Do not expose half-actions as public functions with boolean mode flags or `| None` results that callers interpret differently.
- **Evidence (good):**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_investigations.py:40-89`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/adjust_admission.py:28-60`, which returns a frozen `AdmissionTickResult`
- **Evidence (drift):**
  - `request_one(..., filtered: bool = False) -> ... | None`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_investigations.py:102-113`. One caller asserts the result is not `None` (`:81`). The other treats `None` as "history exclusion" (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_filtered_investigations.py:91-93`).
  - A second entry point that copies the ownership check: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/record_investigation_failure.py:64-69` and `:105-110`.
- **Priority:** Medium.

### 5.4 Constructor contracts: no test-only optional collaborators or legacy branches

- **Target skill:** python-service-architecture, `references/boundaries.md` (new "Constructor contracts" section). Add an audit check to `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture-audit/SKILL.md`.
- **Proposed rule:**
  > A production class's required collaborators and limits are **required** parameters. Do not make them `X | None = None` with a built-in fallback, a default magic number, or a "legacy" branch just so tests or old callers can leave them out. Tests construct the real shape with fakes, or through a test-local builder.
  >
  > Defaults are allowed only for effect seams (clock, sleep, random, uuid) whose default *is* the real effect, and for genuinely optional, settings-documented features.
- **Why:** this is the most expensive readability pattern in the codebase. Readers have to understand branches that production never takes.
- **Evidence:**
  - `budget_limits: … | None = None, finalizer: AnalysisHarness | None = None`, plus `_raise_legacy_error` ("Preserve the pre-finalizer port behavior for explicitly unconfigured callers"): `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/analyst.py:59-60`, `:160-161`, `:295-307`. Production always passes a finalizer (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/contextual_analyst.py:124`).
  - `legacy_budget` / `bind_tool_budget`, used only by a unit test: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/limits.py:204-214`, `:234-250`.
  - `pause: PauseTracker | None = None` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/supervisor.py:48`. Production always passes one.
  - A `factory: ChatModelFactory | None` test seam in every production `llm.py` (e.g. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/llm.py:21`).
  - `bedrock_client: Any | None` threaded through the composition root: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:224`, `:445`.
- **Priority:** High.

### 5.5 Where Protocols live: root `ports/` vs the consumer's module

- **Target skill:** python-service-architecture, `references/boundaries.md:43-53` ("When a port earns its cost").
- **Proposed rule:**
  > Root `ports/` holds only capabilities that application code needs from external systems. A Protocol that exists only to decouple an outer component from a collaborator (a handler from an action, a supervisor from a recorder) is declared **next to its single consumer** and kept minimal.
  >
  > Introduce any Protocol only when a test substitutes it or a second implementation exists today. That single question replaces the current "two of three criteria" test, which almost any I/O passes.
- **Evidence:** the good pattern is already in use:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:41-72`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/investigate_exception.py:67-68`

  Borderline: one capability split into a Protocol plus two classes only so a test can fake the generator (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/config_summarization/summarizer.py:16-62`).
- **Priority:** Medium.

### 5.6 Reuse technology-neutral contract-library types; don't mirror them

- **Target skill:** python-service-architecture, `references/boundaries.md` ("Contract ownership") and `references/shared-libraries.md:143-144`.
- **Proposed rule:**
  > When a workspace library exists to publish a technology-neutral contract (frozen dataclasses, enums and errors, with no framework types), `domain/` and `ports/` may import its types directly. Do not mirror them into identical service-local dataclasses and copy them field by field.
  >
  > Mirror a type only when the service's meaning differs, and say how in the module docstring. Apply one decision per library, consistently.
- **Evidence:**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/models.py:1-32` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/ports/investigation/exception_source.py:1-43` are identical, including the docstring. Between them sits a 44-line re-mapping wrapper: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/ctc/exception_repository.py:17-44`.
  - `InvestigationRequested` is mirrored in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/domain/investigation.py:61-70`. The orchestrator uses the library type directly, and the worker already imports `investigation_contracts.PersistedAnalysis` in the same module (`:8`). The worker is inconsistent with itself.
  - `CandidateCursor` is copied and converted both ways: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/ctc_candidate_source.py:20-24`, `:46`.
- **Exceptions:** libraries that expose SQLAlchemy or other framework types stay behind `db/` or `adapters/`.
- **Priority:** High.

### 5.7 `api/` must not import `bootstrap/`; bootstrap runs no queries

- **Target skill:** python-service-architecture, `references/api-and-workers.md` (FastAPI section). Also update the audit script `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-service-architecture-audit/scripts/audit_service.py:11-26`, which should add `api`, `adapters` and `observability` to `INTERNAL_FORBIDDEN`.
- **Proposed rule:**
  > `api/` declares the narrow Protocol it needs from runtime state (`api/dependencies.py: class ApiRuntime(Protocol)`), and bootstrap satisfies it. `api/`, `adapters/`, `db/` and `genai/` never import `bootstrap/`. Readiness checks call a port method (`PlatformHealth.ping()`). Bootstrap does not execute SQL itself.
- **Evidence:**
  - `from orchestrator.bootstrap.runtime import RuntimeState` in:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/dependencies.py:11`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/routers/health.py:10`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/middleware/authentication.py:8`

    This is circular, because `bootstrap/app.py` imports those modules.
  - `text("SELECT 1")` in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/runtime.py:76-82`.
  - The current audit script reports 0 findings on both services and misses this.
- **Priority:** High.

### 5.8 Removing a capability removes its generality

- **Target skill:** python-service-architecture, `references/modularization.md:67-72` ("Migration sequence"). Add one line to `CLAUDE.md` #9.
- **Proposed rule:**
  > When a capability is removed, delete in the same change:
  > - the parameters, branches, `**kwargs` passthroughs and HTTP verbs it justified;
  > - its compatibility shims and error mappings;
  > - its domain-record fields;
  > - its read paths.
  >
  > Keep DB columns in the persistence model until a contract migration drops them (§8.10). Search for single-value parameters and test-only call paths before finishing. An in-repo re-export shim with only internal consumers is a violation, not a transition.
- **Evidence (the report-only release, commit `f112e79`):**
  - `CtcClient.request(method, path, **kwargs: Any)` rejects every method except GET, yet still runs `_is_replayable(kwargs)`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/client.py:84-94`, `:412-421`. Its only caller passes `"GET"`.
  - `comment_outcome`/`codes_outcome` fields that nothing reads:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/domain/investigation.py:97-100`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/domain/investigation.py:66-69`
  - A "compatibility imports" shim: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/ctc/engine.py:1-5`.
  - Dead code:
    - `_retry_delay`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:299-309`
    - `session_scope`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/session.py:13-17`
  - A stale e2e expectation (§10.7).
- **Priority:** High.

### 5.9 Parameter objects, flag arguments and forwarding wrappers

- **Target:** `code-conventions.md` and python-service-architecture `references/boundaries.md` ("Constructor contracts").
- **Proposed rule:**
  > - Group settings-derived scalars that one owner always consumes together into a frozen policy dataclass validated in `__post_init__`. Follow the existing `ControlContextCachePolicy`.
  > - Do not create a one-field wrapper while sibling scalars stay loose.
  > - Replace a boolean flag that selects different object shapes or methods with two functions.
  > - Delete private functions whose body forwards one call with the same arguments.
  > - Never recover structured data by regex from text you rendered yourself. Pass the structure.
- **Evidence:**
  - Five loose scalars: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/resolve_control_context.py:64-68`.
  - A one-field `AnalysisSettings` next to a loose `report_inline_limit`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/investigate_exception.py:71-73`.
  - A mode flag: `finalizer: bool` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/genai.py:170`.
  - Regex over rendered text: `re.findall(r'"([^"]+)"', schema_context)` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/genai.py:189`.
  - A forwarding wrapper: `_read_cached` at `resolve_control_context.py:129-133`.
  - Good pattern to follow: `resolve_control_context.py:38-52`.
- **Priority:** Low–Medium.

### 5.10 GenAI: share provider construction; per-request agent assembly lives in `genai/`

- **Target skill:** python-service-architecture, `references/ai.md:183-193` and `:244-263`.
- **Proposed rule:**
  > - A task-level `llm.py` is required only when it binds something task-specific: structured output, tools, or task-only parameters.
  > - Provider construction policy is shared once, in `genai/shared/<provider>.py::build_chat_model(options)`. That policy includes timeouts, disabled retries, client validation and callback plumbing.
  > - When the prompt, schema or tools depend on runtime context, bootstrap injects the *static* ingredients into an assembler class in `genai/<task>/agent.py`. That class builds or caches harnesses per context.
  > - Bootstrap never defines closures that contain GenAI assembly or parsing logic.
- **Why:** "Every GenAI task has `llm.py`" (`ai.md:193`), together with an undefined threshold ("meaningful construction policy beyond an `init_chat_model` call", `ai.md:183-185`), produced copies of the same file.
- **Evidence:**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/sql_fixer/llm.py`, `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/config_summarization/llm.py` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/llm.py:13-45` differ only in docstring and temperature.
  - A pure pass-through: `exception_analysis/llm.py:47-66`.
  - Four identical 6-keyword calls: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/genai.py:113-153`.
  - A 60-line `build_harness` closure in bootstrap, including a `ContextVar` and a regex: `bootstrap/genai.py:156-219`.
- **Priority:** High.

### 5.11 `ContextVar`s as the GenAI tool channel

- **Target skill:** python-service-architecture, `references/ai.md` ("Tools and MCP").
- **Proposed rule:**
  > Pass per-invocation state (budgets, evidence collectors) to framework-invoked tools through `ContextVar`s only when the framework offers no explicit context channel.
  > - Declare each `ContextVar` at module level in the GenAI module that owns the state, never in bootstrap.
  > - Bind them all in one context manager inside the capability's `analyze()`/`invoke()`.
  > - Readers fail loudly when nothing is bound. They never silently skip enforcement.
- **Evidence:**
  - Consumers that silently no-op: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/limits.py:217-222`, `:243-256`.
  - A `ContextVar` created in bootstrap: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/genai.py:182-185`.
- **Priority:** Medium.

### 5.12 Broker adapters map outcomes; they do not own retry policy

- **Target skill:** python-service-architecture-audit `SKILL.md` semantic checklist (`:47-85`). Also add an example to `references/api-and-workers.md:137-146`.
- **Proposed rule:**
  > Flag any consumer adapter that computes backoff schedules, merges server retry deadlines, or decides claim/ownership outcomes. The adapter maps a typed application outcome (for example `RecordedFailure(outcome, retry_not_before)`) to ack/nak/term plus a delay. The delay policy is a domain function.
- **Evidence:**
  - Backoff and lease policy inside the handler: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:238-261`, `:311-327`.
  - Good pattern: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/max_delivery_advisories.py:41-62` maps `MaxDeliveryOutcome` to message deletion.
- **Priority:** Medium.

### 5.13 Cross-service plumbing: extract into an existing library when identical

- **Target skill:**
  - python-service-architecture `SKILL.md:40-47` (discovery step 7)
  - `references/shared-libraries.md` ("Review questions")
- **Proposed rule:**
  > Before finishing, grep the other members for identical function names (`def <name>(` across `services/*/src` and `libs/*/src`).
  >
  > An identical, non-business helper in two or more services, whose natural library is *already a dependency of both*, moves into that library now. That does not require creating a new library.
  >
  > Treat an implicit shared storage layout (a prefix one service writes and another purges) as a contract with a single owner.
  >
  > Per-service settings loaders are the exception: about 40 lines each, deliberately kept per deployable and structurally identical.
- **Evidence:**
  - `authenticated_database_url` exists three times:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/engine.py:8`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/engine.py:7`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/engine.py:7`
  - `_instrument_httpx` exists twice:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/app.py:61`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/process.py:40`
  - Retry backoff is implemented two different ways:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/retry.py:35-71`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/llm_client.py:167-172`
  - Divergent secrets models (§2.4).
- **Exceptions:** helpers whose semantics differ per service.
- **Priority:** Medium.

---

## 6. Typing and modern Python idioms

### 6.1 Fix type-checker escapes centrally

- **Target skill:** python-repository-setup `SKILL.md:304-307` (mypy block). For persistence, python-sqlmodel-alembic `references/models-and-base.md`.
- **Proposed rule:**
  > - Enable `plugins = ["pydantic.mypy"]` whenever pydantic or pydantic-settings is used.
  > - For untyped third-party packages, add stubs (`boto3-stubs`, `types-botocore`) or **one** `[[tool.mypy.overrides]] module=[...] ignore_missing_imports = true` block. Never repeat `# type: ignore[import-untyped]` per import.
  > - When the same `cast`/ignore pair appears more than twice, wrap it once in a typed helper owned by the package that owns the type. For example, export typed `Table` handles from the models library instead of `cast(Table, M.__table__)  # type: ignore`.
- **Why:** there are 43 `# type: ignore` in `src`, and roughly 35 of them disappear with these three moves.
- **Evidence:**
  - 12 `import-untyped` ignores, e.g.:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/aws/s3_manual_store.py:7-8`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/ctc/query_executor.py:11`
  - 4 `Settings()  # type: ignore[call-arg]`, e.g. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:390`.
  - 19 `cast(Table, X.__table__)  # type: ignore`, e.g.:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/repositories/investigations.py:46`, `:79`, `:112`, `:128`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/repositories/outbox.py:44`
- **Priority:** High.

### 6.2 No `getattr` duck typing on project-owned types

- **Target skill:** python-service-architecture `references/boundaries.md:103-105`, extended from "no `dict[str, Any]` at boundaries".
- **Proposed rule:**
  > Do not use `getattr(obj, "attr", default)` on types the project owns. Declare the attribute on the Protocol or base class and access it directly. Reserve `getattr`, `Any` and `cast` for untyped third-party payloads (LangChain callbacks, botocore responses), isolated in one translation function per payload.
- **Evidence:**
  - Error attributes read with `getattr` (§3.1).
  - `getattr(message, "trace_carrier", None)` although the Protocol declares it:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:106`
    - declaration at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/delivery.py:13`
  - `_secret_value(value: object | None)`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:466-468`.
- **Exceptions (legitimate):**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/genai_content.py`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/llm_client.py:247-273`
- **Priority:** Medium.

### 6.3 Standardize the good idioms already dominant

- **Target:** `code-conventions.md`.
- **Proposed rule (to codify, not to change):**
  > - Value objects are `@dataclass(frozen=True, slots=True)`. Mutable dataclasses are only for explicit state holders, and those get a one-line comment.
  > - Constructors take keyword-only dependencies (`def __init__(self, *, ...)`).
  > - On Python 3.13, use PEP 695 generics (`def f[T](...)`, `type Alias = ...`).
  > - Do not add `from __future__ import annotations`.
  > - Use `TYPE_CHECKING` only for real import cycles or heavy optional imports.
  > - Exception classes end in `Error` (ruff N818).
- **Evidence:**
  - Dataclasses: 95 of 109 are frozen and 108 are slotted.
  - Mixed `TypeVar` styles:
    - `ResultT = TypeVar("ResultT")` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/llm_client.py:27`
    - `def await_with_phase_deadline[ResultT](...)` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/limits.py:263`
  - `from __future__ import annotations` in only 3 files.
  - N818 hits:
    - `RunBudgetExceeded`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/limits.py:15`
    - `LLMRetriesExhausted`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/llm_client.py:68`
- **Priority:** Low.

### 6.4 Package markers: pick one style

- **Target skill:** python-repository-setup (tooling section).
- **Proposed rule:**
  > Every directory under `src/<package>/` that holds modules has an `__init__.py`, empty unless it is a deliberate public surface. Enable ruff `INP001`. Only libraries re-export through `__init__.py`/`__all__`; service packages leave `__init__.py` empty.
- **Evidence:**
  - Worker: 4 of 23 package directories have `__init__.py`. Orchestrator: 3 of 14.
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/pyproject.toml:67` sets `explicit_package_bases = true` to cope.
- **Priority:** Low.

---

## 7. Async, concurrency and resource management

### 7.1 Structured concurrency and one cancel-and-drain helper

- **Target skill:** python-service-architecture, `references/api-and-workers.md:78` (new "Concurrency" subsection).
- **Proposed rule:**
  > - Use `asyncio.TaskGroup` for fan-out where one sibling's failure should cancel the others.
  > - Where callers need the original exception type (to map port errors), use **one** service-owned helper (`gather_or_cancel(*aws)`) instead of re-implementing "cancel pending, then gather with `return_exceptions=True`".
  > - Store or await every `create_task` result. Track background tasks in a set with a done-callback that logs failures.
  > - Every `asyncio.wait(...)` has a `finally` that cancels and awaits pending tasks.
  > - Offload blocking SDKs with `asyncio.to_thread`.
- **Evidence:**
  - Four near-identical cancel/drain blocks:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/resolve_control_context.py:236-240`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:232-236`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/supervisor.py:146-150`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:131-133`
  - 0 `TaskGroup` uses.
- **Good patterns to cite:**
  - Tracked tasks with a done-callback: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/supervisor.py:96-98`, `:134-137`.
  - A bounded graceful drain: `supervisor.py:153-170`.
  - `asyncio.timeout` that does not swallow cancellation: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/limits.py:263-269`.
- **Exceptions:** supervisors that signal a stop event and wait for a graceful exit should not become a `TaskGroup`, which cancels immediately. Say so explicitly (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:102-133`).
- **Priority:** Medium.

### 7.2 Build SDK clients once

- **Target skill:** python-service-architecture, `references/boundaries.md` (adapters).
- **Proposed rule:**
  > Build SDK clients once, in the adapter constructor or in bootstrap, and close them through the owner's lifecycle. boto3 low-level clients are thread-safe and reusable; the default `boto3` session is not. Never call `boto3.client()` inside a function run by `asyncio.to_thread`.
- **Evidence:** a client is created per call, typed `Any`:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/aws/s3_manual_store.py:37`, `:51`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/aws/s3_report_store.py:43`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/adapters/s3_manual_store.py:36`
- **Priority:** Medium.

### 7.3 Inject nondeterminism with one naming and typing convention

- **Target skill:** python-service-architecture, `references/boundaries.md:52-53`. Rewrite the claim that the clock is a port.
- **Proposed rule:**
  > Inject clocks, randomness and id generation as keyword-only typed callables whose defaults are the real effect. Use the same names everywhere:
  > - `clock: Callable[[], datetime]`
  > - `monotonic: Callable[[], float]`
  > - `sleep: Callable[[float], Awaitable[None]]`
  > - `uniform: Callable[[float, float], float]`
  > - `id_factory: Callable[[], UUID]`
  >
  > A Protocol "Clock" port is unnecessary. Do not default a clock inside a function body (`now or datetime.now(UTC)`).
- **Why:** the codebase already does this well in 13 places. The skill's suggestion to model the clock as a port is heavier than the working pattern.
- **Evidence:**
  - Good:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/investigate_exception.py:87`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_investigations.py:47-48`
  - Inconsistent: `sleep: Callable[[float], Any]` and differing names (`clock`, `utc_now`, `random_uniform`) at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/client.py:64-67`.
  - Hidden clock: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/shared/llm_client.py:233`.
- **Priority:** Low–Medium.

---

## 8. Persistence (SQLModel / SQLAlchemy / Alembic)

### 8.1 Transaction ownership: the Unit of Work

- **Target skill:** python-sqlmodel-alembic. Add a new section "Transactions and the unit of work" in `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/python-sqlmodel-alembic/references/engine-and-session.md`, plus one bullet in `SKILL.md` "Core conventions".
- **Proposed rule:**
  > Repositories never call `commit()` or `rollback()`. They may `flush()` to obtain server-generated values.
  >
  > Exactly one of these owns the transaction:
  > - (a) an application-facing Unit of Work: an async context manager that exposes repositories and `commit()`, rolls back on exception and always closes the session; or
  > - (b) an adapter method that is itself one short transaction, such as a lease heartbeat.
  >
  > Open the session in `__aenter__`, not in `__init__`. Translate `SQLAlchemyError`/`OSError` into the port's `…UnavailableError` in both `commit()` and `__aexit__`. When two or more UoWs in one service differ only in repositories and error type, share a private base (`_SessionUnitOfWork(unavailable=...)`).
  >
  > Bootstrap constructs *factories* (session factory, `lambda: UoW(sessions)`). Repositories are built per transaction.
- **Why:** the skill shows a FastAPI `get_session` generator and never says who commits. Each service reinvented the UoW, five times in total.
- **Evidence:**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/unit_of_work.py:18-51`, `:54-85`, `:88-119`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/unit_of_work.py:13-44`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/reconciliation_uow.py:13-44`
  - The session is created in `__init__`: orchestrator `unit_of_work.py:20`.
  - Good: repositories only flush (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/repositories/requests.py:35`), the application commits (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_investigations.py:88`), and a rollback-failure test exists (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/db/test_unit_of_work.py:30-50`).
- **Exceptions:** a single UoW needs no base class. Read-only one-shot helpers may use `async with factory() as s:` directly.
- **Priority:** High.

### 8.2 The DB failure contract

- **Target skill:** python-sqlmodel-alembic, `references/repositories-and-queries.md` (new "Failure contract" section).
- **Proposed rule:**
  > Every public DB-adapter method either returns a port type or raises a port-owned exception. There are two kinds:
  > - **Unavailable:** `SQLAlchemyError`, `OSError`, `TimeoutError`. The caller may retry.
  > - **Integrity/corrupt state:** a named error (`ConfigStateMissingError`, `CorruptOutboxEventError`). Never a bare `RuntimeError`.
  >
  > Translate at the outermost DB boundary: the UoW's commit/exit, or the method that opens its own session. Code outside `db/` never needs `except Exception` to detect a database failure. Let `asyncio.CancelledError` pass through untouched.
- **Evidence:**
  - The lease manager translates nothing: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/lease_manager.py:15-49`. That is why the handler falls back to `except Exception` and *assumes* "database_unavailable" (§3.2).
  - Correct counter-example: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/config_state.py:31-38`.
  - `RuntimeError` for integrity faults:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/repositories/config_state.py:26-27`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/repositories/outbox.py:94`, `:98`
- **Priority:** High.

### 8.3 Per-transaction limits

- **Target skill:** python-sqlmodel-alembic, `references/engine-and-session.md` (new "Per-transaction limits" section).
- **Proposed rule:**
  > - Every query against a database the service does not own, and every batch or maintenance statement against one it does, runs in an explicit transaction. That transaction first sets transaction-local limits with a bound parameter: `SELECT set_config('statement_timeout', :v, true)`, plus `lock_timeout` for writes.
  > - Implement this once per DB package (`apply_transaction_limits(conn, *, statement_ms, lock_ms=None)`). Always pass an explicit unit (`'1500ms'`) and round up to whole milliseconds.
  > - For the service's own OLTP database, set a role-level or engine-level default (`connect_args={"server_settings": {...}}` or `ALTER ROLE … SET`) so no query is unbounded.
- **Evidence:**
  - Four different implementations:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/candidates.py:69-73`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/retention.py:192-200`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/ctc/query_executor.py:101-105` (an f-string `SET LOCAL`)
  - Rounding also differs: `int` in some places, `ceil` in others.
  - Gap: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/exceptions.py:79-106` runs `SELECT *` against the customer database with no statement timeout and no READ ONLY. The engine docstring still claims "per-transaction safeguards live in the query executor" (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/engine.py:1`).
- **Priority:** High (because of the gap); Medium for the standardization.

### 8.4 External read-only databases

- **Target skill:** python-sqlmodel-alembic, new `references/external-read-databases.md`.
- **Proposed rule:**
  > For a database the service does not own:
  > 1. Use a least-privilege read-only role, verified by a runnable acceptance check.
  > 2. Run every query inside `engine.begin()`, starting with `SET TRANSACTION READ ONLY` and the local limits from §8.3.
  > 3. Bound result size in SQL (`LIMIT n+1` to detect truncation, or keyset pagination). Never `fetchall` unbounded.
  > 4. Use no ORM models: `text()`/Core plus mapping into frozen dataclasses.
  > 5. Configure the engine with `max_overflow=0` and an explicit acquisition timeout.
  > 6. Translate errors into one `…SourceUnavailableError`.
- **Evidence (good, the template):**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/candidates.py:68-74`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/acceptance.py:64-73`, which proves the role cannot write
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/ctc/query_executor.py:48-56`, `:151-171`
- **Priority:** High.

### 8.5 Raw SQL safety and identifiers

- **Target skill:** python-sqlmodel-alembic, `references/repositories-and-queries.md` ("Raw SQL safety").
- **Proposed rule:**
  > - Values are always bind parameters, including in `IN (...)`: use `bindparam(..., expanding=True)` or `= ANY(:array)`. Never build literals by string escaping.
  > - Identifiers that cannot be bound go through one validated quoting function, owned by a *public* module of the DB package.
  > - DDL identifiers and passwords use PostgreSQL `format('%I', '%L')`.
  > - Do not route trusted internal queries through the path that validates untrusted (agent) SQL.
- **Evidence:**
  - Good:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/exceptions.py:20`, `:160-163` (allow-list plus quoting)
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/platform_migrations/src/platform_migrations/database_bootstrap.py:81-109` (`format('%I','%L')`)
  - Bad: `"'" + name.replace("'", "''") + "'"` sent through the agent SQL path, at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/ctc/query_executor.py:72-77`.
  - Private helpers imported across modules: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/candidates.py:10`.
- **Priority:** Medium.

### 8.6 State transitions as guarded compare-and-set updates

- **Target skill:** python-sqlmodel-alembic, `references/repositories-and-queries.md` ("Concurrent state changes").
- **Proposed rule:**
  > - A lifecycle transition is one `UPDATE … WHERE <current-state guard> [RETURNING]`. The repository returns `bool` or the new state. It never reads, modifies in Python, then writes.
  > - Guard every column the decision depended on, with `IS NULL` for nullable ones.
  > - After a Core UPDATE, re-read with `populate_existing=True` or use `RETURNING`.
  > - A multi-row `FOR UPDATE` orders by primary key. Queue-like claims use `FOR UPDATE SKIP LOCKED LIMIT n`.
- **Evidence (good, to codify):**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/repositories.py:37-43`, `:46-73`, `:168-185`
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/reconciliation.py:52-63`, `:75-105`
- **Priority:** Medium.

### 8.7 Set-based access, and no locks held across network I/O

- **Target skill:** python-sqlmodel-alembic, `references/repositories-and-queries.md` ("Set-based access") and `references/engine-and-session.md` (UoW section).
- **Proposed rule:**
  > - Repository ports accept collections when callers would otherwise loop. Prefer one multi-row `INSERT … ON CONFLICT … RETURNING` over a per-item loop, and return early on empty input.
  > - A per-row loop inside a transaction is acceptable only when it is bounded by configuration and each row depends on the previous one. State the bound in a comment.
  > - Do not await calls to other systems inside an open DB transaction unless holding the lock is the point. If it is, bound the batch and the external timeout, set `idle_in_transaction_session_timeout`, and add a one-line comment naming the invariant the lock protects.
  > - Code whose correctness depends on READ COMMITTED semantics says so in a comment.
- **Evidence:**
  - About 4–6 round trips per id while locks are held:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_investigations.py:70-87`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/repositories/investigations.py:99`, `:110`
  - NATS publishes inside a `FOR UPDATE SKIP LOCKED` transaction: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/publish_outbox.py:35-55`.
  - Good isolation comment: `investigations.py:108-109`.
- **Priority:** Medium.

### 8.8 Retention and bulk maintenance

- **Target skill:** python-sqlmodel-alembic, `references/repositories-and-queries.md` (new section).
- **Proposed rule:**
  > Scheduled deletes and updates:
  > - are bounded per statement: `DELETE … WHERE id IN (SELECT id … ORDER BY ts, id LIMIT n) RETURNING id`;
  > - commit per batch;
  > - set local statement and lock timeouts;
  > - delete children before parents (or rely on declared `ON DELETE CASCADE`, never both);
  > - guard against deleting rows still referenced by pending work;
  > - hold a `pg_try_advisory_lock` (not a blocking lock) when several replicas run the job, and invalidate the connection if unlock fails;
  > - are backed by a partial index whose predicate the delete implies.
- **Evidence:** the whole of `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/retention.py` is the reference implementation (`:33-76`, `:90-150`, `:192-200`), together with `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/platform_migrations/alembic/versions/20260908_0002_retention_indexes.py:19-31`.
- **Priority:** Medium.

### 8.9 Column vocabularies and typed table access

- **Target skill:** python-sqlmodel-alembic, `references/models-and-base.md`.
- **Proposed rule:**
  > - A column with a closed value set gets a `StrEnum` in the shared models package. Repositories compare and assign only that enum.
  > - Domain enums convert in exactly one pair of functions per repository module. Never pass a domain enum into a column expression.
  > - A predicate reused by a partial index and by queries (`ON CONFLICT … index_where`) is defined once, next to the model.
  > - Pick one column-access style per repository package, and export typed `Table` handles once (§6.1).
- **Evidence:**
  - A domain enum passed straight into a column: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/reconciliation.py:91`, `:96`.
  - Explicit conversion in the same service: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/repositories.py:97`.
  - The active status set is expressed three ways, including a raw SQL literal: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_db/src/platform_db/models/investigation.py:40`.
- **Priority:** Medium.

### 8.10 Engine lifetime, pool sizing, and contract migrations after feature removal

- **Target skill:** python-sqlmodel-alembic, `references/engine-and-session.md` and `references/alembic-migrations.md`.
- **Proposed rule:**
  > - Bootstrap builds engines from resolved settings and registers `engine.dispose` on the runtime's `AsyncExitStack` immediately after creating them. `session.py` exposes `build_session_factory(engine)` and imports no global engine.
  > - One-shot processes (probes, CLIs) may build a pool-of-1 engine and dispose it in `finally`.
  > - Pool sizes come from settings; the builder has no literals and validates sizes. When pool capacity is an intended concurrency or admission cap, or the database is external, set `max_overflow=0`.
  > - When a feature is removed, remove its read/write paths and domain fields in the same change, and file a contract (drop) migration for the next release. Remove dialect variants (`.with_variant(JSON(), "sqlite")`) for databases that nothing uses.
- **Evidence:**
  - Good lifetime management:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/runtime.py:204-215`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:164-179`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/connectivity_probe.py:133-144`
  - Good `max_overflow=0`:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_db/src/platform_db/engine.py:7-18`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/engine.py:12-25`
  - Leftover write-back columns still mapped into domain objects: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_db/src/platform_db/models/investigation.py:119-136`.
- **Priority:** High for the engine-lifetime rewrite, because the skill template is wrong (§12.7). Medium otherwise.

### 8.11 Migration tests and conventions

- **Target skill:** python-sqlmodel-alembic, `references/schema-verification.md` and `references/alembic-migrations.md`.
- **Proposed rule:**
  > - Assert a single head with `ScriptDirectory.from_config(cfg).get_heads()`. Do not count files or grep revision text.
  > - Call Alembic `command.*` from async tests via `asyncio.to_thread`.
  > - Name the disposable-DB variable per database (`INTEGRATION_<DB>_DATABASE_URL`). In CI profiles a missing variable is a **failure**, via a `requires_env`-style marker, not a skip.
  > - Use revision ids `YYYYMMDD_NNNN_<slug>` and keep the generated header docstring.
  > - Make every `downgrade()` an exact inverse, or have it raise deliberately.
  > - Use the naming convention `"uq": "uq_%(table_name)s_%(column_0_N_name)s"`. The current `column_0_name` names only the first column, so multi-column uniques get misleading, colliding names. Choose the convention before the first migration.
- **Evidence:**
  - A brittle count: `assert len(revisions) == 5` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/platform_migrations/tests/contract/test_migration_topology.py:10-35`.
  - Good `to_thread`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/platform_migrations/tests/integration/test_filtered_request_migration.py:28`.
  - The repo's deliberate fail-not-skip policy: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/conftest.py:8-16`.
  - A misleading constraint name: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_db/src/platform_db/base.py:8` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_db/src/platform_db/models/api_request_investigation.py:15`.
- **Priority:** Medium.

---

## 9. Observability

### 9.1 Never disable `set_status_on_exception` on ad-hoc spans

- **Target skill:** otel-observability. Fix the contradiction between:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/otel-observability/references/setup/shared_library.md:150-153` ("must start the span with `record_exception=False` and `set_status_on_exception=False`")
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills/otel-observability/references/conventions/errors.md:50-54` ("leave `set_status_on_exception` at its default")
- **Proposed rule** (in errors.md; remove the conflicting sentence from shared_library.md):
  > Ad-hoc spans pass only `record_exception=False`. Only a generic helper that itself catches `BaseException`, sets `ERROR` and `error.type`, and re-raises may disable `set_status_on_exception`. A narrow `except SpecificError` inside a span does **not** make disabling it safe.
- **Evidence (verified):** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/ctc_candidate_source.py:25-44`. Only `ExceptionSourceUnavailableError` sets `ERROR`; any other exception leaves the span UNSET, so error-biased tail sampling drops the trace. The same flag was copied into `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/observability/filtered_requests.py:57-58`.
- **Priority:** High.

### 9.2 Test telemetry through global in-memory providers, not monkeypatching

- **Target skill:** otel-observability `references/testing.md:37-69` (rewrite). Add a pointer from pytest `references/core-principles.md` (§10.4).
- **Proposed rule:**
  > Module-level `tracer = trace.get_tracer(__name__)` and module-level instruments are the default. They are proxies, bound when the provider is set.
  >
  > Tests install one session-scoped global `TracerProvider(InMemorySpanExporter)` and `MeterProvider(InMemoryMetricReader, views=<production views>)` in `conftest.py`, and clear the exporter per test. Metric assertions filter by a unique attribute or compare before/after values, because cumulative temporality accumulates across tests.
  >
  > Do **not** monkeypatch individual instruments or `trace.get_tracer`. Assert production instrument names, units and bounded attribute keys from the exported data. Inject a tracer or meter only when a class already takes collaborators through its constructor for other reasons.
- **Why:**
  - The skill's fixtures build a *non-global* provider and tell tests to "pass the provider into the code under test".
  - Its own templates create module-level instruments at import time (`references/metrics/service.md:124`).
  - Those two instructions cannot both be followed, so tests fall back to patching. A patched instrument proves nothing about the production name or unit.
- **Evidence:**
  - 23 metric names patched in a loop: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/bootstrap/test_supervisor.py:705-735`.
  - The test recreates production instruments by name: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/observability/test_filtered_requests.py:24-31`.
  - `trace.get_tracer` monkeypatched 11 times: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/observability/test_genai_telemetry.py:31`.
  - Three tracer-acquisition styles in production (injected, module-level, per call).
- **Exceptions:**
  - Code that owns global provider registration is tested in a subprocess, as `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_observability/tests/unit/test_providers.py:98-120` does well.
  - Pure label/outcome functions are tested directly.
- **Priority:** High.

### 9.3 State gauges: observable, one writer

- **Target skill:** otel-observability, `references/metrics/service.md:109-114` (instrument table plus a new "State gauges" paragraph).
- **Proposed rule:**
  > - Current state that lives in an object (in-flight work, pending items, paused flag, queue depth) is an `ObservableGauge` whose callback reads that object, registered once at the composition root.
  > - A synchronous `Gauge.set()` is only for a value computed at one well-defined point, and each gauge has exactly one writer.
  > - Each counter event has one owning call site.
  > - A zero baseline in `initialize_metrics` may cover only instruments with a live writer in that process.
  > - Before adding an instrument, grep all services for the same name. One metric name has exactly one producing service.
- **Evidence:**
  - Same gauges set from two components:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/supervisor.py:118-119`, `:131-132`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/diagnostic_supervisors.py:150-157`
  - Metric recording interleaved five times into `run()`: `supervisor.py:76-95`.
  - `outbox_oldest_pending_age_seconds` is declared in both services. The orchestrator only ever sets it to 0:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/observability/metrics.py:7`, `:18`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/metrics.py:19`
  - Good pattern: `register_ctc_pool_metric` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/metrics.py:100-112`.
- **Priority:** High.

### 9.4 Derive telemetry from results at the boundary

- **Target skill:** otel-observability `SKILL.md` Step 4 and `references/metrics/service.md`. Rewrite python-service-architecture `references/boundaries.md:203-205`.
- **Proposed rule:**
  > The use case returns a result or summary object (counts, outcome, stop reason). The *caller* (supervisor, handler, wrapper) records span attributes, metrics and logs from it.
  > - Do not pass mutable telemetry accumulators into business functions.
  > - Do not call a telemetry function from each return path.
  > - When an adapter must report per-attempt facts, inject a typed callback (`record_outcome: Callable[[Outcome], None]`) from the composition root instead of importing instruments.
  >
  > Wrapper shape: open the span, classify once into `(outcome, error_type)`, and emit once in `finally`. The mapping from domain exceptions to codes lives next to the exceptions, not in the observability module.
- **Evidence:**
  - Good:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/diagnostic_supervisors.py:128-131` (`tick` → `_record_tick`)
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/runtime.py:246-254` (injected `record_outcome`)
  - Bad:
    - `record_agent_result` called from four return paths: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/analyst.py:143`, `:174`, `:187`, `:220`
    - `SelectionTelemetry` mutated 11 times inside business code: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_filtered_investigations.py:74-142`
    - 50-line wrappers that mix five concerns:
      - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/observability/filtered_requests.py:43-96`
      - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/genai.py:96-146`, `:187-235`
- **Exceptions:** counts discovered deep inside framework callbacks (model and tool calls per agent run) may use a context-local accumulator.
- **Priority:** High.

### 9.5 One redaction module shared by every sink

- **Target skill:** otel-observability, `references/setup/shared_library.md` and `references/tracing/genai/content_capture.md`. Clarify `references/logging/structlog.md:51-52`.
- **Proposed rule:**
  > One redaction module (patterns plus a recursive `mask(value)`) is owned by the shared observability library. The log processor and the GenAI content serializer both import it. Each sink (log line, span attribute) has one canary test proving that an `api_key=`, Bearer or AWS-key canary is masked.
- **Evidence:** two divergent regexes:
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_observability/src/platform_observability/logging.py:18-24` does not cover `api_key` or AWS key IDs, and it inspects only top-level values (`:99-105`).
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/genai_content.py:17-24` does cover them.
- **Priority:** High (security).

### 9.6 One vocabulary for outcome and error attributes, and one metric naming scheme

- **Target skill:** otel-observability, `references/conventions/naming.md:130-161` and `:196-210`, and `references/conventions/errors.md:145-171`.
- **Proposed rule:**
  > - Outcome is always `app.outcome`, and error classification is always `error.type`, on both spans and app metrics. Do not introduce `status`, `result`, `outcome` or `error_code` synonyms. A key's meaning never changes between instruments.
  > - Build attribute keys only from literals, never f-strings, so they are greppable.
  > - `error.type` is one of: the exception class name, a provider status/code, or a value from the service's documented closed error-code enum. Unclassified is `_OTHER`, never `internal_error`. Use one style per instrument.
  > - New instruments use `app.<domain>.<noun>` with a UCUM unit and no `_total` or unit suffix. Renaming an existing name is an explicit migration (dual-emit, then remove), never a silent fix.
  > - Keep one short table per service (in its `observability/` module docstring) listing each key and its closed value set.
- **Evidence:**
  - Labels `status`/`error_code` for the same fact that spans record as `app.outcome`/`error.type`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:129-134`, `:333-334`.
  - Two naming schemes in one file: `investigation_total` (exported as `…_total_total`) next to `app.worker.admission.*`, at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/metrics.py:14-51`.
  - f-string keys: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/genai.py:180`, `:215`.
  - The skill's own "anything else is a class name" (`errors.md:170-171`) conflicts with its `:145` and `:166`.
- **Priority:** Medium.

### 9.7 Logging: event names, one API, failure ownership, loops

- **Target skill:** otel-observability, `references/logging/business_events.md`, `references/conventions/naming.md:176-188` and `references/logging/structlog.md`.
- **Proposed rule:**
  > - The first positional argument of a log call is always a snake_case past-tense event name (`investigation_handler_failed`). It is never a sentence, and it never contains values or thresholds. If named OTel events are exported, derive `event_name` mechanically (`app.` + dots) instead of choosing a second name.
  > - A repository uses one call-site logging API: stdlib with `extra=`, or structlog kwargs. Record the choice in the shared library's docstring.
  > - A function that logs a summary *and* re-raises omits `exc_info`. The boundary that finally handles the exception logs it. For HTTP, that boundary is the registered exception handler, for every mapped exception.
  > - In poll, heartbeat and supervisor loops, count every failure but log only on state transitions: healthy→failing with `exc_info`, failing→recovered with the count and duration. A condition already exported as a gauge is alerted from the metric, not logged at ERROR on every pass.
- **Evidence:**
  - Prose events:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/supervisor.py:137`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/bootstrap/reconciliation_supervisor.py:33`, `:52`, `:57` (the last one has a threshold baked into the message)
  - Mixed logging APIs: `filtered_requests.py:28` (structlog) vs `logging.getLogger` in 10 files.
  - Log-and-raise double trace:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/retain_platform_history.py:71-72`
    - plus `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/supervisor.py:134-135`
  - Per-iteration stack traces:
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/consumer.py:138`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:245`, `:253`
- **Exceptions:** a *secondary* exception raised during cleanup while another is propagating is logged where it is suppressed. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/resolve_control_context.py:113-118` is correct.
- **Priority:** Medium.

### 9.8 Smaller observability rules

- **Histograms** (`references/metrics/service.md:118`, `references/setup/sdk_bootstrap.md:122-148`):
  > Declare buckets at creation with `explicit_bucket_boundaries_advisory`, alongside the name and unit. Use a central `View` registry only for third-party instruments. Every histogram that can exceed ~5 s, or that counts tokens or rows, declares boundaries.

  Evidence: no views exist anywhere, so the LLM-duration and token histograms use the default buckets. The colocated form already works at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/observability/filtered_requests.py:22-26`. **Medium.**
- **Redundant instruments:**
  > Before adding a counter, list the instruments that already count the event, including a duration histogram's `_count`.

  Evidence: one CTC attempt is counted three times, at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/client.py:310-313`, `:432-443` and `runtime.py:246-254`. **Low.**
- **Spans are write-only:**
  > Never read attributes back from a span. Pass correlation values explicitly. `gen_ai.usage.*` goes only on the model-call span (and the agent span, if the convention defines it). Roll-ups use `app.*` keys.

  Evidence: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/genai.py:106-108`, `:134-139`. **Medium.**
- **No spans as events:**
  > Do not create a span to represent an occurrence (zero duration, or a name that encodes the outcome). Emit a named log plus a counter. Do not copy `http.*` server attributes onto internal spans.

  Evidence: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/routers/health.py:27-40`. **Low.**
- **Parent vs link:** put a one-line decision table in `SKILL.md` rule 12: outbox publish → link; queue redelivery → link plus `app.message.attempt`; synchronous in-process call → parent. The guidance is correct today but spread over three files. **Medium.**

---

## 10. Testing

### 10.1 Bounded waits: an idiom, not just a principle

- **Target skill:** pytest, `references/core-principles.md:87-90` and `SKILL.md:36-38`.
- **Proposed rule:**
  > - Every `await` on an event, queue, task or future in a test is wrapped in `asyncio.timeout(...)`, with ≤ 1 s for unit tests.
  > - Poll a semantic condition only through one bounded helper (`await wait_until(lambda: …, timeout=1)`). `while cond: await asyncio.sleep(0)` is forbidden.
  > - Do not count event-loop yields (`sleep(0)` followed by an exact-state assertion). Await a signal the code under test emits.
  > - For "nothing happens" assertions, drive a deterministic step (a manual clock plus `tick()`). If a real broker makes that impossible, name the observation window as a constant with a comment and keep the test in the integration profile.
  > - Test builders default to minimal time budgets (≤ 0.1 s). A unit test over ~1 s is a defect; check `--durations`.
- **Evidence:**
  - 16 bare `.wait()` calls, e.g. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/bootstrap/test_supervisor.py:170`.
  - Unbounded busy loops:
    - `test_supervisor.py:544`, `:579`, `:587`
    - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/bootstrap/test_supervisor.py:130`, `:149`
  - Sleep as a negative assertion: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/integration/test_admission_consumer.py:240-247`.
  - A hidden 5 s default that makes one test 43% of the whole hermetic run: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/bootstrap/test_supervisor.py:27-33`, `:183-209`.
- **Bad / good:**
  ```python
  # bad
  while state.actual_inflight:
      await asyncio.sleep(0)
  # good
  async with asyncio.timeout(1):
      await drained.wait()
  ```
- **Exceptions:** `sleep(0)` *inside a fake* to force a context switch, as long as no assertion depends on the number of yields.
- **Priority:** High.

### 10.2 Unit-of-work fakes must be transactional

- **Target skill:** pytest, `references/core-principles.md` ("Use doubles deliberately"), plus an example in `references/examples-core.md`.
- **Proposed rule:**
  > A fake unit of work stages writes and makes them visible only on `commit()`. Leaving the context without committing discards them. Assert durable outcomes on the *committed* store. Counting commits is not a substitute.
- **Evidence:** there are 10 `FakeUnitOfWork` classes, and none of them is transactional:
  - `async def commit(self): return None` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/application/test_request_investigations.py:122-123`
  - a commit counter only, with writes landing before commit: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/application/test_investigate_exception.py:119-134`, `:169-170`
- **Good example:**
  ```python
  class FakeUnitOfWork:
      def __init__(self, store: Store) -> None:
          self.store, self.pending = store, []
      async def __aexit__(self, *exc: object) -> None:
          self.pending.clear()
      async def commit(self) -> None:
          self.store.rows.extend(self.pending)
          self.pending.clear()
  ```
- **Priority:** High.

### 10.3 No assertions inside doubles

- **Target skill:** pytest, `references/core-principles.md` (doubles section).
- **Proposed rule:**
  > Doubles record their arguments, and the test body asserts on them after the action. Never `assert` inside a double when the production code under test wraps that call in a broad `except Exception`. The failed assertion becomes a handled error, and the test passes vacuously. If a double must reject unexpected input, raise a dedicated `UnexpectedCall(BaseException)`.
- **Evidence:**
  - 28 `assert`s inside double methods, e.g. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/adapters/nats/test_handler.py:197-198`.
  - That call is wrapped by `except Exception` in production at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:277`.
- **Priority:** High.

### 10.4 Missing-seam thresholds, and the seam shapes to propose

- **Target skill:** pytest `SKILL.md:45-48` and `references/core-principles.md:35-36`. Also python-service-architecture `references/testing.md` ("Dependency and isolation rules").
- **Proposed rule:**
  > Stop and propose a production seam, instead of adding patches, when a test:
  > - needs more than three `monkeypatch.setattr` calls on one production module;
  > - patches instrument globals or `trace.get_tracer` (use §9.2 instead);
  > - patches `asyncio`/`httpx` module attributes;
  > - raises an exception to abort production code midway;
  > - calls `_private` methods.
  >
  > The seam shapes to propose:
  > - settings→policy mapping as a pure function (`ctc_retry_policy(settings) -> CtcRetryPolicy`);
  > - composition-root lifecycle tested by injecting constructed resources or a builder callable;
  > - a public `tick()`/`poll_once()` on loops (§5.2);
  > - caches observed through factory-call counts, not through their private storage.
- **Evidence:**
  - 10 patches in one test: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/bootstrap/test_runtime.py:96-107`.
  - The "raise to stop composition" trick plus a `SimpleNamespace` cast to `Settings`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/bootstrap/test_runtime.py:71-119`.
  - `analyst._cache` tuple layout locked by a test: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/genai/exception_analysis/test_contextual_analyst.py:47-63`.
- **Exceptions:** one in-process wiring smoke test per service may keep a few patches.
- **Priority:** Medium.

### 10.5 Shared test support: an importable recipe

- **Target skill:** python-service-architecture, `references/testing.md:155-174`. Its current rules are "member-qualified support package", "omit `tests/__init__.py`", importlib mode and no global `pythonpath`. Together they leave no import path. Add a one-line consequence note in pytest `references/examples-core.md:130-136`.
- **Proposed rule:**
  > When the same double, builder or setup appears in **three or more** modules of one member, extract it:
  > - Reusable *instances* (span exporter, manual clock, fake runtime, engine) become fixtures in the narrowest `conftest.py`. No import is needed.
  > - Reusable *types* go in `tests/<profile>/support/<capability>.py` and are imported through **one** mechanism the repository declares, for example an installed `<member>_testing` package in the dev group, or `tests.<…>` packages with `__init__.py` files. State which one, and never rely on bare module names.
  >
  > Counterweight to "fixtures hide the scenario": setup that carries no scenario facts (exporters, clocks, engines) *should* be a fixture once it is repeated.
- **Evidence:**
  - 0 support modules and 0 sub-`conftest.py` files.
  - `FakeUnitOfWork` ×10, `FakeRuntime` ×7, `AcceptingVerifier` ×4 (byte-identical, e.g. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/api/test_report_routes.py:19-34` and `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/api/test_investigation_routes.py:29-44`).
  - The 4-line span-exporter setup ×16.
  - The DB engine fixture ×6, with divergent isolation strategies.
- **Exceptions:** doubles whose scenario-specific behavior *is* the test.
- **Priority:** High.

### 10.6 Mechanical review checklist for the quality gate

- **Target skill:** pytest, `SKILL.md:186-207`. Add a greppable checklist below the prose gate.
- **Proposed rule:** reject a test with any of the following:
  - a bare `.wait()` or `await task` without a timeout;
  - `while …: await asyncio.sleep(0)`;
  - `assert` inside a class used as a double;
  - an asserted variable that no code path under test writes;
  - `pytest.raises((A, B))` in a parametrized test (put the expected exception in the parameter table);
  - an expected value computed with the production expression (with fixed inputs, write the literal);
  - a spec-less `Mock()`/`AsyncMock()` for an application port;
  - `SimpleNamespace` standing in for a constructible library type;
  - `cast(Any, object())`;
  - private `._x` access;
  - a parameter table with more than 3 non-scalar cases and no `pytest.param(..., id=...)`.
- **Evidence:**
  - A variable that is never incremented and then asserted `< 5`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/integration/test_admission_consumer.py:162`, `:175`.
  - A union `pytest.raises` over 5 cases: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/application/test_request_filtered_investigations.py:47-50`.
  - An oracle that copies production logic: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/bootstrap/test_observability.py:53`, `:56`.
  - Spec-less `AsyncMock` for ports: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/unit/application/test_request_filtered_investigations.py:22-29`.
  - A `SimpleNamespace` imitation of `LLMResult`: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/observability/test_genai_telemetry.py:33-45`.
  - Only 4 of 80 parametrizations set ids.
- **Priority:** High.

### 10.7 Keep opt-in suites in step with the code

- **Target skill:** pytest `SKILL.md` ("Writing workflow") and `references/integration-boundaries.md`.
- **Proposed rule:**
  > When you remove or rename behavior, search every profile (integration, e2e, live) and their expected-name constants, and update them in the same change. The hermetic job runs `pytest --collect-only` over all profiles.
  >
  > Once a fail-fast prerequisite hook exists (`requires_env`), delete the per-module `pytest.skip` fallbacks.
- **Evidence:**
  - `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/tests/e2e/test_observability_trace.py:105`, `:135` still expects the `"write CTC comment"` span and "writeback", which were removed in `f112e79`. No production code emits them.
  - 15 dead skip guards, e.g. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/integration/test_admission_consumer.py:26`.
- **Priority:** High.

### 10.8 Smaller testing rules

- **Settings tests** (pytest risk map; cross-link from python-settings-config `SKILL.md:328-332`):
  > Cover validators, cross-field invariants, derived values, redaction and the document↔model contract. Do not assert literal defaults one by one, and do not test that pydantic-settings reads env vars.

  Evidence: 30 literal-default asserts at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/config/test_settings.py:106-149`. **Medium.**
- **Do not reimplement production control flow in tests.** Evidence: a retention loop is rewritten in a test subclass at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/tests/integration/db/test_retention.py:37-67`. **Medium.**
- **Type-check doubles:**
  > Port fakes must satisfy the production Protocol under mypy. Include test support in the type-check run, or add a static conformance line `_: Port = Fake()`.

  Remove the conditional "when the repository type-checks tests" (`core-principles.md:64`, `SKILL.md:212-213`); in this repo it never applies. **Medium.**
- **Log assertions:**
  > Assert logs only when they are a contract. Match the event name and structured fields, never prose. Use one capture mechanism.

  Evidence: `"Reconciliation pass failed" in caplog.text` at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/bootstrap/test_supervisor.py:677`. **Medium.**
- **Destructive integration fixtures:**
  > Use one engine fixture per member. Prefer unique schema or tenant namespaces over table wipes. Any wipe first asserts that the database name is a test database. Broker and stream setup is fixture-owned, with teardown.

  Evidence: unguarded table-wide deletes at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/integration/db/test_platform_repository.py:50-59`. Good per-test schemas at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/tests/integration/test_exceptions.py:76`. **Medium.**
- **Prompt tests:**
  > Keep one reviewed snapshot per prompt, paired with a version constant. Other prompt tests assert invariants with whitespace-normalized matching.

  Evidence: wrap-sensitive fragments at `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/genai/exception_analysis/test_prompts.py:104`, `:106`. **Low.**

---

## 11. Good patterns to write into the skills as positive examples

| Pattern | Evidence | Where to document it |
|---|---|---|
| YAML-policy allowlist, policy fields with no Python default, and a contract test | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:30-111`; `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/contract/config/test_settings_documents.py:74-76` | python-settings-config scaffold |
| Settings confined to bootstrap and mapped to frozen dataclasses | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/consumer.py:33-43` | python-settings-config |
| `@asynccontextmanager` runtime with a single `AsyncExitStack` | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/bootstrap/runtime.py:191-226` | python-service-architecture `boundaries.md` |
| Use-case class: keyword-only dependencies, one `execute`, frozen result | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/application/adjust_admission.py:28-60` | python-service-architecture `templates.md` |
| Consumer-owned Protocols | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:41-72` | python-service-architecture `boundaries.md` |
| Effects injected as typed callables with real defaults | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/application/request_investigations.py:47-48` | `code-conventions.md` |
| Two-step GenAI error translation (framework → GenAI-private → port) | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/genai/exception_analysis/harness.py:29-34`; `analyst.py:141-142` | python-service-architecture `ai.md` |
| Guarded CAS updates with `RETURNING` | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/repositories.py:168-185` | python-sqlmodel-alembic |
| Retention: batched deletes, advisory lock, local timeouts | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/retention.py` | python-sqlmodel-alembic |
| Read-only external DB access with a privilege acceptance probe | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/acceptance.py:64-73` | python-sqlmodel-alembic |
| Retry: whole transaction only, classified by type, injected sleep and jitter | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/ctc/query_executor.py:48-65`, `:116-147` | python-sqlmodel-alembic |
| Observable gauge read at collection time | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/observability/metrics.py:100-112` | otel-observability `metrics/service.md` |
| Bounded-label normalization at the source | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/ctc/client.py:424-429` | otel-observability `naming.md` |
| An ordered effect log to prove "commit before ack" | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/unit/adapters/nats/test_handler.py:248` | pytest `examples-workers.md` (framework-neutral) |
| Fail-fast infrastructure prerequisite hook | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/conftest.py:8-16` | pytest `integration-boundaries.md` |
| Architecture gate with a mutation self-test | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/tests/contract/architecture/test_service_boundaries.py:330-404` | python-service-architecture `testing.md` |
| Subprocess isolation for set-once globals | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_observability/tests/unit/test_providers.py:98-120` | otel-observability `testing.md` |
| Why-only comments (all 11 inline comments in `src` explain *why*) | `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/db/platform/repositories.py:37-38` | `CLAUDE.md` #3 as the example |

---

## 12. Critique of the existing skills: rewrite, merge or remove

Skill root: `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/.agents/skills`.

### 12.1 python-settings-config

| Location | Problem | Recommendation |
|---|---|---|
| `SKILL.md:247-248`; `references/settings-py.md:74` | Mandates a `description=` on every field. This produced descriptions that restate the name in the orchestrator, and was ignored in the worker. | Replace with the §2.1 rule. |
| `SKILL.md:45`, `:237-238`; `references/settings-py.md:78`, `:290`, `:427` | `Field(...)` with an ellipsis is redundant in Pydantic v2. | "A field without a default is required; do not write `Field(...)`." |
| `references/settings-py.md:436-469`; `references/config-yaml.md:192-227` | The YAML scaffold gives YAML-owned fields Python defaults as well, so the value has two homes. | Rewrite per §2.5. |
| `references/config-yaml.md:194`, `:208`, `:220` | YAML examples set `environment_name`, which contradicts `SKILL.md:236-238`. | Remove it from the examples. |
| `references/config-yaml.md:197-198`; `references/settings-py.md:441-450` | Host and port appear in YAML, although the skill classifies topology as env-only. | Remove them, or carve out "container bind address" explicitly. |
| `references/env-example.md:49-62`, `:170-235` vs `:84-86` | Two incompatible `.env.example` structures: 5 sections vs "exactly three". | Keep the 3-section taxonomy only. Allow command-scoped REQUIRED subsections for one-shot jobs, and omit empty sections. |
| `references/env-example.md:84-86` | "One-line comment per variable" produces comments that restate the name. | "Comment a variable when name, type and value do not already say what it is, its unit, or what omission does." |
| `references/env-example.md:100-102`, `:125-126` | "Baseline value" does not say which environment layer it means. | "Show the value resolved for `ENVIRONMENT_NAME=local`, and say so in the section header." |
| `SKILL.md:245-246`; `references/env-example.md:130-134` | "Safe default ⇒ YAML" is over-rigid. | Add the diagnostic/telemetry carve-out from §2.10. |
| `SKILL.md:57-59` | Nesting "pays off" at "several dozen+" fields. The worker has 106 flat fields and stays readable. | "Prefer flat fields with consistent prefixes; nesting changes the env contract and needs an explicit reason." |
| `SKILL.md:271` | "Validate … during FastAPI startup" is too narrow; the worker is a NATS consumer. | "Validate at process start, before accepting traffic or consuming messages." |
| `references/settings-py.md:140-141` | `PositiveFloat` for timeouts conflicts with `FiniteFloat`. | Merge per §2.3. |
| `references/settings-py.md:63-67` vs `:239` | The flat scaffold requires `case_sensitive=True` plus aliases, while the nested scaffold does not. | See §2.2. |
| `references/secrets-py.md:94-111`, `:144-150` | The scaffolds lack `hide_input_in_errors`, and required secrets accept `""`. | See §2.4. |
| `references/secrets-py.md:162-220` | A `SecretsProvider` ABC with one remote implementation plus a mutable module-global cache. | Use a plain `load_secrets(settings) -> Secrets` with an `if`. Add a Protocol only when there are two or more remote backends. Cache at bootstrap. |
| `SKILL.md:175` vs repo | The skill doesn't say whether empty `services/<svc>.<env>.yaml` override files should exist. The repo keeps `{}` files, and a test requires them. | "Do not create empty override layers; the loader treats them as optional." |

### 12.2 python-service-architecture

| Location | Problem | Recommendation |
|---|---|---|
| `SKILL.md:81-86` vs `CLAUDE.md:25-29` | Contradiction over business-capability packages. | Rewrite both per §1.3. |
| `references/ai.md:3-6`, `:193`, `:183-185` | "Mandatory even for one small model call", "Every task has `llm.py`" and the undefined "meaningful construction policy" together produced three identical factories. | Rewrite per §5.10. |
| `references/ai.md:54` vs audit `SKILL.md:79-80` | The two skills disagree on tool layout: a `tools.py` of a few tools vs one tool per module. | "A few cohesive tools may share `tools.py`; convert to `tools/<tool>.py` when tools gain their own schemas." The audit skill should reference this rule rather than restate it. |
| `references/ai.md:284-286` | "Deterministic fallback selection" forbidden in GenAI is too absolute. | "GenAI may return a typed incomplete/degraded result as part of the port contract; application decides what it means." |
| `references/ai.md:210`, `:229` | Example signatures are untyped and would fail the mandated mypy strict setting. Agents copy examples literally. | Add return and parameter types (`-> BaseChatModel`, `tools: Sequence[BaseTool]`). |
| `references/ai.md:28-43` vs `references/templates.md:37-40` | `core/context.py` appears in the ordinary GenAI tree, while `templates.md` says `core/` is absent by default. | Mark it as conditional. |
| `references/boundaries.md:43-50` | The "at least two of three" port-admission test passes almost any I/O. | Replace it with the single question in §5.5. |
| `references/boundaries.md:52-53` | Suggests the clock as a port. | Replace with typed callables (§7.3). |
| `references/boundaries.md:80-82` | "A fixed database … often does not need a second Protocol." Here the UoW Protocols make four application test files possible. | "Add a repository/UoW Protocol when application state-transition logic is unit-tested with fakes; skip it for thin CRUD pass-through." |
| `references/boundaries.md:203-205` | "May call a narrow telemetry helper" is vague. | Replace per §9.4. |
| `references/shared-libraries.md:160` | "Avoid mutable module-global state" is absolute, yet OTel providers are process singletons. | Add the exception: "process-singleton SDK state behind idempotent configure/shutdown and a test reset hook". |
| `references/modularization.md:69-71` | Temporary re-exports have no removal trigger. | "Remove in the same change once in-repo consumers migrate." |
| `SKILL.md:93-99`, `references/boundaries.md:109-126`, `references/api-and-workers.md:100-127` | The flat-first adapter rule is stated three times. | Keep it once, in `boundaries.md`, and link to it from the others. |
| `SKILL.md:130-132` and `references/boundaries.md:298-305` | The absolute-imports rule is stated twice, and ruff TID252 already enforces it. | Keep one sentence plus "enforced by ruff TID252". |
| `references/boundaries.md:307-337` | Duplicates the audit skill's semantic checklist. | Keep the checklist only in the audit skill. |
| `references/templates.md:37-40` and `references/boundaries.md:167-173` | `core/` guidance appears twice. | Keep it once. |
| `SKILL.md:133-140` | The YAML-location invariant belongs to python-settings-config. | Replace with a one-line pointer. |
| `references/boundaries.md:293-296` | "External naming" is one sentence with no check. | Give a concrete check (identical service name across pyproject, package, container and `service.name`) or remove it. |
| `references/testing.md:169-174` | The rules for importing test support cannot all be satisfied at once. | Replace with §10.5. |
| `references/testing.md` vs the pytest skill | Duplicated rules have started to diverge in wording: narrowest fixtures, the conftest-import ban, markers, the silent-skip ban, clock injection. | `testing.md` owns placement and profile layout only, and links to pytest for mechanics. |

### 12.3 python-service-architecture-audit

| Location | Problem | Recommendation |
|---|---|---|
| `SKILL.md:55-56` | "No universal adapter hierarchy" reads as a ban on shared retry bases. | See §3.1. |
| `SKILL.md:141-170` | "Do not stop at a chat-only report just because the user called the task an audit". The skill then mandates an OpenSpec proposal, or `FEEDBACK.md` plus implementing fixes. That is heavy ceremony, and it overrides a plain "audit" request. | "Default: report the findings with a recommended route. Create a proposal or `FEEDBACK.md`, or implement fixes, only when the user asks for repair." |
| `scripts/audit_service.py:11-26`, `:59-65` | It returned 0 findings on both services while missing `api → bootstrap` imports. | Add `api`, `adapters` and `observability` to `INTERNAL_FORBIDDEN`. Add `traceparent`, `trace_carrier`, `stream_seq` and `delivery_attempt` to the transport fields. Add REVIEW notices for: `getattr(<exc>, …)` in `except`; `X \| None = None` constructor parameters in `application/`/`genai/`; `datetime.now`/`uuid4`/`random.` in `domain/`/`application/` outside default arguments; `text(`/`execute(` in `bootstrap/`; functions over ~60 lines in `bootstrap/`; identical `genai/*/llm.py` bodies. |

### 12.4 python-sqlmodel-alembic

| Location | Problem | Recommendation |
|---|---|---|
| `references/engine-and-session.md:20`, `:85` | A module-level global `engine`, which contradicts bootstrap ownership. | Rewrite per §8.10. |
| `references/engine-and-session.md:94-97`, `:111-115` | `get_session` for `Depends` has no commit owner. The orchestrator copied it as the dead `session_scope`. | Replace with the UoW section (§8.1). Mention `Depends` only for request-scoped designs. |
| `references/engine-and-session.md:12-14`, `:59-60` | Literal `pool_size=10, max_overflow=5`. | Take sizes from settings, and add the `max_overflow=0` case. |
| `SKILL.md:88-90` | "Never create an engine per call" ignores one-shot processes. | Add the pool-of-1 plus `finally` exception. |
| `SKILL.md:91-94` | "`repositories/` is the only code that imports `AsyncSession`/`text()`" is too narrow: UoWs, lease managers, retention and external readers also live in `db/`. | "Only the service's `db/` package (and shared DB libraries) imports these." |
| `SKILL.md:95-98`; `references/repositories-and-queries.md:43-46` | "Multi-join SQL goes in `.sql` files" is over-rigid. The repo has zero `.sql` files, and its complex queries compose dynamically. | "Prefer Core for queries that compose or vary. Use `.sql` files only for long, static reporting queries." |
| `SKILL.md:79-81` | "Async only" doesn't mention the sync `Connection` inside `run_sync`. | Add that exception. |
| `references/repositories-and-queries.md:29-33` | "Bootstrap constructs `UserRepository(session)`" is impossible with per-UoW sessions. | "Bootstrap constructs session and UoW factories." |
| `references/models-and-base.md:23` | The `uq` naming convention uses `column_0_name`. | Use `column_0_N_name` (§8.11). |
| `references/schema-verification.md:97-98` | "Skip when unset" conflicts with the repo's fail-fast policy. | Rewrite per §8.11. |
| `references/alembic-migrations.md:185-187` | The single-head check has no mechanism, so agents wrote a file-count test. | Give the three-line `get_heads()` test. |
| `references/engine-and-session.md:30-36` | The "declare `greenlet`" rule is applied unevenly across members. | Say it applies to every member importing `sqlalchemy.ext.asyncio`, or drop it in favour of the lockfile. |
| Whole skill | No guidance on transactions, failure contracts, timeouts, external databases, SQL identifiers, CAS updates, set-based access, retention or retry. | Add §8.1–8.8 as short sections. Use this repo's code as the positive example. |

### 12.5 otel-observability

| Location | Problem | Recommendation |
|---|---|---|
| `references/setup/shared_library.md:151-152` vs `references/conventions/errors.md:52-54` | A direct contradiction that already caused a defect. | See §9.1. |
| `references/testing.md:37-69` vs `references/metrics/service.md:124` | The fixtures cannot observe the templates' module-level instruments. | See §9.2. The fixture should yield `(provider, exporter)` or install global providers, and helpers should use the declared support location. |
| `references/metrics/service.md:109-114` | The instrument table omits the synchronous `Gauge` and the single-writer rule. | See §9.3. |
| `references/conventions/errors.md:170-171` | "Anything else is a class name" is over-rigid and conflicts with the same file's `:145` and `:166`. | See §9.6. |
| `references/conventions/errors.md:107-109`, `:207`; `references/logging/structlog.md:251-253` | Two names per event. | Keep snake_case only, and derive the OTel name mechanically. |
| `SKILL.md:237-242` | Mandates specific file names (`genai_metrics.py`, `agent_counters.py`), which conflicts with `references/setup/package_layout.md:7-9` ("follow the project"). | "Put them in the service's existing metrics module unless it is already large." |
| `references/metrics/genai.md:33` | "Every recorder is a function" adds a wrapper layer even for single-call-site instruments. | "Add a recorder when an instrument is recorded from two or more call sites or needs normalization." |
| `references/conventions/naming.md:208-210` | Pushes a constants module even for spec-defined keys such as `error.type`. | "Semconv keys may be literals. Centralize only `app.*` keys used in two or more modules, plus closed value sets." |
| `references/setup/package_layout.md:26` | "`metrics.py` ← provider, readers, instrument definitions" mixes setup with instruments and produces a 45-instrument catch-all. | "Provider setup lives in bootstrap or the shared lib. Instruments live with their capability once a module passes ~15 instruments." |
| `SKILL.md:76-86` (rule 8) | GenAI projection detail inside the rules that apply to *every* implementation. | Keep two sentences and move the rest to `tracing/genai/content_capture.md`. |
| `SKILL.md:87`, `references/conventions/errors.md:43-49` and `:235`, `references/logging/structlog.md:215-218` and `:242`, `references/logging/business_events.md:67-70` | The `LOG_FULL_EXCEPTION_TRACE` contract is restated six or more times. | State it once in errors.md and link to it elsewhere. |
| `references/logging/business_events.md:18`, `:21` | Default `job_started`/`job_completed` events, plus a warning per recovered failure, conflict with `structlog.md:233` and cause log spam in loops. | "Default worker events: `job_failed` (owner) plus one terminal business event. In loops, log transitions, not iterations." |
| `references/metrics/genai.md:14-24` | Lists `gen_ai.*` metric names without their convention status, while `SKILL.md:69` forbids inventing `gen_ai.*` keys. | Mark each row stable, development or app-defined. Move non-spec rows to `app.gen_ai.*`. |
| `SKILL.md:61` | Routes to `opentelemetry/` and `architecture/02_metrics_design_cheatsheet.md`, which don't exist in this repo. | "Read the repo's observability docs if any." |
| `references/setup/shared_library.md:132-141`, `:209-218` | Requires idempotent same-config init, conflict detection, a threaded bounded shutdown and more, even for a single bootstrap call. That produced a 271-line lifecycle library that detects foreign providers by private SDK class names (`/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_observability/src/platform_observability/providers.py:88-93`). | "Implement only the invariants a current consumer exercises. With one bootstrap call per process, 'configure once; raise on a second call' is enough." |
| Overall size (about 300-line router plus about 10.5k lines of references; Audit mode loads about 1.7k lines) | "Complete" templates with no size guidance push agents toward building every layer. | Add a **"Minimum viable instrumentation"** section to `SKILL.md` Step 2: boundary spans, one error helper, a few outcome metrics, and owner logs. Every further layer needs a named consumer (`CLAUDE.md` #9). |

### 12.6 pytest

| Location | Problem | Recommendation |
|---|---|---|
| `references/core-principles.md:87-90`; `SKILL.md:36-38` | A goal with no idiom, and no guidance for negative assertions. | See §10.1. |
| `references/core-principles.md:64`; `SKILL.md:212-213` | Typing rules conditional on "if the repo type-checks tests" never fire here. | See §10.8. |
| `references/core-principles.md:62-63`; `references/examples-core.md:130-136` | The support-module rule has no mechanism, and importlib mode's consequence goes unstated. | See §10.5. |
| `SKILL.md:168-169`; `references/core-principles.md:45` | One-sided fixture advice ("fixtures hide scenarios"). The repo ended up with 0 unit fixtures and 16 copies of the same setup. | Add the counterweight from §10.5. |
| `SKILL.md:45-48` | "Explain a missing seam" has no threshold. | See §10.4. |
| `SKILL.md:186-207` | The prose-only quality gate has no mechanical checks. | Add the §10.6 checklist. |
| `references/workers.md:36-62`; `references/examples-workers.md:7-75` | Celery-centric and irrelevant to asyncio/NATS workers. | Move Celery and RQ into a subsection. Add framework-neutral asyncio examples: an effect log, a public `tick()`, a bounded drain. |
| (missing) | No telemetry-testing guidance at all. | Add a pointer to otel `references/testing.md` (§9.2). |

### 12.7 python-repository-setup

| Location | Problem | Recommendation |
|---|---|---|
| `SKILL.md:287-291`; `references/pre-commit.md:108-113`; `assets/workspace-template/pyproject.toml:23-27` | The ruff selection cannot back any CLAUDE.md threshold. | See §1.2. |
| `SKILL.md:304-307` | The mypy block has no Pydantic plugin and no stubs policy. | See §6.1. |
| (missing) | No package-marker convention, and mypy does not cover test support. | See §6.4. Type-check `tests/**/support` and conftest files. |

---

## Appendix A: Measurements

**Source code (`libs/*/src`, `services/*/src`)**

| Metric | Count |
|---|---|
| Functions longer than 40 lines | 44 (the longest is 220) |
| ruff C901 / PLR0912 / PLR0915 | 5 / 2 / 1 |
| `# type: ignore` / `cast(` / `Any` | 43 / 35 / 109 |
| `getattr(` | 40 |
| `except Exception` / bare `except` | 21 / 0 |
| `create_task` / `gather` / `TaskGroup` | 18 / 8 / 0 |
| Dataclasses that are frozen / slotted | 95 / 108 (of 109) |
| `StrEnum` / `Literal[` / `Protocol` | 23 / 25 / 48 |
| `Field(` / of which with `description=` | 219 / 40 (settings: 145 fields, 28 descriptions) |
| Decorative banners / commented-out code / TODO / `noqa` | 0 / 0 / 0 / 0 |

**Tests**

| Metric | Count |
|---|---|
| Hermetic suite | 894 passed in 11.65 s (one test takes 5.00 s) |
| `monkeypatch` uses / of which `setattr` | 230 / 97 |
| Test-local classes | 180 (about 19% of unit-test lines) |
| `conftest.py` files below the root | 0 |
| Bare `.wait()` / busy loops | 16 / 5 |

## Appendix B: Incidental defects found (not skill work)

These are concrete bugs, not skill changes. They are listed so they are not lost, and each is linked to the rule that would have prevented it.

1. **Spans left UNSET on unexpected errors**, so error-biased sampling drops those traces. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/db/ctc_candidate_source.py:25-44` (§9.1).
2. **Claim failures swallowed and mislabeled "database_unavailable" with no log.** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/handler.py:152-154` (§3.2, §8.2).
3. **A `ValueError` escapes `receive()` and the sequence stays pending, so every reconcile pass fails again.** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/adapters/nats/max_delivery_advisories.py:106-108` (§3.2).
4. **Timeout fields accept `inf`**, e.g. `LEASE_SECONDS`. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/settings.py:193` (§2.3).
5. **The CTC exception fetch has no statement timeout and no READ ONLY transaction.** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/ctc_database/src/ctc_database/exceptions.py:79-106` (§8.3).
6. **Log redaction misses `api_key=` and AWS key IDs**, which span redaction does mask. `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/libs/platform_observability/src/platform_observability/logging.py:18-24` (§9.5).
7. **`outbox_oldest_pending_age_seconds` is also emitted as a constant 0 by the orchestrator.** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/observability/metrics.py:7`, `:18` (§9.3).
8. **Missing `hide_input_in_errors`, and empty secrets accepted, in the worker.** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/src/worker/config/secrets.py:13-23` (§2.4).
9. **Request models ignore unknown keys, including on the destructive reset endpoint.** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/orchestrator/src/orchestrator/api/schemas/config.py:6-9` (§2.11).
10. **Stale e2e expectation of the removed write-back span.** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/tests/e2e/test_observability_trace.py:105` (§10.7).
11. **Vacuous integration assertion.** `/Users/arafiet/OpsFleet/Projects/Gresham/GreshamNew/Control/services/worker/tests/integration/test_admission_consumer.py:162`, `:175` (§10.6).
