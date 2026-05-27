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
    main.py                      # FastAPI app + lifespan (MCP client, graph, Langfuse)
    core/
      config.py                  # DATABASE_URL, MCP_BASE_URL, LiteLLM, Langfuse
      database.py                # AsyncSessionLocal, engine
      dependencies.py            # get_db
      exceptions.py              # NotFoundError, ForbiddenError, DomainError
      prompts.py
    api/
      router.py                  # include_router for all modules
      deps.py                    # get_user_service, get_chat_service, get_message_service
    services/
      llm.py                     # get_chat_model(config) → ChatOpenAI → LiteLLM gateway
      embedding.py               # embed_text(text) → list[float]
      langfuse_service.py        # new_trace(user_id, session_id, name) → (trace_id, handler)
    modules/
      users/
        schemas.py
        repository.py
        service.py
        router.py                # POST /users, GET /users/{user_id}
      chats/
        schemas.py
        repository.py
        service.py
        router.py                # POST /chats, GET /chats/{chat_id}
      messages/
        schemas.py
        repository.py
        gateways.py              # TurnContext, GraphRunResult DTO
        service.py               # list_history, persist_turn, stream_turn (Stage 10)
        router.py                # GET + POST /chats/{id}/messages (SSE)
      cache/
        repository.py
        gateways.py              # lookup_market, store_market, lookup_semantic, write_semantic
      guardrails/
        repository.py
        gateways.py              # write_guardrail_log — opens own AsyncSessionLocal
      rag_retrievals/
        repository.py            # bulk_create (ON CONFLICT DO NOTHING)
      agents/
        state.py                 # ZimShireState TypedDict
        routing.py               # route_after_input, route_after_cache, route_after_output_guardrail
        builder.py               # build_graph(checkpointer, store) → CompiledGraph
        mcp_client.py            # MultiServerMCPClient; init/close/get_mcp_tools
        service.py               # init_graph, close_graph, get_graph, get_store
        gateways.py              # Chat → RunnableConfig; final_state → persist DTO
        nodes/
          guardrails.py          # input_guardrail, output_guardrail, faithfulness_guardrail
          cache.py               # semantic_cache_check
          memory.py              # load_memory (AsyncPostgresStore short+long-term)
          orchestrator.py        # create_react_agent with 3 subagent tools
        tools/
          subagents.py           # build_tools_with_accumulator → [rag_agent, market_agent, web_agent]
    models/
      models.py                  # central ORM registry for Alembic / FK refs
  mcp_server/                    # separate process (renamed from `mcp/` to avoid clashing with the official `mcp` SDK that fastmcp depends on)
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
START → input_guardrail
input_guardrail →[blocked]→ END
input_guardrail →[continue]→ semantic_cache_check
semantic_cache_check →[hit]→ END
semantic_cache_check →[miss]→ load_memory
load_memory → orchestrator
orchestrator → output_guardrail
output_guardrail →[retry, retry_count < 2]→ orchestrator
output_guardrail →[proceed]→ faithfulness_guardrail
faithfulness_guardrail → END
```

**Orchestrator** decides which subagent tools to call per turn (no separate planner). On output guardrail retry, `feedback_message` is passed back through state so orchestrator revises its answer.

**Subagent tools** (3 wrappers over real MCP tools via closure accumulator):
- `rag_agent(query, years=None)` → calls `search_buffett_letters`
- `market_agent(tickers, data_type="info")` → routes to granular MCP tools (`get_stock_info`, `get_stock_price`, `get_income_statement`, `get_balance_sheet`, `get_cashflow`, `get_stock_history`, etc.) via `_MARKET_TOOL_MAP`; cache-first via cache gateway
- `web_agent(query)` → calls `web_search`

**Guardrails** — lightweight LLM classifiers (single `gpt-4o-mini` JSON call each, no guardrails-ai, no RAGAS):
- `input_guardrail`: off-topic / injection check; fails open on LLM error
- `output_guardrail`: buy/sell/price-target safety check; max 2 retries; safe fallback text on exhaustion
- `faithfulness_guardrail`: atomic-claim check against `rag_agent_chunks`; `grounded=None` when RAG not invoked

---

## Graph state (`ZimShireState`)

```python
class ZimShireState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    query: NotRequired[str]
    user_profile: NotRequired[dict]           # {"tracked_companies": [...], "research_interests": [...]}
    collected_context: NotRequired[dict]       # {"rag": str, "market": str, "web": str}
    rag_agent_chunks: NotRequired[list[dict]]
    rag_invoked: NotRequired[bool]
    web_agent_sources: NotRequired[list[dict]]
    draft_answer: NotRequired[str]
    grounded: NotRequired[bool | None]
    sources: NotRequired[list[dict]]
    feedback_message: NotRequired[str | None]  # output_guardrail → orchestrator retry feedback
    retry_count: NotRequired[int]              # output_guardrail retry counter (max 2)
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
6. Graph nodes call MCP tools via `app/modules/agents/mcp_client.py` and `MCP_BASE_URL`. **Direct import of anything under `mcp_server/` in graph nodes is forbidden.**
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

