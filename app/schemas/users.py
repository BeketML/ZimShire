from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    """Empty body — server allocates user_id and created_at."""


class UserResponse(BaseModel):
    user_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
