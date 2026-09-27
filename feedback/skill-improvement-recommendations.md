# Skill Improvement Recommendations: Evidence from `libs/` and `services/`

**Date:** 2026-09-27
**Scope reviewed:** Python code only.
- Source: `/Users/arafiet/MyProjects/Deep-Analyst/libs/{evidence_model,observability}` and `/Users/arafiet/MyProjects/Deep-Analyst/services/{ingestion,investigation_agent}`. That is 173 production modules (about 19k lines) and 88 test files (371 tests).
- `services/investigation_web` is TypeScript, so none of these skills apply to it and it was not reviewed.

**Skills reviewed:**
- `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/otel-observability`
- `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-repository-setup`
- `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture`
- `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture-audit`
- `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-settings-config`
- `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-sqlmodel-alembic`
- `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/pytest`
- `/Users/arafiet/MyProjects/Deep-Analyst/CLAUDE.md`, which is always loaded and so acts as a skill

**Method:**
- Read every skill in full, including its references.
- Scanned the code with grep counts, AST scripts, and read-only `ruff`/`mypy` runs with extra rule families enabled.
- Ran two runtime reproductions (secret leakage, and YAML versus code defaults).
- Re-checked the most important claims by hand before including them.
- Line numbers refer to the working tree on the date above.

This document proposes changes to the skills. Code examples appear only as evidence for rules that apply beyond the example. It is not a list of bugs to fix, although a few of the evidence items are real defects and are marked as such.

---

## 0. Executive summary

### What the codebase already does well (standardize it; don't disturb it)

- There is no `unittest.mock` anywhere in 371 tests. Tests use typed fakes and recorders and assert on resulting state.
- Typing is modern: PEP 604 unions everywhere, PEP 695 generics and `type` aliases, Protocols rather than ABCs (32 versus 0), and 54 of 74 dataclasses are `frozen=True, slots=True`.
- There are zero relative imports and no `utils.py`, `helpers.py` or `common.py` modules.
- Validated policy value objects are built from settings in bootstrap. Examples: `RetryPolicy`, `InvocationPolicy`, `PoolBounds`.
- One unit of work per port method: `SqlEvidenceStore` owns the transaction and repositories never commit.
- Guarded read-only execution of LLM-authored SQL uses AST allowlisting, a read-only role, transaction-local timeouts and bounded fetch.
- Comments are sparse and mostly explain why. Docstrings are one-line contracts.
- Telemetry usually stays out of the way: `with phase_span("x"):` one-liners, and middleware-owned spans.

### Where the skills are failing

1. **The skills teach some of the bad patterns.**
   - `python-settings-config` requires `Field(..., description=...)` and an alias on every field.
   - `python-service-architecture` requires an `llm.py` file in every GenAI task, which led to a 7-line re-export module.
   - The otel snippets teach a redundant `except CancelledError: raise`.
   - The pytest and architecture testing references ask for importable support modules but never say how to make them importable under `--import-mode=importlib`. The repo worked around this with a fixture that returns `sys.modules[__name__]`.
2. **Duplicated rules decay, and single-owner rules hold.**
   - The `LOG_FULL_EXCEPTION_TRACE` rule is stated about 18 times across 10 otel files. Every consumer still violates it.
   - "Flat-first" is stated in 7 places. Test classification is stated in 3.
   - The skills also contradict each other: audit script versus architecture skill on telemetry in `application/`; audit versus `ai.md` on tool layout; the otel files among themselves on `set_status_on_exception`; `.env.example` described as having three sections in one place and five in another.
3. **Missing topics produce the most serious defects.** None of these has a home today:
   - error-handling design (broad `except`, fallback recording, exception→HTTP mapping);
   - async and resource lifecycle;
   - raw-SQL/psycopg access;
   - code-level idioms (closed vocabularies, `Any` policy, helper reuse).
4. **CLAUDE.md spends words on rules that tooling already enforces** (bare `except`, mutable defaults, type hints) while missing rules that tooling cannot enforce. Its rule 9 ("prefer duplication") is being read as permission to copy semantically identical helpers. One result: 6 canonical-JSON hash helpers in one service, with 4 different serialization flag sets.
5. **`python-sqlmodel-alembic` does not match the repository.**
   - There is no Alembic, and half the database access uses raw `psycopg`.
   - The skill is silent on what the code actually depends on: roles, read-only transactions, timeouts, bulk upsert and raw SQL composition.

### Top 12 recommendations (by expected impact)

| # | Recommendation | Target | Priority |
|---|---|---|---|
| 1 | Replace the "always `Field(..., description=)`" rule with the "Field only when informative" rule, and use `alias_generator` instead of per-field aliases | `python-settings-config` | High |
| 2 | YAML-owned keys get no Python default, and a missing baseline file fails startup | `python-settings-config` | High |
| 3 | Secret-safe validation errors (`from None` or `hide_input_in_errors`); a credential-bearing DSN is always `SecretStr` | `python-settings-config` | High |
| 4 | New `references/errors.md`: broad-`except` shapes, fallback recording, translate-once, exhaustive exception→transport table | `python-service-architecture` (+ CLAUDE.md rule 7) | High |
| 5 | New `references/code-idioms.md`: closed vocabularies, `Any` policy, search-before-helper, `kw_only`, `__all__` scope | `python-service-architecture` (+ CLAUDE.md rules 6 and 9) | High |
| 6 | New `references/async-and-lifecycle.md`: `AsyncExitStack`, `to_thread`, deadline propagation, a single retry owner, cancellation idioms | `python-service-architecture` | High |
| 7 | Document the test-support package mechanism (`pythonpath` + member-qualified package) and ban `sys.modules`/class-returning fixtures | `python-service-architecture/references/testing.md` + `pytest` | High |
| 8 | Ports: no `Any`/`object`/framework payloads; `ports/` holds only application-facing contracts | `python-service-architecture` + audit script | High |
| 9 | Drop the file mandates (`llm.py`, `agent.py`), keep the ownership rules | `python-service-architecture` | High |
| 10 | Split the DB skill: SQLModel/Alembic becomes one reference, raw psycopg another; add transaction ownership, untrusted-SQL, bulk-write and schema-ownership rules | `python-sqlmodel-alembic` | High |
| 11 | Give each otel rule exactly one owner file; add telemetry-failure isolation and an intrusion budget; fix contradictory snippets | `otel-observability` | High |
| 12 | Move enforceable rules into ruff/mypy and remove them from prose | `python-repository-setup` + root `pyproject.toml` | Medium |

---

## 1. Cross-cutting: how the skills are organized

These recommendations concern the skill set as a whole. They matter more than any single rule, because they decide whether the rules get followed.

### 1.1 Every rule has exactly one owner file; everything else links to it

- **Target skill:** all of them. Most urgently `otel-observability`, `python-service-architecture` and `pytest`.
- **Proposed guideline (for skill authors):** State each normative rule once, in the file that owns the topic. Other files use one line: "See `<file>#<section>`." Do not restate a rule in different words. Paraphrases drift, and agents cannot tell which version is authoritative.
- **Why:** The evidence shows that repeating a rule does not get it followed. It spends context budget and creates contradictions.
- **Evidence:**
  - `log_full_exception_trace` is stated about 18 times: `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/otel-observability/SKILL.md:87`, `references/conventions/errors.md:43-49`, `references/logging/structlog.md:215-218,242,414`, `references/setup/package_layout.md:169-173,206`, `references/setup/shared_library.md:178,216`, `references/testing.md:173`, among others. Yet:
    - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/bootstrap/app.py:53,69-71` derives the policy from the environment name, which is the thing the rule forbids.
    - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/bootstrap/runtime.py:195` hard-codes `exception_detail="full"`.
    - Neither service declares the setting.
  - "Flat-first" package growth is stated in 7 places: `python-service-architecture/SKILL.md:93-99,112-115`, `references/boundaries.md:19-35,107-126`, `references/api-and-workers.md:100-127`, `references/shared-libraries.md:58-103`, `references/templates.md:85-87`, `references/modularization.md:62-63`.
  - Test classification, markers and CI appear in `pytest/SKILL.md:92-117`, `pytest/references/integration-boundaries.md:81-107`, `pytest/references/examples-core.md:124-151` and `python-service-architecture/references/testing.md:29-67,197-215`.
  - The same `.env`/YAML precedence is stated 4 times in `python-settings-config`, and "GenAI coordinates are env-only" 5 times.
- **Priority:** High

### 1.2 Resolve contradictions between skills, and within a skill

- **Target skill:** listed per row.
- **Proposed change:** Fix each contradiction below. Agents faced with conflicting instructions pick one arbitrarily, and the codebase shows both choices being made.

