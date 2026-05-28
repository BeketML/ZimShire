from fastapi import APIRouter

from app.modules.chat_history.router import router as chat_history_router
from app.modules.chats.router import router as chats_router
from app.modules.inspect.router import router as inspect_router
from app.modules.messages.router import router as messages_router
from app.modules.users.router import router as users_router

router = APIRouter()
router.include_router(users_router)
router.include_router(chats_router)
router.include_router(messages_router)
router.include_router(chat_history_router)
router.include_router(inspect_router)
