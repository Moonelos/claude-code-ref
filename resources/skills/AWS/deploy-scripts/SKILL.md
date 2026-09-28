---
name: deploy-scripts
description: Conventions and patterns for writing shell scripts that wrap Terraform stacks (deploy-platform-*.sh, deploy-app-*.sh, destroy-*.sh, build-*.sh, and the deploy.sh / deploy-platform.sh / destroy.sh orchestrators). Use whenever creating a new per-stack script, adding scripts for a newly added Terraform stack, modifying or reviewing any script in `scripts/`, wiring up CI workflows and their deployment roles for platform-tier applies or per-service releases, choosing between a monorepo and a split application/infrastructure repository layout or wiring the artifact handoff between two repositories, or debugging confirmation prompts / idempotent destroys. Apply even when the user just says things like "add a script for the new stack", "add a release workflow for this service", "the destroy script is broken", "should the app code live in its own repo", or "how should I structure this deploy?".
---

# Deploy & Destroy Script Conventions

Each logical Terraform stack gets two dedicated scripts:
`deploy-<stack>.sh` and `destroy-<stack>.sh`. A pair of orchestration scripts —
`deploy.sh` and `destroy.sh` — run stacks in dependency order. Stacks with
Lambda or container artifacts also get a `build-<service>.sh`.

Stacks are tiered, and the tier decides which workflow runs the script.
`deploy-platform-<name>.sh` applies shared infrastructure that changes weekly to
monthly. `deploy-app-<service>.sh` applies one independently releasable service
and is the whole of a normal release. The boundary is defined in the sibling
`terraform-aws` skill's `references/platform-application-split.md`.

