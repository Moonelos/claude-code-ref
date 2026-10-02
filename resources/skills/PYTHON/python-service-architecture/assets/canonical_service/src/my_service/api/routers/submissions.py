from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from my_service.api.dependencies import RuntimeDep, WriteIdentity
from my_service.application.submit import submit_investigation
from my_service.domain.submissions import SelectionRequest
from my_service.ports.submissions import Receipt

router = APIRouter()


class SubmissionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: str
    max_records: int | None = None

    def to_request(self) -> SelectionRequest:
        return SelectionRequest(record_type=self.record_type, max_records=self.max_records)


class SubmissionOut(BaseModel):
    request_id: str
    replayed: bool

    @classmethod
    def from_receipt(cls, receipt: Receipt) -> "SubmissionOut":
        return cls(request_id=str(receipt.request_id), replayed=receipt.replayed)


@router.post("/submissions", status_code=status.HTTP_202_ACCEPTED)
async def submit(
    body: SubmissionBody, runtime: RuntimeDep, identity: WriteIdentity
) -> SubmissionOut:
    receipt = await submit_investigation(
        store=runtime.submission_store,
        policy=runtime.submission_policy,
        client_id=identity.client_id,
        request=body.to_request(),
    )
    return SubmissionOut.from_receipt(receipt)
