from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    name: str | None = None
    surname: str | None = None


class UserResponse(BaseModel):
    user_id: UUID
    name: str | None = None
    surname: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