The approval gate is **plan on pull request, apply on merge behind an environment
protection rule** — see [`references/ci-workflows.md`](references/ci-workflows.md).
`${CI:-}` remains the only branch between a human running a script and CI running
it unattended: locally you review the plan and approve it at the terminal, and in
CI the script does not prompt ([Deploy Workflow](#deploy-workflow)). What it is
not is the authorization. That comes from which workflow may run an apply, with a
role scoped to that one stack.

These scripts wrap the conventions in the sibling `terraform-aws` skill — this doc
covers the shell layer (environment/root selection, local metadata isolation,
workflow, confirmation gates, and CI branching). Read both together when adding
a stack. The `terraform-aws` skill normally creates one shared root plus environment
values and backend files; this skill creates the scripts that select it safely.
For a genuine topology difference, the logical stack maps to one of a small,
reviewed set of compatible roots.

## Repository Topology

Resolve this before writing any script or workflow, because it decides where the
build lives and how the artifact version reaches Terraform. Two supported modes:

| Mode | Layout | An application release is |
|---|---|---|
| **Monorepo** (default) | `Terraform/`, `scripts/`, and application source in one repository | one job: `build-<service>.sh` then `deploy-app-<service>.sh` |
| **Split repo** | an application repository owns source and its build; an infrastructure repository owns `Terraform/` and `scripts/` | two pipelines with an explicit artifact handoff |

Detect the mode from the repository rather than asking first:

- `Terraform/` **and** application source (`apps/`, `lambdas/`) → monorepo.
- `Terraform/` with `stacks/app-*` but **no** application source → the
  infrastructure repository of a split.
- Application source, **no** `Terraform/`, and a workflow that publishes to ECR or
  an artifact bucket → the application repository of a split. The
  `split-repo-app-releases` skill covers that side.
- Genuinely ambiguous — a new repository, or `Terraform/` beside one stray
  application directory — ask once, then record the answer in that repository's
  `CLAUDE.md` and `AGENTS.md` (create whichever is missing) so it is resolved
  permanently for both Claude Code and Codex.

One rule holds in both modes: **the build travels with the source; the apply
travels with the Terraform.** `build-<service>.sh` belongs beside the source it
reads, because it stamps the artifact with the source commit. `deploy-app-*.sh`
and `destroy-app-*.sh` belong beside `Terraform/`.

Everything else in this skill is mode-independent — the script spine, the helper
functions, the plan/apply gate, the destroy pattern, `TF_DATA_DIR` isolation.
Only the artifact handoff and the CI wiring differ:
[`references/split-repo-releases.md`](references/split-repo-releases.md).

Read the focused references when applicable:

- CI workflows and deployment roles:
  [`references/ci-workflows.md`](references/ci-workflows.md)
- Two-repository releases and the artifact handoff:
  [`references/split-repo-releases.md`](references/split-repo-releases.md)
- Lambda (uv) and Docker artifact builds:
  [`references/build-scripts.md`](references/build-scripts.md)
- AMI builds for the EC2/ASG release path:
  [`references/ami-builds.md`](references/ami-builds.md)
- Full `deploy.sh` / `destroy.sh` / `_stacks.sh` listings:
  [`references/orchestrators.md`](references/orchestrators.md)
- ECS drain and stuck-ENI destroy diagnostics:
  [`references/destroy-troubleshooting.md`](references/destroy-troubleshooting.md)
- The local-backend state-bucket stack:
  [`references/bootstrap-stack.md`](references/bootstrap-stack.md)

## File Naming

| Pattern | Purpose |
|---|---|
| `deploy-platform-<name>.sh` | Deploy a platform-tier stack (VPC, cluster, database, ALB, ECR) |
| `deploy-app-<service>.sh` | Deploy one application stack — a single service's release |
| `deploy-<stack>.sh` | Deploy a stack via Terraform; the tier-neutral form, for a repository below the split threshold |
| `create-<stack>.sh` | Bootstrap-only stack (local backend, import logic — e.g. S3 state bucket) |
| `destroy-<stack>.sh` | Tear down a specific stack; `destroy-platform-<name>.sh` / `destroy-app-<service>.sh` follow the deploy name |
| `build-<service>.sh` | Build an immutable artifact — Lambda ZIP, Docker image, or AMI — and publish it |
| `deploy-platform.sh` | Orchestrator — platform tier only, in dependency order |
| `deploy.sh` | Orchestrator — every stack, for bring-up and disaster recovery |
| `destroy.sh` | Orchestrator — all stacks in reverse order |

The filename carries the tier, so no separate naming concept is needed. Use
`deploy-` for standard remote-backend stacks and reserve `create-` for bootstrap
stacks on a local backend.

A stack that owns both an ECR repo and the service that pushes to it (ECS, Lambda) splits into two stacks: `platform-ecr` and the app stack. ECR repos are created once and almost never destroyed; the app stack churns on every deploy. Giving them separate lifecycles means a normal deploy never needs `-target` — see [ECR as a Platform Stack](#ecr-as-a-platform-stack).

### Folder layout when scripts grow

Inspect the existing repository before scaffolding. A small repository can keep
its few scripts directly under `scripts/`. When the directory has roughly a dozen
or more entrypoints across several capabilities, or it is clearly growing toward
that size, use one level of folders by purpose:

```text
scripts/
  deploy.sh  deploy-platform.sh  destroy-app.sh  destroy-platform.sh  _stacks.sh
  platform/       deploy-platform-*.sh, destroy-platform-*.sh
  application/    deploy-app-*.sh, destroy-app-*.sh
  setup/          bootstrap/create scripts and account-wide shared stacks
  release/        build and artifact-resolution scripts (monorepo only)
  operations/     readiness, migrations, scheduled tasks, repair commands
  checks/         Terraform checks and smoke scripts
```

Create only folders that have a real purpose in that repository. Keep public
orchestrators and `_stacks.sh` at the root so bring-up remains easy to discover;
per-stack scripts stay executable and standalone. Store paths relative to
`scripts/` in `_stacks.sh`, for example
`platform/deploy-platform-network.sh`, and invoke them through
`"$SCRIPT_DIR/$deploy_script"`. A build script in a split repository stays with
the application source, in that repository's own script layout.

For a nested script, resolve the repository root with
`REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"`; root-level scripts use
`$SCRIPT_DIR/..`. Resolve sibling calls from `$SCRIPT_DIR` and cross-folder calls
from `$REPO_ROOT/scripts/<folder>/...`. Never rely on the caller's working
directory. When reorganizing an existing repository, update workflow invocations,
test fixtures and path assertions, documentation and Terraform comments together.
Use recursive discovery for ShellCheck and Bash syntax checks; `scripts/*.sh`
misses nested files. Keep incident-specific scratch files outside the committed
entrypoint layout.

---

## Script Structure

### Header

```bash
#!/usr/bin/env bash
# One-line description
set -euo pipefail
```

`#!/usr/bin/env bash` picks up whatever `bash` is on `PATH` — macOS ships an ancient `/bin/bash` (3.2). `set -euo pipefail` fails fast on errors, unset vars, and broken pipes.

### Bash 3.2 Compatibility

Every script must remain compatible with the Bash 3.2 shipped by macOS. Under
`set -u`, expanding an initialized but empty array with `"${items[@]}"` raises an
unbound-variable error on Bash 3.2 even though it succeeds on newer Bash
versions. Whenever an array can legitimately be empty, use the conditional
expansion form:

```bash
EXTRA_ARGS=()
[[ -n "${OPTIONAL_VALUE:-}" ]] && EXTRA_ARGS+=(--option "$OPTIONAL_VALUE")

some_command ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}

for item in ${ITEMS[@]+"${ITEMS[@]}"}; do
  process "$item"
done
```

The inner quotes preserve each element as a separate argument; the outer
`${array[@]+...}` expands to nothing when the array is empty. Ordinary
`"${array[@]}"` remains correct when the script's structure guarantees at least
one element.

**Associative arrays do not exist on Bash 3.2.** `declare -A` is a *syntax*
error there, not a runtime one, so the shell rejects the whole file and the
script dies before its first command — no output, no partial work, and any
`mkdir -p` earlier in the file never runs. That failure mode is easy to
misdiagnose: a wrapper that shells out to such a script sees an empty output
directory and looks as though the upstream work never happened, when in fact it
completed. Key a second indexed array off the same positions instead:

```bash
IMAGES=(api worker scheduler)
DIGESTS=()                              # parallel to IMAGES, not associative

for index in "${!IMAGES[@]}"; do
  image="${IMAGES[$index]}"
  DIGESTS[index]="$(lookup_digest "$image")"
done

for index in "${!IMAGES[@]}"; do
  printf '%s = %s\n' "${IMAGES[$index]}" "${DIGESTS[$index]}"
done
```

`${!array[@]}` (index expansion) is available on Bash 3.2. Assign with the bare
subscript `DIGESTS[index]=` — inside a subscript the name is already evaluated
arithmetically, and `DIGESTS[$index]=` trips ShellCheck SC2004.

Also absent on 3.2: `mapfile` / `readarray`, and the `${var^^}` / `${var,,}`
case-conversion expansions. Use `tr` or `awk` for case folding, and a
`while IFS= read -r` loop where you would reach for `mapfile`.

### Multi-Line Values Through `read`

`read` consumes one line. Piping records into `while IFS=$'\t' read -r key value`
therefore truncates any value that contains newlines, and — worse — the remaining
lines are parsed as further records, so the second line of a value silently
becomes the next record's key. A Terraform output holding a multi-line file body
is the common case:

```bash
# WRONG: every line after the first becomes a bogus record
terraform output -json configs | jq -r 'to_entries[] | "\(.key)\t\(.value)"' \
  | while IFS=$'\t' read -r name body; do printf '%b' "$body" > "$name.conf"; done
```

Escape the newlines so each record really is one line, and restore them when
writing:

```bash
terraform output -json configs \
  | jq -r 'to_entries[] | "\(.key)\t\(.value | gsub("\n"; "\\n"))"' \
  | while IFS=$'\t' read -r name body; do
      printf '%b' "$body" > "$name.conf"      # %b expands the \n escapes
    done
```

`jq -r` with `@tsv`, or NUL-delimited records with `read -r -d ''`, are equally
valid; what matters is that the record delimiter cannot occur inside a value.
Verify by counting lines in a generated file, not by eyeballing the log: the
truncated form still prints a cheerful "Wrote ..." for the first record.

### Path Resolution

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)" # For scripts/<folder>/<script>.sh; use /.. at the root.
ENV="${ENV:?Set ENV to a supported environment, for example dev, staging, or prod}"
LOGICAL_STACK="<stack>"
ROOT_STACK="<stack>" # May differ by environment for an explicit topology variant.
TF_DIR="$REPO_ROOT/Terraform/stacks/$ROOT_STACK"
VAR_FILE="$REPO_ROOT/Terraform/environments/$ENV/$LOGICAL_STACK.tfvars"
BACKEND_CONFIG="$REPO_ROOT/Terraform/backend-config/$ENV/$LOGICAL_STACK.backend.hcl"
export TF_DATA_DIR="$REPO_ROOT/.terraform-data/$ENV/$LOGICAL_STACK/$ROOT_STACK"
PLAN_FILE="$TF_DATA_DIR/tfplan"
```

Always resolve paths from `${BASH_SOURCE[0]}` — not `$PWD`. CI runners,
orchestrators, and humans invoke scripts from different working directories.
Use absolute paths for environment values and backend configuration.

Require `ENV` for every mutating workflow. Never default to production. Validate
it against the environments the repository actually supports:

```bash
case "$ENV" in dev|staging|prod) ;; *) print_error "ENV must be dev, staging, or prod"; exit 1 ;; esac
```

`TF_DATA_DIR` is load-bearing when environments share one stack root. It keeps
backend metadata separate so a prior staging initialization cannot silently
select staging state during a production command. Including `ROOT_STACK` also
prevents different topology implementations from sharing provider/module
metadata. Gitignore `.terraform-data/`.

When an environment uses a genuinely different root implementation, each
standalone deploy and destroy wrapper maps it explicitly without changing the
logical stack/output contract:

```bash
case "$ENV" in
  staging) ROOT_STACK="platform-data-rds" ;;
  prod)    ROOT_STACK="platform-data-aurora" ;;
  *) print_error "No platform-data root is configured for ENV=$ENV"; exit 1 ;;
