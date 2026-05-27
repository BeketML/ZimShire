"""Web subagent — recent news and events specialist."""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.core.prompts import WEB_SUBAGENT_PROMPT
from app.modules.agents.mcp_registry import format_tool_names_for_prompt, get_agent_tools
from app.modules.agents.schemas import SubagentResult
from app.modules.agents.subagents.base import run_react_subagent


async def run_web_subagent(
    *,
    sub_query: str,
    config: RunnableConfig,
) -> SubagentResult:
    tools = get_agent_tools("web", wrap_market_cache=False)
    tool_block = format_tool_names_for_prompt(tools)
    system_prompt = (
        f"{WEB_SUBAGENT_PROMPT}\n\n## Tools available for this run\n{tool_block}"
    )

    formatted, artifacts = await run_react_subagent(
        agent="web",
        system_prompt=system_prompt,
        human_message=sub_query,
        config=config,
        tools=tools,
        error_label="Web subagent",
    )

    return SubagentResult(
        agent_name="web",
        sub_query=sub_query,
        formatted_context=formatted,
        raw_artifacts=artifacts,
    )
