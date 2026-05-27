"""Short-term memory service — last N turn-pairs from graph state messages."""
from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.modules.chat_history.short_term.schemas import ShortTermContext, TurnPair


class ShortTermMemoryService:
    """Reads conversation history from LangGraph state messages.

    Only Human/AI pairs are included; intermediate tool messages are skipped.
    """

    def format_recent_turns(
        self,
        messages: list[BaseMessage],
        *,
        limit_turn_pairs: int = 5,
    ) -> str:
        ctx = self._extract(messages, limit=limit_turn_pairs)
        return ctx.format_for_prompt()

    def get_recent_turn_messages(
        self,
        messages: list[BaseMessage],
        *,
        limit_turn_pairs: int = 5,
    ) -> list[BaseMessage]:
        ctx = self._extract(messages, limit=limit_turn_pairs)
        result: list[BaseMessage] = []
        for pair in ctx.turn_pairs:
            result.append(HumanMessage(content=pair.human))
            result.append(AIMessage(content=pair.assistant))
        return result

    def _extract(
        self,
        messages: list[BaseMessage],
        *,
        limit: int,
    ) -> ShortTermContext:
        pairs: list[TurnPair] = []
        pending_human: str | None = None

        for msg in messages:
            if isinstance(msg, HumanMessage):
                pending_human = msg.content if isinstance(msg.content, str) else str(msg.content)
            elif isinstance(msg, AIMessage) and pending_human is not None:
                pairs.append(TurnPair(human=pending_human, assistant=msg.content if isinstance(msg.content, str) else str(msg.content)))
                pending_human = None

        # Keep only the most recent N pairs
        return ShortTermContext(turn_pairs=pairs[-limit:] if pairs else [])