esac
```

Do not accept an unrestricted `ROOT_STACK` override: the mapping is part of the
reviewed deployment policy. Keep backend and tfvars names under the logical
`platform-data` stack, but ensure the selected roots never share a backend state
object. If an environment changes implementations later,
perform an explicit state/consumer cutover; never let both roots manage the same
SSM parameter, DNS record, or other discovery object concurrently.

### Helper Functions

Paste these four verbatim in every script — do not source them from a shared lib:

```bash
print_info()    { printf "\033[0;34m[INFO]\033[0m    %s\n" "$1"; }
print_success() { printf "\033[0;32m[SUCCESS]\033[0m %s\n" "$1"; }
print_warning() { printf "\033[0;33m[WARNING]\033[0m %s\n" "$1"; }
print_error()   { printf "\033[0;31m[ERROR]\033[0m   %s\n" "$1"; }
```

Every listing in the references marks where these go with a comment rather than
repeating them, so there is exactly one copy to keep correct. Paste all four even
if a given script calls only two — a later edit that adds a `print_warning` call
to a script missing the definition fails under `set -u`.

Each script must be runnable standalone. Sourcing a sibling file adds a failure mode (file not found, wrong path) for a handful of printf lines. The duplication buys portability and auditability.

This standalone rule is about per-stack `deploy-*.sh` / `destroy-*.sh` scripts, which are meant to run in isolation. The orchestrators (`deploy.sh`, `destroy.sh`) are a narrow exception: they never run standalone by definition — they call the per-stack scripts — so they share one file for stack order. See [Orchestrators](#orchestrators).

### Pre-flight Checks

```bash
for cmd in terraform aws; do   # add docker/jq if the script needs them
  if ! command -v "$cmd" &>/dev/null; then
    print_error "$cmd is not installed"
    exit 1
  fi