---
description: Архитектура ZimShire — слои, модули, LangGraph, MCP. Обязательно для всех сессий.
alwaysApply: true
---

# ZimShire — Правила проектирования и Архитектурные паттерны

Данный документ определяет стандарты проектирования, структуру папок и правила написания кода для проекта ZimShire (FastAPI + SQLAlchemy + LangGraph + MCP). Все изменения и новые модули обязаны строго следовать этим правилам.

**Каноничная документация (источники истины):**
- `docs/api_endpoints.md` — 7 HTTP-эндпоинтов, контракт SSE
- `docs/agent_architecture.md` — граф, `ZimShireState`, guardrails, узлы
- `docs/assistant_flow.md` — Stage 1–10, read/write по таблицам на каждом этапе
- `docs/db_schema_reference.md` — ORM-схемы и LangGraph-таблицы

---

## 1. Основные архитектурные принципы

- **Clean/Layered Architecture:** полное разделение ответственности между слоями.
- **DIP (SOLID):** сервисы и граф зависят от абстракций (репозиториев, gateways), не от конкретных HTTP-объектов или ORM-сессий.
- **Domain-driven layout:** код группируется по бизнес-доменам в `app/modules/`, а не только по техническому типу файлов.
- **Process boundary:** `mcp_server/` — отдельный процесс; `app/` не импортирует ничего из `mcp_server/` (за исключением offline-скриптов в `scripts/`).

---

## 2. Целевая структура `app/`

Каждый новый домен создаётся в `app/modules/<domain>/` с изолированными слоями:

```
app/
├── main.py
├── core/                        # глобальная инфраструктура, без бизнес-логики
│   ├── config.py
│   ├── database.py              # единый модуль (устранить дубль app/db/database.py)
│   ├── dependencies.py          # get_db
│   ├── exceptions.py            # NotFoundError, DomainError
│   └── prompts.py               # только общие промпты; промпты агента — в modules/agents
│
├── api/
│   ├── router.py                # include_router для всех модулей
│   └── deps.py                  # фабрики: get_user_service, get_message_service и т.д.
│
├── models/                      # единый ORM-реестр для Alembic / FK-ссылок
│   ├── base.py
│   └── __init__.py              
│
├── domains/
│   ├── users/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── router.py
│   ├── chat_history/
│   │
│   ├── short_term_memory/
│   │   ├── models.py                # ORM models: ShortTermMemory
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── router.py
│   │
│   ├── long_term_memory/
│   │   ├── models.py                # ORM models: LongTermMemory
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── router.py
│   │
│   ├── chats/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── router.py
│   │
│   ├── messages/                # HTTP-история + оркестрация Stage 10
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── gateways.py          # TurnContext, GraphRunResult DTO
│   │   ├── service.py           # list_history, persist_turn, stream_turn
│   │   └── router.py            # GET + POST /chats/{id}/messages (SSE)
│   │
│   ├── cache/                   # semantic_cache + market_data_cache
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── service.py           # lookup_semantic, get_market_cached, insert_semantic
│   │   └── gateways.py          # вызывается из graph nodes
│   │
│   ├── guardrails/
│   │   ├── models.py
│   │   ├── repository.py
│   │   └── service.py           # write_guardrail_log — вызывается из graph nodes
│   │
│   └── agents/                  # весь LangGraph как домен
│       ├── state.py
│       ├── routing.py
│       ├── builder.py
│       ├── mcp_client.py
│       ├── service.py           # init_graph, close_graph, run_turn(config, input)
│       ├── gateways.py          # Chat → RunnableConfig; final_state → persist DTO
│       ├── nodes/
│       │   ├── guardrails.py    # input_guardrail, output_guardrail, faithfulness_guardrail
│       │   ├── cache.py         # semantic_cache_check
│       │   ├── memory.py        # load_memory
│       │   └── orchestrator.py
│       └── tools/
│           └── subagents.py     # build_tools_with_accumulator
│
mcp_server/                      # отдельный процесс — НИКОГДА не импортируется из app/
scripts/                         # offline ingest (разрешён импорт mcp_server/services/)
alembic/
docs/
```

