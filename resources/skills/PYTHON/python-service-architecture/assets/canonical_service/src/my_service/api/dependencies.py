from typing import Annotated, Protocol

from fastapi import Depends, Request

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