done

if ! aws sts get-caller-identity &>/dev/null; then
  print_error "AWS credentials are not configured"
  exit 1
fi

# If Docker is required:
if ! docker info >/dev/null 2>&1; then
  print_error "Docker daemon is not running"
  exit 1
fi
```

Perform the identity check before piping an ECR password into `docker login`. Otherwise an
expired SSO session appears as the misleading downstream Docker error “interactive login
from a non TTY”. When the target account is declared in tfvars, compare it with the caller
account before publishing or applying.

### Deploy Workflow

```bash
cd "$TF_DIR"

# Fires on every exit path — success, cancellation, or a failed apply — so a
# stale tfplan never survives a crash. (Cleaning up per-branch instead of with
# trap looks clearer but misses the failure path: `terraform apply` can exit
# non-zero before any explicit `rm -f` runs.)
trap 'rm -f "$PLAN_FILE"' EXIT

print_info "Initializing Terraform ($ENV/<stack>)..."
terraform init -reconfigure -backend-config="$BACKEND_CONFIG" -input=false

print_info "Validating..."
terraform validate

print_info "Formatting check..."
if ! terraform fmt -check -recursive "$REPO_ROOT/Terraform" >/dev/null 2>&1; then
  print_error "Terraform formatting issues found; run terraform fmt -recursive Terraform"
  exit 1
fi

print_info "Planning..."
PLAN_ARGS=(-input=false -lock-timeout=5m -var-file="$VAR_FILE" -out="$PLAN_FILE")
# Add -var-file="$ARTIFACT_VARS" if the stack consumes build artifacts
PLAN_CODE=0
if [[ "$DETAILED_EXITCODE" == "true" ]]; then
  set +e
  terraform plan "${PLAN_ARGS[@]}" -detailed-exitcode
  PLAN_CODE=$?
  set -e
  [[ "$PLAN_CODE" == "1" ]] && exit 1
else
  terraform plan "${PLAN_ARGS[@]}"
fi

if [[ "$PLAN_ONLY" == "true" ]]; then
  print_info "Plan-only run — not applying"
  exit "$PLAN_CODE"
fi

if [[ "${CI:-}" == "true" ]]; then
  print_info "CI detected — applying the saved plan without a prompt"
  terraform apply -input=false "$PLAN_FILE"
else
  print_info "Review the plan above."
  read -p "Apply? (yes/no): " -r
  if [[ "$REPLY" == "yes" ]]; then
    terraform apply -input=false "$PLAN_FILE"
  else
    print_info "Cancelled"
    exit 0
  fi
fi
```

Parse the two flags at the top of the script, beside the `ENV` resolution:

```bash
PLAN_ONLY=false
DETAILED_EXITCODE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan-only)         PLAN_ONLY=true ;;
    --detailed-exitcode) DETAILED_EXITCODE=true ;;
    *) print_error "Unknown argument: $1"; exit 1 ;;
  esac
  shift