### Текущее состояние (переходный период)

Сейчас код живёт в `app/routers/`, `app/repositories/`, `app/services/`, `app/graph/`. При изменениях двигаться к `modules/`. Не смешивать оба стиля в одном домене.

**Зафиксированный технический долг:**
- `app/db/database.py` и `app/core/database.py` — дублирование; объединить в `core/database.py`.
- `app/routers/users.py` и `app/routers/chats.py` вызывают `repo` напрямую — целевой паттерн: `router → service → repository`.

---

## 3. Спецификация слоёв и правила вызовов

Поток данных строго сверху вниз:

```
Router → Service → Repository → Database
               ↘ Gateway → Внешняя система / Другой модуль
```

### 3.1 Слой Router (`router.py`)

**Ответственность:** приём HTTP-запросов, Pydantic-валидация входных данных, маппинг domain errors → `HTTPException`, SSE-обёртка для стриминга.

**Запрещено:**
- Напрямую вызывать `session.execute`, `session.query` или методы репозитория для нетривиальных use-case
- Содержать бизнес-логику (условия прав, расчёты)
- Вызывать `session.commit()` — это делает service

**Инъекция:** все сервисы внедряются через `Depends()` из `api/deps.py`.

### 3.2 Слой Service (`service.py`)

**Ответственность:** чистая бизнес-логика, оркестрация нескольких репозиториев или вызовов агента, управление транзакциями (`commit` / `rollback`).

**Запрещено:**
- Принимать объекты `Request`, `Response` из FastAPI
- Бросать `HTTPException` — только кастомные Python-ошибки (`NotFoundError`, `ValueError`), которые router переведёт в HTTP

### 3.3 Слой Repository (`repository.py`)

**Ответственность:** инкапсуляция работы с СУБД (SQLAlchemy). Принимает `AsyncSession` при инициализации или как параметр функции.

**Запрещено:**
- Вызывать `session.commit()` — допустимо только `session.flush()`
- Вызывать бизнес-логику других модулей

### 3.4 Слой Gateway (`gateways.py`)

**Ответственность:** адаптация данных между доменами и внешними системами. Примеры: `messages ↔ agents` (TurnContext/GraphRunResult), `agents/tools ↔ cache` (market TTL lookup), `agents/nodes ↔ guardrails` (write log).

**Запрещено:**
- Зашивать промпты или логику графа внутрь gateway
- Выполнять SQL-запросы напрямую

---

## 4. Шаблон кода (Dependency Injection boilerplate)

При создании любой связки Router → Service → Repository использовать:

```python
# --- repository.py ---
class ItemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, item_id: int): ...

# --- service.py ---
class ItemService:
    def __init__(self, repo: ItemRepository):
        self.repo = repo

    async def process_item(self, item_id: int):
        result = await self.repo.get_by_id(item_id)
        if result is None:
            raise NotFoundError(f"item {item_id} not found")
        return result

# --- api/deps.py ---
async def get_item_service(db: AsyncSession = Depends(get_db)) -> ItemService:
    return ItemService(ItemRepository(db))

# --- router.py ---
@router.get("/{item_id}")
async def read_item(
    item_id: int,
    service: ItemService = Depends(get_item_service),
):
    return await service.process_item(item_id)
```

**Domain exceptions** объявляются в `app/core/exceptions.py`; router делает маппинг:

```python
# router.py
try:
    return await service.process_item(item_id)
except NotFoundError:
    raise HTTPException(status_code=404, detail="not found")
```

---

## 5. LangGraph и агенты

Инварианты из `docs/agent_architecture.md` (нарушение недопустимо):

| Правило | Детали |
|---------|--------|
| State isolation | `ZimShireState` без `AsyncSession` и без `chat_history: list[str]` |
| Config vs state | `thread_id`, `user_id`, `chat_id`, `human_message_id`, `langfuse_trace_id` — только в `RunnableConfig["configurable"]`, не в state |
| Pre-invocation fetch | Все данные для агента получаются до запуска графа через gateway/service, не через SQL в узлах |
| Tools | `rag_agent` / `web_agent` → MCP через `mcp_client.py`; `market_agent` → cache gateway/service; SQL-сессия никогда не попадает внутрь тела tool |
| Closure accumulator | Subagent tools пишут в `accumulated` dict через замыкание; orchestrator возвращает всё одним dict из node |
| `ainvoke` в orchestrator | Не `astream` — guardrails требуют полный `draft_answer` |
| Streaming | Граф завершается полностью → output_guardrail → faithfulness_guardrail → FastAPI отдаёт SSE-токены |
| Checkpointer | `thread_id` всегда `str(chat_id)` |
| Retry loop | `output_guardrail` — максимум 2 retry; `feedback_message` передаётся обратно в orchestrator через state |
| `grounded` | `True` / `False` / `None`; `False` не блокирует ответ — только флаг в SSE `done` event |

