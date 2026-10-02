from pydantic import BaseModel, ConfigDict


class Document(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    document_id: str
    title: str
    version: int
