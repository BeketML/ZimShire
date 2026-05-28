"""Compatibility re-export — split into tool_allowlists, tool_registry, tool_wrappers."""
from app.modules.agents.tool_allowlists import (
    AGENT_PRIMARY_TAG,
    AGENT_TOOL_ALLOWLIST,
    EXCLUDE_TAGS,
    MARKET_TOOL_MAP,
    AgentName,
)
from app.modules.agents.tool_registry import (
    get_all_tools,
    matches_agent as _matches_agent,
    set_all_tools,
    tool_tags,
)
from app.modules.agents.tool_wrappers import (
    format_tool_names_for_prompt,
    get_agent_tools,
)

__all__ = [
    "AgentName",
    "AGENT_PRIMARY_TAG",
    "AGENT_TOOL_ALLOWLIST",
    "EXCLUDE_TAGS",
    "MARKET_TOOL_MAP",
    "set_all_tools",
    "get_all_tools",
    "tool_tags",
    "get_agent_tools",
    "format_tool_names_for_prompt",
]
