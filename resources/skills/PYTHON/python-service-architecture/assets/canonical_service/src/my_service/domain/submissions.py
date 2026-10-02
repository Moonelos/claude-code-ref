import hashlib
from dataclasses import dataclass


class InvalidSelectionError(Exception):
    """The selection violates submission policy."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectionRequest:
    record_type: str
    max_records: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Selection:
    """A normalized selection; only `normalize` builds one from a request."""

    record_type: str
    max_records: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmissionPolicy:
    default_records: int
    max_records: int


def normalize(request: SelectionRequest, policy: SubmissionPolicy) -> Selection:
    max_records = policy.default_records if request.max_records is None else request.max_records
    if max_records > policy.max_records:
        raise InvalidSelectionError("submission_limit")
    return Selection(record_type=request.record_type.strip().lower(), max_records=max_records)


def payload_hash(selection: Selection) -> str:
    return hashlib.sha256(repr(selection).encode()).hexdigest()