**Топология графа:**
```
START → input_guardrail
input_guardrail →[blocked]→ END
input_guardrail →[continue]→ semantic_cache_check
semantic_cache_check →[hit]→ END
semantic_cache_check →[miss]→ load_memory
load_memory → orchestrator
orchestrator → output_guardrail
output_guardrail →[retry]→ orchestrator
output_guardrail →[proceed]→ faithfulness_guardrail
faithfulness_guardrail → END
```

**Запрещено изменять топологию** без одновременного обновления `docs/agent_architecture.md`.

---

## 6. MCP и внешние данные

- Все runtime-данные (Qdrant RAG, yfinance, web search) — только через MCP-сервер (порт 8001, SSE).
- `init_mcp_client()` и `close_mcp_client()` — в lifespan `app/main.py`.
- MCP-инструменты: `search_buffett_letters`, `get_stock_info`, `get_stock_price`, `get_income_statement`, `get_balance_sheet`, `get_cashflow`, `get_stock_history`, `get_earnings_estimate`, `get_institutional_holders`, `get_insider_transactions`, `get_stock_news`, `lookup_ticker`, `web_search`, `web_search_news`, `web_search_knowledge` — вызываются через `get_mcp_tools()` из `mcp_client.py`. `market_agent` маршрутизирует к нужным инструментам через `_MARKET_TOOL_MAP`.
- Postgres-кэши (`market_data_cache`, `semantic_cache`) — через `cache` module/service; логику TTL не дублировать в graph nodes.
- `mcp_server/services/` разрешено импортировать только из `mcp_server/` и `scripts/` (offline ingest).

---

## 7. Персистентность и транзакции (Stage 10)

Порядок операций после завершения графа (`messages/service.py` / текущий `chat_service.persist_assistant_turn`):

1. `messages` — INSERT assistant row (`content`, `grounded`, `langfuse_trace_id`)
2. `rag_retrievals` — bulk INSERT по `rag_agent_chunks` из final_state
3. `semantic_cache` — INSERT при отсутствии cache hit
4. `store.aput` — long-term memory per ticker/interest
5. `chats.updated_at` — UPDATE

**Правила транзакций:**
- `session.commit()` — в service или router, никогда в repository.
- LangGraph tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `store`, `store_vectors`) — только через LangGraph Python API, не raw SQL.
- Qdrant — только чтение в runtime (через MCP); запись только в `scripts/`.

---

## 8. API-контракт (7 эндпоинтов)

Ровно 7 публичных эндпоинтов согласно `docs/api_endpoints.md`. Добавление новых требует обновления docs.

| Метод | Путь |
|-------|------|
| POST | `/users` |
| GET | `/users/{user_id}` |
| POST | `/chats` |
| GET | `/chats/{chat_id}` |
| GET | `/chats/{chat_id}/messages` |
| POST | `/chats/{chat_id}/messages` (SSE) |
| GET | `/health` |

**SSE-события:** `token`, `blocked`, `done`. `done` всегда последний.
**Запрещено:** добавлять `/invoke`, принимать client-supplied `thread_id`, дублировать эндпоинты.

---

## 9. Антипаттерны — запрещено

- Router вызывает Repository напрямую для нетривиального use-case
- `session.commit()` внутри repository-метода
- Импорт `mcp_server.*` из `app/` (кроме `scripts/`)
- `AsyncSession` или прямые SQLAlchemy-вызовы внутри LangGraph nodes или tool functions
- Промпты и routing-логика графа в `gateways.py`
- `chat_history: list[str]` в `ZimShireState` (история уже в `state["messages"]` через checkpointer)
- Клиентский `thread_id` в API
- Изменение топологии графа без обновления `docs/agent_architecture.md`
- Новые публичные эндпоинты без обновления `docs/api_endpoints.md`

---

## 10. План поэтапного рефакторинга

Не делать big-bang. При работе над каждым доменом следовать порядку:

