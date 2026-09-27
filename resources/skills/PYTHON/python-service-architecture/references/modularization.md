# Modularizing an existing service

Folder restructuring is useful only when it makes ownership, dependency
direction, testing, or change isolation clearer. Preserve behavior unless the
task explicitly includes behavioral change.

## Find boundaries before moving files

For every current module, record:

- its public entry points;
- the business action or technical boundary that owns it;
- external effects it performs;
- who imports it and what it imports;
- the success and failure contracts it exposes;
- the lifecycle and test profiles in which it runs.

Files that change for the same business reason should usually stay together.
Files that share only a framework or SDK do not necessarily belong together.

## Split by responsibility signals

Consider splitting when a module:

- combines process lifecycle with business execution;
- combines deterministic policy with network, model, or storage invocation;
- owns several unrelated public entry points;
- has test groups requiring different setup or execution profiles;
- mixes outer-technology imports with domain decisions;
- is repeatedly edited for unrelated business actions;
- forces consumers to import private details to access one contract.

Line count, function count, and nesting are review signals, not reasons by
themselves; the numbers live in `python-code-conventions` (fallback:
`../../python-code-conventions/SKILL.md`, "Size signals").

## Resolve the target shape

Do not redefine the structural rules during a migration:

- Use [templates.md](templates.md) for the target service tree and placement
  map.
- Use [boundaries.md](boundaries.md) for dependency direction, port admission,
  ownership, flat-first growth, and constants; [errors.md](errors.md) for error
  design; `python-service-architecture-audit` for the final audit.
- Use [ai.md](ai.md) when any GenAI responsibility exists.
- Use [api-and-workers.md](api-and-workers.md) for process-specific boundaries.
- Use [testing.md](testing.md) before moving tests or fixtures.
- Use [shared-libraries.md](shared-libraries.md) when extracting reusable code.

These references are authoritative. A migration must enforce their rules rather
than preserve a conflicting legacy layout for cosmetic compatibility.

## Migration sequence

1. Establish the target ownership map and dependency direction.
2. Stabilize or introduce typed contracts at the boundary being moved.
3. Move contract errors first when business code currently imports concrete
   implementation errors.
4. Move deterministic logic and keep its focused tests passing.
5. Move concrete integrations, persistence, and GenAI responsibilities to their
   canonical owners; translate failures at the port boundary.
6. Flatten speculative packages or introduce only the narrower package justified
   by demonstrated growth.
7. Move composition and lifecycle into `bootstrap/`; keep `main.py` thin.
8. Update API/consumer entry points, diagnostics, configuration, deployment
   entry points, telemetry names, tests, markers, hooks, and CI selectors.
9. Remove compatibility re-exports in the same change once in-repo consumers
   migrate; an in-repo shim with only internal consumers is a violation.

When a capability is removed, delete in the same change the parameters,
branches, `**kwargs` pass-throughs, HTTP verbs, shims, and error mappings it
justified; its domain-record fields and read paths; and dead helpers and stale
e2e or live expectations. Keep DB columns until a contract migration drops them.
Before finishing, search for single-value parameters and test-only call paths.

Move one coherent boundary or action at a time, run its
focused tests and import/type checks, then finish with repository-wide
verification proportional to the change.

## Reporting a structural review

Distinguish:

- **Violation:** dependency direction or ownership is concretely wrong.
- **Improvement:** another shape materially improves navigation or isolation.
- **Preference:** naming or layout differs without a material effect.

Recommend migrations for violations and improvements with a clear benefit. Do
not report aesthetic consistency as an architectural requirement.
