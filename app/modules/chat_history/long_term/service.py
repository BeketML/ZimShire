"""Long-term memory service — reads/writes user profile in AsyncPostgresStore."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from langgraph.store.base import BaseStore

from app.modules.chat_history.long_term.extraction import extract_memory_from_turn
from app.modules.chat_history.long_term.schemas import MemoryExtraction, UserProfile
from app.modules.chat_history.short_term.schemas import TurnPair

logger = logging.getLogger(__name__)


class LongTermMemoryService:
    def __init__(self, store: BaseStore) -> None:
        self._store = store

    async def load_profile(self, user_id: str, query: str = "") -> UserProfile:
        profile = UserProfile()
        try:
            # Interests: vector-indexed on "company"/"interest" fields — asearch works
            namespace = ("users", user_id, "interests")
            all_items = await self._store.asearch(namespace, query=query or "company", limit=100)
            for it in all_items:
                val = it.value or {}
                company = val.get("company") or val.get("ticker") or ""
                interest = val.get("interest") or ""
                if company and company not in profile.tracked_companies:
                    profile.tracked_companies.append(company)
                if interest and interest not in profile.research_interests:
                    profile.research_interests.append(interest)

            # Profile meta: NOT in the vector index (fields=["interest","company"] only)
            # Use aget with exact key instead of asearch
            meta_item = await self._store.aget(("users", user_id, "profile"), "meta")
            if meta_item:
                val = meta_item.value or {}
                profile.name = val.get("name") or None
                profile.surname = val.get("surname") or None
                profile.preferences = val.get("preferences") or {}
                profile.explicit_memories = val.get("explicit_memories") or []
                profile.topics = val.get("topics") or []
        except Exception as exc:
            logger.warning("load_profile failed for user %s: %s", user_id, exc)
        return profile

    async def load_profile_with_raw(self, user_id: str, query: str = "") -> tuple[UserProfile, list[dict]]:
        """Load profile + ALL raw store items (bypasses vector search via direct SQL)."""
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text

        profile = await self.load_profile(user_id, query)
        raw: list[dict] = []
        try:
            prefix_pattern = f"users.{user_id}.%"
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text("SELECT prefix, key, value FROM store WHERE prefix LIKE :p ORDER BY prefix, key"),
                    {"p": prefix_pattern},
                )
                for row in result.fetchall():
                    ns_suffix = row[0].split(".")[-1]
                    raw.append({
                        "namespace": f"users/{user_id}/{ns_suffix}",
                        "key": row[1],
                        "value": row[2] if isinstance(row[2], dict) else {},
                    })
        except Exception as exc:
            logger.warning("load_profile_with_raw SQL failed for user %s: %s", user_id, exc)
        return profile, raw

    async def init_user(
        self,
        user_id: str,
        *,
        name: str | None = None,
        surname: str | None = None,
    ) -> None:
        try:
            await self._store.aput(
                ("users", user_id, "profile"),
                key="meta",
                value={
                    "name": name,
                    "surname": surname,
                    "preferences": {},
                    "explicit_memories": [],
                    "topics": [],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("init_user failed for %s: %s", user_id, exc)

    async def persist_from_turn(
        self,
        *,
        user_id: str,
        user_query: str,
        draft_answer: str,
        recent_turns: list[TurnPair],
        current_profile: UserProfile,
        market_tickers: list[str] | None = None,
    ) -> None:
        # Heuristic fallback: persist tickers from market context immediately
        if market_tickers:
            for ticker in market_tickers:
                try:
                    await self._store.aput(
                        ("users", user_id, "interests"),
                        key=ticker,
                        value={
                            "company": ticker,
                            "interest": user_query,
                            "last_seen": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                except Exception as exc:
                    logger.warning("store.aput ticker %s failed: %s", ticker, exc)

        # LLM extraction (fire-and-forget — caller doesn't await merge result)
        extraction = await extract_memory_from_turn(
            user_query=user_query,
            draft_answer=draft_answer,
            recent_turns=recent_turns,
            current_profile=current_profile,
        )
        if extraction.should_update:
            await self.merge_extraction(user_id=user_id, extraction=extraction)

    async def merge_extraction(self, *, user_id: str, extraction: MemoryExtraction) -> None:
        if not extraction.should_update:
            return

        # Persist tickers
        now = datetime.now(timezone.utc).isoformat()
        for ticker in extraction.tickers:
            try:
                await self._store.aput(
                    ("users", user_id, "interests"),
                    key=ticker,
                    value={"company": ticker, "interest": "; ".join(extraction.research_topics), "last_seen": now},
                )
            except Exception as exc:
                logger.warning("merge_extraction ticker %s failed: %s", ticker, exc)

        # Persist preferences / topics / explicit memories to profile meta
        if extraction.preferences or extraction.research_topics or extraction.explicit_memories:
            try:
                meta_ns = ("users", user_id, "profile")
                existing_items = await self._store.asearch(meta_ns, query="preferences", limit=1)
                existing: dict = {}
                for it in existing_items:
                    existing = it.value or {}

                merged_preferences = {**existing.get("preferences", {}), **extraction.preferences}
                merged_topics = list(set(existing.get("topics", []) + extraction.research_topics))
                merged_memories = list(set(existing.get("explicit_memories", []) + extraction.explicit_memories))

                await self._store.aput(
                    meta_ns,
                    key="meta",
                    value={
                        "preferences": merged_preferences,
                        "topics": merged_topics,
                        "explicit_memories": merged_memories,
                        "updated_at": now,
                    },
                )
            except Exception as exc:
                logger.warning("merge_extraction profile meta failed: %s", exc)

        # Deprecate keys
        for key in extraction.deprecate_keys:
            try:
                await self._store.adelete(("users", user_id, "interests"), key=key)
            except Exception as exc:
                logger.warning("merge_extraction deprecate %s failed: %s", key, exc)
