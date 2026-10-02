# Resource Identity and Runtime Attribution

Resource attributes answer two different questions: *which logical service is
this?* and *which running copy produced this telemetry?* Keep those identities
separate so replicas aggregate as one service without becoming
indistinguishable during an incident.

## Contents

- [Identity contract](#identity-contract)
- [Ownership](#one-owner-per-attribute)
- [Configuration modes](#configuration-modes)
- [Version policy](#version-policy)
- [Runtime routing](#route-runtime-identity)
- [Repository mapping](#record-the-repositorys-concrete-mapping)
- [Failure modes](#failure-modes)

---

## Identity contract

Set these on the `Resource`, not repeatedly on individual spans:

| Attribute | Meaning | Example |
| --- | --- | --- |
| `service.namespace` | Stable system or application grouping | `order-management` |
| `service.name` | Logical component; identical across its replicas | `orders-api`, `orders-worker` |
| `service.instance.id` | One running service instance | platform identity or process UUID |
| `deployment.environment.name` | Deployment tier | `development`, `test`, `staging`, `production`, custom `uat` |
| `service.version` | Immutable software version/build | full Git commit SHA |

The triplet `service.namespace`, `service.name`, `service.instance.id` must be
globally unique. `deployment.environment.name` is **not** part of that
uniqueness rule. A value such as `worker-1` therefore collides when reused by
another developer, environment, or deployment.

Use `service.version` for the code artifact, not for a rollout name. When a
specific rollout also needs correlation, add `deployment.id`; it does not
replace `service.version`.

The normative definitions live in the OpenTelemetry
[service](https://opentelemetry.io/docs/specs/semconv/resource/service/) and
[deployment](https://opentelemetry.io/docs/specs/semconv/registry/attributes/deployment/)
resource conventions.

---

## One owner per attribute

Assign ownership before writing configuration:

| Attribute group | Preferred owner |
| --- | --- |
| Namespace, service name, environment | Deployment manifest or service configuration |
| Service version | CI/build pipeline |
| Service instance ID | Runtime platform adapter or process startup |
| `k8s.*`, `container.*`, `aws.ecs.*`, `cloud.*` | Resource detector or unambiguous Collector enrichment |

The application-provided service identity wins. The mechanism differs by
component and the two are not interchangeable:

| Component | Setting that preserves the application's value |
| --- | --- |
| Collector `resource` / `attributes` processor | `action: insert` (`upsert` overwrites) |
| Collector `resourcedetection` processor | `override: false` |
| SDK resource detectors | merge the detected resource *under* the configured one |

Getting this wrong is silent: a service correctly reporting `uat` is relabelled
`production` by the gateway, and nothing on the application side can see it.

A gateway Collector must not derive `service.instance.id` from its own pod,
container, task, hostname, or IP. Those values describe the Collector, not the
application that sent the telemetry. A Collector may set the attribute only
when it can associate the telemetry with exactly one originating service
instance — for example, a scraping receiver with a known target or a
per-workload sidecar.

Keep the native platform identity too. `service.instance.id` identifies the
service instance; `k8s.pod.uid`, `container.id`, and `aws.ecs.task.arn` explain
where it ran. Equal values are acceptable, but the attributes have different
semantic roles.

---

## Configuration modes

Pick one configuration owner for the service attributes: the provider owner
chosen in `sdk_bootstrap.md`.

**Code-based SDK setup** — the default in this skill:

```bash
OTEL_SERVICE_NAME=orders-worker
SERVICE_NAMESPACE=order-management
SERVICE_VERSION=<full-git-sha>
SERVICE_INSTANCE_ID=<runtime-supplied-id>
ENVIRONMENT=development
```

The typed settings object supplies these to `Resource.create()`. Do not also
set the same keys in `OTEL_RESOURCE_ATTRIBUTES`.

**Zero-code setup** — the launcher owns the SDK:

```bash
OTEL_SERVICE_NAME=orders-worker
OTEL_RESOURCE_ATTRIBUTES="service.namespace=order-management,deployment.environment.name=development,service.version=<full-git-sha>,service.instance.id=<runtime-supplied-id>"
```

Do not add a second resource builder in this mode (one provider owner:
`sdk_bootstrap.md`). Static deployment files may contain the static attributes, but the
runtime ID placeholder must be resolved by the platform or startup wrapper; a
literal `<runtime-supplied-id>` is invalid.

---

## Version policy

Prefer an immutable version that is known before the process starts. A full
Git commit SHA is reproducible, works across API and worker images built from
the same revision, and avoids collisions between abbreviated SHAs.

Inject it during build or deployment:

```dockerfile
ARG GIT_SHA
RUN test -n "${GIT_SHA}"
ENV SERVICE_VERSION=${GIT_SHA}
```

The build must fail when `GIT_SHA` is empty. Do not run `git rev-parse` inside
the application: production images often have no `.git` directory, and a
runtime checkout is not the artifact that CI built.

If an image combines code from more than one repository, use the release or
image build identifier that actually identifies that artifact instead of one
arbitrary repository SHA.

---

## Route runtime identity

Keep this core file loaded for every service, then load only the runtime files
selected by `SKILL.md`: Kubernetes, Docker Compose, ECS, Lambda, or the generic
process fallback. Multi-process identity is an independent condition and may
be combined with any container platform.

Do not copy a platform example into the common SDK bootstrap. Resolve runtime
identity in the selected startup adapter before building the immutable
`Resource`.

---

## Record the repository's concrete mapping

Write the actual values down once, in the repository — its agent-instruction file, deployment manifest, or a `local/` reference next to this skill —
in this shape:

```text
service.namespace = <one stable grouping for the whole system>
service.name      = <one per deployable component>
service.version   = full Git commit SHA supplied by CI/build
```

Do **not** put a concrete namespace in this file. It is loaded for every
service, and a namespace sitting in context is a namespace that gets adopted by
an unrelated one.

Sibling components may share a `service.version` when they were built from the
same commit; they remain distinct because `service.name` differs. Each replica
receives its instance ID from Kubernetes, Docker, or ECS using the rules above.

Repository-specific mappings live in `references/local/`, loaded only when the
target repository matches. None are defined yet; add one there and route it
from `SKILL.md` when a repository needs a concrete mapping.

---

## Failure modes

| Symptom | Likely cause |
| --- | --- |
| IDs collide across environments | The environment was incorrectly assumed to be part of service-instance uniqueness |
| All telemetry has the Collector's pod/task ID | A gateway detector enriched from its own runtime |
| Version is `unknown` in production | CI did not inject the Git SHA into the image or deployment |
| One rollout shows several versions unexpectedly | Mutable tags or inconsistent build inputs were used |