done
```

- `--plan-only` is what the pull-request workflow calls. The script initializes,
  validates, plans, prints, and exits without applying — so a PR job can hold a
  read-only role and still fail on a broken configuration.
- `--detailed-exitcode` propagates Terraform's exit code: 0 for no changes, 2 for
  changes, 1 for an error. Drift detection needs the distinction; a 1 must not be
  reported as drift. Wrap it in `set +e`/`set -e`, because a 2 would otherwise
  abort the script under `set -e`.
- Use `-input=false` everywhere so a missing value fails loudly instead of hanging.
  Use a bounded lock timeout. Apply the exact saved plan; never run a second
  implicit plan at apply time.
- Render the saved plan as JSON and list every action containing `delete` before the
  approval gate. For a known stateful or externally referenced replacement, add a
  resource-specific preflight that verifies live consumers are gone and require a narrowly
  named opt-in. A warning alone is insufficient when AWS is guaranteed to reject deletion.
- `CI=true` skips the terminal prompt. It is not the approval — the workflow's
  environment protection is. See
  [`references/ci-workflows.md`](references/ci-workflows.md).

### Apply failures and convergence

Terraform apply is not transactional. Once apply starts, an error can leave earlier
resource actions committed. Orchestrator failure traps may say that the previous runtime is
untouched only for phases that precede the runtime apply. During or after runtime apply,
report that state may be partial and direct the operator to refresh state and inspect live
service revisions.

Static validation and mocked `terraform test` cannot detect every provider/API
normalization mismatch. For a release root that contains provider-normalized nested blocks
or immutable resources, run a post-apply plan with the exact same inputs and
`-detailed-exitcode`; zero is success, one is an error, and two means the applied
configuration did not converge. Show that second plan and fail the release evidence step.
This check is especially important after adding a new resource type or upgrading a
provider.

### ECR as a Platform Stack

`-target` is Terraform's documented escape hatch for exceptional recovery, and it prints a warning every time it's used — it is not a pattern to build a routine deploy path around. Instead of targeting the ECR resources inside a combined stack, give ECR its own stack with its own lifecycle. `deploy-platform-ecr.sh` is then an ordinary stack script — no targeting, no partial applies, every stack applies its whole plan.

ECR is one instance of platform-tier ownership rather than a special case:
repositories and images outlive the services that push to them, exactly like the
VPC, the cluster, and the database. The tier rule is in the sibling
`terraform-aws` skill's `references/platform-application-split.md`.

The app stack reads the repository through `data "aws_ecr_repository"` or a
platform-published SSM parameter rather than owning it. Avoid
`terraform_remote_state` unless that service's deployment role may read the
entire platform state snapshot — which defeats the point of a scoped role.

The ordering — `platform-ecr`, then the build script, then the app stack — is
wired in `deploy.sh` for bring-up; see
[`references/orchestrators.md`](references/orchestrators.md). In a release, the
build script and the one app stack run in the same job and ECR already exists.

### Summary Banner (deploy scripts)

```bash
echo ""
print_success "════════════════════════════════════════"
print_success "  <Stack> deployed ($ENV)!"
print_success "════════════════════════════════════════"

SOME_OUTPUT=$(terraform output -raw some_key 2>/dev/null || echo "N/A")
echo ""
print_info "Some output: $SOME_OUTPUT"
```

For simple stacks with no notable outputs, call `terraform output` (no args) to print everything.

---

## Destroy Scripts

Init first, then show the *real* destroy plan — not just a hand-maintained bullet list — before the confirmation gate:

```bash
if [[ ! -d "$TF_DIR" ]]; then
  print_warning "Directory $TF_DIR does not exist, skipping"
  exit 0
fi

cd "$TF_DIR"

print_info "Initializing Terraform ($ENV/<stack>)..."
terraform init -reconfigure -backend-config="$BACKEND_CONFIG" -input=false >/dev/null

if ! terraform state list >/dev/null 2>&1 || [[ -z "$(terraform state list 2>/dev/null)" ]]; then
  print_info "No resources in <stack> state, skipping"
  exit 0
fi

DESTROY_PLAN_FILE="$TF_DATA_DIR/tfplan-destroy"
trap 'rm -f "$DESTROY_PLAN_FILE"' EXIT
print_warning "This will destroy the <STACK> stack ($ENV). Plan:"
terraform plan -destroy -input=false -lock-timeout=5m \
  -var-file="$VAR_FILE" -out="$DESTROY_PLAN_FILE"
# Add -var-file="$ARTIFACT_VARS" when the stack declares artifact variables.

if [[ "${CI:-}" != "true" && "${SKIP_CONFIRM:-}" != "true" ]]; then
  echo ""
  read -p "Type 'DESTROY' to confirm: " -r
  echo ""
  if [[ "$REPLY" != "DESTROY" ]]; then
    print_info "Cancelled"
    exit 0
  fi
fi

