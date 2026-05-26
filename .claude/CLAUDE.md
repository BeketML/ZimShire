# ZimShire — CLAUDE.md

AI investment **research** assistant (Buffett-first lens). Not a screener, prediction engine, or financial advisor.

**Deadline:** 29 May 2026, 19:00.

**Hard rule:** Never generate buy/sell recommendations, price targets, or personalized portfolio advice — enforced in `output_guardrail` at every layer.

---

## Stack

| Layer | Choice |
|-------|--------|
| Orchestration | LangGraph (`StateGraph`) |
| LLM / embeddings | LiteLLM via Zimran gateway (`https://litellm.zimran.net`) |
| HTTP API | FastAPI async + SSE |
| Vector DB | Qdrant — collection `buffett_letters` |
| Observability | Langfuse |
| Persistence | Postgres (custom tables + LangGraph checkpointer/store) |
| MCP | FastMCP (separate process) |

No direct OpenAI/Anthropic/Google SDK keys. All LLM calls go through the gateway.

---

## Project layout

```
zimshire/
  app/
    main.py
    core/
      config.py                 # DATABASE_URL, MCP_BASE_URL, LiteLLM, Langfuse
      prompts.py
      dependencies.py
    routers/                    # canonical HTTP layer (7 endpoints)
      users.py
      chats.py
      messages.py               # SSE streaming
      health.py
    graph/
      state.py
      routing.py
      builder.py
      mcp_client.py             # langchain-mcp-adapters → MCP_BASE_URL
      tools/
        subagents.py            # rag_agent, market_agent, web_agent
      nodes/
        guardrails.py
        cache.py
        memory.py               # load_memory (ST + LT)
        orchestrator.py
    services/
      llm.py
      embedding.py
      guardrails.py
      chat_service.py
      graph_service.py
      langfuse_service.py
    models/
    schemas/
    db/
    repositories/
  mcp_server/                   # separate process (renamed from `mcp/` to avoid clashing with the official `mcp` SDK that fastmcp depends on)
    main.py                     # entry point; registers all tools via imports
    core/
      mcp.py                    # shared FastMCP instance
      config.py                 # Settings (qdrant, litellm, serpapi, hybrid search params)
    rag/
      tools.py                  # search_buffett_letters (hybrid RAG)
      qdrant.py                 # QdrantStore — dense / hybrid+RRF / full+ColBERT search
      embeddings.py             # DenseEmbedder, SparseEmbedder (BM25), LateInteractionEmbedder (ColBERT)
    market/
      tools.py                  # 11 yfinance tools (stock info, price, history, financials, holders, news)
    search/
      tools.py                  # web_search, web_search_news, web_search_knowledge (SerpApi/DuckDuckGo)
      models.py                 # TypedDicts for search result shapes
    ui/
      rag_ui.py                 # search_buffett_letters_ui (prefab_ui DataTable)
      market_ui.py              # get_stock_*_ui, get_*_ui tools (metrics, charts, tables)
      search_ui.py              # web_search_ui, web_search_news_ui, web_search_knowledge_ui
  scripts/
    ingest_letters.py
  tests/
  docs/
  docker-compose.yaml
```

---

## Quick commands

```bash
# Full stack (recommended)
docker compose up -d            # postgres, qdrant, mcp (8001), api (8000)
alembic upgrade head
python scripts/download_letters.py
python scripts/ingest_letters.py
pytest tests/ -v

# Local dev (without Docker for app services)
docker compose up -d postgres qdrant
python -m mcp_server.main --transport streamable-http --port 8001
uvicorn app.main:app --reload --port 8000

# Cursor / Claude Code MCP client
python -m mcp_server.main              # stdio transport for Cursor/Claude Code
```

---

## Environment variables

All real values go in root `.env` (never commit). Variable names only:

| Variable | Purpose |
|----------|---------|
| `LITELLM_BASE_URL` | `https://litellm.zimran.net` |
| `LITELLM_API_KEY` | Virtual key from Zimran |
| `LITELLM_END_USER_ID` | Gmail for `x-litellm-end-user-id` header |
| `DEFAULT_CHAT_MODEL` | Default slug, e.g. `gpt-4o-mini` |
| `EMBEDDING_MODEL` | e.g. `text-embedding-3-small` |
| `OPENAI_API_BASE` | Optional OpenAI-compatible alias |
| `OPENAI_API_KEY` | Optional alias for `LITELLM_API_KEY` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse |
| `LANGFUSE_SECRET_KEY` | Langfuse |
| `LANGFUSE_BASE_URL` | Langfuse |
| `DATABASE_URL` | Postgres |
| `QDRANT_URL` | Qdrant |
| `DUCKDUCKGO_API_KEY` | SerpApi key used to query DuckDuckGo (`mcp_server/search/tools.py`) |
| `MCP_BASE_URL` | Internal MCP endpoint, e.g. `http://localhost:8001` (docker: `http://mcp:8001`) |
| `MCP_PORT` | MCP listen port (default `8001`) |

