"""Rule anchors every finding cites, and the vocabularies the checks match."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

Severity = Literal["VIOLATION", "REVIEW"]
MethodKey = tuple[str, tuple[str, ...]]

ARCH = "python-service-architecture/references"
CONV = "python-code-conventions"
R_DIRECTION = f"{ARCH}/boundaries.md#The core rule"
R_CONFIG = f"{ARCH}/boundaries.md#config/"
R_TELEMETRY = f"{ARCH}/boundaries.md#observability/"
R_PORTS = f"{ARCH}/boundaries.md#When a port earns its cost"
R_APPLICATION_PORTS = f"{ARCH}/boundaries.md#Application ports"
R_TOOL_ACTION = f"{ARCH}/ai.md#When a tool calls an action"
R_GENAI_OWNERSHIP = f"{ARCH}/ai.md#Ownership inside genai/<task>/"
R_FLAT = f"{ARCH}/boundaries.md#Flat-first growth across boundaries"
R_OWNERSHIP = f"{ARCH}/boundaries.md#Errors and constants follow ownership"
R_ADAPTERS = f"{ARCH}/boundaries.md#Adapters and their placement"
R_DB_LAYOUT = "python-sqlmodel-alembic/references/repo-layout.md#The db/ package"
R_REPOSITORIES = f"{ARCH}/boundaries.md#Repositories apply decisions"
R_NONDETERMINISM = f"{ARCH}/boundaries.md#Nondeterminism"
R_CONSTRUCTOR_CONTRACTS = f"{ARCH}/boundaries.md#Constructor contracts"
R_BOOTSTRAP = f"{ARCH}/boundaries.md#bootstrap/"
R_WORKERS = f"{ARCH}/api-and-workers.md#Long-running worker"
R_BROKER = f"{ARCH}/api-and-workers.md#SQS, Kafka, or another broker"
R_SHARED = f"{ARCH}/shared-libraries.md"
R_CONTRACTS = "python-repository-setup/references/pre-commit.md#Architecture contracts"
R_CLASSIFICATION = f"{ARCH}/errors.md#Classification bases"
R_PUBLIC_ERRORS = f"{ARCH}/api-and-workers.md#Public error mapping"
R_IMPORTS = f"{CONV}#Imports and package markers"
R_ASSERT = f"{CONV}#No assert in production"
R_WRAPPERS = f"{CONV}#Constructors and wrappers"
R_ESCAPE = f"{CONV}#Type escape hatches"
R_ONE_OWNER = f"{CONV}#One owner per semantics"
R_MAGIC = f"{CONV}#Magic values and constants"
R_LIB_SHAPE = f"{ARCH}/shared-libraries.md#A library is not a smaller service"
R_LIB_KINDS = f"{ARCH}/shared-libraries.md#Library kinds and importers"
R_LIB_RULES = f"{ARCH}/shared-libraries.md#Library rules"
R_LIB_FLAT = f"{ARCH}/shared-libraries.md#Flat first"
R_LIB_API = f"{ARCH}/shared-libraries.md#Public API and compatibility"
R_LIB_EXCEPTION = f"{ARCH}/shared-libraries.md#Database-runtime exception"
R_LIB_CONFIG = f"{ARCH}/shared-libraries.md#Configuration mechanics"
R_LIB_ENFORCEMENT = f"{ARCH}/shared-libraries.md#Enforcement"

LIBRARY_KINDS = (
    "contract",
    "client",
    "persistence",
    "configuration",
    "observability",
    "genai",
    "testing",
)
GENERIC_LIBRARY_NAMES = {"base", "common", "core", "helpers", "shared", "utils"}
SPECULATIVE_LIBRARY_PACKAGES = {
    "factories",
    "implementations",
    "interfaces",
    "plugins",
    "schemas",
    "types",
}
ENVIRONMENT_READS = {"os.environ", "os.getenv", "os.environb"}
LOGGING_CONFIG_CALLS = {"basicConfig", "dictConfig", "fileConfig"}
LANGCHAIN_ROOTS = ("langchain", "langgraph")
# Model-call keywords that tune behavior or cost; a literal value belongs in settings.
MODEL_TUNING_KEYWORDS = {
    "dimensions",
    "max_output_tokens",
    "max_tokens",
    "temperature",
    "top_k",
    "top_p",
}
MODEL_ID_KEYWORDS = {"model", "model_id", "model_name"}
MODEL_FACTORIES = {"init_chat_model", "init_embeddings"}
SESSION_MODULES = (
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm.session",
    "sqlmodel.ext.asyncio",
)
SESSION_NAMES = {
    "AsyncSession",
    "Session",
    "async_sessionmaker",
    "create_async_engine",
    "create_engine",
    "sessionmaker",
}

INTERNAL_FORBIDDEN: dict[str, set[str]] = {
    "domain": {
        "adapters",
        "api",
        "application",
        "bootstrap",
        "config",
        "db",
        "genai",
        "observability",
        "ports",
        "workers",
    },
    "ports": {
        "adapters",
        "api",
        "application",
        "bootstrap",
        "config",
        "db",
        "genai",
        "observability",
        "workers",
    },
    # application may import the service's own observability helpers (not OTel types).
    "application": {"adapters", "api", "bootstrap", "config", "db", "genai", "workers"},
    "db": {"adapters", "api", "application", "bootstrap", "genai", "workers"},
    "genai": {"adapters", "api", "bootstrap", "db", "workers"},
    "api": {"adapters", "bootstrap", "config", "db", "genai", "workers"},
    # workers/ is the non-HTTP entry-point boundary: loops and consumers.
    "workers": {"adapters", "api", "bootstrap", "config", "db", "genai"},
    "core": {
        "domain",
        "ports",
        "application",
        "api",
        "adapters",
        "db",
        "genai",
        "bootstrap",
        "config",
        "observability",
        "workers",
    },
    # adapters may import the inbound contract a worker declares (workers/); they reach
    # db/ and genai/ only through a port.
    "adapters": {"api", "application", "bootstrap", "db", "genai"},
    "observability": {"api", "application", "bootstrap", "workers"},
}
# The per-service contracts in python-repository-setup (pre-commit.md, "Architecture
# contracts"): (invariant, source boundaries, boundaries they must not import).
REQUIRED_CONTRACTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "application uses only admitted inner dependencies",
        ("application",),
        ("adapters", "api", "bootstrap", "config", "db", "genai", "workers"),
    ),
    (
        "domain and ports are pure",
        ("domain", "ports"),
        (
            "adapters",
            "api",
            "application",
            "bootstrap",
            "config",
            "db",
            "genai",
            "observability",
            "workers",
        ),
    ),
    (
        "entry points do not import concrete integrations",
        ("api", "workers"),
        ("adapters", "config", "db", "genai"),
    ),
    (
        "only entry points import bootstrap",
        ("adapters", "api", "db", "genai", "workers"),
        ("bootstrap",),
    ),
)
PURE_BOUNDARIES = {"application", "core", "domain", "ports"}
# Pure boundaries may import only the stdlib, these packages, and the service itself.
# Extend per repository with --allow-external.
PURE_ALLOWED_EXTERNAL = {
    "__future__",
    "annotated_types",
    "pydantic",
    "typing_extensions",
}
# Application actions may log a recorded fallback (errors.md, broad except
# shape 5); domain/ and ports/ never log.
APPLICATION_ALLOWED_EXTERNAL = {"structlog"}
GENERIC_COLLECTIONS = {
    Path("errors.py"),
    Path("constants.py"),
    Path("core/errors.py"),
    Path("core/constants.py"),
    Path("common/errors.py"),
    Path("common/constants.py"),
}
FRAMEWORK_PORT_NAMES = {
    "adelete_thread",
    "ainvoke",
    "astream",
    "checkpoint_ns",
    "configurable",
    "durability",
    "recursion_limit",
    "stream_mode",
}
TRANSPORT_COORDINATE_FIELDS = {
    "ack_token",
    "consumer_group",
    "delivery_attempt",
    "offset",
    "partition",
    "receipt_handle",
    "stream_seq",
    "trace_carrier",
    "traceparent",
}
NONDETERMINISTIC_CALLS = {
    "date.today",
    "datetime.now",
    "datetime.today",
    "datetime.utcnow",
    "datetime.datetime.now",
    "datetime.datetime.utcnow",
    "time.time",
    "time.monotonic",
    "uuid.uuid4",
    "uuid4",
}
IO_CALL_ROOTS = {
    "boto3",
    "httpx",
    "open",
    "os",
    "requests",
    "socket",
    "subprocess",
    "urllib",
}
IO_METHODS = {"read_bytes", "read_text", "write_bytes", "write_text"}
TRANSPORT_EXCEPTION_FIELDS = {"public_message", "retryable", "status_code"}
SQL_HANDLE_HINTS = ("conn", "cursor", "session")
# runtime() stays one flat function, however long, until it builds ~10 collaborators.
BOOTSTRAP_COLLABORATORS = 10
# Calls that construct a collaborator: a class (capitalized) or one of these factories.
BOOTSTRAP_FACTORY_PREFIXES = ("build_", "create_", "init_", "open_")
REPOSITORY_METHOD_LINES = 40
SHARED_LITERAL_MODULES = 3
# Standard names nobody owns; repeating them is not a missing owner.
STANDARD_TOKENS = {"utf-8", "utf-16", "us-ascii", "iso-8859-1"}
IDENTIFIER_LITERAL = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)+$")
LIFECYCLE_NAMES = {"aclose", "close", "dispose", "shutdown"}
STATE_METHODS = {
    "add",
    "append",
    "clear",
    "discard",
    "extend",
    "pop",
    "remove",
    "update",
}
IMPLEMENTATION_OWNERS = {"adapters", "db", "genai"}
# Prescribed in every service (errors.md, "Classification bases"), so identical
# copies across members are expected, not an extraction candidate.
CLASSIFICATION_BASES = "ports/errors.py"
# A member with none of these is not a service (a migration runner keeps only its
# entry point and db/ helpers), so the service contracts do not apply to it.
APPLICATION_BOUNDARIES = ("adapters", "api", "application", "domain", "genai", "ports", "workers")
# Standard shared db/ root modules (repo-layout.md, "The db/ package"); any other root
# entry is a shared helper (imported by db/ capabilities, not by bootstrap) or a
# capability named after the contract it implements.
DB_SHARED_ROOT = {
    "alembic",
    "engine",
    "models",
    "queries",
    "readiness",
    "repositories",
    "retention",
    "schema",
    "tables",
    "transactions",
}
# Protocol name words that say what kind of contract it is, not which one.
DB_ROLE_WORDS = {"port", "probe", "protocol", "service", "store"}
SKIPPED_DIRS = {
    ".git",
    ".mypy_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
