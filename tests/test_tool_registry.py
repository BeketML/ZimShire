"""Unit tests for ToolRegistry and tag-based filtering."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


def _make_tool(name: str, tags: list[str] | None = None) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.metadata = {"tags": tags} if tags else {}
    return tool


def test_tool_registry_set_and_get():
    from app.modules.agents.tool_registry import ToolRegistry

    registry = ToolRegistry()
    tools = {
        "search_buffett_letters": _make_tool("search_buffett_letters", ["rag"]),
        "get_stock_price": _make_tool("get_stock_price", ["market"]),
    }
    registry.set_tools(tools)
    assert len(registry.get_tools()) == 2


def test_tool_registry_empty_raises():
    from app.modules.agents.tool_registry import ToolRegistry

    registry = ToolRegistry()
    with pytest.raises(RuntimeError, match="empty"):
        registry.get_tools()


def test_matches_agent_rag_by_tag():
    from app.modules.agents.tool_registry import matches_agent

    tool = _make_tool("search_buffett_letters", ["rag"])
    assert matches_agent("search_buffett_letters", tool, "rag") is True
    assert matches_agent("search_buffett_letters", tool, "market") is False


def test_matches_agent_market_by_allowlist():
    from app.modules.agents.tool_registry import matches_agent

    # No tags — fallback to allowlist
    tool = _make_tool("get_stock_price")
    assert matches_agent("get_stock_price", tool, "market") is True
    assert matches_agent("get_stock_price", tool, "rag") is False


def test_ui_tool_excluded():
    from app.modules.agents.tool_registry import matches_agent

    tool = _make_tool("get_stock_price_ui", ["market", "ui"])
    assert matches_agent("get_stock_price_ui", tool, "market") is False
