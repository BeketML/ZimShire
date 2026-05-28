"""Input guardrail node — blocks off-topic or injection queries."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.prompts import GUARDRAIL_INPUT_PROMPT
from app.modules.agents.state import ZimShireState
from app.modules.guardrails.gateways import write_guardrail_log
from app.services.llm import get_guardrail_model

logger = logging.getLogger(__name__)


def _message_id(config: RunnableConfig) -> UUID | None:
    raw = config.get("configurable", {}).get("human_message_id")
    if not raw:
        return None
    return UUID(raw) if isinstance(raw, str) else raw


async def input_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    last_human = ""
    for m in reversed(state.get("messages", [])):
        if getattr(m, "type", None) == "human":
            last_human = m.content if isinstance(m.content, str) else str(m.content)
            break

    mid = _message_id(config)

    try:
        llm = get_guardrail_model()
        resp = await llm.ainvoke(
            [SystemMessage(content=GUARDRAIL_INPUT_PROMPT), HumanMessage(content=last_human)]
        )
        raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        blocked = bool(result.get("blocked"))
        reason = result.get("reason") or None
    except Exception as exc:
        # Explicit: fail-open (allow) or fail-closed (block) on LLM error
        blocked = not settings.fail_open_on_guardrail_error
        reason = None
        if blocked:
            logger.error("input_guardrail LLM failed (%s) — blocking (fail-closed)", exc, exc_info=True)
        else:
            logger.warning("input_guardrail LLM failed (%s) — allowing through (fail-open)", exc)

    await write_guardrail_log(
        message_id=mid,
        guardrail_type="input",
        result="blocked" if blocked else "passed",
        blocked_reason=reason if blocked else None,
    )

    if blocked:
        safe_msg = AIMessage(
            content=(
                "I can only help with investment research questions grounded in "
                "Warren Buffett's philosophy and public market data. "
                "Try: 'How did Buffett evaluate Coca-Cola's moat?' or "
                "'What does Apple's P/E ratio say about its margin of safety?'"
            )
        )
        return {
            "query": last_human,
            "input_blocked": True,
            "input_blocked_reason": reason,
            "messages": [safe_msg],
        }

    return {"query": last_human, "input_blocked": False, "input_blocked_reason": None}
