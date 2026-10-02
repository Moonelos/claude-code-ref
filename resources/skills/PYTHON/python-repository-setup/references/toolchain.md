# Toolchain Versions

Choose and align the Python and uv pins before scaffolding, in either
repository mode. Read this before copying a template, changing a pin, or
reviewing version drift between local, CI, and Docker.

## Choose the versions

Before scaffolding, verify the current stable patch release for the chosen
Python minor and the current stable uv release from official sources. Propose
the defaults, then ask one concise question: “I will use Python X.Y.Z and uv
A.B.C; do you want different versions?” Skip the question when the user has
already supplied both versions. When nobody can be asked (a delegated agent, a
non-interactive run), use the installed uv and Python if they are stable
releases of the intended minor, otherwise the template's pins, and state the
chosen pins as an assumption in the handoff. After copying the bundled asset
to a writable location and before using it, update its single toolchain
manifest and every derived pin with
`scripts/update_toolchain.py --python X.Y.Z --uv A.B.C`; do not hand-edit a
subset of the copies. Run that script on a writable copy of the template,
never on the installed skill source. When constructing a service without
copying the template, set all new toolchain pins coherently and run the
equivalent pin checks in that service; the template update script does not
apply to files it does not own.

## Version contract

The bundled template snapshot keeps these version surfaces aligned;
`.python-version` contains exactly the Python patch:

```text
.python-version                         3.13.15
member requires-python                  >=3.13,<3.14
Docker ARG PYTHON_VERSION               3.13.15
root [tool.uv] required-version         ==0.12.7
Docker ARG UV_VERSION                   0.12.7
```

The exact Python patch belongs in `.python-version`, Docker, and CI. The member
metadata uses a compatible minor range because it describes package
compatibility rather than selecting an interpreter. Put the same range on
every service and library; a virtual workspace root has no `[project]` table.

Apply the pins in this order:

1. Put `requires-python = ">=3.13,<3.14"` in every service and library
   `pyproject.toml`.
2. Run `uv python pin 3.13.15` at the workspace root to create
   `.python-version`.
3. Read that exact value into each Dockerfile's `ARG PYTHON_VERSION` default
   and keep the in-build equality check.
4. Put `required-version = "==0.12.7"` in the root `[tool.uv]` table and use
   the same exact uv version in Docker and CI.

Treat these as a coherent set. If the user changes the Python minor, update
all member `requires-python` ranges, Ruff's `target-version`,
`.python-version`, the Docker `PYTHON_VERSION`, and CI. If only the patch
changes within the minor, update `.python-version`, Docker, and CI. If uv
changes, update root `required-version`, Docker, and CI.

## Local, CI, and Docker

Do not add mise. Locally, let uv read `.python-version`; run
`uv python install` when the interpreter is absent. Pin uv in the root so the
wrong local version fails immediately.

In CI, install the exact root `required-version`, run `uv python install`, and
then use the root lockfile. `required-version` enforces the uv pin but does not
install the matching uv binary by itself.

Docker evaluates `FROM` before it can `COPY` `.python-version`. Therefore it
cannot dynamically derive a pre-`FROM` `ARG PYTHON_VERSION` from that file in
the build context. Repeat the literal exact version and fail the build if it
differs from `.python-version`, with this early builder check:

```dockerfile
ARG PYTHON_VERSION
COPY .python-version ./
RUN test "$(tr -d '\r\n' < .python-version)" = "${PYTHON_VERSION}"
```

When invoking Docker from a wrapper or CI shell, deriving the build argument
from the file is also valid:

```bash
docker build \
  --build-arg PYTHON_VERSION="$(tr -d '\r\n' < .python-version)" \
  -f services/api/Dockerfile .
```

Keep the Dockerfile default and the in-build equality check even when the
wrapper supplies the argument.

## Final ownership

| Environment | Python | uv |
| --- | --- | --- |
| Local project | exact `.python-version` | exact root `required-version` |
| CI | exact `.python-version` | exact root `required-version` |
| Docker builder | exact `PYTHON_VERSION` | exact `UV_VERSION` |
| Docker runtime | exact `PYTHON_VERSION` | absent |

The commands that verify this contract are in
[verification.md](verification.md#toolchain).
