from pydantic import BaseModel, Field


class SqlAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    max_rows: int | None = Field(default=None, ge=1, le=1000)


class SqlAskResponse(BaseModel):
    question: str
    answer: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    row_count: int = 0
    status: str


class SqlValidateRequest(BaseModel):
    sql: str


class SqlValidateResponse(BaseModel):
    valid: bool
    reason: str | None = None
