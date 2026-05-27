"""FastAPI dependency factories for service injection."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.modules.chats.service import create_chat as _create_chat
from app.modules.users.service import create_user as _create_user


# Re-export get_db for convenience
__all__ = ["get_db"]