---

## Gateway models (whitelist)

Only use these slugs:

| Slug | Use |
|------|-----|
| `gpt-4o-mini` | Default (fast, cheap) |
| `gpt-4o` | Higher-quality chat |
| `claude-haiku-4-5` | Chat |
| `claude-sonnet-4-6` | Chat |
| `gemini-3.1-flash-lite-preview` | Chat |
| `gemini-2.5-flash-lite` | Chat |
| `text-embedding-3-small` | RAG ingest + query embeddings |

---

## Graph topology

```
START → input_guardrail → (blocked? END)
      → semantic_cache_check → (hit? END)
      → load_memory → orchestrator (tools: rag_agent, market_agent, web_agent)
      → output_guardrail → faithfulness_guardrail → END
```

**Orchestrator** decides which subagent tools to call per turn (no separate planner).

---

## Graph state (`ZimShireState`)

```python
class ZimShireState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    user_preferences: NotRequired[list[str]]
    rag_agent_chunks: NotRequired[list[dict]]
    rag_agent_result: NotRequired[str]
    rag_invoked: NotRequired[bool]
    web_agent_sources: NotRequired[list[dict]]
    web_agent_result: NotRequired[str]
    market_agent_result: NotRequired[str]
    draft_answer: NotRequired[str]
    grounded: NotRequired[bool | None]
    sources: NotRequired[list[dict]]
    cache_hit: NotRequired[bool]
    input_blocked: NotRequired[bool]
    input_blocked_reason: NotRequired[str | None]
    output_blocked: NotRequired[bool]
    output_blocked_reason: NotRequired[str | None]
    output_rewritten: NotRequired[bool]
```

**NOT in state** (goes in `RunnableConfig["configurable"]`): `thread_id`, `user_id`, `chat_id`, `model`, `provider`, `human_message_id`, `langfuse_trace_id`.

---

## Critical invariants

1. **`config["configurable"]["thread_id"]` === `str(chat_id)`** — derived from chat PK, not stored in `chats`.
2. `rag_agent_chunks` live in graph state; **`rag_retrievals` rows are written in FastAPI Stage 10 only** (after `assistant_message_id` exists).
3. One Qdrant search → **k rows** in `rag_retrievals` (same `message_id`, different `qdrant_point_id`).
4. **`grounded = false`** when `rag_invoked` but `rag_agent_chunks` empty or fewer than 2 strong hits (score ≥ 0.75).
5. MCP tools = data only. Guardrails, `grounded`, synthesis stay in FastAPI + LangGraph.
6. Graph nodes call MCP tools via `app/graph/mcp_client.py` and `MCP_BASE_URL`. **Direct import of anything under `mcp_server/` in graph nodes is forbidden.**
7. **`draft_answer` never reaches the client before `output_guardrail` completes.** Orchestrator uses `ainvoke`; SSE streaming happens in FastAPI after the graph completes.
8. **Langfuse trace is created for every request** — including cache hits (one span `cache_hit`).

---

## API surface (7 endpoints)

| Method | Path | Action |
|--------|------|--------|
| `POST` | `/users` | Create user |
| `GET` | `/users/{user_id}` | Get user metadata |
| `POST` | `/chats` | Create chat (server generates `chat_id`) |
| `GET` | `/chats/{chat_id}` | Chat metadata |
| `GET` | `/chats/{chat_id}/messages` | Conversation history |
| `POST` | `/chats/{chat_id}/messages` | Streaming research turn (SSE — tokens after guardrails) |
| `GET` | `/health` | Health check |

Assistant response shape:
```json
{
  "message_id": "uuid",
  "content": "...",
  "grounded": true,
  "sources": [{ "letter_year": 1988, "passage": "...", "similarity_score": 0.87, "qdrant_point_id": "uuid" }],
  "langfuse_trace_id": "..."
}
```

---

## Request flow (stages)

