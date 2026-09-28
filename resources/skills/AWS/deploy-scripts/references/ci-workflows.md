# CI Workflows and Deployment Roles

GitHub Actions workflows for the two-tier stack model, and the IAM roles they
assume. The tier boundary itself is defined in the sibling `terraform-aws` skill
(`references/platform-application-split.md`).

When this repository uses the grouped script layout in `SKILL.md`, point
workflow commands at `scripts/platform/`, `scripts/application/`, or
`scripts/release/` as appropriate. The examples below show flat paths for small
repositories; do not copy those paths unchanged into a grouped repository.

Five workflows, five role shapes. The approval gate is **plan on pull request,
apply on merge behind an environment protection rule** — not `CI=true` skipping
a terminal prompt. `CI=true` still controls how a script behaves when nobody is
watching; it is no longer what authorizes the change.

## Contents

- [The Workflows](#the-workflows)
- [infra-plan.yml](#infra-planyml)
- [infra-apply.yml](#infra-applyyml)
- [App Release: One Reusable Workflow](#app-release-one-reusable-workflow)
- [drift-detect.yml](#drift-detectyml)
- [Deployment Roles](#deployment-roles)
- [Generating the Per-Service Roles](#generating-the-per-service-roles)

## The Workflows

| Workflow | Trigger | Gate | Role |
|---|---|---|---|
| `infra-plan.yml` | pull request touching platform `Terraform/**` | none; read-only | `TerraformPlanRole` |
| `plan-app-<service>.yml` → `_app-plan.yml` | pull request touching that service's stack/tfvars | none; read-only | `AppPlanRole` |
| `infra-apply.yml` | merge to `main`, or `workflow_dispatch` | GitHub Environment, required reviewers on prod | `TerraformPlatformApplyRole` |
| `release-<service>.yml` → `_app-release.yml` | push to `apps/<service>/**` or that stack | environment protection per service+environment | `AppDeployRole-<service>-<env>` |
| `drift-detect.yml` | schedule | none; opens an issue | `TerraformPlanRole` |

Every job that assumes a role needs `permissions: id-token: write` for OIDC.
Grant `contents: read` explicitly, and add `pull-requests: write` only to the job
that posts a comment.

**This file describes the monorepo, where all five workflows live in one
repository.** In a split application/infrastructure layout the release row becomes
two workflows in two repositories, and every `sub` claim below is repository-scoped
— so which repository may assume which role becomes the enforcement point of the
split. Read [`split-repo-releases.md`](split-repo-releases.md) for that variant;
`infra-plan.yml`, `infra-apply.yml`, and `drift-detect.yml` are unchanged by it.

**Pin third-party actions to a commit SHA, not a mutable tag.** Every example in
this file references actions by tag (`@v4`, `@v5`, `@v7`, `@v1`) for readability.
A tag can be moved by its publisher; a workflow that assumes a broad role should
not trust that it wasn't. Resolve and pin the exact commit SHA for each action
your repository actually adopts — do not copy a SHA from this document, since
one written here would go stale the moment a referenced action ships a new
release — and keep them current with Dependabot or Renovate rather than by hand.
First-party `actions/*` actions carry lower supply-chain risk than a small
third-party action, but the roles in this file are broad enough that both are
worth pinning.

## infra-plan.yml

```yaml
name: infra-plan

on:
  pull_request:
    paths:
      - 'Terraform/stacks/platform-*/**'
      - 'Terraform/environments/*/platform-*.tfvars'
      - 'Terraform/backend-config/*/platform-*.backend.hcl'
      - 'Terraform/modules/**'
      - '.github/workflows/infra-*.yml'

permissions:
  contents: read
  id-token: write
  pull-requests: write

concurrency:
  group: infra-plan-${{ github.ref }}
  cancel-in-progress: true

jobs:
  plan:
    runs-on: ubuntu-latest
    if: github.event.pull_request.head.repo.full_name == github.repository
    strategy:
      fail-fast: false
      matrix:
        stack: [platform-network, platform-data, platform-ecr]
    env:
      ENV: dev
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.TERRAFORM_PLAN_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Plan
        id: plan
        run: |
          set -o pipefail
          ./scripts/deploy-${{ matrix.stack }}.sh --plan-only 2>&1 | tee /tmp/plan.txt

      - name: Comment plan summary
        uses: actions/github-script@v7
        if: always()
        with:
          script: |
            const fs = require('fs');
            const body = fs.readFileSync('/tmp/plan.txt', 'utf8').slice(-60000);
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `### \`${{ matrix.stack }}\` plan\n\n<details><summary>output</summary>\n\n\`\`\`\n${body}\n\`\`\`\n\n</details>`,
            });
```

- The `if:` on the job blocks pull requests from forks. A fork PR gets no secrets
  and a read-only token, so the plan would fail confusingly; refusing it outright
  is clearer than a broken run.
- `ENV: dev` means a pull request is planned against dev only. That catches
  configuration errors but not a value that is wrong solely in prod's tfvars. Add
  `environment` as a second matrix dimension once per-environment values diverge
  enough for that to bite — at the cost of one plan per stack per environment on
  every push to the branch.
- `--plan-only` is the flag your deploy script needs for this workflow: init,
  validate, plan, print, exit — never apply. Add it to every `deploy-*.sh`
  alongside the existing `CI` branch.
- Truncate before commenting. GitHub rejects a comment body over 65,536
  characters, and a large platform plan will exceed it.
- A plan can print resolved values. Keep the comment inside the repository, never
  post it to an external service, and remember anyone with read access sees it.

**This matrix is exhaustive for the platform tier only, by design — it does not
also cover application stacks, and its path filter is scoped to `platform-*`
so it does not fire on one.** An earlier, unscoped `Terraform/**` filter here
matched an app stack's `.tf` files, its tfvars, and (in a split repository) its
published `*.artifacts.tfvars` too, while the hardcoded `matrix.stack` list
never ran `deploy-app-<service>.sh` — so a pull request that changed only
`app-notifier` got three unrelated platform-tier plans commented on it and
never saw a plan of the change it actually contained. Do not widen this
matrix to "fix" that; widening it means every PR plans every service, which is
exactly the blast-radius-on-every-push problem the stack split exists to avoid.
Plan app stacks with their own thin, per-service pull-request workflow instead:

```yaml
# .github/workflows/_app-plan.yml — reusable, one copy
name: app-plan

on:
  workflow_call:
    inputs:
      service:
        required: true
        type: string
      stack:
        required: true
        type: string

permissions:
  contents: read
  id-token: write
  pull-requests: write

concurrency:
  group: app-plan-${{ inputs.stack }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  plan:
    runs-on: ubuntu-latest
    if: github.event.pull_request.head.repo.full_name == github.repository
    env:
      ENV: dev
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.APP_PLAN_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Plan
        id: plan
        run: |
          set -o pipefail
          ./scripts/deploy-${{ inputs.stack }}.sh --plan-only 2>&1 | tee /tmp/plan.txt

      - name: Comment plan summary
        uses: actions/github-script@v7
        if: always()
        with:
          script: |
            const fs = require('fs');
            const body = fs.readFileSync('/tmp/plan.txt', 'utf8').slice(-60000);
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `### \`${{ inputs.stack }}\` plan\n\n<details><summary>output</summary>\n\n\`\`\`\n${body}\n\`\`\`\n\n</details>`,
            });
```

```yaml
# .github/workflows/plan-app-notifier.yml — one per service, about ten lines
name: plan-app-notifier

on:
  pull_request:
    paths:
      - 'Terraform/stacks/app-notifier/**'
      # Unlike the apply-side single-environment rule, wildcarding the
      # environment segment here is safe: a plan never mutates state, so
      # planning "the wrong" environment has no consequence beyond a comment.
      # This still always plans dev — see the ENV: dev note on infra-plan.yml —
      # but it means a staging or prod artifacts.tfvars change gets a plan
      # comment at all, instead of matching no trigger.
      - 'Terraform/environments/*/app-notifier*.tfvars'

jobs:
  plan:
    uses: ./.github/workflows/_app-plan.yml
    with:
      service: notifier
      stack: app-notifier
```

`AppPlanRole` is read-only across every `app-*` state prefix in `dev`, trusted
from `pull_request` — the same shape as `TerraformPlanRole`, just scoped to the
application tier instead of the platform tier. It is deliberately not one role
per service: a plan role only reads state and takes the lock, so the IAM-blast-radius
argument that justifies a role per service for *apply* does not carry the same
weight for read-only *plan*. In a split repository the artifact PR
(`Terraform/environments/{env}/app-notifier.artifacts.tfvars`) matches
`plan-app-notifier.yml`'s paths filter the same way it matches `infra-plan.yml`'s
— this is the workflow that actually makes the claim in
[`split-repo-releases.md`](split-repo-releases.md) true, not `infra-plan.yml`
by itself.

## infra-apply.yml

```yaml
name: infra-apply

on:
  push:
    branches: [main]
    paths:
      - 'Terraform/stacks/platform-*/**'
      - 'Terraform/environments/*/platform-*.tfvars'
      - 'Terraform/backend-config/*/platform-*.backend.hcl'
      - 'Terraform/modules/**'
  workflow_dispatch:
    inputs:
      environment:
        description: Target environment
        required: true
        type: choice
        options: [dev, staging, prod]

permissions:
  contents: read
  id-token: write

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment || 'dev' }}
    concurrency:
      group: tfstate-platform-${{ inputs.environment || 'dev' }}
      cancel-in-progress: false
    env:
      CI: 'true'
      ENV: ${{ inputs.environment || 'dev' }}
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.TERRAFORM_PLATFORM_APPLY_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - run: ./scripts/deploy-platform.sh
```

- `environment:` is what makes this job gateable. Put required reviewers on the
  `prod` environment; the role's trust policy below refuses to be assumed from
  any job that does not declare it.
- `cancel-in-progress: false` on a state-scoped concurrency group. Cancelling a
  run mid-apply leaves a stale lock and, worse, a partially applied change.
- Promotion to staging and prod is `workflow_dispatch`, not an automatic
  cascade. A merge applies to dev only.
- **The path filter is scoped to `platform-*` on purpose.** An unscoped
  `Terraform/environments/**` (or `backend-config/**`) also matches every app
  stack's tfvars and, in a split repository, every artifact file — so merging
  an ordinary app release would additionally trigger a full platform-tier apply
  for no platform reason. Keep this filter platform-only and let app changes
  apply exclusively through their own per-service release workflow, below.

**On handing a saved plan between jobs.** Applying the exact plan a reviewer read
is the stronger guarantee, and it needs `actions/upload-artifact` in the plan job
and `download-artifact` in the apply job. The cost is real: a plan file contains
resolved values, and any artifact is downloadable by anyone with repository read
access. If you do it, set `retention-days: 1` and treat the artifact as
sensitive. If that is unacceptable, keep plan and apply in one protected job so
the plan never leaves the runner, and accept that the reviewer approves the diff
rather than the plan file.

## App Release: One Reusable Workflow

| Option | Verdict |
|---|---|
| One workflow file per service | Rejected — N copies of identical YAML that drift apart |
| One workflow with a "which directories changed" matrix | Rejected — the role ARN becomes derived from the diff, so a mistaken or malicious path can assume another service's role |
| **One reusable workflow plus a thin per-service caller** | **Chosen** |

The distinction that matters: a service name **literal in a committed caller
file** is reviewable, and the IAM trust policy constrains it independently. A
service name **computed from the changed-files list** is neither.

```yaml
# .github/workflows/_app-release.yml
name: app-release

on:
  workflow_call:
    inputs:
      service:
        required: true
        type: string
      stack:
        required: true
        type: string
      environment:
        required: false
        type: string
        default: dev

permissions:
  contents: read
  id-token: write

jobs:
  release:
    runs-on: ubuntu-latest
    # A composite name, not just the environment — see "One Role Per Service Is
    # Not Automatically One Trust Domain" below. Create "api-prod",
    # "worker-prod", etc. as separate GitHub Environments, each with its own
    # required reviewers.
    environment: ${{ inputs.service }}-${{ inputs.environment }}
    concurrency:
      group: tfstate-${{ inputs.stack }}-${{ inputs.environment }}
      cancel-in-progress: false
    env:
      CI: 'true'
      ENV: ${{ inputs.environment }}
      SERVICE: ${{ inputs.service }}
      # Only consumed when the service's build is a Lambda ZIP; harmless and
      # unused for a Docker/ECR service.
      LAMBDA_ARTIFACT_BUCKET: ${{ vars.LAMBDA_ARTIFACT_BUCKET }}
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5 # only needed for a Lambda service; a Docker build ignores it

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/AppDeployRole-${{ inputs.service }}-${{ inputs.environment }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Build and publish the artifact
        run: ./scripts/build-${{ inputs.service }}.sh

      - name: Apply the app stack
        run: ./scripts/deploy-${{ inputs.stack }}.sh
```

Two additions beyond the original spine, both here because this workflow is
generic across artifact kinds and cannot assume which one a given caller needs:

- **`setup-uv` and `LAMBDA_ARTIFACT_BUCKET`.** `build-<service>.sh` for a Lambda
  ZIP requires both `uv` on `PATH` and `$LAMBDA_ARTIFACT_BUCKET` (see
  `references/build-scripts.md`). Each GitHub Actions job runs on its own fresh
  runner — a `setup-uv` step in a different job (for example a separate `test`
  job) does not carry over. Installing `uv` and passing the bucket variable
  through unconditionally costs a Docker-based service nothing; omitting them
  breaks every Lambda-based service's release.

```yaml
# .github/workflows/release-api.yml — one per service, about ten lines
name: release-api

on:
  push:
    branches: [main]
    paths:
      - 'apps/api/**'
      - 'Terraform/stacks/app-api/**'
      # dev only, deliberately — see the split-repo caller's identical rule in
      # split-repo-releases.md. A hand-edited value for staging or prod reaches
      # its environment only through workflow_dispatch.
      - 'Terraform/environments/dev/app-api.tfvars'
  workflow_dispatch:
    inputs:
      environment:
        required: true
        type: choice
        options: [dev, staging, prod]

jobs:
  release:
    uses: ./.github/workflows/_app-release.yml
    with:
      service: api
      stack: app-api
      environment: ${{ inputs.environment || 'dev' }}
    secrets: inherit
```

The caller carries only what must be static and reviewable: its `paths:` filter,
its service name, its stack name. Adding a service is a new ten-line file, not a
change to shared logic.

Without the `app-api.tfvars` entry, a hand-edited environment value — a memory
bump, a desired-count change — has no path that applies it: this caller only
watches application source and the stack's own `.tf` files, so an operator who
edits the tfvars and merges sees a green build with nothing deployed until the
next unrelated code change happens to trigger a release.

Notes on the reusable workflow:

- A reusable workflow called with `uses:` must be referenced by a local path or a
  full `owner/repo/.github/workflows/file.yml@ref`. There is no wildcard.
- `secrets: inherit` passes secrets, not `vars`. Repository and environment
  variables resolve normally in the called workflow, but an *environment*
  variable only resolves in a job that declares that `environment:` — which this
  job does.
- Keep the build before the apply in one job. The artifact tfvars file the build
  writes is on the runner's disk; splitting them across jobs means uploading it.

## drift-detect.yml

Schedule the **platform tier**. Platform stacks change rarely, so a non-empty
plan is meaningful. Nightly plans across N services × M environments are noise
and cost; run app-stack drift weekly or on demand.

```yaml
name: drift-detect

on:
  schedule:
    - cron: '17 6 * * 1-5'
  workflow_dispatch:

permissions:
  contents: read
  id-token: write
  issues: write

jobs:
  drift:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        stack: [platform-network, platform-data, platform-ecr]
        environment: [staging, prod]
    env:
      ENV: ${{ matrix.environment }}
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.TERRAFORM_PLAN_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Detect drift
        id: drift
        run: |
          set +e
          ./scripts/deploy-${{ matrix.stack }}.sh --plan-only --detailed-exitcode 2>&1 | tee /tmp/drift.txt
          code="${PIPESTATUS[0]}"
          set -e
          case "$code" in
            0) echo "drifted=false" >>"$GITHUB_OUTPUT" ;;
            2) echo "drifted=true"  >>"$GITHUB_OUTPUT" ;;
            *) exit "$code" ;;
          esac

      - name: Open an issue
        if: steps.drift.outputs.drifted == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const body = fs.readFileSync('/tmp/drift.txt', 'utf8').slice(-60000);
            const title = `Drift: ${{ matrix.stack }} (${{ matrix.environment }})`;
            const existing = await github.rest.search.issuesAndPullRequests({
              q: `repo:${context.repo.owner}/${context.repo.repo} is:issue is:open in:title "${title}"`,
            });
            if (existing.data.total_count === 0) {
              await github.rest.issues.create({
                owner: context.repo.owner, repo: context.repo.repo,
                title, body: `\`\`\`\n${body}\n\`\`\``, labels: ['drift'],
              });
            }
```

- `-detailed-exitcode` returns 0 for no changes, 2 for changes, 1 for an error.
  Only 2 is drift; do not collapse 1 and 2 into "something changed".
- Capture `${PIPESTATUS[0]}`, not `$?`, when the command is piped to `tee` —
  `$?` is `tee`'s status. This is the single most common bug in this workflow.
- Search before creating, or a persistent drift opens one issue per weekday.
- Scheduled workflows run against the default branch and are disabled after 60
  days of repository inactivity.

## Deployment Roles

One role per workflow, and for the application tier one role per service per
environment. Each trust policy pins the repository **and the claim that proves
which workflow context is asking**.

`TerraformPlanRole` — read-only plus the state lock. **This one role is
assumed from two different trigger shapes** — `infra-plan.yml`'s
`pull_request` and `drift-detect.yml`'s `schedule` — and each produces a
different OIDC `sub` claim. A schedule (or a `workflow_dispatch` with no
`environment:`) has no pull request and no declared environment, so GitHub
issues a ref-based subject instead. Trust both explicitly; a policy that only
lists the `pull_request` form lets `infra-plan.yml` work while
`drift-detect.yml` fails every run with an OIDC trust error:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Federated": "arn:aws:iam::<account>:oidc-provider/token.actions.githubusercontent.com" },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:<org>/<repo>:pull_request",
            "repo:<org>/<repo>:ref:refs/heads/main"
          ]
        }
      }
    }
  ]
}
```

Confirm the exact ref-based subject format against GitHub's current OIDC
documentation for your default branch name before shipping this; it has to
match what the token actually carries for a scheduled run, not an assumption.

Its permission policy is a read-only managed or scoped policy, plus
`s3:GetObject` on the state object, `s3:ListBucket` on the state prefix, and
`s3:GetObject`/`s3:PutObject`/`s3:DeleteObject` on the `.tflock` object. A plan
takes the lock — acquiring it can require reading the current lock holder, not
only writing and clearing one — but it never writes state itself. Match
`terraform-aws/SKILL.md`'s Remote State Backend section, which grants all three
verbs on `.tflock`; a role that only has `PutObject`/`DeleteObject` there is
narrower than what that skill documents as the baseline.

`TerraformPlatformApplyRole` — broad, but only reachable from a protected job.
The `sub` claim carries `environment:<name>` exactly when the job declares an
`environment:`, which is what ties the role to the reviewer requirement:

```json
{
  "Condition": {
    "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
    "StringLike": { "token.actions.githubusercontent.com:sub": "repo:<org>/<repo>:environment:prod" }
  }
}
```

`AppDeployRole-<service>-<env>` may do only what a release needs:

- ECS: `RegisterTaskDefinition`, `UpdateService`, `DescribeServices` and
  `DescribeTaskDefinition` for that cluster and service ARN.
- `iam:PassRole` on exactly that service's task and execution role ARNs. Without
  this scoping, a release role can pass any role into a task and inherit it.
- Lambda: update/publish and alias actions on that function ARN only.
- ECR: push and `GetAuthorizationToken` for that service's repository.
- ELB: target group and listener rule actions for its own resources.
- State: read and write under `<env>/app-<service>/` and its `.tflock`.
- SSM: `GetParameter`/`GetParameters` on `/{project}/{env}/platform/*`, read-only.

It must **not** hold RDS, VPC, KMS-key-policy, Route 53 zone, or cluster-level
permissions. Nothing in an application release needs them.

**If the app stack owns its own task role**, the deploy role needs IAM write, and
that is an escalation path unless you bound it. Scope `iam:CreateRole`,
`iam:PutRolePolicy`, `iam:AttachRolePolicy`, and `iam:DeleteRole` to a name
prefix or path reserved for that service, and require a permissions boundary:

```json
{
  "Effect": "Allow",
  "Action": ["iam:CreateRole", "iam:PutRolePolicy", "iam:AttachRolePolicy"],
  "Resource": "arn:aws:iam::<account>:role/app-api/*",
  "Condition": {
    "StringEquals": { "iam:PermissionsBoundary": "arn:aws:iam::<account>:policy/AppTaskBoundary" }
  }
}
```

Without the boundary condition, a role that can create roles and attach policies
can grant itself anything.

## Generating the Per-Service Roles

One role per service per environment is N×M roles. Generate them from a
platform-tier module rather than writing them by hand, so the trust policy and
the boundary are identical everywhere:

```hcl
locals {
  app_deploy_roles = {
    for pair in setproduct(var.services, var.environments) :
    "${pair[0]}-${pair[1]}" => { service = pair[0], environment = pair[1] }
  }
}

module "app_deploy_role" {
  source   = "../../modules/github-oidc-role"
  for_each = local.app_deploy_roles

  name                = "AppDeployRole-${each.key}"
  github_repository   = var.github_repository
  # Composite, not just the environment name — see the isolation note below.
  subject              = "repo:${var.github_repository}:environment:${each.value.service}-${each.value.environment}"
  permissions_boundary = aws_iam_policy.app_task_boundary.arn
  service             = each.value.service
  environment         = each.value.environment
}
```

The cheaper alternative is one role per service across environments, relying on
separate AWS accounts for environment isolation. That is defensible with account
separation and wrong without it: in a single account it lets a dev release touch
prod. Do not default to it.

**One role per service is not automatically one trust domain per service.** A
GitHub Actions OIDC token's `sub` claim carries `environment:<name>` — just the
environment, not which workflow file or which service produced it. If every
service in `prod` shares the plain environment name `prod` (as `_app-release.yml`
did before this note), then `AppDeployRole-api-prod` and
`AppDeployRole-worker-prod` end up with **the same trust condition**
(`environment:prod`), because every per-service caller's job declares that same
`environment:`. Any workflow in the repository authorized to run against `prod`
can then request credentials for *any* service's `prod` role — the "which
workflow context is asking" claim this section opens with is true of the
repository and the environment, not of the service, unless the environment name
itself is made service-specific.

The fix is the composite `${service}-${environment}` name used above, matched
by `_app-release.yml`'s job declaring `environment: ${{ inputs.service }}-${{
inputs.environment }}` (see [App Release: One Reusable
Workflow](#app-release-one-reusable-workflow)). This means creating one GitHub
Environment per service per deployment environment — `api-prod`,
`worker-prod`, and so on — each with its own required reviewers, rather than
one shared `prod`. It is more environments to configure, and it is what makes
the per-service blast-radius claim in this file actually true.

The `subject` above is what ties a role to one repository. Under a split layout
this module generates two role kinds with two different subjects — a publish-only
role trusted from each application repository, and the deploy role trusted from the
infrastructure repository. Listing both repositories as acceptable subjects on one
role silently restores the monorepo's blast radius while looking like a split; see
[`split-repo-releases.md`](split-repo-releases.md).

Deploying these roles is a platform-tier change, applied by
`infra-apply.yml` — not by any release.
