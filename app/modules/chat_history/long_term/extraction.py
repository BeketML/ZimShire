"""LLM-based memory extraction from a completed turn."""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.prompts import MEMORY_EXTRACTION_PROMPT
from app.modules.chat_history.long_term.schemas import MemoryExtraction, UserProfile
from app.modules.chat_history.short_term.schemas import TurnPair
from app.services.llm import get_memory_model

logger = logging.getLogger(__name__)


async def extract_memory_from_turn(
    *,
    user_query: str,
    draft_answer: str,
    recent_turns: list[TurnPair],
    current_profile: UserProfile,
) -> MemoryExtraction:
    turns_text = "\n".join(
        f"User: {p.human}\nAssistant: {p.assistant}" for p in recent_turns
    ) or "(none)"

    prompt = (
        f"USER QUERY:\n{user_query}\n\n"
        f"DRAFT ANSWER:\n{draft_answer}\n\n"
        f"RECENT TURNS:\n{turns_text}\n\n"
        f"CURRENT PROFILE:\n{current_profile.model_dump_json(indent=2)}"
    )

    try:
        llm = get_memory_model()
        resp = await llm.ainvoke(
            [SystemMessage(content=MEMORY_EXTRACTION_PROMPT), HumanMessage(content=prompt)]
        )
        raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return MemoryExtraction(**data)
    except Exception as exc:
        logger.warning("memory extraction failed (%s) — skipping update", exc)
        return MemoryExtraction(should_update=False)