| Stage | What |
|-------|------|
| 1 | `POST /users` → `users` table, init `store` profile namespace |
| 2 | `POST /chats` → `chats` row with new `chat_id` (server-generated) |
| 3 | Human message → `messages` (human); load `chats`; restore checkpoint |
| 4 | `input_guardrail` → `guardrail_logs`; may END early |
| 5 | `semantic_cache_check` → optional skip graph; Langfuse trace created even on cache hit |
| 6 | `load_memory` → `orchestrator` (subagent tools via MCP) |
| 7 | orchestrator produces full `draft_answer` in state — no client streaming yet |
| 8 | `output_guardrail` → `guardrail_logs`; may rewrite `draft_answer` |
| 9 | `faithfulness_guardrail` → `grounded`, `sources`; `guardrail_logs` |
| 9.5 | FastAPI streams approved `draft_answer` to client as SSE token events |
| 10 | Persist: `messages` (assistant), N×`rag_retrievals`, `semantic_cache`, `store.aput`, `chats.updated_at` |

Multi-turn: skip stages 1–2; start at stage 3.

---

## Postgres custom tables

| Table | Key notes |
|-------|-----------|
| `users` | `user_id` (uuid PK) |
| `chats` | `chat_id` PK (= LangGraph `thread_id` as `str(chat_id)`), `model`, `provider`, `user_id` FK |
| `messages` | `role` human/assistant; `grounded` + `langfuse_trace_id` on assistant rows |
| `rag_retrievals` | One row per Qdrant point; UK `(message_id, qdrant_collection, qdrant_point_id)` |
| `guardrail_logs` | `guardrail_type` ∈ {input, output, faithfulness}; `result` ∈ {passed, blocked} |
| `market_data_cache` | TTL cache keyed by `(ticker, data_type)` |
| `semantic_cache` | pgvector `query_embedding`; similarity threshold ~0.92 |

**LangGraph-managed (no direct SQL):** `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `store`, `store_vectors`.

---

## Qdrant — Buffett letters

- Collection: `buffett_letters`, cosine distance
- Vector spaces: `dense` (dim=1536, text-embedding-3-small), `sparse` (BM25 via fastembed), `multi` (ColBERT dim=96, answerdotai/answerai-colbert-small-v1)
- Collection mode auto-detected at runtime: `full` (all three) → prefetch dense+sparse, rerank with ColBERT; `hybrid` (dense+sparse) → RRF fusion; `dense` → single-vector search
- Chunk size: 800–1200 tokens, overlap 100–150 tokens
- Point ID: `uuid5(namespace, f"{letter_year}:{chunk_index}")` — deterministic for idempotent re-ingest
- Payload fields: `letter_year`, `chunk_index`, `text`, `source_file`
- Payload index on `letter_year` for year filters
- Search result fields: `letter_year`, `passage_snippet`, `similarity_score` (dense cosine), `rerank_score` (ColBERT/RRF), `qdrant_point_id`, `chunk_index`, `source_file`
- Hybrid prefetch limit: 20 candidates per vector type before reranking

---

## MCP server (Task 4)

Two processes: `uvicorn app.main:app` (port 8000) and `python -m mcp_server.main --transport streamable-http --port 8001` (data tools only).

Tools are registered via `@mcp.tool` decorators and imported in `mcp_server/main.py`. The `mcp_server/core/mcp.py` module holds the shared FastMCP instance.

**Data tools:**

| Tool | Module | Description |
|------|--------|-------------|
| `search_buffett_letters(query, top_k, letter_years_filter)` | `rag/tools.py` | Hybrid RAG: dense+sparse prefetch, ColBERT rerank |
| `get_stock_info(ticker)` | `market/tools.py` | Full company overview (sector, P/E, EPS, description) |
| `get_stock_price(ticker)` | `market/tools.py` | Fast price snapshot (last, prev close, 52W high/low) |
| `get_stock_history(ticker, period, interval)` | `market/tools.py` | OHLCV history |
| `get_income_statement(ticker, quarterly)` | `market/tools.py` | Revenue, gross profit, EBITDA, net income |
| `get_balance_sheet(ticker, quarterly)` | `market/tools.py` | Assets, debt, cash, equity |
| `get_cashflow(ticker, quarterly)` | `market/tools.py` | Operating cash flow, capex, free cash flow |
| `get_earnings_estimate(ticker)` | `market/tools.py` | Forward EPS estimates |
| `get_institutional_holders(ticker)` | `market/tools.py` | Top institutional holders |
| `get_insider_transactions(ticker)` | `market/tools.py` | Recent insider buy/sell |
| `get_stock_news(ticker, count)` | `market/tools.py` | Latest Yahoo Finance news |
| `lookup_ticker(query)` | `market/tools.py` | Ticker lookup by company name |
| `web_search(query, max_results, region, date_filter)` | `search/tools.py` | Organic search via SerpApi/DuckDuckGo |
| `web_search_news(query, max_results, region, date_filter)` | `search/tools.py` | News search via SerpApi/DuckDuckGo |
| `web_search_knowledge(query)` | `search/tools.py` | Knowledge Graph card via SerpApi/DuckDuckGo |

**UI tools** (Claude Code `prefab_ui` apps, `app=True`): mirror for each data tool in `mcp_server/ui/` — `search_buffett_letters_ui`, `get_stock_info_ui`, `get_stock_price_ui`, `get_stock_history_ui`, `get_income_statement_ui`, `get_balance_sheet_ui`, `get_cashflow_ui`, `get_earnings_estimate_ui`, `get_institutional_holders_ui`, `get_insider_transactions_ui`, `get_stock_news_ui`, `lookup_ticker_ui`, `web_search_ui`, `web_search_news_ui`, `web_search_knowledge_ui`.

**Do NOT expose via MCP:** full graph, guardrails, `rag_retrievals`, semantic cache, LiteLLM synthesis.

**MCP transport:**

| Client | Transport | Endpoint |
|--------|-----------|----------|
| LangGraph graph nodes (internal) | streamable-http | `http://mcp:8001/mcp` |
| Cursor / Claude Code | stdio | `python -m mcp_server.main` |

