from __future__ import annotations

from pydantic import BaseModel, Field


class SearchBuffettLettersInput(BaseModel):
    query: str = Field(..., description="Semantic search query over Buffett shareholder letters")
    top_k: int = Field(5, ge=1, le=20, description="Number of results to return")
    letter_years_filter: list[int] | None = Field(
        None, description="Restrict search to specific letter years, e.g. [1988, 1989]"
    )


class SearchHitOutput(BaseModel):
    letter_year: int
    passage_snippet: str
    similarity_score: float
    qdrant_point_id: str
    chunk_index: int | None = None
    source_file: str | None = None


class GetMarketDataInput(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol, e.g. AAPL")
    data_type: str = Field(
        "info",
        description="Type of data: 'info' (company overview), 'financials', or 'history' (1-month OHLCV)",
    )


class WebOrganicSearchInput(BaseModel):
    query: str = Field(..., description="Search query for DuckDuckGo organic web search")
    max_results: int = Field(5, ge=1, le=50, description="Maximum number of organic results")
    region: str = Field("us-en", description="Region code, e.g. us-en, uk-en, fr-fr")
    date_filter: str | None = Field(
        None,
        description="Filter by date: d (past day), w (past week), m (past month), y (past year), or custom range 2021-06-15..2024-06-16",
    )


class WebOrganicResultOutput(BaseModel):
    title: str
    url: str
    snippet: str
    date: str | None = None
    favicon: str | None = None


class WebNewsSearchInput(BaseModel):
    query: str = Field(..., description="Search query for DuckDuckGo News")
    max_results: int = Field(10, ge=1, le=100, description="Maximum number of news results")
    region: str = Field("us-en", description="Region code, e.g. us-en, uk-en, fr-fr")
    date_filter: str | None = Field(
        None,
        description="Filter by date: d (past day), w (past week), m (past month)",
    )


class WebNewsResultOutput(BaseModel):
    title: str
    url: str
    snippet: str
    source: str
    date: str
    thumbnail: str | None = None


class WebKnowledgeSearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Entity name to look up: company, person, place, etc.",
    )


class WebKnowledgeGraphOutput(BaseModel):
    title: str
    description: str
    website: str | None = None
    facts: dict[str, str] = Field(default_factory=dict)
    profiles: list[dict] = Field(default_factory=list)
    related_topics: list[dict] = Field(default_factory=list)
