from my_service.domain.submissions import (
    SelectionRequest,
    SubmissionPolicy,
    normalize,
    payload_hash,
)
from my_service.ports.submissions import Receipt, SubmissionStore


async def submit_investigation(
    *, store: SubmissionStore, policy: SubmissionPolicy, client_id: str, request: SelectionRequest
) -> Receipt:
    selection = normalize(request, policy)
    return await store.submit(
        client_id=client_id, selection=selection, payload_hash=payload_hash(selection)
    )
