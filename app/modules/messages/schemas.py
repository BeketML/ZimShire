from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    user_id: UUID
    chat_id: UUID
    query: str = Field(min_length=1, max_length=2000)


class SourceItem(BaseModel):
    letter_year: int | None = None
    passage: str
    similarity_score: float
    qdrant_point_id: str


class MessageItem(BaseModel):
    message_id: UUID
    role: Literal["human", "assistant"]
    content: str
    grounded: bool | None = None
    sources: list[SourceItem] = []
    langfuse_trace_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HistoryResponse(BaseModel):
    chat_id: UUID
    messages: list[MessageItem]
