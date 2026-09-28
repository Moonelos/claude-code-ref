# AMI Builds for the EC2 and ASG Release Path

An EC2 release ships a **new AMI**, not new files on running instances. This file
covers building the image, handing its ID to Terraform, and driving the instance
refresh to completion. The Terraform side is in the sibling `terraform-aws`
skill's `references/workload-deploy-patterns.md`.

In a grouped monorepo layout place the build script under `scripts/release/`.
Adapt the listing's repository root to `$SCRIPT_DIR/../..` and resolve sibling
build scripts from that folder.

## Contents

- [Why Not Copy Files to Running Instances](#why-not-copy-files-to-running-instances)
- [Building with Packer](#building-with-packer)
- [The Build Script](#the-build-script)
- [Handing the AMI ID to Terraform](#handing-the-ami-id-to-terraform)
- [Waiting for the Instance Refresh](#waiting-for-the-instance-refresh)
- [EC2 Image Builder](#ec2-image-builder)
- [Retention and Rollback](#retention-and-rollback)

## Why Not Copy Files to Running Instances

The pattern this replaces was `aws s3 sync` of application files followed by
`terraform apply`. It reports success while shipping nothing:

- `user_data` runs **once, at instance launch**. Editing it changes the launch
  template, not any running instance.
- If `user_data` is unchanged, the apply is a no-op. Terraform prints
  "No changes" and the deploy step exits 0.
- Existing instances keep serving the previous code until something unrelated
  replaces them — at which point they silently pick up whatever is in S3.

An S3 upload is still legitimate as **first-boot seeding during environment
bring-up**. Label it as that. It is not a release mechanism.

## Building with Packer

Keep the template beside the application, version it, and pass the release
identity in as variables:

```hcl
# packer/api.pkr.hcl
packer {
  required_plugins {
    amazon = {
      source  = "github.com/hashicorp/amazon"
      version = "~> 1.3"
    }
  }
}

variable "git_sha" { type = string }
variable "aws_region" { type = string }
variable "source_ami_filter_name" { type = string }

source "amazon-ebs" "api" {
  region        = var.aws_region
  instance_type = "t4g.small"
  ssh_username  = "ec2-user"

  ami_name        = "api-${var.git_sha}-${formatdate("YYYYMMDDhhmmss", timestamp())}"
  ami_description = "api @ ${var.git_sha}"

  source_ami_filter {
    filters = {
      name                = var.source_ami_filter_name
      virtualization-type = "hvm"
      root-device-type    = "ebs"
    }
    owners      = ["amazon"]
    most_recent = true
  }

  encrypt_boot = true

  tags = {
    Service   = "api"
    GitSha    = var.git_sha
    ManagedBy = "packer"
  }
}

build {
  sources = ["source.amazon-ebs.api"]

  provisioner "shell" {
    scripts = ["packer/scripts/install-runtime.sh", "packer/scripts/install-app.sh"]
  }

  post-processor "manifest" {
    output     = "build/api/packer-manifest.json"
    strip_path = true
  }
}
```

- The `manifest` post-processor is how the build script learns the AMI ID.
  Parsing `packer build` console output is brittle.
- `source_ami_filter` with `most_recent = true` means two builds of the same
  commit can produce different images. That is fine — the AMI ID is the artifact
  version, not the commit — but it is why the AMI name carries a timestamp.
- Bake the application into the image. An AMI whose `user_data` downloads the app
  at boot reintroduces the problem this path exists to solve.
- `encrypt_boot = true` unless you have a specific reason not to; snapshots
  outlive instances.

## The Build Script

`build-<service>-ami.sh` follows the same spine as every other build script: it
produces an artifact and writes the artifact tfvars file the deploy script passes
as a second `-var-file`, on every exit path including the "already built"
short-circuit.

```bash
#!/usr/bin/env bash
# Build the <service> AMI and write its ID for Terraform
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV="${ENV:?Set ENV to a supported environment}"
BUILD_DIR="$REPO_ROOT/build/<service>"
MANIFEST="$BUILD_DIR/packer-manifest.json"
ARTIFACT_VARS="$BUILD_DIR/<service>-ami.tfvars"
AWS_REGION="${AWS_REGION:?Set AWS_REGION}"

# Paste the four print_* helpers verbatim (SKILL.md -> Helper Functions).

for cmd in packer aws jq git; do
  if ! command -v "$cmd" &>/dev/null; then
    print_error "$cmd is not installed"; exit 1
  fi
done

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)"
mkdir -p "$BUILD_DIR"

write_artifact_vars() {
  cat >"$ARTIFACT_VARS" <<EOF
<service>_ami_id = "$1"
EOF
  print_info "AMI: $1"
}

# Reuse an AMI already built from this commit: the image is the artifact, and
# rebuilding produces a different ID for identical code.
EXISTING_AMI="$(aws ec2 describe-images \
  --owners self \
  --region "$AWS_REGION" \
  --filters "Name=tag:Service,Values=<service>" \
            "Name=tag:GitSha,Values=$GIT_SHA" \
            "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text)"

if [[ -n "$EXISTING_AMI" && "$EXISTING_AMI" != "None" ]]; then
  write_artifact_vars "$EXISTING_AMI"
  print_success "Reusing existing AMI for $GIT_SHA"
  exit 0
fi

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
  print_warning "Uncommitted changes — AMI tagged $GIT_SHA will not reproduce this build"
fi

rm -f "$MANIFEST"
# Packer resolves the provisioner `scripts` and post-processor `output` paths
# in the template relative to its own working directory, not relative to the
# template file — cd first, or a caller invoking this script from anywhere
# other than $REPO_ROOT gets "no such file" mid-build or a manifest written to
# the wrong place.
cd "$REPO_ROOT"
packer init "packer/<service>.pkr.hcl"
packer build \
  -var "git_sha=$GIT_SHA" \
  -var "aws_region=$AWS_REGION" \
  -var "source_ami_filter_name=${SOURCE_AMI_NAME:?Set SOURCE_AMI_NAME}" \
  "packer/<service>.pkr.hcl"

AMI_ID="$(jq -r '.builds[-1].artifact_id' "$MANIFEST" | cut -d: -f2)"
if [[ -z "$AMI_ID" || "$AMI_ID" != ami-* ]]; then
  print_error "Could not resolve an AMI ID from $MANIFEST"
  exit 1
fi

write_artifact_vars "$AMI_ID"
print_success "<Service> AMI built: $AMI_ID"
```

`artifact_id` in the manifest is `<region>:<ami-id>`, which is why it is cut on
the colon. Validate the result before writing it: a malformed value would reach
Terraform as a plan-time validation failure at best, and as a silent no-op at
worst if the variable had a default. It must not have one.

## Handing the AMI ID to Terraform

Exactly like an image tag or a Lambda object version. Capture the ASG's most
recent refresh ID *before* the apply, so the waiter below can tell "a new
refresh started" from "no refresh started, this is stale" instead of guessing:

```bash
"$SCRIPT_DIR/build-<service>-ami.sh"

ASG_NAME="$(terraform output -raw <service>_asg_name 2>/dev/null || echo "")"
PRE_APPLY_REFRESH_ID="None"
if [[ -n "$ASG_NAME" ]]; then
  PRE_APPLY_REFRESH_ID="$(aws autoscaling describe-instance-refreshes \
    --auto-scaling-group-name "$ASG_NAME" \
    --region "$AWS_REGION" \
    --max-records 1 \
    --query 'InstanceRefreshes[0].InstanceRefreshId' \
    --output text 2>/dev/null || echo "None")"
fi

terraform plan -input=false -lock-timeout=5m \
  -var-file="$VAR_FILE" -var-file="$ARTIFACT_VARS" -out="$PLAN_FILE"
# ... apply happens here ...
```

In CI, `AMI_ID` may be supplied directly as an environment variable
(`TF_VAR_<service>_ami_id`) when the image was built by an earlier job. The rule
is unchanged: the variable is required, validated, and has no default, so a
release that skipped its build fails at plan.

## Waiting for the Instance Refresh

`terraform apply` returns once the refresh has **started**. Without a wait, a
release that rolls back mid-refresh looks like a successful deploy — and
without comparing against a pre-apply baseline, `[0]` (most recent) can just as
easily be a completed refresh from an *earlier* release when this apply's
launch template didn't actually change:

```bash
ASG_NAME="$(terraform output -raw <service>_asg_name)"

REFRESH_ID="$(aws autoscaling describe-instance-refreshes \
  --auto-scaling-group-name "$ASG_NAME" \
  --region "$AWS_REGION" \
  --max-records 1 \
  --query 'InstanceRefreshes[0].InstanceRefreshId' \
  --output text)"

if [[ "$REFRESH_ID" == "$PRE_APPLY_REFRESH_ID" ]]; then
  print_info "No new instance refresh started — launch template did not change"
  exit 0
fi

print_info "Waiting for instance refresh $REFRESH_ID..."
DEADLINE=$((SECONDS + 1800))
while (( SECONDS < DEADLINE )); do
  read -r STATUS PERCENT <<<"$(aws autoscaling describe-instance-refreshes \
    --auto-scaling-group-name "$ASG_NAME" \
    --instance-refresh-ids "$REFRESH_ID" \
    --region "$AWS_REGION" \
    --query 'InstanceRefreshes[0].[Status,PercentageComplete]' \
    --output text)"

  case "$STATUS" in
    Successful)
      print_success "Instance refresh complete"
      break
      ;;
    Failed|Cancelled|RollbackSuccessful|RollbackFailed)
      print_error "Instance refresh ended as $STATUS"
      exit 1
      ;;
    *)
      print_info "  $STATUS ${PERCENT}%"
      sleep 30
      ;;
  esac
done

if (( SECONDS >= DEADLINE )); then
  print_error "Instance refresh did not finish within 30 minutes"
  exit 1
fi
```

- Treat `RollbackSuccessful` as a failed release. The fleet is healthy, but it is
  running the previous AMI — reporting success would be a lie.
- `PercentageComplete` is absent while a refresh is `Pending`, so print it
  loosely and never parse it for control flow.
- Bound the wait. An ASG with a failing health check will sit in `InProgress`
  until the refresh's own timeout, which is longer than any CI job should hold.
- The `PRE_APPLY_REFRESH_ID` comparison above is what makes "no new refresh
  started" distinguishable from "the new refresh already finished by the time
  we asked" — both look like `[0]` being a `Successful` refresh with a
  different ID than the one you expected. Without the baseline, a build that
  didn't change the launch template can report a stale, unrelated refresh as
  this release's outcome.

## EC2 Image Builder

Use it instead of Packer when you want the pipeline itself declared in Terraform
and managed by AWS: an `aws_imagebuilder_image_recipe`,
`aws_imagebuilder_infrastructure_configuration`, and
`aws_imagebuilder_image_pipeline`.

The pipeline is **platform-tier infrastructure** — it changes rarely and is
shared. The images it produces are application artifacts. Do not put the pipeline
in an app stack, and do not let the app stack's apply trigger a build.

Read the resulting AMI out of the pipeline's latest image version and pass it to
the app stack the same way, still as a required input with no default. Resolving
it with `data "aws_ami"` inside the app stack instead makes every plan depend on
whatever the newest image happens to be, which is exactly the mutable-`latest`
problem in a different costume.

## Retention and Rollback

- **Rollback is the previous AMI ID.** Keep it: record the ID per release, or find
  it by its `GitSha` tag. Rollback is then a normal apply with the old value, plus
  the refresh wait.
- **AMIs and their snapshots cost money after the release.** Deregister old images
  and delete their snapshots on a schedule, keeping at least the current and
  previous per service per environment. Deregistering an AMI still referenced by a
  launch template version leaves that version unusable.
- **Never delete the AMI a running ASG launched from** until the fleet is on the
  next one; a scale-out event needs it.
