Apply the consolidated skill feedback in feedback/CONSOLIDATED_SKILL_CHANGES.md
to the skills in resources/skills/PYTHON/, using one sub-agent per skill plus
one for a new skill, running in parallel.

## Decisions (these override §0 of the file)
- D1: create a new standalone skill resources/skills/PYTHON/python-code-conventions/
- D2: case_sensitive=False, no per-field aliases equal to NAME.upper(); mention alias_generator only as a note for platforms needing case-sensitive names
- D3: extract the YAML settings loader only when ≥2 services copy it verbatim AND the copies drifted, or a shared config lib already exists
- D4: native `async def` tests with the plugin the repo already has; no nested run()+asyncio.run per test
- D5: one exception-detail setting whose value is set per environment in YAML, never derived from ENVIRONMENT_NAME in code; prod baseline = safe projection; ask when the service handles personal/financial data and no policy is stated
- D6: preserve the deployed flat/nested settings shape; new services start flat; nest cohesive units; no field-count threshold

## Before spawning
1. Create branch `skills/apply-feedback` from main. Do not commit; I will review the diff.
2. Read resources/skills/AGENTS.md (resources/skills/CLAUDE.md is a symlink to it).
3. Read feedback/CONSOLIDATED_SKILL_CHANGES.md fully (§0, §1, §12 and "Not carried forward" especially) so you can brief agents and resolve cross-skill questions.

## Agents (spawn all 9 in one message, in parallel)
Give each agent: the decisions above, its assigned sections, its directory, and
the shared rules below. Each agent reads the consolidated-file sections it owns
PLUS §1 (cross-cutting), the §1.2 contradiction rows touching its skill, and
"Not carried forward".

1. settings — python-settings-config/ — §3, §1.2 settings rows, §1.5 settings.
2. architecture — python-service-architecture/ — §4, §1.2 arch rows, §1.5 arch. Create references/errors.md (§4.11) and references/async-and-lifecycle.md (§4.12) and route them from SKILL.md. Also owns the placement parts of §9.1/§9.11 in references/testing.md (layout, profiles, markers, support-package mechanism). Add a one-line pointer to python-code-conventions for anything below module placement.
3. audit — python-service-architecture-audit/ (incl. scripts/audit_service.py and agents/openai.yaml) — §5, §1.3.
4. db — python-sqlmodel-alembic/ — §6. New references allowed: external-read-databases.md, and psycopg routing per §6.14.
5. otel — otel-observability/ — §7, §1.5 otel. Replace scripts/validate_skill.py with the code-audit script per §7.14 (≤150 lines, runnable, with a quick self-test). Delete scripts/__pycache__/.
6. logging — python-logging/ — §8.
7. pytest — pytest/ — §9 (except the placement parts owned by agent 2), including the §9.12 examples.
8. repo-setup — python-repository-setup/ — §10, §1.5 repo-setup. Delete assets/workspace-template/.ruff_cache/ and exclude caches from assets.
9. conventions (NEW skill) — python-code-conventions/ — §2 in full.
   - Load the skill-creator skill first. Match the frontmatter and layout of sibling skills.
   - SKILL.md ≤ ~200 lines, one bad/good pair per rule; each rule maps to a Ruff/mypy check or states a concrete trigger. Split into references/ only if it would exceed that.
   - The description must trigger for any Python source edit or review in services/ or libs/, and say that architecture, settings, persistence, logging, observability and testing specifics live in their own skills.
   - Owns the single module/function-size numbers (§2.15); others point here.
   - Also write feedback/CLAUDE_MD_CHANGES.md: the §11 edits as a ready-to-paste snippet for project CLAUDE.md files (those live in each project, not in this repo).
   - Do NOT edit resources/skills/AGENTS.md or resources/skills/CLAUDE.md.

## Shared rules for every agent
- Edit only your own skill directory. For a rule owned by another skill, add a one-line pointer instead of restating it. Owners: errors and async → python-service-architecture/references/errors.md and references/async-and-lifecycle.md; language-level idioms and size numbers → python-code-conventions/SKILL.md; test placement → python-service-architecture/references/testing.md; test design → pytest.
- Follow resources/skills/AGENTS.md: cross-skill references use flat sibling paths (`../<skill>/references/<file>.md`, adding `../` from inside references/), never the `PYTHON/` grouping folder. Prefer invoking another skill by name, with the relative path as fallback.
- Read every file before editing it. Preserve correct existing guidance. Do not add anything listed under "Not carried forward".
- State each rule once in your skill; delete the duplicates listed in §1.1, §1.5 and §4.20 for your skill.
- Examples must be typed, mypy-strict clean, and follow the new rules themselves, because agents copy examples literally.
- Keep skills concise: net line count should stay flat or shrink for settings, otel and architecture. No evidence paths, counts or repo-specific names (Gresham, Deep-Analyst, service names) from the feedback.
- Return: files changed; per-section status (done / partial / skipped + why); every cross-skill pointer you added; any conflict you could not resolve.

## After all agents finish
0. Update resources/skills/AGENTS.md (edit AGENTS.md only; CLAUDE.md is a symlink to it; keep it short). Add a "Rule ownership" section: each normative rule is stated once, in the skill/file that owns the topic; other skills link to it with one line ("See `../<skill>/<file>#<section>`") instead of restating it. Do not add Python-specific rules there.
1. Verify every cross-skill pointer resolves to a real file/section and uses flat sibling paths per AGENTS.md; fix broken ones.
2. grep resources/skills/PYTHON for the old texts listed in the consolidated file's "Verified" note ("Include concise `description=`", "Every GenAI task has `llm.py`", "engine = build_engine(settings.database_url)", "at least two of these", "set_status_on_exception=False", "Do not scatter string literals", "column_0_name", "global _cached_secrets", "legitimately varies", and the three-vs-five `.env.example` section conflict) and confirm each is resolved.
3. Check that no rule is now stated in two skills with different wording (size numbers, error rules, async rules, test placement vs test design).
4. Run the new/changed scripts (audit_service.py, the otel audit script) on a small fixture to prove they execute.
5. Report to me: a per-skill summary, all items marked partial/skipped, the path of feedback/CLAUDE_MD_CHANGES.md, and `git diff --stat`. Do not commit.
