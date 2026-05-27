from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.modules.chats import service
from app.modules.chats.schemas import ChatCreate, ChatResponse

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(body: ChatCreate, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    try:
        chat = await service.create_chat(
            db,
            user_id=body.user_id,
            chat_title=body.chat_title,
            model=body.model,
            provider=body.provider,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ChatResponse.model_validate(chat)


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(chat_id: UUID, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    try:
        chat = await service.get_chat(db, chat_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="chat not found")
    return ChatResponse.model_validate(chat)
