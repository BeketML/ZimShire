from __future__ import annotations

import httpx

from mcp_server.core.config import Settings
from mcp_server.services.embedding_service import LiteLLMEmbeddingService
from mcp_server.services.protocols import (
    MarketDataServiceInterface,
    RAGServiceInterface,
    WebSearchServiceInterface,
)
from mcp_server.services.rag_service import RAGService
from mcp_server.services.reranker import FastEmbedCrossEncoderReranker
from mcp_server.services.sparse_embedding_service import FastEmbedSparseEmbeddingService
from mcp_server.services.vector_store import QdrantVectorStore
from mcp_server.services.web_search_service import SerpApiWebSearchService
from mcp_server.services.yfinance_data_service import YFinanceDataService


class ServiceContainer:
    """Composition root — the only place that constructs concrete service instances."""

    def __init__(self) -> None:
        self.rag: RAGServiceInterface
        self.search: WebSearchServiceInterface
        self.market: MarketDataServiceInterface
        self._http: httpx.AsyncClient

    async def startup(self, settings: Settings) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)

        embedding_service = LiteLLMEmbeddingService(settings, self._http)
        sparse_service = FastEmbedSparseEmbeddingService(settings.sparse_embedding_model)
        reranker = FastEmbedCrossEncoderReranker(settings.reranker_model)
        vector_store = QdrantVectorStore(settings)

        self.rag = RAGService(embedding_service, sparse_service, vector_store, reranker)
        self.search = SerpApiWebSearchService(
            api_key=settings.duckduckgo_api_key,
            http_client=self._http,
        )
        self.market = YFinanceDataService()

    async def shutdown(self) -> None:
        await self._http.aclose()


_container: ServiceContainer | None = None


async def init_services(settings: Settings) -> None:
    global _container
    _container = ServiceContainer()
    await _container.startup(settings)


async def close_services() -> None:
    global _container
    if _container is not None:
        await _container.shutdown()
        _container = None


def get_rag_service() -> RAGServiceInterface:
    if _container is None:
        raise RuntimeError("Services not initialised — call init_services() in lifespan")
    return _container.rag


def get_web_search_service() -> WebSearchServiceInterface:
    if _container is None:
        raise RuntimeError("Services not initialised — call init_services() in lifespan")
    return _container.search


def get_market_data_service() -> MarketDataServiceInterface:
    if _container is None:
        raise RuntimeError("Services not initialised — call init_services() in lifespan")
    return _container.market
