from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.repositories import chat_repo, user_repo
from app.schemas.chats import ChatCreate, ChatResponse

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(body: ChatCreate, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    user = await user_repo.get_user(db, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_id not found")
    chat = await chat_repo.create_chat(
        db,
        user_id=body.user_id,
        chat_title=body.chat_title,
        model=body.model,
        provider=body.provider,
    )
    await db.commit()
    return ChatResponse.model_validate(chat)


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(chat_id: UUID, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    chat = await chat_repo.get_chat(db, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return ChatResponse.model_validate(chat)