print_info "Destroying <stack> stack..."
terraform apply -input=false "$DESTROY_PLAN_FILE"
print_success "<Stack> stack destroyed"
```

A hardcoded "this will destroy: Resource A, Resource B" list drifts from the
stack. Generate and save the real destroy plan, then apply that exact plan after
confirmation. Use `DESTROY` for standard stacks and a specific token for
irreversible data loss.

**A destroy plan still has to satisfy every required variable.** An app stack's
artifact variables have no default, so `-input=false` fails on a missing value
even though a destroy never uses the artifact. Pass the artifact tfvars file to
the destroy plan as well. When no artifact was ever published for that
environment, supply a syntactically valid placeholder with `-var` on that single
invocation — never by adding a default or writing it into a committed file.

Destroy scripts are always idempotent: missing directory or empty state → exit 0. The `destroy.sh` orchestrator runs stacks in sequence — a previously-torn-down stack must not halt the rest.

**Stacks that run workloads in a VPC need more than this.** ECS services must be
drained to zero before their security groups can go, and Lambda/ECS ENIs are the
usual cause of a destroy that hangs then fails. Both patterns — the drain loop
and the ENI diagnostic that replaces the final bare `terraform apply` — are in
[`references/destroy-troubleshooting.md`](references/destroy-troubleshooting.md).

---

## Orchestrators

**`deploy.sh` is day-one environment bring-up and disaster recovery. It is not
your CD path.** Nothing in a normal release runs it: a release applies exactly one
app stack, from that service's own workflow, with that service's own role. Reach
for `deploy.sh` when standing up a new environment or rebuilding one from nothing.

`deploy-platform.sh` is the realistic recurring orchestrator — it applies the
platform tier in dependency order and stops there. It is what `infra-apply.yml`
runs on merge, and it never touches an app stack.

`deploy.sh` and `destroy.sh` are the one place scripts share state: a single
ordered stack list in `scripts/_stacks.sh`, so destroy order is always the exact
reverse of deploy order — not two hand-maintained lists that can silently drift
apart. Adding a stack is one edit, in one place. The list holds platform stacks in
dependency order followed by app stacks in any order; `deploy-platform.sh` runs
the platform section only.

The rules that matter from outside those two files:

- `export ENV` before invoking child scripts; a variable created inside the
  orchestrator is not exported automatically.
- `destroy.sh` owns the single top-level `DESTROY` gate and passes
  `SKIP_CONFIRM=true` to children as an inline prefix, never an export.
- The orchestrator's pre-flight checks the **union** of tools every child needs,
  so a run fails at the top rather than three stacks deep.
- Build scripts are called inline between stacks — they are not stacks and have
  no destroy counterpart, so they do not belong in the stack list.
- Anything a teardown intentionally leaves behind must be restated in the
  closing summary, naming the concrete resource. That is when the operator
  decides what to delete by hand; the upfront warning scrolled past several
  confirmations ago.

Full listings, the `<name>:<deploy>:<destroy>` list format, `SKIP_STACKS`, and
the `FAILED_STACK` trap: [`references/orchestrators.md`](references/orchestrators.md).

---

## Build Scripts

`build-<service>.sh` produces an **immutable artifact** and hands its version to
Terraform through a generated `.tfvars` file that the deploy script passes as a
second `-var-file`. Three artifact kinds, one contract:

| Artifact | Version handed to Terraform |
|---|---|
| Docker image | Git SHA tag against an immutable ECR repository, or the resolved digest |
| Lambda ZIP | S3 object version plus the ZIP's `base64sha256` |
| AMI | the `ami-` ID |

Two rules regardless of kind:

- **Version explicitly.** Never `latest`, never a branch name, never "whatever is
  newest" resolved at plan time. The variable is required and has no default, so a
  release that skipped its build fails at plan instead of silently redeploying the
  previous artifact.
- **The build runs before `terraform init`,** and its tfvars file must exist on
  every exit path, including the "artifact already published, nothing to do"
  short-circuit.

Python Lambda source lives at `lambdas/<service>/`, at the root of whichever
repository owns the source and outside the Terraform directory. Use the function's
committed `pyproject.toml` and `uv.lock` with uv; a generated requirements file is
an ignored build artifact, never a second dependency source of truth.

**Where the build script lives follows the source, not the Terraform.** In a
monorepo it sits in `scripts/` (under `release/` in a grouped layout), and the deploy script
calls it inline. In a split repository it lives in the application repository, and
the artifact version reaches Terraform through a committed
`Terraform/environments/{env}/{stack}.artifacts.tfvars` file instead of a path on
one runner's disk — [`references/split-repo-releases.md`](references/split-repo-releases.md).
Resolve any `<repo-root>` in a build script against the repository holding the
source, so the git SHA that tags the artifact identifies the code inside it.

Full Lambda ZIP/uv and Docker/ECR listings:
[`references/build-scripts.md`](references/build-scripts.md). The EC2/ASG path —
Packer or EC2 Image Builder, the AMI ID handoff, and waiting out the instance
refresh — is in [`references/ami-builds.md`](references/ami-builds.md). For the
tag-versus-digest decision, read `references/docker-image-tagging.md` in the
sibling `terraform-aws` skill.

---

## The Bootstrap Exception

The state-bucket stack cannot use the standard workflow — the remote backend it
would use is the thing it creates. It runs on a local backend, imports
pre-existing buckets idempotently at runtime, and is the single place where the
imperative `terraform import` CLI is correct rather than a declarative `import`
block. Name it `create-<stack>.sh` so the exception is visible in the filename.

Set it up once per project: [`references/bootstrap-stack.md`](references/bootstrap-stack.md).

---

## CI Integration (GitHub Actions)

The scripts do not change between local and CI use — only the env vars and flags
set around them do. Five workflows, each with its own role. Platform and
application changes are planned and applied by entirely separate workflows —
merging one never triggers the other:

| Workflow | Trigger | Runs | Role |
|---|---|---|---|
| `infra-plan.yml` | PR touching platform `Terraform/**` | `deploy-platform-<name>.sh --plan-only` | `TerraformPlanRole` — read plus the state lock |
| `plan-app-<service>.yml` → `_app-plan.yml` | PR touching that service's stack/tfvars | `deploy-app-<service>.sh --plan-only` | `AppPlanRole` — read-only, application tier |
| `infra-apply.yml` | merge to main, or dispatch | `deploy-platform.sh` | `TerraformPlatformApplyRole` — broad, only from a protected job |
| `release-<service>.yml` → `_app-release.yml` | push to `apps/<service>/**` or that stack/tfvars | `build-<service>.sh` then `deploy-app-<service>.sh` | `AppDeployRole-<service>-<env>` — that stack only |
| `drift-detect.yml` | schedule | `--plan-only --detailed-exitcode` | `TerraformPlanRole` |

Two consequences worth stating plainly. A code push can no longer reach a role
that modifies databases or networking — the release role holds ECS/Lambda/ECR
permissions for one service and write access to one state prefix. And no workflow
runs `deploy.sh`; bring-up is a deliberate, manual operation.

Complete YAML for all five, the reusable `_app-release.yml`/`_app-plan.yml` with
their per-service callers, the rejected alternatives, and every trust and
permission policy: [`references/ci-workflows.md`](references/ci-workflows.md).

That table describes the monorepo. In a split repository the release row becomes
two workflows in two repositories: the application repository publishes the
artifact under a publish-only role, then opens a pull request carrying the version;
the infrastructure repository's caller triggers on that file and applies the stack.
The other workflows are unchanged, and the service's own `plan-app-<service>.yml`
plans the release pull request — not `infra-plan.yml`, whose filter is
platform-only and never matched an app stack. Both trust policies, the bring-up
sequencing, and the promotion and rollback paths (including what a shared vs.
per-environment artifact registry requires):
[`references/split-repo-releases.md`](references/split-repo-releases.md).

---

## CI / Environment Variables

| Variable | Used by | Effect |
|---|---|---|
| `ENV` | all | Required target environment; validate against the environments the repository supports |
| `CI=true` | all | Skip interactive prompts and apply the saved plan; not the approval gate |
| `SKIP_CONFIRM=true` | destroy scripts | Skip `DESTROY` confirmation (set by `destroy.sh` orchestrator) |
| `SKIP_STACKS` | `deploy.sh` | Comma-separated stack names to skip. **Bring-up only** — a release applies one stack, so it has nothing to skip |
| `SERVICE` | app release workflow | Informational only — identifies the service in the job's own environment for logging; no script in this skill reads it. `open-release-pr.sh` on the application-repository side does consume its own `$SERVICE`, set independently there |
| `IMAGE_TAG` | build scripts | Docker image tag; defaults to the current git SHA |
| `<SERVICE>_IMAGE_TAG` | build scripts | Per-service override when multiple images are deployed |
| `TARGET_PLATFORM` | Docker build scripts | Required; the task/function architecture (`linux/arm64`, `linux/amd64`) — never the builder's own |
| `AMI_ID` | build/deploy scripts | Pre-built AMI for the EC2/ASG path, when an earlier job produced it |
| `LAMBDA_OBJECT_VERSION` | build/deploy scripts | S3 object version of a published Lambda ZIP, when the publish and apply are separate steps |
| `TF_PLAN_ARTIFACT` | CI plan/apply jobs | Path of the saved plan handed from a plan job to a protected apply job; treat as sensitive, short retention |
| `AWS_REGION` | build/destroy scripts | Explicit region; falls back to parsing tfvars/ECR URL locally only |
| `TF_VAR_*` | deploy scripts | Inject values without a tfvars file; secrets still enter state unless every consumer is ephemeral/write-only |
| `INFRA_REPO` | split-repo handoff | `<org>/<repo>` the application repository opens its release pull request against |
| `ENVIRONMENT` | split-repo handoff | Target environment for the artifact file the application repository publishes; `ENV` stays the name the Terraform wrappers read |

---

## Quality Gates

Every script declares `set -euo pipefail`, so latent quoting and unset-variable
bugs surface as hard failures at the worst possible time — mid-deploy. Lint
before committing:

- Run `find scripts -type f -name '*.sh' -not -path 'scripts/temp/*' -print0 | xargs -0 shellcheck` and resolve findings (or annotate intentional
  ones with `# shellcheck disable=SCxxxx` plus a reason). It catches unquoted
  expansions, masked exit codes in pipelines, and `read` misuse that
  `pipefail` would otherwise only reveal at runtime.
- Add a regression contract for every legitimately empty array expanded under
  `set -u`. CI commonly runs Bash 5, so a successful CI execution and ShellCheck
  do not prove that the script is safe on macOS Bash 3.2.
- Parse every script with the *system* shell, including nested scripts:
  `find scripts -type f -name '*.sh' -not -path 'scripts/temp/*' -exec /bin/bash -n {} +`.
  ShellCheck accepts `declare -A` and the other Bash 4 constructs without
  comment, and a Bash 5 CI runner executes them happily, so this is the only
  cheap check that reproduces what an operator on macOS actually gets. Assert it
  in the test suite alongside a grep for `declare -A`, `local -A`, `mapfile`,
  `readarray`, `${var^^}` and `${var,,}`.
- Prefer testing a script's *output artifact* over its exit code. Several of
  these failure modes (a truncated rendered file, an empty output directory)
  leave a zero exit somewhere upstream and only surface much later.
- Run `chmod +x` on new scripts — a non-executable script invoked by an
  orchestrator fails with a confusing permission error.
- Optionally wire both into a pre-commit hook so they run automatically.

---

## Adding a New Stack

Both tiers, every time: copy the nearest similar deploy script and update
`LOGICAL_STACK`, `ROOT_STACK`, `VAR_FILE`, `BACKEND_CONFIG`, and the summary
outputs; copy the nearest destroy script and update its paths; add the stack to
`_stacks.sh` (**format in
[`references/orchestrators.md`](references/orchestrators.md)**); then
`chmod +x` and `shellcheck` both new scripts.

**If the stack runs workloads in a VPC, read
[`references/destroy-troubleshooting.md`](references/destroy-troubleshooting.md)**
and add the ECS drain loop and ENI diagnostics to the destroy script. In practice
that is always an app stack.

### Adding a platform stack

1. Name it `deploy-platform-<name>.sh` / `destroy-platform-<name>.sh`.
   In a grouped layout place both in `scripts/platform/`.
2. Place it in the **ordered** section of `_stacks.sh`, ahead of every app stack,
   and add it to `deploy-platform.sh`'s run.
3. If an environment selects a different root implementation, add an explicit
   `case "$ENV"` mapping in the per-stack wrappers and keep the logical output
   contract stable.
4. Confirm the stack publishes what app stacks need as SSM parameters. A platform
   stack whose values are only Terraform outputs cannot be consumed by an app
   stack that may not read its state.
5. No release workflow. It is applied by `infra-apply.yml` on merge or dispatch.

### Adding an application stack

0. Resolve the [repository topology](#repository-topology) first — it decides
   whether steps 2 and 4 happen in this repository or another one.
1. Name it `deploy-app-<service>.sh` / `destroy-app-<service>.sh`.
   In a grouped layout place both in `scripts/application/`.
2. Add `build-<service>.sh` for its artifact — **read
   [`references/build-scripts.md`](references/build-scripts.md)**, or
   [`references/ami-builds.md`](references/ami-builds.md) for an EC2/ASG service.
   In a grouped monorepo layout place it in `scripts/release/`.
   The app stack reads its ECR repository URL from the platform tier rather than
   owning it; create `platform-ecr` once if the project has no ECR stack yet. In a
   split repository the build script belongs to the application repository, and
   this repository consumes a committed
   `Terraform/environments/{env}/app-<service>.artifacts.tfvars` instead.
3. Append it to the **unordered app section** of `_stacks.sh`. App stacks do not
   depend on each other, so position within that section carries no meaning.
4. Add its release caller workflow and its per-environment deployment role —
   **read [`references/ci-workflows.md`](references/ci-workflows.md)**. The caller
   is about ten lines: its `paths:` filter, its service name, its stack name. In a
   split repository the filter matches the artifact file rather than application
   source — **one environment's file, not a wildcard**, because the push trigger
   carries no environment and the job applies whatever `ENV` resolves to — and the
   role's trust policy pins this repository:
   [`references/split-repo-releases.md`](references/split-repo-releases.md).
5. Support `--plan-only` so the pull-request workflow can plan it with a read-only
   role.
6. Pass the artifact tfvars file to the **destroy** plan too, or its no-default
   artifact variables make `terraform plan -destroy -input=false` fail.