| Contradiction | Location A | Location B | Resolution |
|---|---|---|---|
| Telemetry in `application/` | `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/boundaries.md:203-205` ("Application… may call a narrow telemetry helper") | `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture-audit/scripts/audit_service.py:27,35` (forbids `opentelemetry` in application) | Application code may use the service's own `observability/` helpers but not `opentelemetry` types. Make the script agree (see §6.8). |
| Tool module layout | audit `SKILL.md:79-80` ("one exposed tool per module") | `python-service-architecture/references/ai.md:54` (`tools.py # A few cohesive tools`) | The architecture skill owns this rule. The audit skill cites it. |
| Bootstrap injects raw handles? | audit `SKILL.md:75-76` ("capability implementation rather than a raw client, model…") | `ai.md:249-263` (bootstrap passes raw models to `build_agent`) | "Application actions receive capability implementations. Raw handles go only into genai/adapter constructors." |
| `set_status_on_exception` | `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/otel-observability/references/conventions/errors.md:52-54` (leave default) | `otel-observability/references/setup/shared_library.md:152` (pass `False`) | Keep the `shared_library.md` version, which the code follows. Delete the other. |
| Module-global logger identity | `otel-observability/references/logging/structlog.md:89` (binds `service.name` at import) | `shared_library.md:184-185` (forbids that) | Fix the `structlog.md` example. |
| Exception field name | `structlog.md:53` (`exception.stacktrace`) | Shared library emits `exception` (`/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/logging.py:111`) | Pick one and update the other. |
| `.env.example` sections | `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-settings-config/SKILL.md:240-246`, `references/env-example.md:84` ("exactly three") | `references/env-example.md:49-62,170-235` (five sections plus a five-section template) | Keep three, which the code and the contract tests implement. Allow named sub-sections inside REQUIRED for secrets. |
| `ENVIRONMENT_NAME` has no YAML default | `python-settings-config/SKILL.md:236-239` | `references/config-yaml.md:194,207,220` (YAML examples set it) | Remove it from the YAML examples. |
| Host/port are env-only | `python-settings-config/SKILL.md:78-85` | `config-yaml.md:163,197-198,210-211,223-224`; `settings-py.md:441-450` (YAML and defaults for `app_host`/`app_port`) | Remove them from the examples and scaffolds. Add one ruling on collector/OTLP endpoints, which the repo puts in YAML: `/Users/arafiet/MyProjects/Deep-Analyst/config/ingestion/local.yaml:32`. |
| Class-default fallback | `python-settings-config/SKILL.md:67-69` ("one authoritative home") | `config-yaml.md:83-85,156` ("Otherwise use a Pydantic field default") | Delete the fallback sentences (see §2.2). |
| Framework-behaviour tests | `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/pytest/SKILL.md:195-196` (reject tests of LangGraph features) | The repo's most valuable upgrade guard is exactly such a test (`/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/contract/framework/test_pinned_langchain_langgraph.py`) | Add a "framework characterization" profile with constraints (§9.9). |
| File-per-table | `python-sqlmodel-alembic/references/models-and-base.md:65,81` | `python-service-architecture/references/boundaries.md:21-35` (flat-first) | "Split when a table develops relationships or behaviour." |
| Import-time engine singleton | `python-sqlmodel-alembic/references/engine-and-session.md:20,38-39,85` | `python-service-architecture/references/boundaries.md:144-146,324-326` (bootstrap constructs handles) | Delete the import-time example. The repo already follows bootstrap construction: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/engine.py:15-26`. |

- **Priority:** High

### 1.3 CLAUDE.md should state what tooling cannot check, and nothing that it can

- **Target:** `/Users/arafiet/MyProjects/Deep-Analyst/CLAUDE.md`
- **Proposed change:**
  - **Remove** clauses already enforced by the root `pyproject.toml` (`/Users/arafiet/MyProjects/Deep-Analyst/pyproject.toml:34`: ruff `E4,E7,E9,F,I,UP,B,TID252`; `:64-67`: mypy `strict` + pydantic plugin):
    - "Type-hint public interfaces" (mypy strict);
    - "Avoid mutable default arguments" (B006);
    - "Do not use bare `except`" (E722).
  - **Rewrite rule 1.** The numbers "~40 lines, complexity ≤ 10, nesting ≤ 3" are not enforced. The complexity limit holds (ruff C901 finds 2 functions over it). The line count does not: 53 functions exceed 40 lines, and the three worst are composition roots (`/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/api/sse.py:116` at 118 lines, `bootstrap/runtime.py:332` at 103, `bootstrap/runtime.py:215` at 97). Enforce complexity with ruff `C90` (`max-complexity = 10`) and replace the line count with this: "A function longer than ~40 lines should be doing one thing at one level of abstraction. Composition roots that only wire objects are exempt from the length signal but not from mixing concerns (see §6.9)."
  - **Rewrite rule 9** (the duplication rule; see §3.3).
  - **Extend rule 6** with one sentence on `Any` (see §3.2).
  - **Extend rule 7** with two bright-line sentences on errors (see §4.1).
  - **Replace the parts of rules 5 and 9 that restate skill content** (no `utils`, no speculative abstraction; both are also in `python-service-architecture/SKILL.md:112-120`). Keep them in CLAUDE.md and delete them from the skill, which should instead say: "General code-style rules come from CLAUDE.md; this skill adds only architecture-specific rules."
- **Why:** CLAUDE.md is loaded in every session, so each line competes for attention. A rule that a linter already enforces adds nothing. A rule that is contradicted every day ("~40 lines") teaches agents that the numbers do not matter.
- **Priority:** Medium

### 1.4 Skill length, dead links and repository leakage

- **Target:** all skills
- **Proposed changes:**
  - **`otel-observability`:**
    - About 12,959 lines including `scripts/validate_skill.py` (1,978 lines). Audit mode loads about 2,050 lines before any GenAI reference. `SKILL.md:33` admits a "23k-token intake".
    - What reaches the code is the headline rules: no span events, `record_exception=False`. Second-tier rules do not: the detail switch, error-type vocabulary, naming, `_NONE`.
    - Target a SKILL.md of 150 lines or fewer, with a rule index pointing to the owner files.
    - Move `SKILL.md:76-86` (Langfuse projection) into `content_capture.md`.
    - Cut the deprecation hedging in `SKILL.md:62-68`.
  - **`otel-observability/SKILL.md:61`** refers to `opentelemetry/` and `architecture/02_metrics_design_cheatsheet.md` "in this repo". Neither exists. Remove the reference.
  - **`otel-observability/scripts/validate_skill.py`** (e.g. `:1658-1697`, `:1727+`) checks the skill's own prose for literal substrings and line caps. That freezes wording and does nothing for audited code. Replace it with a small (<150-line) repository audit script, specified in §7.8.
  - **`python-repository-setup/SKILL.md`** (611 lines):
    - Dead cross-references: `:126`, `:436` and `:609` name `observability`; the skill is `otel-observability`. `:600-606` name `terraform-aws`, `deploy-scripts` and `split-repo-app-releases`, none of which exist in `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/`.
    - Anecdotes (`:457-458` "Confirmed directly: …", `:472`) and the rationale essay (`:128-141`) should move to a reference.
    - The code-shaping quality-tooling section gets about 25 lines with no rationale (see §10).
  - **`python-settings-config`** (1,570 lines across 5 files): target a SKILL.md of 120 lines or fewer, with a single ownership table and scaffold-only references (see §2.12).
  - **`python-service-architecture/SKILL.md`:**
    - Invariant 9 (absolute imports, `:130-132`) has zero violations, is enforced by `TID252`, and is repeated in `boundaries.md:298-305,335`. Reduce it to one line.
    - Invariant 10 (`:133-140`) is YAML config ownership. Move it to `python-settings-config` and leave a one-line pointer.
- **Priority:** Medium

### 1.5 Scripted audits should look for defects that actually occur

- **Target:** `python-service-architecture-audit/scripts/audit_service.py`; `otel-observability` (new script)
- **Proposed change:**
  - Every check in a script should correspond to a rule in the owner skill and cite it by ID (for example `B-PORT-3`).
  - The audit skill should reference rule IDs, not paraphrase them. Paraphrasing is how the audit drifted from `boundaries.md`, as the contradictions in §1.2 show.
  - Change `audit SKILL.md:26-35` from "Treat script failures as concrete violations" to "Treat script failures as candidates to confirm against the owning rule."
- **Evidence:** On this repo the audit script reports 4 violations for ingestion, all of them the contested OTel-in-application rule. For `investigation_agent` it reports 0 violations and 0 notices, despite the port, `Any` and adapter-layout issues in §6. The concrete checks to add are in §6.12.
- **Priority:** Medium

### 1.6 Audits should be report-only by default

- **Target:** `python-service-architecture-audit/SKILL.md:139-177` and `agents/openai.yaml`
- **Proposed change:** Make report-only the default. Move the roughly 40 lines of routing policy (openspec proposal versus `FEEDBACK.md` versus implementing a fix) into a short "If the user asks for repairs" section. Remove "and repair confirmed boundary violations" from `agents/openai.yaml`.
- **Why:** An audit that edits code without being asked is surprising. It also mixes structural changes with behaviour changes, which the architecture skill itself forbids (`python-service-architecture/SKILL.md:160-162`).
- **Priority:** Low

---

## 2. Pydantic models, settings, secrets and serialization

The main owner is `python-settings-config`. Its scope should grow slightly, or it should gain a sibling reference `pydantic-models.md`, because most of the recurring Pydantic issues are in domain, port and LLM schemas, not in `Settings` (see §2.13).

### 2.1 Use `Field(...)` only when it carries information (the rule proposed in the request, refined)

- **Target skill:** `python-settings-config`, replacing `SKILL.md:247-248`, `references/settings-py.md:62-63,74,78-79` and `references/secrets-py.md:113`. Add a general version to the proposed `pydantic-models.md`.
- **Proposed rule:**
  > Use `Field(...)` only when it adds metadata or behaviour: a constraint (`ge`, `le`, `min_length`, `pattern`), an alias that is not mechanically derivable, `default_factory`, `discriminator`, `exclude`/`repr=False`, or a `description` that adds information the name and type do not give. Examples: units, accepted format, what omission means, when the value is required, or a server-side clamp. Do not wrap a field only to restate its name in `description`, or only to add an alias that upper-cases the field name. For `BaseSettings`, generate env names once with `model_config = SettingsConfigDict(alias_generator=str.upper, populate_by_name=True, case_sensitive=True)` rather than writing `alias=` on each field. Prefer a named type (`PositiveInt`, `AwareDatetime`, a project `Annotated` alias) over `Field(ge=1)` when the type exists.
- **Why:**
  - The skill currently *mandates* the opposite: "Use `Field(..., description="...")` for required values and `Field(default=..., description="...")` only for sensible, safe defaults" (`/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-settings-config/SKILL.md:247-248`).
  - Its own scaffolds use descriptions that restate the name ("Server bind port.", "Application log level.": `references/settings-py.md:216-218,297,302,307,312,322,331`).
  - Mechanical wrapping makes the field declaration noisy and hides the few fields whose metadata matters.
- **Evidence:** An AST classification of all 368 `Field(` calls in `src` found:
  - 0 pure `Field(default=x)` wraps, and 336 with a constraint, alias or factory. Outside settings, the code already follows the proposed rule.
  - The mechanical noise is concentrated in settings. There are 92 `alias=` kwargs, each simply the upper-cased field name, and about 23 `Field` calls exist *only* to add that alias. Examples: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/config/settings.py:205-216` (12 calls) and `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/config/settings.py:162,196,229-231,238-246`.
  - Descriptions that restate the name: ingestion `settings.py:180` ("Bedrock region."), `:182` ("Chat model for extraction."), `:185` ("Embedding model.").
  - Descriptions that add information, and so should be kept: `:149` (selects the YAML file), `:154` (URL scheme), `:198` ("unset disables export").
  - The investigation agent's `Settings` has 58 `Field` calls and 0 descriptions, and relies on grouped YAML comments (`/Users/arafiet/MyProjects/Deep-Analyst/config/investigation-agent/local.yaml:4-58`). It reads well, which shows per-field descriptions are not required.
  - Replacing the 92 aliases with `alias_generator=str.upper` was verified to keep env binding, YAML and snake_case kwargs working, and to keep errors reported by env name.
- **Good:**
  ```python
  class Settings(BaseSettings):
      model_config = SettingsConfigDict(alias_generator=str.upper, populate_by_name=True,
                                        case_sensitive=True, env_ignore_empty=True)

      db_pool_size: PositiveInt                 # YAML-owned
      otel_exporter_otlp_endpoint: AnyHttpUrl | None = Field(
          default=None, description="Unset disables telemetry export.")
      turn_timeout_s: float = Field(gt=0, le=900)
  ```
- **Bad:**
  ```python
  db_pool_size: PositiveInt = Field(default=5, alias="DB_POOL_SIZE")
  bedrock_region: str = Field(alias="BEDROCK_REGION", description="Bedrock region.")
  ```
- **Exceptions:**
  - **Model-facing schemas** (LLM structured output, tool arguments). Here `description` *is* behaviour, because it becomes the JSON-schema text the model reads. Keep descriptions there, and state the choice once per schema module: either every field carries semantics in its description, or the prompt carries them. Evidence of good use: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/entity_extraction/schemas.py:13-45` and `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/domain/connections.py:22-50`, which build descriptions from the ontology. Inconsistent: the investigation verdict schemas have none (`genai/guardrails/schemas.py:18-37`, `genai/evidence_search/schemas.py:67-80`).
  - **Server-side clamps must be described to the model.** `connections.py:129-131` advertises `max_depth … le=1_000`, but `application/find_connections.py:215` silently clamps it to 16.
  - **Env names that are not the upper-cased field name** (for example `INVESTIGATION_AGENT_HOST` for `host`) keep an explicit `alias=`.
- **Priority:** High

### 2.2 A YAML-owned key has no Python default, and a missing baseline fails startup

- **Target skill:** `python-settings-config`: `SKILL.md` core conventions and change checklist, `references/settings-py.md:436-469` (scaffold), `references/config-yaml.md:83-85,156` (delete).
- **Proposed rule:**
  > A setting owned by the YAML baseline is declared *without* a default (`turn_timeout_s: float = Field(gt=0, le=900)`), so a missing key, file or mount fails validation naming the field. If a class default is kept deliberately (for example, a library-level fallback), a contract test must assert it equals every committed baseline. A configured YAML directory with no file for the selected environment raises; it never silently drops the YAML source.
- **Why:**
  - The skill's own precedence order puts class defaults below YAML (`SKILL.md:24-27`), and its scaffold gives every YAML key a Python default. The result is two sources of truth that drift silently.
  - A mis-mounted `config/` directory then passes validation with different behaviour.
- **Evidence (verified at runtime):**
  - In `investigation_agent`, 38 of 50 YAML policy fields also carry a Python default, and 12 of those differ. Examples:

    | Field | Python default | YAML (`local.yaml`) |
    |---|---|---|
    | `turn_timeout_s` | 120 | 240 |
    | `model_retry_attempts` | 3 | 5 |
    | `max_physical_attempts` | 40 | 80 |

    Sources: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/config/settings.py:188-202` versus `/Users/arafiet/MyProjects/Deep-Analyst/config/investigation-agent/local.yaml:14-33`.
  - `config_file()` returns `None` when no file is found (`.../investigation_agent/config/settings.py:39-50`; `.../ingestion/config/settings.py:49-64`), and `settings_customise_sources` then omits YAML (`:156-159`, `:143-146`). A missing mount therefore halves the turn timeout without any error.
  - A unit test locks in the fallback: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/unit/config/test_settings.py:50-51`.
  - The skill's scaffold does the missing-file check correctly (`settings-py.md:482-488`), but that part was not copied.
- **Exceptions:** A shared library's own config object may have defaults, because it has no YAML (see `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/config.py`).
- **Priority:** High

### 2.3 Validation errors must not carry secret input, and credential DSNs are `SecretStr`

- **Target skill:** `python-settings-config`: `references/secrets-py.md` ("failure rules") and `references/settings-py.md:143` (the `AnyUrl` row)
- **Proposed rules:**
  1. A loader that converts a `pydantic.ValidationError` into its own error type raises with `from None`, or the model sets `hide_input_in_errors=True`. `exc.errors(include_input=False)` only cleans *your* message; the chained `__cause__` still prints `input_value=...` in every traceback.
  2. Any value that contains a credential, including a DSN with a password, is `SecretStr`. Parse it after `.get_secret_value()`. Do not use `AnyUrl` or `PostgresDsn` for it.
  3. Add a test asserting that `repr(settings)` and `str(exc_info.value.__cause__)` do not contain a fixture secret.
- **Why:**
  - `secrets-py.md:74-75` says messages must not include raw values, but does not mention exception chaining.
  - `settings-py.md:143` recommends `AnyUrl` for a "Non-HTTP URL/DSN without credentials". Agents miss the qualifier.
- **Evidence (reproduced):**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/config/secrets.py:176,190`: `raise SecretsError(_safe_validation_message(...)) from exc`. With a malformed DSN, `str(e.__cause__)` contains the password.
  - The same leak occurs at `.../investigation_agent/config/settings.py:298-300`, even though it passes `include_input=False`.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/config/settings.py:153-155`: `database_url: AnyUrl` holds `postgresql+psycopg://app:<password>@…`, and `repr(load_settings())` contains the password. Lines 165-174 of the same file correctly use `SecretStr` for the S3 keys.
- **Good (already in the repo):** `.../investigation_agent/config/secrets.py:106-107` keeps DSNs as `SecretStr` and validates them in `_parse_postgres_dsn` (`:85-100`).
- **Priority:** High

### 2.4 Pass a settings slice to a component, not the `Settings` object

- **Target skill:** `python-settings-config` (new core convention), with a cross-link to `python-service-architecture/references/ai.md:245-246`, which already says it for GenAI only.
- **Proposed rule:**
  > Only `bootstrap/` and `main.py` import the service `Settings`. Adapters, repositories and GenAI factories take keyword arguments or a small frozen policy dataclass built in bootstrap. A test that needs `Settings.model_construct(...)` to skip required fields indicates a missing slice.
- **Evidence:**
  - Bad: 5 ingestion modules import `Settings`: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/engine.py:12-15`, `adapters/s3/evidence_bucket.py:185`, `genai/entity_extraction/llm.py:12-23`, `genai/embeddings/llm.py:11`, `genai/shared/throttle.py:106`. The consequence: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/genai/test_llm.py:24,53,77` use `Settings.model_construct(...)`.
  - Good: in `investigation_agent` only `bootstrap/runtime.py`, `bootstrap/app.py` and `main.py` import it. They slice it into `RetryPolicy`, `AgentLimits` and `PoolBounds` (`/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/bootstrap/runtime.py:140-197`).
  - Good (library): `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/config.py:1,12-38` ("The library never reads the environment"; frozen, slotted dataclasses).
- **Priority:** Medium

### 2.5 Use Pydantic's types before writing validators

- **Target skill:** proposed `pydantic-models.md` (or a new section in `python-settings-config/references/settings-py.md`, "Preferred Pydantic Types", extended beyond Settings)
- **Proposed rule:**
  > Prefer types to validators: `AwareDatetime` instead of `datetime` plus a `tzinfo is None` check; `PositiveInt`/`NonNegativeInt` instead of `Annotated[int, Field(ge=1)]`; `SecretStr = Field(min_length=16)` instead of a `field_validator` that measures length. Use `model_validator` only for cross-field invariants. Do not validate the same invariant twice (a constraint *and* a validator).
- **Evidence:**
  - `AwareDatetime` is used 0 times. 6 datetime fields in 4 models are validated by hand: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/domain/investigation_state.py:63,77-81`, `domain/history.py:51,56-57`, `domain/connections.py:79-92,102-105`, `ports/evidence_search.py:30-31,36-39`.
  - Datetimes in persisted models are left unchecked: `/Users/arafiet/MyProjects/Deep-Analyst/libs/evidence_model/src/evidence_model/drafts.py:99-101`, `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/ports/ingestion_ledger.py:64`.
  - `.../investigation_agent/config/secrets.py:138-143`: a length validator where `Field(min_length=16)` would do.
  - Double validation: `libs/evidence_model/src/evidence_model/drafts.py:51` has `min_length=1` *and* `require_source_refs()` at `:62`.
- **Exceptions:** Bounds are policy, so choose them from the library's semantics, not by habit. `db_max_overflow: PositiveInt` (`.../ingestion/config/settings.py:211`) forbids 0, which is valid for SQLAlchemy. Prefer an explicit `ge=0, le=…` with an upper bound where an unbounded value is dangerous, as `investigation_agent/config/settings.py:181-227` does.
- **Priority:** Medium

### 2.6 Name a repeated constraint as a domain type

- **Target skill:** proposed `pydantic-models.md`
- **Proposed rule:**
  > When the same `Annotated[...]` constraint expresses one domain concept three or more times, define it once in the owning domain module (`type Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]`, `type OpaqueId = Annotated[str, Field(min_length=1, max_length=256)]`) and import it. Do not move it into a generic `common.py` or `types.py`. Limits that legitimately differ per field (`max_length=4_000` vs `32_000`) stay inline.
- **Evidence:**
  - `Annotated[str, Field(min_length=1, max_length=256)]` appears 25 times, `…max_length=128)]` 18 times and `…max_length=64)]` 10 times.
  - The SHA-256 pattern appears 17 times, and a private `_SHA256_PATTERN` constant is redefined in 5 files: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/ports/record_query.py:19`, `ports/evidence_search.py:16`, `domain/connections.py:19`, `genai/record_query/schemas.py:13`, `genai/evidence_search/schemas.py:15`.
  - Only 2 named aliases exist in the codebase: `/Users/arafiet/MyProjects/Deep-Analyst/libs/evidence_model/src/evidence_model/provenance.py:44` and `.../investigation_agent/api/routers/threads.py:14`.
- **Priority:** Medium

### 2.7 One strict model configuration per package, and immutable containers in frozen models

- **Target skill:** proposed `pydantic-models.md`
- **Proposed rules:**
  1. For boundary, persisted and model-facing Pydantic models, `ConfigDict(frozen=True, extra="forbid")` is the default. Declare it once per member (for example a `StrictModel` base in `domain/`) and import it. The alternative is to write the config on every model; do not mix the two styles, and do not copy the base class into several modules.
  2. LLM structured-output schemas also use `extra="forbid"`, so the generated JSON schema says `additionalProperties: false`.
  3. In frozen models and frozen dataclasses, use `tuple[...]`, `Mapping`, or a nested frozen model. Do not use `list` or `dict`, which leave the "frozen" object mutable.
  4. Type a field with the existing enum, `Literal`, or model, not `str` or `dict[str, int]`.
