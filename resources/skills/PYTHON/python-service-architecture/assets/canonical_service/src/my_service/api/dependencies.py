from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, Request, Security

from my_service.domain.submissions import SubmissionPolicy
from my_service.ports.submissions import SubmissionStore


class ApiRuntime(Protocol):
    """What routes read from the runtime; bootstrap's `Runtime` satisfies it."""

    @property
    def submission_store(self) -> SubmissionStore: ...
    @property
    def submission_policy(self) -> SubmissionPolicy: ...


def get_runtime(request: Request) -> ApiRuntime:
    runtime: ApiRuntime = request.app.state.runtime
    return runtime


RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


class AuthenticationRequiredError(Exception):
    """The request carries no verified client identity."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientIdentity:
    client_id: str


def get_write_identity(request: Request) -> ClientIdentity:
    """The client the authentication middleware verified; never a field of the body."""
    identity = request.scope.get("user")
    if not isinstance(identity, ClientIdentity):
        raise AuthenticationRequiredError
    return identity


WriteIdentity = Annotated[ClientIdentity, Security(get_write_identity)]
