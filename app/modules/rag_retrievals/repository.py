from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RagRetrieval

QDRANT_COLLECTION = "buffett_letters"


async def bulk_create(
    session: AsyncSession,
    *,
    message_id: UUID,
    chunks: list[dict],
    used_point_ids: set[str] | None = None,
) -> int:
    if not chunks:
        return 0
    used_point_ids = used_point_ids or set()
    rows = []
    for rank, chunk in enumerate(chunks):
        point_id = str(chunk.get("qdrant_point_id", ""))
        rows.append(
            {
                "message_id": message_id,
                "qdrant_collection": QDRANT_COLLECTION,
                "qdrant_point_id": point_id,
                "rank": rank,
                "letter_year": chunk.get("letter_year"),
                "passage_snippet": (chunk.get("passage_snippet") or "")[:500],
                "similarity_score": chunk.get("similarity_score"),
                "used_in_response": point_id in used_point_ids,
            }
        )
    stmt = pg_insert(RagRetrieval).values(rows)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["message_id", "qdrant_collection", "qdrant_point_id"]
    )
    await session.execute(stmt)
    return len(rows)


async def list_for_chat(
    session: AsyncSession, chat_id: UUID, *, limit: int = 200
) -> list[RagRetrieval]:
    from app.models.models import Message  # local import to avoid circularity

    rows = await session.scalars(
        select(RagRetrieval)
        .join(Message, RagRetrieval.message_id == Message.message_id)
        .where(Message.chat_id == chat_id)
        .order_by(RagRetrieval.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def list_for_message(session: AsyncSession, message_id: UUID) -> list[RagRetrieval]:
    rows = await session.scalars(
        select(RagRetrieval)
        .where(RagRetrieval.message_id == message_id)
        .order_by(RagRetrieval.rank)
    )
    return list(rows)
