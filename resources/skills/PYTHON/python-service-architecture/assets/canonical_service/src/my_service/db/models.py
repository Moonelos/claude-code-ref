from uuid import UUID

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class SubmissionRow(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("client_id", "payload_hash", name="uq_submission_payload"),)

    request_id: UUID = Field(primary_key=True)
    client_id: str
    max_records: int
    record_type: str
    payload_hash: str
