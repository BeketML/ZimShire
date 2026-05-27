from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.modules.users import service
from app.modules.users.schemas import UserCreate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    name = body.name if body else None
    surname = body.surname if body else None
    user = await service.create_user(db, name=name, surname=surname)
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db)) -> UserResponse:
    try:
        user = await service.get_user(db, user_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="user not found")
    return UserResponse.model_validate(user)
