# Build Scripts

`build-<service>.sh` produces an immutable deployable artifact — a Lambda ZIP or a
Docker image in ECR — and hands its version to Terraform through a generated
`.tfvars` file. For the AMI artifact the EC2/ASG path releases, see
[`ami-builds.md`](ami-builds.md).

Every listing here follows the standard script spine in `SKILL.md`: `set -euo
pipefail`, `${BASH_SOURCE[0]}` path resolution, the four `print_*` helpers
pasted verbatim, and a pre-flight tool check.

## Contents

- [Which Repository The Build Runs In](#which-repository-the-build-runs-in)
- [Lambda Artifact Build](#lambda-artifact-build)
- [Docker ECR Build](#docker-ecr-build)
- [First-Boot Asset Seeding](#first-boot-asset-seeding)

## Which Repository The Build Runs In

`REPO_ROOT` in every listing below is **the root of the repository that owns the
source**, which is only the same as the Terraform repository in a monorepo. Resolve
[the repository topology](../SKILL.md#repository-topology) before copying a
listing, because two lines depend on it:

- `LAMBDA_DIR` / `APP_DIR` — where the source is read from.
- `git -C "$REPO_ROOT" rev-parse HEAD` — the commit that names the artifact.

For a script at the root of either repository, both resolve correctly against
`$SCRIPT_DIR/..`. For `scripts/release/build-<service>.sh` in a grouped layout,
use `$SCRIPT_DIR/../..` and point sibling calls at the same `release/` folder.
What changes in a split repository is the
handoff: instead of the deploy script reading the generated tfvars off the same
runner's disk, the application repository publishes the version as a committed
`Terraform/environments/{env}/{stack}.artifacts.tfvars` in the infrastructure
repository — [`split-repo-releases.md`](split-repo-releases.md).

Leaving the build script in the Terraform repository while the source lives
elsewhere is the failure to avoid. `git rev-parse` then returns the infrastructure
commit, so the image tag or S3 key no longer identifies the code in the artifact,
and every "which commit is running?" answer afterwards is wrong.

An ECR-URL argument or a `$ECR_REPO_URL` environment variable is how a split-repo
build script gets the repository URL. It cannot run `terraform output` — it has no
Terraform tree, no backend configuration, and no state access, by design.

## Lambda Artifact Build

Keep source at `lambdas/<service>/` in the repository that owns it, outside the
Terraform directory.
Use `pyproject.toml` and `uv.lock` as the dependency source of truth and bundle
the dependencies into the function ZIP by default. Generate `requirements.txt`
only as a temporary build artifact; never commit it beside the lockfile.

The `base64sha256` below is unrelated to the container image tagging decision.
It is the content hash the Lambda API requires through `source_code_hash` to
detect a real change, not a version tag a human or another stack reads.

```bash
#!/usr/bin/env bash
# Build the <service> Lambda ZIP with uv
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAMBDA_DIR="$REPO_ROOT/lambdas/<service>"
BUILD_DIR="$REPO_ROOT/build/<service>"
PACKAGE_DIR=""
FUNCTION_ZIP="$BUILD_DIR/<service>.zip"
REQUIREMENTS_FILE="$BUILD_DIR/requirements.txt"
ARTIFACT_VARS="$BUILD_DIR/<service>-artifacts.tfvars"
ARTIFACT_BUCKET="${LAMBDA_ARTIFACT_BUCKET:?Set LAMBDA_ARTIFACT_BUCKET to the versioned artifact bucket}"
PYTHON_VERSION="3.12" # Must equal the Terraform Lambda runtime.
LAMBDA_ARCHITECTURE="${LAMBDA_ARCHITECTURE:-x86_64}"

# Paste the four print_* helpers verbatim (SKILL.md -> Helper Functions).

for cmd in aws uv zip openssl; do
  if ! command -v "$cmd" &>/dev/null; then
    print_error "$cmd is not installed"; exit 1
  fi
done

case "$LAMBDA_ARCHITECTURE" in
  x86_64) UV_PLATFORM="x86_64-manylinux2014" ;;
  arm64)  UV_PLATFORM="aarch64-manylinux2014" ;;
  *) print_error "LAMBDA_ARCHITECTURE must be x86_64 or arm64"; exit 1 ;;
esac

if [[ ! -f "$LAMBDA_DIR/handler.py" || ! -d "$LAMBDA_DIR/src" ]]; then
  print_error "Lambda requires handler.py and src/: $LAMBDA_DIR"
  exit 1
fi

if [[ "$(aws s3api get-bucket-versioning \
  --bucket "$ARTIFACT_BUCKET" --query Status --output text)" != "Enabled" ]]; then
  print_error "Artifact bucket must have S3 versioning enabled: $ARTIFACT_BUCKET"
  exit 1
fi

base64_sha256() { openssl dgst -sha256 -binary "$1" | openssl base64 | tr -d '\n'; }

mkdir -p "$BUILD_DIR"
PACKAGE_DIR="$(mktemp -d "$BUILD_DIR/package.XXXXXX")"
trap 'rm -rf "$PACKAGE_DIR"; rm -f "$REQUIREMENTS_FILE"' EXIT
rm -f "$FUNCTION_ZIP"

# pyproject.toml is optional only for a dependency-free handler. When it exists,
# the committed lockfile must be current and is the only dependency lock.
if [[ -f "$LAMBDA_DIR/pyproject.toml" ]]; then
  if [[ ! -f "$LAMBDA_DIR/uv.lock" ]]; then
    print_error "Missing committed lockfile: $LAMBDA_DIR/uv.lock"
    exit 1
  fi

  (
    cd "$LAMBDA_DIR"
    uv lock --check
    uv export \
      --frozen \
      --no-dev \
      --no-editable \
      --no-emit-project \
      --format requirements.txt \
      --output-file "$REQUIREMENTS_FILE"
  )

  uv pip install \
    --requirements "$REQUIREMENTS_FILE" \
    --target "$PACKAGE_DIR" \
    --python-version "$PYTHON_VERSION" \
    --python-platform "$UV_PLATFORM" \
    --only-binary=:all:
elif [[ -f "$LAMBDA_DIR/uv.lock" ]]; then
  print_error "Found uv.lock without pyproject.toml in $LAMBDA_DIR"
  exit 1
fi

cp "$LAMBDA_DIR/handler.py" "$PACKAGE_DIR/"
cp -R "$LAMBDA_DIR/src/." "$PACKAGE_DIR/"
(cd "$PACKAGE_DIR" && zip -q -X -r "$FUNCTION_ZIP" .)

SOURCE_CODE_HASH="$(base64_sha256 "$FUNCTION_ZIP")"
CONTENT_SHA256="$(openssl dgst -sha256 "$FUNCTION_ZIP" | awk '{print $NF}')"
S3_KEY="lambdas/<service>/${CONTENT_SHA256}.zip"

# The content hash makes the key immutable. Reuse its current version when it
# already exists, but always write artifact vars for the following plan.
OBJECT_VERSION="$(
  aws s3api head-object \
    --bucket "$ARTIFACT_BUCKET" \
    --key "$S3_KEY" \
    --query VersionId \
    --output text 2>/dev/null || true
)"
if [[ -z "$OBJECT_VERSION" || "$OBJECT_VERSION" == "None" ]]; then
  OBJECT_VERSION="$(
    aws s3api put-object \
      --bucket "$ARTIFACT_BUCKET" \
      --key "$S3_KEY" \
      --body "$FUNCTION_ZIP" \
      --query VersionId \
      --output text
  )"
fi
if [[ -z "$OBJECT_VERSION" || "$OBJECT_VERSION" == "None" ]]; then
  print_error "S3 did not return an object version for s3://$ARTIFACT_BUCKET/$S3_KEY"
  exit 1
fi

cat >"$ARTIFACT_VARS" <<EOF
<service>_lambda_s3_key            = "$S3_KEY"
<service>_lambda_s3_object_version = "$OBJECT_VERSION"
<service>_lambda_source_code_hash  = "$SOURCE_CODE_HASH"
EOF

print_success "<Service> Lambda artifact published: s3://$ARTIFACT_BUCKET/$S3_KEY?versionId=$OBJECT_VERSION"
```

Pin `PYTHON_VERSION` and the architecture mapping to the function's Terraform
configuration. `--only-binary=:all:` makes a missing compatible native wheel
fail during the build instead of compiling for the host and failing at
invocation. If a dependency requires a source build, run that build in a
container matching the Lambda OS, runtime, and architecture.

The script copies `handler.py` and the contents of `src/` to the ZIP root.
Therefore, import `<package>`, not `src.<package>`, from the handler. Do not copy
`pyproject.toml`, `uv.lock`, tests, `.venv`, caches, or the generated
requirements file into the artifact. Introduce a Lambda layer only for an
intentionally shared, independently versioned dependency; it is not the default
packaging mechanism. For Lambda container images, follow
`references/python-lambda.md` in the sibling `terraform-aws` skill; the generic
Docker/ECR example below still applies to ordinary application containers.

Give the application release role `s3:PutObject` and `s3:GetObject` only on that
function's artifact prefix and `s3:GetBucketVersioning` on the bucket. Keep
artifact-bucket read permissions for the Lambda deployment path separate from
permission to build or mutate artifacts.

In a monorepo the deploy script calls the build script before `terraform init`,
then passes the artifact vars as a second `-var-file`:

```bash
"$SCRIPT_DIR/build-<service>.sh"
# ...
terraform plan -input=false -lock-timeout=5m \
  -var-file="$VAR_FILE" -var-file="$ARTIFACT_VARS" -out="$PLAN_FILE"
```

In a split repository there is no build call — the deploy script points
`ARTIFACT_VARS` at the committed file and fails loudly when it is absent. The
`-var-file` line is identical either way, which is why the split needs no change to
the Terraform side.

## Docker ECR Build

Tag with the Git SHA — never `latest` or a branch name — and configure the ECR
repository as immutable. Read `references/docker-image-tagging.md` from the
sibling `terraform-aws` skill for the tag-versus-digest decision.

```bash
#!/usr/bin/env bash
# Build the <service> Docker image and push to ECR
# Usage: ./scripts/build-<service>.sh [ECR_REPO_URL]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV="${ENV:?Set ENV before building or selecting an environment repository}"
APP_DIR="$REPO_ROOT/apps/<service>"
BUILD_DIR="$REPO_ROOT/build/<service>"
ARTIFACT_VARS="$BUILD_DIR/<service>-image.tfvars"
TARGET_PLATFORM="${TARGET_PLATFORM:?Set TARGET_PLATFORM to the task/function architecture, e.g. linux/arm64 or linux/amd64}"

# Paste the four print_* helpers verbatim (SKILL.md -> Helper Functions).

for cmd in aws docker git; do
  if ! command -v "$cmd" &>/dev/null; then
    print_error "$cmd is not installed"; exit 1
  fi
done

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)"
IMAGE_TAG="${IMAGE_TAG:-$GIT_SHA}"
[[ "$IMAGE_TAG" == "latest" ]] && { print_error "'latest' is not valid; ECR uses immutable tags."; exit 1; }

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain -- "$APP_DIR")" ]]; then
  print_warning "Uncommitted changes in $APP_DIR — tag $IMAGE_TAG won't reproduce this exact build. Commit first for a real deploy."
fi

# Accept repo URL as argument or environment variable; fall back to terraform
# output only in a monorepo, and only when neither was supplied.
# Split repo: pass it in (argument or ECR_REPO_URL) — there is no Terraform tree
# here to read an output from. Publish it as a platform SSM parameter and read
# that, or set it as a repository variable in the application repository.
if [[ -n "${1:-}" ]]; then
  ECR_REPO_URL="$1"
elif [[ -z "${ECR_REPO_URL:-}" ]]; then
  ECR_TF_DATA_DIR="$REPO_ROOT/.terraform-data/$ENV/platform-ecr/platform-ecr"
  ECR_BACKEND_CONFIG="$REPO_ROOT/Terraform/backend-config/$ENV/platform-ecr.backend.hcl"
  TF_DATA_DIR="$ECR_TF_DATA_DIR" \
    terraform -chdir="$REPO_ROOT/Terraform/stacks/platform-ecr" \
    init -reconfigure -backend-config="$ECR_BACKEND_CONFIG" -input=false >/dev/null
  ECR_REPO_URL="$(
    TF_DATA_DIR="$ECR_TF_DATA_DIR" \
      terraform -chdir="$REPO_ROOT/Terraform/stacks/platform-ecr" \
      output -raw <service>_ecr_repository_url
  )"
fi

if [[ -z "$ECR_REPO_URL" ]]; then
  print_error "ECR_REPO_URL could not be resolved; pass it as an argument or set ECR_REPO_URL"
  exit 1
fi

AWS_ACCOUNT_ID="$(echo "$ECR_REPO_URL" | cut -d'.' -f1)"
AWS_REGION="${AWS_REGION:-$(echo "$ECR_REPO_URL" | cut -d'.' -f4)}"
ECR_REPO_NAME="$(echo "$ECR_REPO_URL" | cut -d'/' -f2)"

write_artifact_vars() {
  mkdir -p "$BUILD_DIR"
  cat >"$ARTIFACT_VARS" <<EOF
<service>_image_tag = "$IMAGE_TAG"
EOF
}

# Skip build if this commit's tag already exists in ECR — immutable tags + a
# git-SHA tag make this safe: same commit always produces the same tag.
if aws ecr describe-images --repository-name "$ECR_REPO_NAME" \
    --image-ids imageTag="$IMAGE_TAG" --region "$AWS_REGION" >/dev/null 2>&1; then
  write_artifact_vars
  print_success "Image tag already exists in ECR; skipping build"
  exit 0
fi

aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin \
  "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker build --platform "$TARGET_PLATFORM" -t "${ECR_REPO_URL}:${IMAGE_TAG}" "$APP_DIR"
docker push "${ECR_REPO_URL}:${IMAGE_TAG}"

write_artifact_vars
print_success "<Service> image pushed: ${ECR_REPO_URL}:${IMAGE_TAG}"
```

`write_artifact_vars` is a function, not an inline heredoc, because the
early-exit path needs it too: when the tag already exists in ECR the script must
still hand the deploy script a tfvars file, or the following `terraform plan`
fails on a missing variable.

Set `TARGET_PLATFORM` to the task/function architecture, not the builder's — it
is a required input for exactly this reason, the same way `LAMBDA_ARCHITECTURE`
drives `UV_PLATFORM` in the Lambda build above. Building `linux/arm64` on an x86
runner requires `docker buildx` with QEMU configured, or a native arm64 runner.

The terraform-output fallback for `ECR_REPO_URL` reads a *different* stack's
state (`platform-ecr`), so it must initialize that stack's backend before
calling `output` — it is not already initialized just because this script is
running. Route the fallback through `platform-ecr`, never a bare `ecr` root;
every other reference to the ECR stack in these skills uses that name, and a
mismatched root name means `terraform -chdir` points at a directory that does
not exist.

`AWS_REGION` prefers an explicit env var (CI always sets one) and only falls
back to parsing the ECR URL locally; `cut`-ing the URL on dots assumes the
standard `<account>.dkr.ecr.<region>.amazonaws.com` shape and breaks on
FIPS/dualstack/`.cn` endpoints, so don't rely on it as the only source of truth
in CI.

## First-Boot Asset Seeding

**This is not a deploy mechanism.** An `aws s3 sync` followed by
`terraform apply` does not update running instances: `user_data` runs once at
launch, so an unchanged launch template makes the apply a no-op and the deploy
reports success having shipped nothing. Application releases for EC2 go through a
new AMI — [`ami-builds.md`](ami-builds.md).

Seeding files into S3 is still legitimate for **environment bring-up**, when the
bucket must hold first-boot assets before any instance launches. Label it as
that, keep it in the bring-up path, and never wire it into a release:

```bash
# Bring-up only. Seeds first-boot assets; does NOT update running instances.
S3_BUCKET="${S3_BUCKET:?Set S3_BUCKET explicitly for bring-up seeding}"
print_info "Seeding first-boot assets to s3://$S3_BUCKET/..."
aws s3 sync "$APP_DIR/" "s3://$S3_BUCKET/$S3_PREFIX/" \
  --exclude "*.pyc" --exclude "__pycache__/*" --delete
```

Require `S3_BUCKET` explicitly rather than scraping it out of a tfvars file. A
regex over HCL handles only the simplest `key = "value"` line, and a silent parse
failure here means syncing to nowhere.