- **Evidence:**
  - `StrictModel`/`_StrictModel` is defined 6 times in one service (`.../investigation_agent/src/investigation_agent/ports/record_query.py:22`, `ports/evidence_search.py:19`, `domain/connections.py:53`, `genai/record_query/schemas.py:16`, `genai/investigation/schemas.py:15`, `genai/evidence_search/schemas.py:20`), alongside 51 inline `ConfigDict(frozen=True, extra="forbid")`.
  - The ingestion LLM schemas have no config: `.../ingestion/genai/entity_extraction/schemas.py:12,38`.
  - Shallow-frozen containers: `libs/evidence_model/src/evidence_model/drafts.py:51,102,103`; `.../ingestion/domain/records.py:89-92`.
  - Stringly-typed fields:
    - `.../ingestion/ports/ingestion_ledger.py:62` has `chunking: dict[str, int]`, although `ChunkingConfig` exists at `:14-17` of the same file.
    - `.../ingestion/application/ingest_dataset.py:88-90` has `RunOutcome.outcome: str`, but callers always pass `Outcome`.
    - `.../ingestion/config/settings.py:224` has `log_level: str`, whereas investigation uses a `LogLevel` `Literal`.
- **Good (already in the repo):** the investigation domain uses `tuple[...]` fields throughout (56 of them).
- **Priority:** Medium

### 2.8 One canonical JSON/fingerprint function per member

- **Target skill:** proposed `pydantic-models.md` ("Serialization"); also covered by the search-before-helper rule in §3.3.
- **Proposed rule:**
  > Hash inputs through one canonical-JSON function per member: `model_dump(mode="json")` first, then `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, with **no `default=str`**. Unknown types must fail rather than be stringified: `str(datetime)` is not `isoformat()`, so the same value would hash differently depending on the path it took. Persist with `model_dump(mode="json")` and read with `model_validate_json`.
- **Evidence:** 6 divergent digest helpers exist in `investigation_agent`, even though `domain/tool_outcome.py:138-162` already provides `canonical_json` / `canonical_fingerprint`:
  - `application/find_connections.py:333-335` (`default=str`);
  - `genai/evidence_search/agent.py:333-335`;
  - `genai/record_query/agent.py:351-352` (default separators; also dead code);
  - `ports/record_query.py:213-215` (`digest_payload`, `default=str`);
  - `ports/evidence_search.py:53-54`;
  - `db/record_query_executor.py:350`.

  Ingestion has another at `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/domain/records.py:14-16`.
- **Good (already in the repo):** `.../ingestion/adapters/s3/evidence_bucket.py:138,143` and `adapters/filesystem/receipt.py:25,33` use `model_dump(mode="json")` / `model_validate_json`.
- **Priority:** Medium (High if fingerprints are compared across modules, which here they are)

### 2.9 Standardize the good env-source hygiene already in the code

- **Target skill:** `python-settings-config/references/settings-py.md`
- **Proposed rules (each taken from existing code):**
  - **A YAML allowlist source** that rejects non-policy keys at startup. Evidence: `PolicyYamlSource` + `POLICY_FIELDS` in `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/config/settings.py:67-106` and `.../investigation_agent/config/settings.py:53-120`. The skill only mentions a "YAML policy allowlist" in passing, at `references/env-example.md:138`.
  - **`env_ignore_empty=True`** when Compose passes unset variables as `""`, with a comment explaining why (ingestion `settings.py:126-127`).
  - **`load_settings()`** that translates `ValidationError` into a typed `SettingsError` naming the fields (ingestion `:252-261`), combined with §2.3. Promote this over the skill's `lru_cache` `get_settings()` with `# type: ignore[call-arg]` (`settings-py.md:251-253,335-337`). Settings are passed down from bootstrap, not fetched from a global cache.
  - **Per-process secret models** with least privilege (`ServingSecrets` vs `InitializerSecrets`, `.../investigation_agent/config/secrets.py:103-150`).
  - **Do not hand-parse `.env`.** `.../investigation_agent/config/secrets.py:21,39-65` reimplements `dotenv_values` with a regex and swallows `OSError` (`:57-58`).
- **Priority:** Medium

### 2.10 Contract tests compare values, not just names; unit tests are isolated from local config

- **Target skill:** `python-settings-config` ("Change Checklist", `SKILL.md:328-332`) and `references/env-example.md`
- **Proposed rules:**
  1. The `.env.example` contract test compares **values** as well as names against the YAML baselines. The root `.env.example` is checked against each service file for shared keys.
  2. Unit tests that construct `Settings` pass `_env_file=None` and point the config-dir variable at `tmp_path`, or use one autouse fixture that does both. Tests that intentionally read the committed baseline belong under `contract/`.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/.env.example:61` has `# CAPTURE_AI_CONTENT=false`, but the YAML (`/Users/arafiet/MyProjects/Deep-Analyst/config/ingestion/local.yaml:35`) says `true`, and the header claims "values shown are the baseline defaults".
  - `EXPECTED_AGENT_INITIALIZER_VERSION` is `agent-runtime@1` in `services/investigation_agent/.env.example:18` but `@2` in the root `.env.example:74`.
  - The contract tests (`/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/contract/config/test_env_example.py:33-45`, `.../investigation_agent/tests/contract/config/test_environment_contract.py:28-41`) compare names only.
  - Isolation is inconsistent. `.../ingestion/tests/unit/bootstrap/test_runtime.py:96-108` and `.../investigation_agent/tests/unit/bootstrap/test_runtime.py:75` isolate nothing, while `.../investigation_agent/tests/unit/bootstrap/test_initializer_wiring.py:23,44` pass `_env_file=None`.
- **Priority:** Medium

### 2.11 Soften or scope the rigid layout rules

- **Target skill:** `python-settings-config/SKILL.md`
- **Proposed changes:**
  - **`SKILL.md:15-22`** forces migrating an env-only project to YAML whenever the task is "a configuration refactor". Change it to "propose the migration; do not perform it unless asked". This conflicts with CLAUDE.md rule 10, and it is a large change nobody requested.
  - **`SKILL.md:156-182`** mandates `config/base.yaml` + `config/services/<service>.{env}.yaml`. The repo uses `config/<service>/<env>.yaml` with no base layer (`/Users/arafiet/MyProjects/Deep-Analyst/config/ingestion/`, `/Users/arafiet/MyProjects/Deep-Analyst/config/investigation-agent/`). Add: "Preserve an existing YAML layout; propose migration separately." The current escape clause (`:153-154`) covers only environment names.
  - **"Secrets never on `Settings`"** (`SKILL.md:232`, `settings-py.md:156`). Ingestion puts `SecretStr` S3 keys on `Settings`, which is reasonable for a one-shot job with two secrets. Change to: "A single-process job may keep `SecretStr` fields on `Settings`; use a separate `secrets.py` when processes need different secret sets or a remote provider."
  - **Speculative scaffolding** (`references/secrets-py.md:162-221`): an ABC `SecretsProvider`, a stub `RemoteSecretsProvider` that raises `NotImplementedError`, a factory, and `global _cached_secrets`. Show the env-backed model only, and add the provider seam when a second backend actually exists (CLAUDE.md rule 9).
  - **`settings-py.md:404-412`** uses an `or raise_missing_environment_name()` expression trick. Replace it with an explicit `if … raise`.
- **Priority:** Medium

### 2.12 Restructure the skill around one ownership table

- **Target skill:** `python-settings-config`
- **Proposed change:** Replace the prose in `SKILL.md:65-119,204-278` with a table of 15 rows or fewer, with these columns: *value kind → owner (code / YAML / env-only / secret) → Python declaration → `.env.example` section → test*. The references then contain only scaffolds. This removes the 4–5 restatements listed in §1.1.
- **Priority:** Medium

### 2.13 Where the general Pydantic guidance lives

- **Proposed change:** Create `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/pydantic-models.md` (about 80 lines) covering §2.1 (general form), §2.5–§2.8, and a short decision table that records the split the code already uses well:
  - frozen, slotted `dataclass` for internal values, policies and wiring;
  - frozen `BaseModel` with `extra="forbid"` for untrusted, persisted or model-facing data;
  - `TypedDict` only for framework state channels.

  Route to it from `python-service-architecture/SKILL.md`. `python-settings-config` links to it for general field rules.
- **Why:** `python-settings-config` is scoped to settings, but most Pydantic code in this repo is domain, port and LLM schema code, and there is no guidance for it.
- **Priority:** Medium

---

## 3. Code-level idioms: typing, vocabularies and helper reuse

There is no home for code-level idioms today. `python-service-architecture` is about placement, CLAUDE.md is generic, and the audit skill is structural. As a result, style splits by service: agents copy whichever service they are working in.

**Proposal:** create `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/code-idioms.md` (about 80–100 lines, one bad/good pair per rule), routed from `SKILL.md:48-75` for any implementation work. Agents already load this skill for module work, so this is preferable to a separate skill. Move enforceable parts into ruff and mypy (§10).

### 3.1 Define each closed vocabulary once

- **Target:** `code-idioms.md`, with a one-line pointer from `ai.md` → Tools
- **Proposed rule:**
  > When a fixed set of names (tool names, statuses, phases, failure classes, event names) is used by more than one module, define it once. Use a `StrEnum` when code branches on it or it crosses a boundary. Use `type X = Literal[...]` only when it is purely a schema field type. Import the definition; never re-spell its members as string literals. A `Literal` subset of an enum (for a provider schema) is named after the enum and tested against it.
- **Why:** String literals scattered across modules drift silently. Renaming a tool or a status then becomes a grep exercise.
- **Evidence:**
  - The tool-name vocabulary has **6 separate definitions** plus about 25 raw literals:
    - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/api/sse.py:46-49` (`PublicTool`);
    - `genai/investigation/tools/__init__.py:23` (`TOOL_NAMES`);
    - `domain/tool_outcome.py:130`, `domain/investigation_state.py:94`, `domain/investigation_state.py:287` (three identical `Literal`s);
    - `bootstrap/runtime.py:364` (`frozenset`);
    - raw literals in `genai/investigation/tools/search_evidence.py:41,44,57,91,97,100,122` and siblings.
  - `FailureClass` is defined twice, word for word: `.../observability/events.py:14` and `.../observability/turn_observation.py:9`.
  - There are 65 `== "literal"` comparisons in `src`.
- **Good:**
  ```python
  class ToolName(StrEnum):            # domain/tool_outcome.py
      SEARCH_EVIDENCE = "search_evidence"
      QUERY_RECORDS = "query_records"
      FIND_CONNECTIONS = "find_connections"
  ```
- **Bad:**
  ```python
  progress({"phase": "searching_evidence", "tool": "search_evidence", "attempt": 1})
  fingerprint = canonical_fingerprint({"tool": "search_evidence", "intent": intent})
  ```
- **Exceptions:** A public wire enum (such as `PublicTool`) may stay separate when the external contract must not follow internal renames. Say so in a comment and map the two explicitly.
- **Priority:** High

### 3.2 `Any` only where the type is truly dynamic

- **Target:** CLAUDE.md rule 6 (one sentence), `code-idioms.md` (details), `ai.md` (GenAI handles), ruff `ANN401` (§10)
- **Proposed rule:**
  > Use `Any` only for truly dynamic values. Type model handles as `BaseChatModel` or a narrow local Protocol, and agent/graph handles as `Runnable[...]`, `CompiledStateGraph`, or a private Protocol. For heterogeneous input that you narrow with `isinstance`/`getattr`, use `object`: mypy then enforces the narrowing, whereas `Any` switches checking off. Allow `dict[str, Any]` only at a serialization seam (framework state channels, JSONB), and parse it into a model at the first accessor. Do not write `cast(Any, …)`; annotate the container once with a one-line variance comment.
- **Why:** mypy strict is on, but `Any` silently satisfies it. "Type-hint public interfaces" (CLAUDE.md:31-32) is met while checking is effectively off.
- **Evidence:**
  - There are 325 `Any` in `src`, 110 of them `dict[str, Any]`. `ANN401` would flag 80 signatures.
  - `model: Any` appears across investigation GenAI code: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/record_query/agent.py:86`, `genai/evidence_search/agent.py:86`, `genai/guardrails/llm.py:34,64`, `genai/shared/structured_output.py:28,44,73`, `genai/investigation/llm.py:22,29-31`, `genai/investigation/agent.py:84,97-98`. This is despite a `ChatModel` Protocol at `genai/shared/llm.py:9-10`.
  - `cast(Any, …)` is applied to middleware 6 times with no explanation: `genai/record_query/agent.py:106,112`, `genai/evidence_search/agent.py:112,118`, `genai/investigation/agent.py:129,133`.
  - Tool builders return `-> Any` (`evidence_search/agent.py:128`, `record_query/agent.py:122`), while a sibling returns `BaseTool` (`tools/search_evidence.py:31`).
  - Duck-typed parameters are declared `Any` where `object` fits: `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/genai_content.py:19,31,39,74,82,107`.
