from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict


class SearchHit(TypedDict):
    letter_year: int
    passage_snippet: str
    similarity_score: float
    qdrant_point_id: str
    chunk_index: int | None
    source_file: str | None


class WebOrganicResult(TypedDict):
    title: str
    url: str
    snippet: str
    date: str | None
    favicon: str | None


class WebNewsResult(TypedDict):
    title: str
    url: str
    snippet: str
    source: str
    date: str
    thumbnail: str | None


class WebKnowledgeGraph(TypedDict):
    title: str
    description: str
    website: str | None
    facts: dict[str, str]
    profiles: list[dict]
    related_topics: list[dict]


class EmbeddingServiceInterface(ABC):
    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        pass


class SparseEmbeddingServiceInterface(ABC):
    @abstractmethod
    def embed_query_sparse(self, text: str) -> dict[int, float]:
        """Return {token_id: weight} sparse vector. Sync — CPU-local model."""
        pass


class RerankerInterface(ABC):
    @abstractmethod
    def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        """Return top_k hits reordered by cross-encoder score. Sync — CPU-local model."""
        pass


class VectorStoreInterface(ABC):
    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        *,
        sparse_vector: dict[int, float] | None = None,
        top_k: int = 5,
        letter_years_filter: list[int] | None = None,
    ) -> list[SearchHit]:
        pass

    @abstractmethod
    async def get_letter_years(self) -> list[int]:
        pass


class RAGServiceInterface(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        letter_years_filter: list[int] | None = None,
    ) -> list[SearchHit]:
        pass


class WebSearchServiceInterface(ABC):
    @abstractmethod
    async def search_organic(
        self,
        query: str,
        max_results: int = 5,
        region: str = "us-en",
        date_filter: str | None = None,
    ) -> list[WebOrganicResult]:
        pass

    @abstractmethod
    async def search_news(
        self,
        query: str,
        max_results: int = 10,
        region: str = "us-en",
        date_filter: str | None = None,
    ) -> list[WebNewsResult]:
        pass

    @abstractmethod
    async def search_knowledge(
        self,
        query: str,
    ) -> WebKnowledgeGraph | None:
        pass


class MarketDataServiceInterface(ABC):
    # Fundamentals
    @abstractmethod
    async def get_stock_info(self, ticker: str) -> dict:
        pass

    @abstractmethod
    async def get_stock_price(self, ticker: str) -> dict:
        pass

    # Price history
    @abstractmethod
    async def get_stock_history(
        self, ticker: str, period: str, interval: str
    ) -> list[dict]:
        pass

    # Financials
    @abstractmethod
    async def get_income_statement(self, ticker: str, quarterly: bool) -> dict:
        pass

    @abstractmethod
    async def get_balance_sheet(self, ticker: str, quarterly: bool) -> dict:
        pass

    @abstractmethod
    async def get_cashflow(self, ticker: str, quarterly: bool) -> dict:
        pass

    # Analysis
    @abstractmethod
    async def get_analyst_targets(self, ticker: str) -> dict:
        pass

    @abstractmethod
    async def get_recommendations(self, ticker: str) -> list[dict]:
        pass

    @abstractmethod
    async def get_earnings_estimate(self, ticker: str) -> dict:
        pass

    @abstractmethod
    async def get_upgrades_downgrades(self, ticker: str) -> list[dict]:
        pass

    # Holders
    @abstractmethod
    async def get_institutional_holders(self, ticker: str) -> list[dict]:
        pass

    @abstractmethod
    async def get_insider_transactions(self, ticker: str) -> list[dict]:
        pass

    # News
    @abstractmethod
    async def get_stock_news(self, ticker: str, count: int) -> list[dict]:
        pass

    # Macro
    @abstractmethod
    async def get_market_summary(self, market: str) -> dict:
        pass

    @abstractmethod
    async def get_calendar_events(self, days_ahead: int) -> dict:
        pass

    # Screener / discovery
    @abstractmethod
    async def lookup_ticker(self, query: str) -> list[dict]:
        pass

    @abstractmethod
    async def screen_stocks(
        self, sector: str | None, region: str, size: int
    ) -> list[dict]:
        pass

    # Backward compat
    @abstractmethod
    async def get_data(self, ticker: str, data_type: str) -> dict:
        pass
