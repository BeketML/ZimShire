from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatCreate(BaseModel):
    user_id: UUID
    chat_title: str | None = Field(default=None, max_length=200)
    model: str | None = None
    provider: str | None = None


class ChatResponse(BaseModel):
    chat_id: UUID
    user_id: UUID
    chat_title: str | None
    model: str | None
    provider: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
