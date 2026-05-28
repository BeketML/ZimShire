"""Compatibility re-export — split into market_cache_repo and semantic_cache_repo."""
from app.models.models import MarketDataCache, SemanticCache  # noqa: F401
from app.modules.cache.market_cache_repo import (
    MARKET_DEFAULT_TTL,
    get_valid_market,
    list_market,
    upsert_market,
)
from app.modules.cache.semantic_cache_repo import (
    SEMANTIC_SIMILARITY_THRESHOLD,
    bump_hit,
    find_similar,
    insert_semantic,
    list_semantic,
)

__all__ = [
    "MarketDataCache",
    "SemanticCache",
    "MARKET_DEFAULT_TTL",
    "SEMANTIC_SIMILARITY_THRESHOLD",
    "get_valid_market",
    "upsert_market",
    "list_market",
    "find_similar",
    "bump_hit",
    "insert_semantic",
    "list_semantic",
]