- **Good (already in the repo):**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/entity_extraction/llm.py:27` returns `BaseChatModel`, and `agent.py:29` accepts it.
  - Private narrow Protocols in `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/investigation/investigator.py:22-39`.
  - A single parse point for the state `dict`: `genai/investigation/schemas.py:83-88`.
- **Bad → good:**
  ```python
  def _role(message: Any, default: str = "user") -> str: ...     # checking off
  def _role(message: object, default: str = "user") -> str: ...  # narrowing enforced
  ```
- **Exceptions:**
  - `**kwargs: Any` in real pass-through wrappers (framework callbacks).
  - Framework-imposed type parameters (`AgentMiddleware[Any, RuntimeContext, Any]`).
  - JSONB column types (`/Users/arafiet/MyProjects/Deep-Analyst/libs/evidence_model/src/evidence_model/tables.py:43-84`).
- **Priority:** High

### 3.3 Search for an existing helper before writing one; semantically identical helpers have one owner

- **Target:** CLAUDE.md rule 9 (rewrite); `python-service-architecture/references/boundaries.md:288` ("Avoid utility gravity"); `SKILL.md:40-46` (discovery step 7); the audit script.
- **Proposed rule (replacement text for CLAUDE.md rule 9, second sentence):**
  > Prefer a small amount of clear duplication over an abstraction whose shape is not yet understood. This applies to behaviour whose shape is still changing. Code with identical semantics has one owner: hashing/canonicalization, closed vocabularies, deadline arithmetic, provider error-code classification, trust-boundary rendering, and DSN/URL rewriting. Before writing a private helper, search the member for an existing one (`rg "sha256|sort_keys|<untrusted|_remaining|Error\"\]\[\"Code"`) and import it. Two copies that differ by accident are a bug.
- **Why:** The current wording ("Prefer a small amount of clear duplication…", `/Users/arafiet/MyProjects/Deep-Analyst/CLAUDE.md:49-51`) and `boundaries.md:288` ("small private helpers in the module that owns the behavior") explain the copies below. Discovery step 7 covers only "technical plumbing in a workspace member", which agents read as cross-member only.
- **Evidence** (paths below are under `.../services/investigation_agent/src/investigation_agent/` unless stated otherwise):
  - **Canonical hashing:** 6 variants with at least 4 flag sets (§2.8).
  - **The `<untrusted-evidence>` wrapper is rendered in 7 places.** The owner, with a budget and trim marker, is `genai/guardrails/middleware.py:258`. `genai/investigation/middleware/turn_close.py:280-283` and `middleware/grounding.py:241-244` are byte-identical to each other. Others: `middleware/context.py:92`, `state_projection/schemas.py:65`, `evidence_search/agent.py:323`, `record_query/agent.py:334`.
  - **`_progress_writer`:** 3 identical copies in `genai/investigation/tools/{search_evidence.py:117, query_records.py:115, find_connections.py:130}`.
  - **The nested-agent `astream` loop** is copied word for word at `genai/evidence_search/agent.py:225-240` and `genai/record_query/agent.py:196-211`.
  - **`_remaining(deadline)`:** `db/evidence_reader.py:457` and `db/record_query_executor.py:358`.
  - **`_native_dsn`:** `db/pools.py:195` and `db/initializer.py:456`.
  - **Locator matching:** `db/evidence_reader.py:436-443` and `db/record_query_executor.py:332-344`.
  - **Bedrock transient-code sets have drifted between services:** `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/shared/failures.py:21-31` has 7 codes; `.../investigation_agent/genai/shared/retry.py:27-35` has 5, missing `ModelTimeoutException` and `ServiceQuotaExceededException`.
  - **`response["Error"]["Code"]` extraction is written 4 times,** including in the shared library: `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/spans.py:25-29`.
- **Exceptions:** Helpers that look alike but mean different things. Keep them separate with a comment explaining why.
- **Detection aid (audit script):** report duplicate private function names across modules, and string literals that appear in 3 or more modules. That is how these copies were found.
- **Priority:** High

### 3.4 Keyword-only construction for dataclasses with several or easily confused fields

- **Target:** `code-idioms.md`; ruff `FBT003` (§10)
- **Proposed rule:**
  > Value-object dataclasses default to `@dataclass(frozen=True, slots=True, kw_only=True)`. A positional `True`/`False`/number that is not self-describing at the call site is a smell. Mutable invocation-state dataclasses (`slots=True` only) are fine; say who mutates them.
- **Evidence:**
  - `kw_only` is used 0 times. `FBT003` finds 37 positional booleans, 24 of them in `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/api/problems.py`, for example `:103` `PublicFailure("cancelled", "The investigation was cancelled.", 499, True)`.
  - `genai/state_projection/compactor.py:148,151` has `ProjectionResult(valid, 1, total_attempts, False)`.
  - Functions already do this well: most functions with 7 or more parameters are keyword-only (for example `observability/instrumentation/attempt.py:129`, 10 of 10).
- **Bad → good:**
  ```python
  PublicFailure("cancelled", "The investigation was cancelled.", 499, True)
  PublicFailure(code="cancelled", message="The investigation was cancelled.",
                status_code=499, retryable=True)
  ```
- **Exceptions:** Two-field value objects whose field order is obvious (`Point(x, y)`).
- **Priority:** Medium

### 3.5 `type: ignore`, `cast` and `assert` are last resorts

- **Target:** `code-idioms.md`; mypy config (§10)
- **Proposed rule:**
  > Before writing `# type: ignore[code]` or `cast`, check whether a Protocol, `dataclasses.fields()`, or a typed accessor removes the need. Ignores are allowed only for untyped or incorrectly typed third-party calls, with a trailing reason. Never use `cast` to recover a type from a string-keyed container. Store typed attributes instead. In production code, `assert` only restates an invariant that is already proven. To narrow a third-party return value, use `if not isinstance(...): raise TypeError(...)`.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/application/invoke_turn.py:242` has `# type: ignore[arg-type]`, because `_CleanupLease` duck-types a concrete `ThreadLease`. The fix is a Protocol.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/repositories.py:72` has `projection.__slots__  # type: ignore[attr-defined]`. Use `dataclasses.fields()` instead.
  - `.../investigation_agent/api/dependencies.py:25-87`: a runtime typed `object`, string `getattr`, 5 `cast`s and 3 re-validations (§6.7).
  - A mypy probe with `warn_unreachable` and `redundant-expr` found 11 dead defensive branches. Examples: `domain/investigation_state.py:244-245`, `db/evidence_reader.py:441`, `db/record_query_executor.py:340`.
  - `assert` used for runtime narrowing: `.../ingestion/genai/entity_extraction/llm.py:40`, `.../investigation_agent/ports/record_query.py:87,91`.
- **Priority:** Medium

### 3.6 Scope of `__all__` and `__init__.py`

- **Target:** `code-idioms.md`; `python-service-architecture/references/shared-libraries.md:153-156`; `ai.md:174-175`
- **Proposed rule:**
  > In a **service**, keep `__init__.py` files empty (no composition logic, no re-exports) and import from the defining module. Use `__all__` only in library public modules and in package `__init__.py` files that intentionally re-export. A leaf service module does not need it; a leading underscore already marks a name private. Never list names that you imported from elsewhere in `__all__`. If you use `__all__`, keep it sorted (ruff `RUF022`). An `observability/__init__.py` must not eagerly import optional GenAI dependencies.
- **Why:** The style currently depends on which service an agent happens to be working in.
- **Evidence:**
  - `__all__` appears in 74 of 97 `investigation_agent` modules but in only 3 of 63 `ingestion` modules. The libraries use it only in `__init__`, which is the right model.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/investigation/tools/__init__.py:1-47` contains composition logic (`ToolDependencies`, `build_investigation_tools`).
  - `.../investigation_agent/observability/__init__.py:8-14` eagerly imports LangChain-dependent instrumentation. That breaks the existing rule at `ai.md:392`, and `api/problems.py:16` therefore loads LangChain.
  - `.../application/invoke_turn.py:378-395` re-exports names defined elsewhere.
  - `ai.md:174-175` ("Preserve its public imports through `__init__.py`…") invites re-export packages. Limit it to libraries.
- **Priority:** Medium

### 3.7 Config-like literals in code

- **Target:** `ai.md` (the `llm.py` section) and `code-idioms.md`
- **Proposed rule:**
  > Do not branch on a substring of a deployment-owned value such as a model ID. Express model capability as a setting (`supports_temperature: bool`) or as one keyed table with a test. A transport-level retry override (`retries={"max_attempts": 0}`) gets a one-line comment explaining why.
- **Evidence:**
  - `"openai.gpt-5.6-terra"` is hard-coded in both services, with opposite polarity: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/shared/llm.py:55` (`not in`) and `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/entity_extraction/llm.py:17` (`in`).
  - Ingestion also hard-codes `temperature: 0` (`:19`), while investigation makes it a setting.
- **Priority:** Medium

### 3.8 Rules deliberately *not* proposed

- **A `Final` mandate:** UPPER_CASE naming suffices, and mypy gains little from it.
- **`match` statements:** used once, and nothing suggests they would help.
- **Comment-density rules:** density is already healthy (77 comment lines in about 16k lines of code, mostly explaining why).
- **`from __future__ import annotations`:** already consistent.

---

## 4. Error handling (new reference; currently has no owner)

Today the only guidance is:
- CLAUDE.md rule 7 (three sentences);
- a clause at `python-service-architecture/SKILL.md:116-120`;
- placement rules in `boundaries.md:86-101,239-258`;
- telemetry-only rules in `otel-observability/references/conventions/errors.md`.

**Proposal:** create `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/errors.md` (about 150 lines). Route it from invariant 6 and from `api-and-workers.md:13`. `otel-observability/references/conventions/errors.md` keeps only the telemetry projection and links here.

Measured baseline: there are 125 `except` clauses in `src`, and 45 of them catch `Exception`/`BaseException`. Of those 45:
- **27 are justified:** mark-and-reraise, cleanup-and-reraise, translate, or a true boundary.
- **18 swallow silently:** 10 are telemetry wrappers, 6 are business fallbacks, and 2 are probes.

### 4.1 The allowed shapes of a broad `except`

- **Target:** new `errors.md`, plus two sentences in CLAUDE.md rule 7
- **Proposed rule:**
  > `except Exception` (or `BaseException`) is allowed only in these shapes:
  > 1. mark and re-raise (span or attempt bookkeeping, then `raise`);
  > 2. clean up and re-raise;
  > 3. translate to a port-owned error with `raise … from exc`;
  > 4. a true process boundary (request handler, job runner, worker loop) that logs once and maps to a response or exit code;
  > 5. a **recorded fallback**: a warning log with `exc_info` and `error.type`, or the handled-failure recorder.
  >
  > An `except` that does not re-raise must catch specific types or record the failure. A broad catch must never map to a *specific* business category (such as "dependency unavailable"), because programming errors would then be reported as outages.

  CLAUDE.md addition: "An `except` that does not re-raise must either catch specific types or record the failure (a log with `exc_info`, or the handled-failure recorder). Map exceptions to public errors through one exhaustive table, never through `getattr(exc, "code")`."
- **Evidence (bad):**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/investigation/middleware/evidence.py:116-117`: `except Exception: return self._failed(..., OutcomeStatus.DEPENDENCY_UNAVAILABLE)`. Any bug in a tool handler is reported to the model and the user as a dependency outage, and nothing is logged.
  - `evidence.py:150-160`: a guardrail fallback that only appends a string.
  - `genai/state_projection/compactor.py:157-160,164-165` and `genai/investigation/middleware/turn_close.py:225-226`: silent fallbacks.
  - `api/routers/health.py:42-43`: `except Exception: result = None`, which produces a 503 with no cause.
- **Evidence (good, used once and worth standardizing):** `.../genai/investigation/middleware/model_failures.py:50-53`:
  ```python
  except Exception as exc:
      attempt = current_attempt()
      if attempt is not None:
          attempt.record_handled_failure(exc)
      code = self._failure_code(exc)
  ```
- **Exceptions:** A readiness probe may swallow the error if it returns a bounded reason code and logs on a *state transition* rather than on every probe (evidence: `.../db/pools.py:174-175,191-192`, which log nothing today).
- **Priority:** High

### 4.2 Translate once; never self-chain; port error types are distinct

- **Target:** new `errors.md`
- **Proposed rule:**
  > A translator returns a new exception for a *foreign* error. Code that already raised a port error re-raises it unchanged:
  > ```python
  > try:
  >     ...
  > except ExtractionError:
  >     raise
  > except Exception as exc:
  >     raise translate_provider_error(exc) from exc
  > ```
  > Do not raise the port's own error inside a `try` whose broad `except` translates. Each port owns distinct error classes; aliasing another port's classes makes `error.type` and ledgers report the wrong thing.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/shared/invocation.py:40-43` raises `PermanentExtractionError` inside the `try`. The broad `except` then calls `translate_provider_error`, which returns the same instance (`genai/shared/failures.py:65-66`). The net effect is `raise exc from exc`, so the exception becomes its own `__cause__`. `genai/embeddings/embedder.py:97-102` has the same shape.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/ports/text_embedder.py:23-25`: `PermanentEmbeddingError = PermanentExtractionError`. Embedding failures are recorded as extraction failures.
  - `genai/shared/failures.py:72-76`: two branches return the same thing, so one of them is dead.
- **Priority:** High

### 4.3 Exception → public error: one exhaustive table, keyed by type or a closed enum

- **Target:** new `errors.md`; `python-service-architecture/references/api-and-workers.md:13`
- **Proposed rule:**
  > Application, port and domain exceptions state *what happened*: their type, plus a stable code only if that code is persisted. The mapping to HTTP status, title, public message, retryability and headers lives in **one** table in `api/`, keyed by exception type (resolved along the MRO) or by a `StrEnum` owned by the layer that raises. A test asserts that every member is mapped. Do not put `public_message`, `status_code` or `retryable` on business exceptions. Do not resolve failures with `getattr(exc, "code", None)`. Do not create synthetic exceptions just to reach the mapper.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/application/invoke_turn.py:64-101`: 7 exceptions with `code`/`public_message`/`retryable`. `public_message` is never read (verified by grep), and it already disagrees with the real table (`api/problems.py:71`).
  - `api/problems.py:132-134` resolves failures with `getattr(error, "code", None)`, so *any* exception with a matching `.code` string, including third-party ones, gets that HTTP status.
  - `domain/investigation_state.py:41` has `code = "invalid_tool_outcome"`, which is missing from `_FAILURES` (`problems.py:45-123`) and silently becomes a 500.
  - `problems.py:202-205` defines `_CodeFailure(RuntimeError)` only to reach the mapper. `problems.py:227-250` (`_title`) is a second classification table. `problems.py:79-90` has duplicate codes with identical messages.
  - Domain and core code carry HTTP vocabulary (`"resource_not_found"`, 21 string `code` attributes across 9 modules).
- **Good (keep):** `problems.py` already uses a closed allowlist, `application/problem+json`, never copies exception text (`:32`), logs only status ≥500 at the handler with `mark_failed` on the span (`:181-199`), and sends `Cache-Control: no-store` and `Retry-After`. Promote all of this as the canonical example.
- **Good (shape):**
  ```python
  _FAILURES: Mapping[type[Exception], PublicFailure] = {
      ThreadBusy: PublicFailure(code="thread_busy", status_code=409, retryable=True, message="…"),
  }
  def public_failure(error: BaseException) -> PublicFailure:
      for exc_type in type(error).__mro__:
          if failure := _FAILURES.get(exc_type):
              return failure
      return INTERNAL
  ```
- **Exceptions:** A code persisted in durable state (for example `safe_failure_code` in checkpoints) needs a stable string. Define it once as a `StrEnum` in `domain/`.
- **Priority:** High

### 4.4 Cancellation and `from None`

- **Target:** new `errors.md`; fix the otel snippets
- **Proposed rules:**
  1. On Python ≥3.8, `except Exception` does not catch `asyncio.CancelledError`. Write a `CancelledError` arm only when it does something different. To mark and re-raise everything, use a single `except BaseException` arm.
  2. Use `raise X from None` only for expected, client-facing control-flow translations (4xx) where the cause adds nothing for diagnosis. Everywhere else, use `from exc`.
  3. **Exception to 2:** use `from None` whenever the cause might carry secret input (§2.3).
- **Evidence:**
  - There are 6 redundant `except asyncio.CancelledError: raise` arms: `.../genai/state_projection/compactor.py:155,162`, `genai/investigation/middleware/model_failures.py:46`, `middleware/turn_close.py:223`, `middleware/evidence.py:110,148`. The skill teaches the pattern at `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/otel-observability/references/tracing/genai/langchain/streaming_and_agent_span.md:79-89` (repeated at `:226,284`).
  - `.../genai/investigation/investigator.py:51,55,80`: `TimeoutError → InvestigationTimedOut from None` hides *which* operation timed out.
- **Good:** `.../db/record_query_executor.py:146-147`, a comment that relies on `CancelledError` being a `BaseException`.
- **Priority:** Medium

### 4.5 Exception class design

- **Target:** new `errors.md`
- **Proposed rule:**
  > Define an exception class when a caller handles it differently or when it crosses a port. Name them consistently: either every exception ends in `Error`, or none does. Today `ThreadBusy`, `InvalidCursor`, `MissingProvenance` and `OntologyViolation` sit alongside names ending in `…Error`. Carry context as typed attributes, not as text in the message.
- **Priority:** Low

---

## 5. Async code and resource lifecycle (new reference)

Neither the architecture skill nor the DB skill says anything about asyncio mechanics. `api-and-workers.md:78-80` only says the supervisor "owns asyncio tasks, stop events, graceful shutdown".

**Proposal:** create `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/async-and-lifecycle.md` (about 100 lines).

### 5.1 Acquire multiple resources with `AsyncExitStack` (or open inside the `try` that closes)