1. `core/database.py` (слить дубли) + `core/exceptions.py` + `api/deps.py`
2. `modules/users/` + `UserService` (убрать прямой repo из router)
3. `modules/chats/` + `ChatService`
4. `modules/messages/` + `MessageService`; вынести `_stream_turn` из router в service
5. `modules/cache/` + `CacheService` + gateway для graph nodes
6. Перенос `app/graph/` → `modules/agents/` без изменения логики графа
7. Split `app/models/models.py` по доменам (опционально; с re-export для Alembic)

При рефакторинге шага N не ломать работающий код шагов до N.

---

## 11. Код-стайл (обязательно для агента)

- Без emoji в коде и комментариях.
- Не создавать README и документацию без явной просьбы пользователя.
- Минимальный diff — не рефакторить несвязанный код в той же задаче.
- Коммиты только по явному запросу пользователя.
- Комментарии только для неочевидной бизнес-логики или технических ограничений.

---

## 12. Обязательная самопроверка и верификация

**Правило:** задача не считается выполненной, пока агент не проверил результат сам. Без верификации код может «выглядеть правильно», но не работать — пользователь не должен быть единственным feedback loop.

### 12.1 Перед завершением задачи — всегда

1. **Зафиксировать критерии успеха** до или в начале реализации (что должно работать, какие входы/выходы).
2. **Запустить проверки** после изменений — не полагаться только на чтение кода.
3. **Сообщить результат проверки** в ответе: что запускали, что прошло, что упало (с полным текстом ошибки).
4. **Исправлять корневую причину**, не подавлять симптомы (не отключать линтеры, не `try/except: pass`, не заглушки без фикса).

### 12.2 Стратегии верификации (примеры)

| Ситуация | Плохо (без проверки) | Хорошо (с проверкой) |
|----------|----------------------|----------------------|
| Новая функция | «реализуй validateEmail» | «напиши validateEmail; тесты: user@example.com → true, invalid → false, user@.com → false; **запусти тесты после реализации**» |
| Баг / падение сборки | «сборка падает» | «ошибка: [текст]; исправь и **убедись, что сборка/тесты проходят**; устрани причину, не маскируй» |
| API / эндпоинт | «добавь POST /users» | «добавь POST /users; **вызови curl/httpx**, ожидаем 201 и тело по `docs/api_endpoints.md`» |
| Рефакторинг слоёв | «перенеси в service» | «перенеси; **импорт модуля + smoke GET /health**; убедись, что старые сценарии не сломаны» |
| LangGraph / агент | «поправь orchestrator» | «поправь; сверь с чеклистом в `docs/agent_architecture.md` §15; **unit/integration там, где возможно**» |

### 12.3 Что запускать в ZimShire (по типу изменения)

| Тип изменения | Минимальная верификация |
|---------------|-------------------------|
| Любой Python-код | `python -c "import app.main"` или импорт затронутого модуля — без ImportError |
| FastAPI роутеры / сервисы | `GET /health` → `status: ok` (если сервис поднят); иначе — pytest/httpx TestClient на затронутые эндпоинты |
| Новый / изменённый эндпоинт | Запрос по контракту из `docs/api_endpoints.md` (метод, путь, тело, ожидаемый status code) |
| Repository / SQLAlchemy | Импорт + при возможности тест с тестовой БД или мок-сессией |
| LangGraph nodes / tools | Импорт `app.graph.builder`; для логики — тесты по таблице в `docs/agent_architecture.md` §15 |
| MCP / `mcp_server` | Импорт `mcp_server.main`; при изменении tools — `scripts/test_market_tools.py` или аналог |
| Миграции Alembic | `alembic check` или `alembic upgrade head` в dev-окружении (если доступно) |
| Зависимости | `pip install -r requirements.txt` без ошибок после правок |

Если инфраструктура недоступна (нет Postgres/Qdrant/MCP), явно указать это и выполнить **максимально возможную** проверку (импорты, unit-тесты с моками, статический разбор).

### 12.4 Тесты

- При добавлении нетривиальной логики — **добавлять или расширять тесты** (pytest), с конкретными case из задачи или из `docs/agent_architecture.md` §15.
- После реализации — **запускать** `pytest` (или точечно `pytest path/to/test_file.py -k name`).
- Не помечать задачу done, если тесты падают, кроме случая когда пользователь явно принял известный техдолг.

### 12.5 Формат отчёта агента в конце задачи

Краткий блок **Verification** в ответе:

```
Verification:
- [x] import app.main — OK
- [x] pytest tests/test_users.py — 3 passed
- [ ] GET /health — skipped (Postgres not running locally)
```

Если проверка не прошла — исправить и повторить цикл, не останавливаться на «должно работать».

