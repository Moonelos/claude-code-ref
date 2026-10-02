# Docker Compose and the root `.env`

Use this reference for local Docker Compose orchestration in either repository
mode.

## Ownership

Keep one real `<repo-root>/.env` for local Compose values and exclude it from
Git and Docker build contexts. Commit `<repo-root>/.env.example` as the stack
bootstrap contract. List active assignments only for values the user must set
or consciously choose to start the local stack and obtain its intended behavior
(including credentials, external endpoints, and consequential feature choices).
Keep values with safe local defaults in Compose or committed configuration;
do not copy the full service settings inventory into the root file. Add brief
comments where a value needs explanation.

In a workspace, also keep `services/<name>/.env.example` beside every
deployable. It is the authoritative runtime environment contract for that
process, whether started by Compose, `uv run`, tests, or a deployment platform;
its sections (REQUIRED, OVERRIDABLE, OPTIONAL) and contents are owned by
`python-settings-config` (fallback
`../../python-settings-config/references/env-example.md`). The root file does
not replace the service file: it contains the user-configured Compose inputs,
including service values passed through Compose, and stack-only values.

For a single service, the root `.env.example` serves both roles: it follows
that service-file contract and also lists any Compose input the user must set.
Do not duplicate it under another directory.

For example, in a workspace with an API service whose launcher command binds
container port `8080` (ports are never YAML keys; see `python-settings-config`,
Ownership):

```dotenv
# <repo-root>/.env.example: values to configure for the local stack
API_ENVIRONMENT_NAME=local
API_OPENAI_API_KEY=replace-me
API_RESPONSE_MODEL_ID=replace-me
```

```yaml
# compose.yaml: explicit mapping and a safe local default
services:
  api:
    ports:
      - "${API_HOST_PORT:-8080}:8080"
    environment:
      ENVIRONMENT_NAME: ${API_ENVIRONMENT_NAME:?set API_ENVIRONMENT_NAME}
      OPENAI_API_KEY: ${API_OPENAI_API_KEY:?set API_OPENAI_API_KEY}
      RESPONSE_MODEL_ID: ${API_RESPONSE_MODEL_ID:?set API_RESPONSE_MODEL_ID}
```

`services/api/.env.example` lists `ENVIRONMENT_NAME`, `RESPONSE_MODEL_ID`, and
`OPENAI_API_KEY` under REQUIRED, in the env-example.md layout.

`API_HOST_PORT` is omitted from the root example because the local stack has a
safe default. Add it there only when choosing a different host port is part of
the intended setup. Service settings that Compose does not pass through still
belong in the service example when they are required at runtime or supported
overrides.

## Explicit per-service mapping

Use interpolation from the root `.env`, but declare exactly which values enter
each container:

```yaml
services:
  api:
    build:
      context: .
      dockerfile: services/api/Dockerfile
    environment:
      ENVIRONMENT_NAME: ${API_ENVIRONMENT_NAME:?set API_ENVIRONMENT_NAME}
      DATABASE_URL: ${API_DATABASE_URL:?set API_DATABASE_URL}
      OPENAI_API_KEY: ${API_OPENAI_API_KEY:?set API_OPENAI_API_KEY}
    ports:
      - "${API_HOST_PORT:-8080}:8080"

  worker:
    build:
      context: .
      dockerfile: services/worker/Dockerfile
    environment:
      ENVIRONMENT_NAME: ${WORKER_ENVIRONMENT_NAME:?set WORKER_ENVIRONMENT_NAME}
      DATABASE_URL: ${WORKER_DATABASE_URL:?set WORKER_DATABASE_URL}
      QUEUE_URL: ${WORKER_QUEUE_URL:?set WORKER_QUEUE_URL}
```

Prefix root variables when services may legitimately need different values,
then map them to the stable variable name expected by each process. Share an
unprefixed root variable only when it intentionally represents one stack-wide
value. Use `${VAR:?message}` for required inputs and `${VAR:-value}` only for
safe local defaults.

Do not use `env_file: .env` as a shortcut for application services. It exposes
every root variable and secret to every container, hides the service dependency
contract, and creates accidental coupling. Explicit mapping produces container
process environment variables, which take precedence over pydantic-settings
dotenv, YAML, and class defaults.

The Compose project `.env` supplies `${...}` interpolation; its presence alone
does not expose every value inside a container. Shell variables and an explicit
Compose environment file can change interpolation precedence, so verify the
resolved model rather than reasoning from filenames alone.

## Secrets and validation

Runtime secrets may enter local containers through explicit `environment:`
mapping, but never through Dockerfile `ARG` or build-time `ENV`. Production uses
an orchestrator or secret provider rather than a committed dotenv file.

Validate the resolved model and the running stack with the commands and checks
in [verification.md](verification.md#compose-stack).
