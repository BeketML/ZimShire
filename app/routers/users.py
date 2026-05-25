from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.repositories import user_repo
from app.schemas.users import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(db: AsyncSession = Depends(get_db)) -> UserResponse:
    user = await user_repo.create_user(db)
    await db.commit()
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db)) -> UserResponse:
    user = await user_repo.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserResponse.model_validate(user)