Graph nodes call MCP via `app/graph/mcp_client.py` (`MultiServerMCPClient`). Client is initialised once in FastAPI lifespan and shared across all concurrent requests.

---

## Langfuse (Task 5)

One trace per user message; spans per node. Store `trace.id` on assistant `messages.langfuse_trace_id`.

Node spans: `load_memory`, `orchestrator`, `rag_retrieval`, `market_data`, `web_search`.

---

## Guardrails (Task 6)

| Guardrail | Trigger | Log |
|-----------|---------|-----|
| `input_guardrail` | Off-topic / prompt injection | `guardrail_logs` type=input |
| `output_guardrail` | Buy/sell advice in draft | `guardrail_logs` type=output; rewrite with safe text |
| `faithfulness_guardrail` | RAG used → check passage support | `guardrail_logs` type=faithfulness; sets `grounded` |

---

## Bonus tasks

- **Semantic cache:** pgvector similarity ≥ 0.92 on `query_embedding` before hitting LLM.
- **Long-term memory:** `store.asearch` in `load_memory`; `store.aput` per ticker after Stage 10. Namespace: `("users", user_id, "interests")`.

---

## Assignment → task map

| Task | Requirement |
|------|-------------|
| 1 | FastAPI async chat, runtime model/provider, SSE streaming, conversation persistence |
| 2 | RAG over Buffett letters, source attribution (year + passage), `grounded: false` when not supported |
| 3 | Multi-agent LangGraph, RAG + yfinance + web, checkpointing by `thread_id` |
| 4 | Standalone FastMCP server, typed tools, separate process |
| 5 | Langfuse traces per user query (latency, tokens, cost) |
| 6 | Input / output / faithfulness guardrails + `guardrail_logs` |
| Bonus | Semantic cache + long-term user memory via `store` |

---

## Definition of done

1. Register → chat → streamed answer with `sources` and `grounded`
2. Multi-turn via same `str(chat_id)` checkpoint key
3. Guardrails: block bad input, rewrite bad output, faithfulness check
4. MCP: tools in separate process, data-only boundary respected
5. Langfuse: full trace per message
6. `docker compose up` + ingest + tests on clean machine
7. `rag_retrievals`: N rows for N Qdrant hits on letter queries

---

## Coding notes

- Match existing patterns in `app/` when adding code; minimal scope per change.
- Persist `rag_retrievals` in FastAPI only (after assistant `message_id`).
- Set `used_in_response` when persisting (snippet match or attribution step).
- Do not commit API keys or secret values to source files.
- README required for submission (Phase 11) with architecture diagram, setup instructions, endpoint reference, and design decision tradeoffs.
- **MCP tool calls only:** `subagents.py` calls MCP tools via `get_mcp_tools()` from `mcp_client.py`. Direct import of anything under `mcp_server/` from `app/` is forbidden.
- **`mcp_server/` subpackage boundary:** each subpackage (`rag/`, `market/`, `search/`) is self-contained. UI tools in `mcp_server/ui/` may call within their corresponding data module (local import). No cross-subpackage imports.
- **Synthesizer uses `ainvoke`** — never `astream`. Full `draft_answer` is buffered in graph state; client streaming happens in FastAPI after guardrails complete (Stage 9.5).
- **Langfuse trace on every request** — including cache hits. Cache hit trace has one span `cache_hit` (no LLM cost). Store `trace.id` on `messages.langfuse_trace_id`.
- **Docker 4 services:** `postgres`, `qdrant`, `mcp` (:8001), `api` (:8000). `api` depends on `mcp`. Use `docker compose up -d` for all.
