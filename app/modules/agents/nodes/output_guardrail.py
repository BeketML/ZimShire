"""Output guardrail node — blocks buy/sell advice + factual hallucinations."""
from __future__ import annotations

import json
import logging
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.prompts import GUARDRAIL_OUTPUT_PROMPT
from app.modules.agents.state import ZimShireState
from app.modules.guardrails.gateways import write_guardrail_log
from app.services.llm import get_guardrail_model

logger = logging.getLogger(__name__)


def _message_id(config: RunnableConfig) -> UUID | None:
    raw = config.get("configurable", {}).get("human_message_id")
    if not raw:
        return None
    return UUID(raw) if isinstance(raw, str) else raw


async def output_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    draft = state.get("draft_answer") or ""
    retry_count = state.get("retry_count", 0)
    mid = _message_id(config)

    ctx = state.get("collected_context") or {}
    profile = state.get("user_profile") or {}
    history = "\n".join(
        f"{'User' if getattr(m, 'type', None) == 'human' else 'Assistant'}: {m.content}"
        for m in state.get("messages", [])[-10:]
    )

    full_context = (
        f"=== RAG CONTEXT ===\n{ctx.get('rag', '(not used)')}\n\n"
        f"=== MARKET DATA ===\n{ctx.get('market', '(not used)')}\n\n"
        f"=== WEB SEARCH ===\n{ctx.get('web', '(not used)')}\n\n"
        f"=== USER PROFILE ===\n{json.dumps(profile)}\n\n"
        f"=== CONVERSATION ===\n{history}"
    )

    try:
        llm = get_guardrail_model()
        resp = await llm.ainvoke([
            SystemMessage(content=GUARDRAIL_OUTPUT_PROMPT),
            HumanMessage(content=f"COLLECTED CONTEXT:\n{full_context}\n\nDRAFT ANSWER:\n{draft}"),
        ])
        raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
        check = json.loads(raw)
    except Exception as exc:
        logger.error("output_guardrail LLM call failed (%s) — passing through (fail-open)", exc, exc_info=True)
        await write_guardrail_log(message_id=mid, guardrail_type="output", result="passed")
        return {"output_blocked": False, "output_rewritten": False, "feedback_message": None}

    any_violation = not check.get("factual_consistent", True) or check.get("safety_violation", False)

    if not any_violation:
        await write_guardrail_log(message_id=mid, guardrail_type="output", result="passed")
        return {"output_blocked": False, "output_rewritten": False, "feedback_message": None}

    if check.get("safety_violation"):
        reason = f"[{check.get('safety_category')}] {check.get('safety_reason', '')}"
    else:
        claims = "; ".join(check.get("unsupported_claims") or [])
        reason = f"[factual] Unsupported claims: {claims}"

    await write_guardrail_log(
        message_id=mid, guardrail_type="output", result="blocked", blocked_reason=reason
    )

    if retry_count < 2:
        return {
            "output_blocked": True,
            "output_blocked_reason": reason,
            "feedback_message": check.get("feedback"),
            "retry_count": retry_count + 1,
        }

    safe_text = (
        "ZimShire can help you research companies through Buffett's philosophy and public "
        "market data, but cannot provide investment recommendations or unverified claims. "
        "Try: 'How did Buffett evaluate Coca-Cola's moat?' or "
        "'What does Apple's P/E ratio suggest about margin of safety?'"
    )
    return {
        "output_blocked": True,
        "output_blocked_reason": reason,
        "output_rewritten": True,
        "draft_answer": safe_text,
        "feedback_message": None,
        "retry_count": retry_count + 1,
    }