- **Proposed rule:**
  > When acquiring N resources, every one that was acquired must be released if a later acquisition fails. Use `contextlib.AsyncExitStack`, or open each resource inside the `try` that owns its cleanup. Prefer `asyncio.TaskGroup` to `ensure_future` + `asyncio.wait(FIRST_EXCEPTION)` + manual cancellation. When closing several resources, use `gather(..., return_exceptions=True)` and report every failure, so one close error does not hide another. Never call a context manager's `__enter__`/`__exit__` by hand.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/pools.py:37-50` (verified): if the writer pool fails to open, the reader pool may already be open, and nothing closes it. `pools.py:52-54` closes both with `gather` without `return_exceptions`.
  - `.../investigation_agent/bootstrap/runtime.py:323-329` calls `await pools.open()` *before* the `try` whose `except` closes them.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/bootstrap/runtime.py:213-265` does manual `finally` bookkeeping with `None` sentinels.
  - `.../ingestion/adapters/s3/evidence_bucket.py:163,170-182` drives a `@contextmanager` by hand, typed `Any`.
- **Good:**
  ```python
  async with AsyncExitStack() as stack:
      reader = await stack.enter_async_context(reader_pool)
      writer = await stack.enter_async_context(writer_pool)
      yield DatabasePools(reader=reader, writer=writer)
  ```
- **Priority:** High

### 5.2 No blocking I/O on the event loop

- **Proposed rule:**
  > Ports for remote I/O (object store, HTTP, DB) are `async`. Adapters that wrap sync SDKs (boto3) offload each call with `await asyncio.to_thread(...)`, or use an async client. Bulk downloads use bounded concurrency. A one-shot CLI may block only before `asyncio.run(...)`.
- **Evidence:**
  - There is no `to_thread` or `run_in_executor` anywhere in `services/*/src`.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/ports/ingestion_ledger.py:68-71`: `ReceiptStore.read/write` are sync S3 calls made from async `ingest_dataset` (`application/ingest_dataset.py:167,187`).
  - `adapters/s3/evidence_bucket.py:86-108,170-176`: an async `load()` lists and downloads a whole edition synchronously and serially.
  - `bootstrap/runtime.py:221-224`: a sync `get_object` inside `async def run`.
- **Note:** `python-settings-config/SKILL.md:288-289` already recommends `asyncio.to_thread` for sync secret SDKs. Generalize that here and link to it.
- **Priority:** High

### 5.3 A deadline bounds every blocking phase

- **Proposed rule:**
  > When a call carries a deadline, bound every phase by the time remaining: pool acquisition, statement execution (`statement_timeout = min(configured, remaining_ms)`), and provider calls (`asyncio.timeout_at(deadline)`). Keep one `remaining(deadline)` helper per member (§3.3). `asyncio.timeout` around an executor-backed SDK call stops the *waiting*, not the thread; always pair it with the SDK's own `read_timeout`/`connect_timeout`.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/evidence_reader.py:132-134,189-191,243-245` bound acquisition with `min(acq, _remaining(deadline))`, but `statement_timeout` is fixed (`:313-316`). The same pattern is in `db/record_query_executor.py:170-184`.
  - Good: `genai/evidence_search/llm.py:18-22` (`async with asyncio.timeout(remaining)`) and `genai/shared/llm.py:49-53`, which sets the SDK's own timeouts.
- **Priority:** Medium

### 5.4 Exactly one retry owner per physical call

- **Proposed rule:**
  > Each physical call has exactly one retry layer. Under LangChain `ModelRetryMiddleware`/`ToolRetryMiddleware` or an application `RetryPolicy`, set SDK retries to zero (`botocore Config(retries={"max_attempts": 0}, connect_timeout=…, read_timeout=…)`) with a comment. An inner retry loop that bootstrap always configures to one attempt is dead code: delete one of the two layers. The retry policy object also owns its `retry_on` exception set, so that set is not passed alongside it through every constructor.
- **Evidence:**
  - Good: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/shared/llm.py:47-54,77-81`.
  - Bad: the ingestion Bedrock clients have no timeouts and keep botocore's default retries under `ModelRetryMiddleware(max_retries=3)`. See `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/entity_extraction/llm.py:36`, `genai/embeddings/llm.py:17`, `entity_extraction/agent.py:17-24`.
  - Nested retries: the executor loop (`.../investigation_agent/db/record_query_executor.py:132-154`) runs under `tool_retry_middleware(...)` (`genai/record_query/agent.py:103-105`), and bootstrap silently sets `max_physical_attempts=1` (`bootstrap/runtime.py:255`).
  - `transient_errors` appears 42 times across 13 files, passed next to `retry_policy=` 7 times in `bootstrap/runtime.py` (lines 236-309). `RetryPolicy` (`genai/shared/retry.py:49-62`) is the natural owner.
- **Existing coverage:** `boundaries.md:282` says only "retry policy near the boundary that retries". Nothing covers retry amplification.
- **Priority:** Medium

### 5.5 Cancellation-safe idioms (standardize the good patterns)

- **Proposed rules:**
  - In an async generator, wrap only the `await` in a timeout scope, never the `yield`.
  - With `gather(..., return_exceptions=True)`, re-raise any `CancelledError` found in the results.
  - Do not declare `async def` or use `asyncio.Lock` where nothing suspends.
  - Prefer `asyncio.Event` to polling with `sleep`.
- **Evidence:**
  - Good: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/application/invoke_turn.py:153-162` (a `timeout_at` around `anext` only, with a why-comment); `genai/evidence_search/retrieval.py:82-86,138-139`.
  - Questionable: `application/thread_locks.py:47-82` has an `asyncio.Lock` that is "never contended" (its own comment at `:64`) and `async` methods with no awaits.
  - `bootstrap/app.py:108-113` polls with `asyncio.sleep(0.05)` to drain in-flight work.
  - Good, and worth naming: shared bounded fan-out through a `Semaphore`-based throttle (`/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/shared/throttle.py:79-103`).
- **Priority:** Low

---

## 6. Service architecture and boundaries

Target: `python-service-architecture`, and the audit skill and script where noted.

### 6.1 Replace file mandates with ownership rules (`llm.py`, `agent.py`)

- **Target:** `python-service-architecture/SKILL.md:100-111` (invariant 4), `references/ai.md:191-286`, `references/boundaries.md:322-323`
- **Proposed rewrite of invariant 4 (GenAI part):**
  > Keep model construction, prompts, schemas, tools and behaviour-changing middleware under `genai/<task>/`. Build the model in a factory function; call the module `llm.py` when it has its own binding policy. Name every other module after what it contains (`runner.py`, `embedder.py`, `classifier.py`). Do not create a module whose body is only a re-export. Reusing a sibling task's factory means importing it from `genai/shared/`, not reaching into the sibling.
- **Why:** "Every GenAI task keeps model construction in an `llm.py` factory" (`SKILL.md:107-108`) and "Every GenAI task has `llm.py`" (`ai.md:193`) turned a filename into a slot to fill.
- **Evidence:** Of the 7 `llm.py` files, only 2 are factories:
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/relationship_extraction/llm.py:1-7` (verified) is a 7-line re-export that exists only to satisfy the rule.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/evidence_search/llm.py:11` is a capability adapter.
  - `genai/guardrails/llm.py:29,59` and `genai/state_projection/llm.py:13` are runner classes.
  - `.../ingestion/genai/relationship_extraction/agent.py:11` imports `retry_middleware` from its sibling task.
- **Also:** `ai.md:191-286` spends about 95 lines on this factory pattern. Shorten it to rules: no import-time handles, no global settings, pass the settings slice, and type the handles (§3.2).
- **Priority:** High

### 6.2 Ports: typed business contracts, and only for application-facing needs

- **Target:** `python-service-architecture/references/boundaries.md:37-55,103-109`; `templates.md:89-103`; audit script
- **Proposed rules:**
  1. Port signatures must not use `Any`, bare `object`, `Mapping[str, Any]`, or a framework method name (`ainvoke`, `astream`, `adelete_thread`). A streaming port yields a closed union of typed business events. Framework events are converted inside the port implementation, never in `api/`.
  2. `ports/` holds only contracts that `application/` imports. A contract between two implementation boundaries (for example, a genai tool that needs a DB reader) lives with its **consumer** (`genai/<task>/…`), and the provider imports it from there. It moves to `ports/` if it ever becomes application-facing.
  3. Ports contain no deterministic helpers and no I/O. Those belong in `domain/` or in the adapter.
  4. A private Protocol that narrows a third-party SDK surface for fakes (for example `ObjectClient` or `ReaderPool`) belongs in the adapter module that uses it. This is legitimate and is not a port. Remove a Protocol whose methods return `Any` or that has one implementation and no fake.
- **Why:**
  - `boundaries.md:103-105` ("Avoid weak contracts such as `dict[str, Any]`") is phrased as advice and is the most violated rule in the repo.
  - `ai.md:64-66` and `boundaries.md:109` disagree about where genai↔db contracts go.
  - 19 of 32 Protocols live outside `ports/`, and the skill never mentions them, so agents cannot tell a legitimate shim from ceremony.
- **Evidence (verified):**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/ports/investigator.py:27-34`: `stream_turn(self, turn_input: Mapping[str, Any] | None, …) -> AsyncIterator[object]`.
  - `api/sse.py:434-457` parses LangGraph `"updates"`/`"custom"` stream modes and node names. `api/sse.py:250-258` edits the graph input dict to inject a trace carrier.
  - `application/invoke_turn.py:291-303` builds the LangGraph message payload.
  - `ports/checkpoints.py:31` names a method `adelete_thread`, copied from LangGraph.
  - `ports/record_query.py` (235 lines) and `ports/evidence_search.py` are imported by no `application/` module, only by `db/` and `genai/`.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/ports/ingestion_ledger.py:43-51` does filesystem I/O (`read_bytes`) in a ports module.
  - Legitimate shims: `.../ingestion/adapters/s3/evidence_bucket.py:29`, `.../investigation_agent/db/record_query_executor.py:33-57`.
  - Ceremony: `bootstrap/runtime.py:88` (`Telemetry` returning `Any`), `api/problems.py:19`, `genai/shared/llm.py:9-14`.
- **Good (already in the repo; replace the invented example at `boundaries.md:86-95` with it):** `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/ports/entity_extractor.py:11-32`. It has a base, a transient and a permanent error, a typed input, and a one-method Protocol.
- **Priority:** High

### 6.3 Streaming use cases: the application owns execution and outcome

- **Target:** `python-service-architecture/references/api-and-workers.md:36-46`
- **Proposed rule:**
  > For a streaming or long-running action, the application layer runs the whole execution and returns a typed stream of business events, including the terminal outcome (completed / failed with class / cancelled). `api/sse.py` only encodes events, sends heartbeats, and turns client disconnects into cancellation. Deciding "timeout → budget exhausted" is application policy.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/api/sse.py:116-233` (118 lines) classifies failures (`:175-189`), reads the final state (`:196-204`), decides the terminal outcome (`:315-331`), and manages the telemetry lifecycle with about 12 `_close_telemetry` calls.
  - `application/invoke_turn.py:144-162` hands the raw graph stream to the API.
  - The router is thin (`api/routers/investigations.py:35`), but the complexity moved into `sse.py` rather than going away.
- **Why:** The existing router rule assumes request/response, so it is silently satisfied here while the business decisions live in the transport.
- **Priority:** Medium

### 6.4 The typed runtime container and test seams

- **Target:** `python-service-architecture/references/boundaries.md:144-159`
- **Proposed rules:**
  1. The runtime container returned by bootstrap holds only what the process boundary uses. Do not add fields for tests to inspect.
  2. Substitute test doubles at **one** seam: pass fakes for ports and resources into the composition function. Do not add `factory=`/`launcher=`/`hooks=`/`clock=None` parameters to every layer. A factories object is justified only for a constructor with an effect that cannot be moved behind an injectable port, and it must be typed without `Any` or `Callable[..., X]`.
  3. Import first-party and always-installed dependencies at module level. Use a function-local import only for an optional extra or to break a cycle, with a comment.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/bootstrap/runtime.py:107-109`: `agent: Any` and `checkpointer: Any` on `Runtime`, read only by `tests/unit/bootstrap/test_runtime.py:122-124`.
  - `runtime.py:127-137`: `RuntimeFactories` with `Callable[[DatabasePools, Settings], Any] | None`.
  - A chain of seams across layers: `main.py:35` `launcher=None`, `bootstrap/app.py:78` `hooks`, `genai/shared/llm.py:41` `factory=`, `application/invoke_turn.py:185` `clock=None`.
  - Local imports of the always-installed `observability` library: `bootstrap/app.py:43,44,62,122` and `bootstrap/runtime.py:340,438`.
  - `runtime.py:188-212` builds 7 identical chat clients through one closure and stores them in a 7-field `ModelClients`.
- **Priority:** High

### 6.5 Split the composition root by concern

- **Target:** `boundaries.md:151-159` (currently "Split a large runtime by construction concern", with no example)
- **Proposed rule:**
  > Keep `build_*` functions pure construction that return a container. Put open/close/flush in a lifecycle context manager (§5.1). Keep `run()` to orchestration and mapping outcomes to exit codes. Business validation (for example "the manifest edition must match the configured edition") belongs in the application action or domain. A composition function that takes more than about 6 positional collaborators should take a container instead.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/bootstrap/runtime.py:182-266` (`run`, 85 lines) sets up telemetry, silences loggers, parses the manifest, performs the edition-mismatch business check (`:227-231`), builds the plan, sets span outcome attributes and disposes resources.
  - `runtime.py:136-146` takes 9 positional parameters.
  - `runtime.py:112-113` is a pass-through wrapper.
  - `.../investigation_agent/bootstrap/runtime.py:215-311` is 97 lines and `:332-434` is 103 lines.
- **Priority:** Medium

### 6.6 Keep telemetry lifecycle out of use cases

- **Target:** `boundaries.md:200-221`; audit script (§6.12); `otel-observability` (§7.4)
- **Proposed rule:**
  > Application code may use the service's own `observability/` vocabulary: span-name constants, instrument wrappers, and one-line context helpers such as `with phase_span("x"):`. It must not import `opentelemetry` types (`Tracer`, `SpanContext`, `Link`), receive a `Tracer` through its dependencies, or build span attribute dictionaries inline. If telemetry makes up more than roughly a fifth of a use case's lines, move it into a decorator or context helper under `observability/`.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/application/ingest_dataset.py:18-22,82,135-136,204,294-306,342-352,395-405`. About 110 of its 439 lines are telemetry (`Tracer` in dependencies, `Link`/`SpanContext`, `otel_context.Context()` resets), which obscures the use case (skip → load → chunk → embed → extract → persist).
  - `investigation_agent` keeps application code free of OTel, so the two services follow opposite conventions.
- **Priority:** High

### 6.7 FastAPI access to the runtime

- **Target:** `python-service-architecture/references/api-and-workers.md:12,36-46`
- **Proposed rule:**
  > Store the typed `Runtime` on `app.state` once. Expose one accessor, `def get_runtime(request) -> Runtime`, and one `Annotated[..., Depends(...)]` alias per action. Do not look up attributes by string name, use `cast`, or re-validate values that bootstrap and settings already validated. Group transport policy scalars into a typed object (for example `SsePolicy`) instead of writing one dependency per scalar.
- **Evidence:** `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/api/dependencies.py:24-87` has 9 getters over `_runtime_component(request, "invoke_turn")` returning `object`, with 4 `cast`s and 4 re-validations (`:40-73`). `getattr(..., "turn_observer", None)` (`:66`) hides a real type error.
- **Good:**
  ```python
  def get_runtime(request: Request) -> Runtime:
      runtime = request.app.state.runtime
      if runtime is None:
          raise RuntimeNotReady
      return runtime

  RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
  ```
- **Priority:** Medium

### 6.8 Relax `api/schemas/`, and let names follow responsibility

- **Target:** `api-and-workers.md:12-17,44-46`
- **Proposed change:**
  > Reuse an application request or result model as the FastAPI model when it is deliberately the public contract (frozen, `extra="forbid"`). Create `api/schemas/` only when the HTTP shape differs (envelopes, path params, versioned fields). Define validation constants once and do not repeat checks Pydantic already enforced. The canonical tree lists roles, not required filenames: `api/problems.py` and `api/sse.py` are good precise names, and the audit should not flag them as drift from `exception_handlers.py`.
- **Evidence:**
  - The code reuses application models directly (`.../api/routers/investigations.py:19`, `threads.py:11`), and this works.
  - The ID pattern is duplicated between `application/invoke_turn.py:37` and `api/routers/threads.py:14`.
  - The 64,000-character limit is duplicated between `invoke_turn.py:47` and `bootstrap/runtime.py:388`.
  - `invoke_turn.py:194-195` repeats a `max_length` check that Pydantic already enforced.
- **Priority:** Low

### 6.9 Agents as workflows: where state transitions live

- **Target:** `ai.md` (new section next to "Classifier versus classification action", `:288-311`)
- **Proposed rule:**
  > When durable workflow state is an agent or graph checkpoint:
  > - **Domain** owns pure state-transition functions (`append_assistant_message`, `complete_turn`, `fail_turn`), tested without LangChain.
  > - **GenAI middleware** decides *when* to call them, at framework hook points, and builds no status payloads inline.
  > - **Application** owns pre-flight, idempotency and the outcome contract (§6.3).
  >
  > This layout is acceptable. Do not invent pass-through orchestration in `application/` to satisfy "no workflow in genai/".
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/investigation/middleware/turn_close.py:155-195` builds `TurnState` payloads (`status`, `safe_failure_code`, `pending_answer`) inline.
  - `ai.md:285-286` ("free of workflow orchestration… persistence decisions") gives no model for agent-as-workflow services.
- **Priority:** Medium

### 6.10 Extending a library type goes through public hooks only

- **Target:** `python-service-architecture/references/shared-libraries.md:151-167`
- **Proposed rule:**
  > A service extends a shared-library type only through documented public hooks or composition parameters. If a subclass needs `self._private` state from the library, the library is missing an extension point: add one, or keep the behaviour local. Do not call another class's `_private` helpers. A callback override must not swallow exceptions from `super()`.
- **Evidence:** `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/observability/instrumentation/model_callback.py:49` subclasses `observability.langchain.OTelModelCallback`. It reads the library-private `self._runs` (`:109,138,161,184,198,211`), calls `AttemptTelemetry._safe_call` from another class, and wraps `super().on_*()` in `except Exception: return` (`:107-108,171-173,192-194,201-204`).
- **Priority:** Medium

### 6.11 Adapter layout: rules exist but are unenforced, plus two additions

- **Target:** `boundaries.md:115-116,194-195` (existing rules); audit script
- **Proposed additions:**
  - `db/` owns all SQL, including DDL, bootstrap SQL and staging loads (see §8.6).
  - Delete production modules that only tests use.
  - Do not name production packages `fixtures/`, because the name reads as test support.
- **Evidence:**
  - One-file subpackages that the skill already forbids: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/adapters/s3/` and `adapters/filesystem/`.
  - `adapters/filesystem/receipt.py:13` (`FileReceiptStore`) is used only by `tests/unit/adapters/test_receipt.py`.
  - `adapters/fixtures/bank.py:123-142` runs DDL and `SET LOCAL search_path` outside `db/`. `adapters/fixtures/*` are production parsers for source formats.
- **Priority:** Medium

### 6.12 Checks to add to the audit script

Every check below would have caught a real miss in this repository.

| Check | Would have caught |
|---|---|
| Port signatures containing `Any`, `object`, `Mapping[str, Any]`, or `a`+framework-verb names | `ports/investigator.py:27-34`, `ports/checkpoints.py:31` |
| Each `ports/<m>.py` imported by ≥1 `application/` module | `ports/record_query.py`, `ports/evidence_search.py` |
| I/O calls (`open`, `read_bytes`, `rglob`) in `ports/` | `ingestion/ports/ingestion_ledger.py:43-51` |
| `adapters/<x>/` with exactly one non-`__init__` module | `adapters/s3/`, `adapters/filesystem/` |
| `sqlalchemy.text` / `.execute(` / `psycopg` outside `db/` | `adapters/fixtures/bank.py:123-142` |
| `observability/__init__.py` importing `langchain*` (directly or transitively) | `investigation_agent/observability/__init__.py:8` |
| `__init__.py` defining classes or functions (services only) | `genai/investigation/tools/__init__.py` |
| Exception classes in `application/`, `ports/` or `domain/` with `public_message`/`status_code`/`retryable` | `application/invoke_turn.py:64-101` |
| A module whose body is only imports plus `__all__` | `relationship_extraction/llm.py` |
| `model: Any` or `-> Any` in `genai/` | §3.2 |
| Duplicate private function names across modules; a string literal in ≥3 modules | §3.1, §3.3 |
| `INTERNAL_FORBIDDEN["observability"] = {"application"}`, plus an `adapters` entry | currently missing, even though `boundaries.md:205` states the rule |
| Fix the message "relative import crosses an implicit boundary" (`audit_service.py:163`) to "relative import (forbidden)" | wording |
| Resolve the telemetry-in-application rule (§6.6) and make the script agree | the 4 contested ingestion findings |

- **Priority:** Medium

### 6.13 Remove redundancy between the architecture skill, the audit skill and CLAUDE.md

- The 22-bullet "Dependency audit" in `boundaries.md:307-337` duplicates the audit skill (`audit SKILL.md:47-85`). Keep one copy, in the audit skill.
- `modularization.md:74-89` review questions repeat the same checklist. Remove them.
- Remove the `core/context` description from 2 of its 3 locations (`ai.md:28-43`, `boundaries.md:229-237`, `templates.md:37-39`).
- `ai.md:74-136` (expanded multi-agent tree with `genai/shared/{middleware,prompts,schemas,tools,retrieval}/`) contradicts flat-first. Delete it or cut it to 5 lines.
- `ai.md:166-189` duplicates the module-size advice in `modularization.md:33-35`. The size numbers disagree ("300–350" versus CLAUDE.md's "~300"); point to CLAUDE.md instead.
- `ai.md:350-356`: say explicitly that genai→application imports are allowed for tools that call a use case, so agents don't "fix" them.
- **Priority:** Medium

---

## 7. Observability and logging (`otel-observability`)

### 7.1 One owner per rule, and a deterministic check for the headline rules

- **Target:** `otel-observability` (all files)
- **Proposed change:**
  - `conventions/errors.md` owns the exception-detail policy. Replace the other roughly 17 statements with a link.
  - Rephrase the rule as a call-site rule: "Call sites never build `exception.*` fields; pass `exc_info=exc` (or `True`) and nothing else. The shared processor applies the one typed boolean `log_full_exception_trace`, which is never derived from the environment name."
  - The shared library must not bake in an environment policy. Today `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/logging.py:102` has the docstring "Full traceback in local/dev/staging; bounded indicators only in production", and `config.py:8,37` uses `Literal["full","safe"]`.
- **Evidence:** Besides §1.1:
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/observability/instrumentation/attempt.py:521-523,546-554` builds `exception.stacktrace` by hand from `traceback.extract_tb`, which keeps the top frames only. It drops the message and the `__cause__` chain, so the real provider or DB error behind `raise InvestigationError from error` (`genai/investigation/investigator.py:58,83`) is never shown.
- **Bad → good:**
  ```python
  fields["exception.stacktrace"] = _stacktrace_without_message(exception)  # bad
  self._logger.error(event, **fields)
  self._logger.error(event, exc_info=exception, **fields)                  # good
  ```
- **Priority:** High

### 7.2 Telemetry failure isolation, a new rule

- **Target:** `otel-observability/references/conventions/errors.md` (new section), plus a "Don't" line in SKILL.md
- **Proposed rule:**
  > Do not wrap OpenTelemetry *API* calls (`set_attribute`, `set_status`, `end`, `start_span`, propagator inject/extract, instrument `add`/`record`) in try/except; the API is specified not to throw. Guard app-owned telemetry code (recorders, aggregators) at most **once**, at the framework-callback or close boundary. That guard emits one `telemetry_failed` warning with `exc_info`. Never write `except Exception: return`.
- **Evidence:**
  - `attempt.py:538-543` defines `_safe_call` (`try: … except Exception: return None`), which is used 11 times, including around `span.end` and `span.set_attribute`.
  - `attempt.py:121-122,205-206,299-301,378-379`: silent `except Exception: return …` around `extract`, `start_span` and `inject`.
  - `.../api/sse.py:351-352`: `_close_telemetry` ends in `except Exception: return`.
  - The closest existing text (`shared_library.md:140`, "telemetry export or shutdown failures do not replace the business result") covers only export and shutdown.
- **Good:** `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/providers.py:163-170` isolates shutdown and logs a warning with `exc_info=True`.
- **Priority:** High

### 7.3 Snippets call the shared span helper; they don't inline the pattern

- **Target:** `otel-observability/references/**` (about 15 `except Exception as exc:` snippets, for example `conventions/errors.md:75,129`, `tracing/genai/langchain/tools_and_middleware.md:84`, `streaming_and_agent_span.md:79-89,226,284`, `tracing/queue_messaging.md:46,136,174`)
- **Proposed change:** Each snippet uses the shared helper (`with start_span(...)` that marks failure and re-raises, as in `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/spans.py:71-100`). The hand-written `set_status` + `ERROR_TYPE` form appears once, labelled "only inside framework callbacks where a context manager cannot be used". Remove the redundant `CancelledError` arms (§4.4).
- **Why:** Agents copy snippets. Evidence of this: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/application/ingest_dataset.py:314-316,369-371` repeats `except BaseException: span.set_attribute(...); raise` even though the helper already marks failure, and the library itself inlines `mark_failed` again at `libs/observability/src/observability/langchain.py:264-265,276-277`.
- **Priority:** High

### 7.4 Budget how much instrumentation intrudes on business code

- **Target:** `otel-observability/SKILL.md` rule list (next to rule 11, `:89`)
- **Proposed rule:**
  > Business functions contain at most one-line telemetry constructs: `with phase_span("x"):`, a decorator, or middleware registration. The terminal outcome, metrics and failure log are closed by **one** context manager or wrapper on every exit path (success, exception, cancellation), never by N manual close calls. Replace `if telemetry is not None` branching with a no-op implementation. Telemetry objects never enforce business behaviour such as cancellation.
- **Evidence:**
  - Bad: `.../investigation_agent/api/sse.py:116-233` has about 12 `_close_telemetry(...)` calls and 4 `if telemetry is not None` checks.
  - Bad: `attempt.py:382-385`, where `ensure_not_cancelled()` is called from telemetry middleware (`observability/instrumentation/middleware.py:28,44,63`).
  - Bad: `attempt.py` is 554 lines mixing span lifecycle, contextvars, metric aggregation, terminal logging and carrier injection.
  - Good: `investigation_agent` GenAI modules have 0–3 telemetry lines each (e.g. `genai/investigation/middleware/evidence.py`, 0 of 225); `with phase_span("verify_grounding"):` (`genai/investigation/middleware/grounding.py:65`); tool and model spans from middleware (`observability/instrumentation/middleware.py:17-67`).
- **Priority:** Medium

### 7.5 One measurement goes to one instrument; each signal has a stated consumer

- **Target:** `otel-observability/SKILL.md` Step 4 (`:270-280`), `references/metrics/service.md`
- **Proposed rule:**
  > Do not record the same value in two instruments that differ only by name or namespace. Each new instrument or span attribute names the query, dashboard or alert it serves. Per-item spans (per chunk, per row) carry no positional or debug attributes (offsets, indices) unless a named investigation needs them. Never build attribute, metric or log keys from runtime values; use a bounded attribute *value* instead.
- **Evidence:**
  - `.../investigation_agent/observability/events.py:73-176` defines 16 instruments. `:214-223` records `duration_s` three times.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/embeddings/embedder.py:108-118` puts 9 attributes on every embedding span, including `chunk_char_start` and `chunk_char_end`.
  - `.../ingestion/bootstrap/runtime.py:256-257` builds attribute keys at runtime (`f"app.ingestion.{key}"`, with keys such as `records_{source_system}`). The same dict becomes log field names (`application/ingest_dataset.py:182`).
  - The existing rules (`naming.md:56`; `SKILL.md:274`, "A value being available is not a reason to record it") are right but are not enforced, and nothing addresses duplicate instruments.
- **Priority:** Medium

### 7.6 Give business failure taxonomies a home; keep `error.type` clean

- **Target:** `otel-observability/references/conventions/errors.md:168-189`
- **Proposed change:**
  > `error.type` is the result of the shared `error_type_of(exc)` (class name or provider code) or one of the defined sentinels. A bounded business failure taxonomy goes in a separate attribute, for example `app.failure.class`. Provider error-code extraction and transient classification exist once, in the shared library.
- **Why:** The current text ("the set of sentinels is exactly these three — anything else is a class name") gives a taxonomy nowhere to go, so the service invented one and wrote it into `error.type`.
- **Evidence:**
  - `.../investigation_agent/observability/events.py:14-26` defines `FailureClass`, which is written to `error.type` on spans (`attempt.py:388-393,473`) and on standard GenAI duration metrics (`events.py:213-218`), mixed with the class name `CancelledError` (`attempt.py:410`).
  - Ingestion's ledger uses `type(exc).__name__` (`application/ingest_dataset.py:162`) while its spans use `error_type_of`.
  - The `_NONE`-on-success rule (`errors.md:184-189`) is used 0 times. Either drop it or explain the reason for it.
- **Priority:** Medium

### 7.7 Naming: one enum per service for event names and label keys

- **Target:** `otel-observability/references/conventions/naming.md`, `references/logging/structlog.md:170-178`
- **Proposed rule:**
  > Log event names and metric label keys come from one enum per service, checked by a regex test. Metric labels use the same keys as span attributes (`app.outcome`, not `outcome`). Pick one event-name style (dotted-namespace or bare snake_case past tense) and make the skill's examples use it.
- **Evidence:**
  - `.../investigation_agent/observability/events.py:30-33` mixes `"investigation.request_failed"` and `"agent_invocation_cancelled"`.
  - Labels are `"workflow"`, `"outcome"` and `"result.kind"` in one service (`:222,252`) but `"kind"`, `"outcome"` and `"source_system"` in the other (`.../ingestion/observability/events.py:66,70`).
  - `observability/instrumentation/middleware.py:65` uses `"unknown_tool"` where the skill says `custom_tool` (`naming.md:47`).
  - The library logs a prose message with `extra=` (`libs/observability/src/observability/providers.py:164`).
- **Priority:** Medium

### 7.8 Replace the skill-prose validator with a code audit

- **Target:** `otel-observability/scripts/`
- **Proposed change:** Add a repository audit script of about 150 lines that flags:
  - an `except Exception`/`BaseException` whose body neither re-raises nor logs;
  - `"exception.` string literals outside the logging processor;
  - `record_exception(` and `add_event(`;
  - f-string attribute keys;
  - `error.type` values that are neither class-like nor a sentinel;
  - redundant `except CancelledError: raise` arms;
  - try/except wrapped around OTel API calls.

  Retire or shrink `validate_skill.py` (§1.4).
- **Priority:** Medium

### 7.9 Fix `references/testing.md` in this skill

- **Target:** `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/otel-observability/references/testing.md`
- **Defects:**
  - The `span_exporter` fixture (`:37-48`) yields only the exporter, but `:65` says "Pass the provider into the code under test", and the provider is unreachable. This is why the repo invented 4-tuple fixtures.
  - `:204` uses an undefined `tracer` fixture, and `:222` an undefined `data_points` helper.
  - `:79` puts helpers in a bare `tests/telemetry_assertions.py`, which contradicts member-qualified support packages (§9.1) and cannot be imported under importlib mode.
  - The helpers are typed `Any` (`:83-93`).
- **Proposed change:** Yield a typed `TelemetryCapture` dataclass (tracer provider, span exporter, meter provider, metric reader) built with the **production View list** (`:57-59`, which is already a rule). Place it in the member's support package, and make the examples self-contained.
- **Evidence the View rule is not followed:** `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/conftest.py:195`, `services/ingestion/tests/unit/genai/conftest.py:130`, `services/investigation_agent/tests/unit/observability/test_instrumentation.py:77` (versus the correct `libs/observability/tests/conftest.py:26`).
- **Priority:** Medium

### 7.10 Good patterns to cite as canonical

- Span helper that marks and re-raises: `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/spans.py:22-40,71-100`.
- One terminal log at the job boundary: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/bootstrap/runtime.py:248-253`.
- Config errors reported before telemetry starts, printed to stderr with a distinct exit code: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/main.py:38-43`, `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/main.py:14-19`.
- Shared redaction and stdlib-bridge processors: `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/src/observability/logging.py:52-88,172-185`.

---

## 8. Database and data access (`python-sqlmodel-alembic`)

### 8.1 Make the skill match the stack, or route around the mismatch

- **Target:** `python-sqlmodel-alembic` (name, SKILL.md routing)
- **Proposed change:** Rename the skill to something like `python-postgres-data-access`, with references for:
  - SQLModel + SQLAlchemy async;
  - raw `psycopg`/`psycopg_pool`;
  - Alembic;
  - roles and read paths.

  At minimum, add a routing line: "If the service uses psycopg directly (including LangGraph `AsyncPostgresSaver`, which requires a psycopg pool), follow `references/psycopg.md`."
- **Why:** The skill says "async only… SQLModel query builder" (`SKILL.md:12-14,79-81,95-98`) and assumes Alembic throughout. The repo's reality is different:
  - there is no Alembic;
  - ingestion uses SQLAlchemy async + SQLModel with `create_all` ("No Alembic: the prototype rebuilds, it never migrates", `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/extensions.py:1,18-19`);
  - `investigation_agent` uses raw psycopg with `AsyncRawCursor` (`/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/pools.py:64-81`) and has its own versioned initializer (`db/initializer.py:13,206-256`).
- **Also fix:**
  - "Prefer SQLModel's `AsyncSession`" (`engine-and-session.md:99-103`, `repositories-and-queries.md:37-41`) should be conditional: use it when you return model instances. Core-shaped repositories (bulk `insert().on_conflict_do_update`) gain nothing from `.exec()`, and the repo correctly uses SQLAlchemy's session.
  - The hard-coded pool numbers and `pool_recycle=1800` (`engine-and-session.md:57-63`) should be taken from settings, with a note on when each knob matters.
  - Recommend the `sqlalchemy[asyncio]` extra rather than the greenlet advice (`:30-36`).
  - Make the naming convention (`models-and-base.md:13-28`) read "or name every constraint explicitly in `__table_args__`".
- **Priority:** High

### 8.2 Transaction ownership (standardize the good pattern)

- **Target:** `references/repositories-and-queries.md`, `references/engine-and-session.md:93-96,111-117`
- **Proposed rule:**
  > Repositories never call `commit`, `begin` or `rollback`. One unit-of-work method on the adapter (the port implementation) opens `async with session_factory() as s, s.begin():` and composes repositories inside it: one port call is one transaction. Durable "run started" markers get their own committed transaction so they survive a failed run. Plain reads may rely on autobegin.
- **Evidence (good):**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/store.py:27-68` wraps every port method in a transaction. Repositories only `execute`/`flush` (`repositories.py:198-199`).
  - The ledger's `start` is committed separately (`store.py:52-54`).
- **Why:** The skill's `get_session` never begins or commits, and nothing says who does.
- **Priority:** High

### 8.3 SQL composition: identifiers versus values, and parameter numbering

- **Target:** new raw-SQL section/reference
- **Proposed rule:**
  > Values are always bound parameters. Identifiers and DDL fragments use `psycopg.sql.Identifier`/`sql.Literal` or SQLAlchemy DDL constructs. An f-string is allowed only for a module constant or an already-validated int, with a comment saying so. For internally composed optional filters, one builder returns `(clauses, params)` and owns *all* placeholder numbering. Use `$n`/`AsyncRawCursor` only where the SQL is externally authored and must round-trip exactly; elsewhere use named placeholders. Inline composed SQL is correct for dynamic filters and view DDL, so the "`.sql` file" rule (`SKILL.md:95-98`, `repositories-and-queries.md:43-46`) applies only to static queries.
- **Evidence:**
  - Good: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/initializer.py:358-363,402-415` (`sql.Identifier`/`sql.Literal`).
  - Fragile: `db/evidence_reader.py:182-206,284-304`. `_graph_filters` hard-codes `$2` while the caller starts numbering at 3.
  - Undocumented f-strings: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/indexes.py:31-48`, `db/extensions.py:15`.
- **Priority:** Medium

### 8.4 Read paths for untrusted or LLM-authored SQL (codify an excellent existing pattern)

- **Target:** new reference in the DB skill; cross-link from `python-service-architecture/references/ai.md`
- **Proposed rule (defence in depth, all required):**
  1. AST allowlist validation before pool checkout.
  2. A dedicated reader role with `default_transaction_read_only=on`, a pinned `search_path`, and grants only on `security_barrier` views.
  3. Per-transaction `SET TRANSACTION READ ONLY` and `set_config(..., true)` for statement, lock and idle timeouts. Use transaction-local settings, never session-level `SET`, on pooled connections.
  4. Wrap the query as `SELECT * FROM (<canonical>) LIMIT max_rows+1` to detect truncation.
  5. Fetch with `fetchmany`, capping both rows and bytes.
  6. Retry transient errors only, never `QueryCanceled`.
  7. Validate once and pass the validated plan down; do not re-parse.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/db/record_query_executor.py:124-130,171-187,220-245,365-378`; `db/initializer.py:394-453`; `db/record_query_policy/validation.py:29-80`.
  - Wasted work: the SQL is validated in the agent (`genai/record_query/agent.py:152`) and again in the executor (`:128`), and each validation parses twice. That is 4 `pglast` parses per call.
- **Priority:** High

### 8.5 Batching, bulk writes, and rebuild semantics

- **Target:** `references/repositories-and-queries.md`
- **Proposed rules:**
  - Load related rows with one `= ANY($1::text[])` query per batch (per hop for graph traversal), never one query per ID.
  - Do pagination and "latest per key" in SQL with keyset predicates, not by deserializing everything in Python.
  - Bulk upsert uses `insert(...).on_conflict_do_update(index_elements=[natural_key], set_={...: excluded...})`. The chunk size comes from the 65,535 bind-parameter limit (`65535 // n_columns`), not a magic number.
  - A projection that is "rebuilt every run" must delete rows this run did not produce. An upsert on its own is not a rebuild.
- **Evidence:**
  - Good: `.../investigation_agent/db/evidence_reader.py:375-398`; `application/find_connections.py:57-86` (one query per hop); `db/initializer.py:262-266` (`unnest`).
  - Bad: `application/read_history.py:109,142-153` scans up to 10,000 checkpoints, deserializing each one, then sorts and pages in memory. Results silently become wrong beyond 10,000.
  - Bad: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/db/repositories.py:37-51` uses a hard-coded 500 and takes the column list from `rows[0]`.
  - Bad: `libs/evidence_model/src/evidence_model/tables.py:3-5` claims projections are "rebuilt… on every run", but there is no DELETE or TRUNCATE anywhere in ingestion.
- **Priority:** Medium

### 8.6 Schema ownership, prototype mode, and staging loads

- **Target:** `python-sqlmodel-alembic/SKILL.md:82-87` and `references/schema-verification.md`
- **Proposed rules:**
  1. Every schema object has exactly one owning deployable and one versioned history, one per **schema-ownership boundary**. Disjoint owners get separate `version_table_schema`s. Cross-owner dependencies (for example views over another owner's tables) are declared, and their ordering is enforced by the deploy graph.
  2. `create_all()` and hand-rolled initializer versions are allowed only in a declared **rebuild-only prototype mode**, stated in the module docstring, with exit criteria: a second DDL owner, or the first persistent environment. One-shot initializers take an advisory lock.
  3. A consumer's column contract over a shared schema is *derived* from the shared metadata (`Table.columns`), not re-typed. Contract tests compare **types**, not only names.
  4. Inside a transaction, never run cleanup SQL in `finally`. After a failed statement Postgres rejects everything until rollback, so the cleanup error replaces the real one. Rely on rollback, or use `CREATE TEMP TABLE … ON COMMIT DROP`.
  5. Never execute SQL text taken from outside the repository (object storage, uploads) under an application role.
- **Evidence:**
  - `.../investigation_agent/db/initializer.py:219-231`: any version bump raises `IncompatibleInitializerVersion`, so there is no upgrade path.
  - The ordering exists only in Compose (`/Users/arafiet/MyProjects/Deep-Analyst/compose.yaml:316-328`).
  - The column contract is copied 3 times (`initializer.py:30-109,111-189`; `db/record_query_policy/catalog.py:11-62`) and has drifted. The catalog says `amount_minor` is `bigint`, but `/Users/arafiet/MyProjects/Deep-Analyst/libs/evidence_model/src/evidence_model/tables.py:106` declares `amount_minor: int` (verified), which SQLModel maps to `INTEGER`. That is also an int32 overflow risk for money.
  - The contract test checks names only: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/contract/test_agent_read_views.py:11-21`.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/adapters/fixtures/bank.py:129-142` runs `DROP SCHEMA` in `finally` inside `engine.begin()`, and runs a SQL script materialized from S3 through `exec_driver_sql` under the ingestion role.
- **Priority:** High

### 8.7 Pools: configure invariant session settings once

- **Target:** `references/engine-and-session.md` (generalized to psycopg_pool)
- **Proposed rule:**
  > Construct pools unopened in bootstrap, from settings, with an explicit `max_waiting` and acquisition timeout. Put invariant session settings (search_path, read-only default, `prepare_threshold=0` behind PgBouncer) in the pool's `configure` callback or connection `options`. Do not set them per query.
- **Evidence:**
  - Good: `.../investigation_agent/db/pools.py:18-29,61-102`.
  - Wasteful: `SET TRANSACTION READ ONLY` plus a `set_config` round trip on every read (`db/evidence_reader.py:307-316`, `db/record_query_executor.py:174-184`), even though the role already defaults to read-only (`initializer.py:429`).
- **Priority:** Low

### 8.8 Disposable test databases: state the invariant, not the variable name

- **Target:** `references/schema-verification.md:95-104`
- **Proposed rule:** The integration fixture reads a variable separate from the application's `DATABASE_URL`, refuses database names that do not look disposable, and fails rather than skips when the variable is absent in the integration profile. Each service's fixtures drop only the schemas that service owns.
- **Evidence:** Both conftests implement the guard well (`/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/integration/conftest.py:36-40`, `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/integration/conftest.py:36-42`), but each drops the *other* service's schemas (`ingestion …:48-54`; `investigation_agent …:52-63`). The agent conftest also re-declares 7 ingestion tables by hand (`:118-168`).
- **Priority:** Low

---

## 9. Tests and testability (`pytest` + `python-service-architecture/references/testing.md`)

### 9.1 A working recipe for importable test-support code under importlib mode

- **Target:** `python-service-architecture/references/testing.md:157-174` owns the mechanism. `pytest/references/core-principles.md:62-63` links to it. Fix `pytest/references/examples-core.md:130-146`.
- **Proposed rule:**
  > Put a fake, builder or harness used by more than one test module in a member-qualified support package, e.g. `services/investigation_agent/tests/investigation_agent_testsupport/`. Make it importable with `[tool.pytest.ini_options] pythonpath = ["services/investigation_agent/tests", …]` plus the matching `mypy_path`. The package name must be globally unique. `conftest.py` only defines fixtures that wire those imported types together. Forbidden: fixtures returning a module (`sys.modules[__name__]`), fixtures returning a class or function just so tests can reach it, and `type(fixture().attr)` to recover a class.
- **Why:** The skills say "Never import `conftest.py`", "use a member-qualified support package" and "prefer importlib mode", but never how to make that package importable. The repo could not work it out and built workarounds, which then led to §9.2.
- **Evidence (verified):**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/unit/genai/investigation/conftest.py:408-414` is a `support()` fixture returning `sys.modules[__name__]`. It is consumed as `support.` 139 times across 3 test files, always typed `Any`.
  - The conftest is 414 lines and holds 4 fakes, 8 builders and a harness.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/genai/conftest.py:97-119` has 5 fixtures that return classes or functions.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/application/test_ingest_dataset.py:111`: `type(deps_factory().entity_extractor)`.
- **Bad → good:**
  ```python
  # bad
  @pytest.fixture
  def support() -> Any:
      return sys.modules[__name__]

  # good
  from investigation_agent_testsupport.agent import Harness, build_harness
  ```
- **Exceptions:** A fake used by exactly one test module stays in that module.
- **Priority:** High

### 9.2 Extract fakes on the second copy

- **Target:** `pytest/references/core-principles.md` ("Fixtures reveal ownership and cost")
- **Proposed rule:**
  > Treat a test double that subclasses a third-party type (`BaseChatModel`, `Embeddings`, `SpanExporter`) or implements a production port as support code. When a second copy appears, extract it (§9.1). Do the same for shared "fast test policy" constants.
- **Evidence:**
  - `ScriptedChatModel` has 5 copies (`.../investigation_agent/tests/unit/genai/record_query/test_query_agent.py:44`, `unit/genai/evidence_search/test_search_agent.py:32`, `integration/test_end_to_end_scripted.py:63`, `contract/framework/test_pinned_langchain_langgraph.py:46`, `unit/genai/investigation/conftest.py:55`). There are 8 handwritten `BaseChatModel` fakes in total.
  - `RetryPolicy(max_attempts=2, initial_delay_s=0, …)` is repeated 10 times.
  - The telemetry capture fixture is rebuilt 6 or more times, in different shapes.
- **Priority:** High

### 9.3 Fakes must be correct: no normalization, and loud exhaustion

- **Target:** `pytest/references/core-principles.md` ("Use doubles deliberately"), `pytest/references/langchain-langgraph.md`
- **Proposed rules:**
  1. A fake records what it received, in the order received. It must not sort, dedupe, trim or canonicalize any property a test asserts on.
  2. A scripted model, tool or runner raises `AssertionError("unscripted call N to <name>")` when its script runs out. It never repeats the last response or returns a default. When a retry or resume can legitimately replay a call, derive the response from the input.
  3. Every harness or builder parameter is used by at least one test. Delete unused helpers.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/conftest.py:74-75` (verified) sorts entities in the fake. The test `test_stored_graph_is_identical_regardless_of_task_completion_order` (`test_ingest_dataset.py:107-126`) then asserts on that order, so the assertion can never fail.
  - Three exhaustion policies exist in one conftest: `.../investigation/conftest.py:86` repeats the last response, `:151` returns `NO_SUPPORT`, and `:208-210` raises (correct).
  - Dead harness parameters: `interrupt_after` (`:359,383-386`), `wait_for` (`:398-407`, no callers).
- **Priority:** High

### 9.4 A canonical tool-binding fake chat model

- **Target:** `pytest/references/examples-langchain-langgraph.md`; `langchain-langgraph.md:58-61`
- **Proposed addition:** One reference `ScriptedToolChatModel(BaseChatModel)` with these properties:
  - `bind_tools` returns `self` and records the tools and `tool_choice`;
  - it mints fresh message and tool-call IDs on every call (the gotcha documented at `.../investigation/conftest.py:88`: "the reducer keys on them");
  - it raises when the script is exhausted;
  - it records the messages it saw;
  - mutable fields use `Field(default_factory=list)`.

  State that `GenericFakeChatModel` does not support `bind_tools`, so `create_agent` tests need a model like this.
- **Evidence:**
  - The skill names `GenericFakeChatModel` and gives no recipe for tool binding. The repo has 0 uses of `GenericFakeChatModel` (verified) and 8 handwritten fakes.
  - Class-level mutable defaults: `.../investigation/conftest.py:58-60`.
- **Priority:** Medium

### 9.5 Typed fixture boundaries

- **Target:** `pytest/references/core-principles.md:64`
- **Proposed rule:**
  > Fixtures and builders return concrete types; never `Any`. Replace tuple fixtures with a small frozen dataclass (for example `TelemetryCapture`). Builders use explicit keyword parameters or `dataclasses.replace` / `model_copy(update=…)`, never `**overrides` into `Model(**values)  # type: ignore`. Narrow an optional with its own `assert x is not None` line, not `assert x is not None and x.y == …`.
- **Evidence:**
  - 58 fixture parameters are typed `Any`.
  - `_, exporter, _, _ = telemetry` (`.../ingestion/tests/unit/application/test_ingest_dataset.py:14`).
  - `**values  # type: ignore[arg-type]` builders: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/domain/test_candidates.py:45,140`, `libs/observability/tests/test_providers.py:27`.
  - 52 compound asserts of the form `is not None and`.
  - Log records stored as tuples and read by index: `.../investigation_agent/tests/unit/observability/test_instrumentation.py:40-62`.
- **Priority:** Medium

### 9.6 One behaviour family per test, and no tautologies

- **Target:** `pytest/SKILL.md` (writing step 5 at `:173-174`, quality gate at `:188-207`)
- **Proposed rules:**
  1. A test asserts one behaviour's oracle. Business outcome, emitted telemetry and framework graph shape go in separate tests, even when they share an arrangement: share the harness, not the assertions. A test name joining two independent outcomes with `_and_` is a signal to split. Sequential protocols such as "pauses and resumes" are exempt. Use exact values when the value is deterministic (not `>=`).
  2. Every assert must depend on a value produced by the subject. Reject assertions on a local literal the subject never touched, on the environment (`datetime.now().year`), and `is not None` on factories that cannot return `None`.
- **Why:** "Assert the complete semantic outcome" (`SKILL.md:173-174`) is being read as permission for kitchen-sink tests. The quality gate only names the mock-tautology case (`:192`).
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/unit/genai/investigation/test_agent.py:60-100` has 14 asserts mixing turn status, citations, usage (`model_calls >= 2`) and middleware node names.
  - `.../ingestion/tests/unit/application/test_ingest_dataset.py:10-60` has 20 asserts, and its name promises a receipt ordering that it never checks.
  - 21 tests have 10 or more asserts; 140 of 371 names contain `_and_`.
  - Tautologies: `.../investigation_agent/tests/unit/observability/test_instrumentation.py:631,652` (`result = {...}` … `assert result == {...}`), `.../ingestion/tests/unit/bootstrap/test_runtime.py:178` (`datetime.now(UTC).year >= 2026`), `libs/observability/tests/test_providers.py:67`.
- **Priority:** Medium

### 9.7 Precise `pytest.raises` and parametrization

- **Target:** `pytest/references/core-principles.md:72-74,169`; `examples-core.md`
- **Proposed rules:**
  - Assert the single exception type the contract promises, plus `match=` or an attribute check that identifies the reason. Use a tuple of types only if the public contract really is a union, and say so in a comment.
  - When a test is parametrized over rejection reasons, every case needs a reason oracle. Otherwise a case can pass because an earlier, unrelated check rejected it.
  - Every parameter is used, and the body never branches on a parameter.
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/libs/evidence_model/tests/test_drafts.py:47,49,109,114` use `(OntologyViolation, ValidationError)`.
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/unit/db/test_record_query_policy.py:86-94` parametrizes adversarial SQL cases but asserts only the exception type.
  - `test_agent.py:295-345` has an unused `verifier` parameter and branches on `violation`.
- **Priority:** Medium

### 9.8 Deterministic interleavings and time

- **Target:** `pytest/references/core-principles.md:82-98,104-124`
- **Proposed rules:**
  - Prove order-independence by forcing a specific adversarial completion order (release per-item `asyncio.Event`s in reverse), not with random sleeps.
  - Drive timeout behaviour with an injected clock or deadline. Never `sleep(2 × timeout)`.
  - Identify real-infrastructure resources with `uuid4()`, not timestamps.
  - Show the concrete async fixture options: `pytest_asyncio.fixture(scope="session", loop_scope="session")`, or a sync session fixture with `asyncio.run`. Use a module-level `pytestmark = pytest.mark.asyncio` rather than per-test markers (175 of them today).
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/conftest.py:135-139` uses an unseeded `random.uniform` sleep.
  - `.../investigation_agent/tests/unit/application/test_invoke_turn.py:333,345,357` uses `turn_timeout_s=0.05` with `sleep(0.1)`, even though a clock is injected.
  - `integration/test_end_to_end_scripted.py:293` builds IDs from a timestamp.
  - Good: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/unit/genai/test_throttle.py:7-17,57-73` (a `FakeClock` with injected sleep and `Event`s).
- **Priority:** Medium

### 9.9 Test profiles: framework characterization and architecture fitness

- **Target:** `pytest/SKILL.md:103-105,195-196`; `python-service-architecture/references/testing.md:40-62`
- **Proposed rule:**
  > Allow a `contract/framework/` suite of **characterization tests** for third-party behaviour the application depends on. Each test is named after the application assumption it protects, runs a minimal synthetic graph rather than the app, and one test pins the locked versions. Rerun and review the suite on every dependency bump. Unit tests then do not re-assert framework shape (node names, `agent.nodes["tools"].bound…`). Also add **architecture fitness** tests (import-boundary checks) to the classification table.
- **Evidence:**
  - Good: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/contract/framework/test_pinned_langchain_langgraph.py:1-6,134-138`.
  - Good: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/contract/architecture/test_import_boundaries.py` (ingestion has no equivalent).
  - Duplication: `test_agent.py:52,98-99` re-asserts what the pinned suite already covers (`:328-384`).
- **Also:** say where settings validation tests go (unit for validation logic, contract for shipped YAML and `.env.example`). Today they sit in `unit/config/` in one service and `contract/config/` in the other. Register a `contract` marker; today only `integration` and `live` exist.
- **Priority:** Medium

### 9.10 Seam smells in production code

- **Target:** `python-service-architecture/references/testing.md:176-195` (list), referenced from `pytest/SKILL.md:45-48`
- **Proposed rule:**
  > Report these as missing seams; do not work around them:
  > - hard-coded `connect()` or client construction inside an adapter method (take a factory);
  > - composition dataclasses typed with concrete classes instead of ports (which forces `# type: ignore` on fakes);
  > - tests that monkeypatch `module._private` names;
  > - `SimpleNamespace` substituted for a typed runtime (field renames go undetected).
- **Evidence:**
  - `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/tests/unit/db/test_initializer.py:159-170` monkeypatches private members because `src/.../db/initializer.py:216,244,380` hard-codes `AsyncConnection.connect`.
  - `test_instrumentation.py:618` and `unit/db/test_pools.py:73` need `# type: ignore` because of concrete-typed fields.
  - `SimpleNamespace` runtimes: `.../tests/contract/api/test_http_contract.py:120`, `tests/unit/api/test_investigations_router.py:51,62-64`.
- **Good seams to cite:** `AttemptTelemetry(..., logger=, clock=)`, `execute_guarded_select(..., sleep=)`, `IngestionDependencies(clock=)`.
- **Priority:** Medium

### 9.11 Split ownership between the two testing skills

- **Target:** `pytest` and `python-service-architecture/references/testing.md`
- **Proposed change:**
  - The architecture `testing.md` owns placement, classification, markers, CI selection and the support-package mechanism.
  - `pytest` owns test design, doubles, assertions and async.
  - Each keeps a single pointer to the other and deletes its duplicate paragraphs (listed in §1.1).
  - Today `pytest/SKILL.md:119-159` never points to the architecture `testing.md`, and `python-service-architecture/SKILL.md:56-61` never points to `pytest`.
- **Also:**
  - Compose/config contract tests should assert structural facts (`depends_on` conditions, read-only mounts, required keys), not substrings of shell commands (`/Users/arafiet/MyProjects/Deep-Analyst/tests/test_compose_contract.py:17-20`).
  - An SQL-text assertion in a unit test is acceptable only if an integration test proves the effect (good pairing: `.../tests/unit/db/test_record_query_executor.py:103-119` with `.../tests/integration/db/test_roles_and_tools.py:149`).
- **Priority:** Medium

### 9.12 Good defaults to state explicitly

- **"Default to zero `unittest.mock`."** The repo has 0 uses across 371 tests. Say it at `pytest/references/core-principles.md:10-23`.
- **Redaction canaries.** Pass a secret sentinel through the code and assert it does not appear in the output: `.../investigation_agent/tests/unit/config/test_secrets.py:102,130,171`, `test_instrumentation.py:499`.
- **Prove "import is inert" in a subprocess:** `/Users/arafiet/MyProjects/Deep-Analyst/libs/observability/tests/test_providers.py:37-45`.
- **Live profile:** `pytestmark = pytest.mark.live`, `pytest.fail` when the environment is missing, and bounded shape assertions: `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/tests/live/test_bedrock_extraction.py:24-40`.

---

## 10. Enforce with tooling instead of prose (`python-repository-setup` + root `pyproject.toml`)

- **Target:** `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-repository-setup/SKILL.md:283-314`, `assets/workspace-template/pyproject.toml`, `/Users/arafiet/MyProjects/Deep-Analyst/pyproject.toml:33-34,64-67`
- **Proposed rule:** For every rule a linter can check, enable the linter and state the rule nowhere else. For each rule family in the template, give a one-line rationale.
- **Measured cost on this codebase** (read-only probe):
  - `RUF, SIM, C4, PIE, RET, PERF, C90, PGH, FURB` produce about 30 findings, 22 of them auto-fixable. That locks in the current quality at almost no cost.
  - `ANN401` (with per-file ignores for true adapters), `FBT001/FBT003` and `PLR2004` (tests excluded) enforce §3.2, §3.4 and §3.7.
  - `RUF022` enforces sorted `__all__`.
  - `S101` with tests excluded enforces §3.5 (`assert`).
  - **Do not** add `TRY003`/`EM`: 349 hits for little value.
- **mypy:** add `warn_unreachable = true` and `enable_error_code = ["ignore-without-code", "redundant-expr", "possibly-undefined"]`. The probe found 11 real dead or unsafe branches. The skill's mypy block is also missing the `pydantic.mypy` plugin that the repo uses.
- **Complexity:** `[tool.ruff.lint.mccabe] max-complexity = 10` makes CLAUDE.md rule 1's complexity limit enforceable (§1.3).
- **Priority:** Medium

---

## 11. GenAI-specific additions (`python-service-architecture/references/ai.md`)

### 11.1 Build prompts from the constants they describe, and version every prompt

- **Proposed rule:**
  > When a prompt states a limit, tool name, schema name or delimiter that code also enforces, build the prompt from the constant (a module-level f-string or builder), or add a test asserting that the two match. Every `prompts.py` exports `PROMPT_VERSION`.
- **Evidence:**
  - "at most three times" is hard-coded in `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/record_query/prompts.py:7` and `genai/evidence_search/prompts.py:7`, while `MAX_SEMANTIC_ATTEMPTS = 3` is itself defined twice (`record_query/schemas.py:12`, `evidence_search/schemas.py:14`).
  - `genai/investigation/prompts.py:14` says "exactly three tools".
  - `PROMPT_VERSION` exists only in ingestion. None of the 5 investigation `prompts.py` files has one, although `ai.md:343-344` already asks for it (with no example).
- **Good (already in the repo):** `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/entity_extraction/prompts.py:5-8,35,44`, where `SOURCE_OPEN`/`SOURCE_CLOSE` are interpolated into both the system prompt and the user-message builder.
- **Priority:** High

### 11.2 Keep tool closures thin; use the ingestion shape as the reference example

- **Proposed rule:**
  > Keep `@tool` closures thin: validate, call one collaborator, return. Bookkeeping goes in module functions that take explicit arguments. Tool builders return `BaseTool`. `agent.py` only sets up the agent; invocation and outcome assembly belong in the capability adapter.
- **Evidence:**
  - Bad: `/Users/arafiet/MyProjects/Deep-Analyst/services/investigation_agent/src/investigation_agent/genai/evidence_search/agent.py:128-204` (a 69-line `retrieve` closure) mixes construction with `run` and a 64-line `_outcome`, against the existing `ai.md:60-61`.
  - Good: `genai/record_query/agent.py:219-270` (`_record_rejection`, `_record_result`).
  - Good, and the one to cite as the reference example: ingestion's `agent.py` (a 21-line factory), `extractor.py` (the port implementation) and `/Users/arafiet/MyProjects/Deep-Analyst/services/ingestion/src/ingestion/genai/shared/invocation.py:18-44` (one generic `run_structured_agent[T: BaseModel]`).
- **Priority:** Medium

### 11.3 Fix the skill's own untyped examples

- **Evidence:** `/Users/arafiet/MyProjects/Deep-Analyst/.agents/skills/python-service-architecture/references/ai.md:210` (`def build_model(*, model_name: str, model_provider: str):` with no return type) and `:229` (`def build_agent(*, model, summary_model, tools, settings: …):`, with untyped parameters and no return type). Agents copy these and then fill in `Any` to satisfy mypy strict. This is the source of the `model: Any` pattern in §3.2.
- **Proposed change:** Type them as `-> BaseChatModel`, `model: BaseChatModel`, `tools: Sequence[BaseTool]`, `-> CompiledStateGraph` (or a narrow Protocol).
- **Priority:** High (small change, directly causal)

---

## 12. Implementation order

1. **Remove causes before adding rules** (small edits, high impact):
   - §2.1 (`Field` rule and `alias_generator`);
   - §2.2 (no YAML duplicate defaults);
   - §2.3 (secret-safe errors);
   - §6.1 (drop the `llm.py` mandate);
   - §11.3 (typed `ai.md` examples);
   - §7.3 and §4.4 (otel snippets);
   - §9.1 (the support-package mechanism);
   - the contradictions table in §1.2.
2. **Add the three missing references:** `errors.md` (§4), `code-idioms.md` (§3, with `pydantic-models.md` §2.13 folded in or kept as a sibling), and `async-and-lifecycle.md` (§5).
3. **Update CLAUDE.md** (§1.3): remove the tooling-redundant clauses; rewrite rules 1 and 9; extend rules 6 and 7.
4. **Tooling** (§10), then the audit-script checks (§6.12, §7.8).
5. **Restructure for single ownership:** otel (§1.1, §1.4, §7.1), settings (§2.12), testing split (§9.11), DB skill routing (§8.1).
