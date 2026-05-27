# ZimShire — Project Guide for Cursor

AI investment **research** assistant with a Buffett-first lens. Answers questions using shareholder letters (RAG), market data, and web search. **Not** a screener, prediction engine, or financial advisor.

**Hard policy:** Never generate buy/sell recommendations, price targets, or personalized portfolio advice — enforced in `output_guardrail` at every layer.

**Deadline (assignment):** 29 May 2026, 19:00.

---

## Where to look first

| Resource | Purpose |
|----------|---------|
| [`docs/implementation_plan.md`](docs/implementation_plan.md) | **План реализации по этапам 0–12** (сначала API, потом агент) |
| [`.cursor/rules/RULES.mdc`](.cursor/rules/RULES.mdc) | Architecture, layers, LangGraph/MCP rules, **mandatory self-verification** (`alwaysApply`) |
| [`.claude/CLAUDE.md`](.claude/CLAUDE.md) | Extended Claude-oriented reference (gateway, MCP tools detail, checklists) |
| [`docs/api_endpoints.md`](docs/api_endpoints.md) | Canonical HTTP API (7 endpoints), SSE contract |
| [`docs/agent_architecture.md`](docs/agent_architecture.md) | LangGraph state, nodes, guardrails, testing checklist §15 |
| [`docs/assistant_flow.md`](docs/assistant_flow.md) | End-to-end Stages 1–10, DB read/write per stage |
| [`docs/db_schema_reference.md`](docs/db_schema_reference.md) | Postgres ORM + LangGraph tables |
| [`docs/mcp_tools_reference.md`](docs/mcp_tools_reference.md) | All MCP tools (RAG, market, web, UI) |

---

## Stack

| Layer | Technology |
|-------|------------|
| HTTP API | FastAPI (async) + SSE |
| Orchestration | LangGraph `StateGraph` |
| LLM / embeddings | LiteLLM via Zimran gateway (`https://litellm.zimran.net`) |
| Vector DB | Qdrant — collection `buffett_letters` |
| Persistence | Postgres + pgvector (custom tables + LangGraph checkpointer/store) |
| Observability | Langfuse |
| MCP | FastMCP — **separate process** (`mcp_server/`) |

No direct OpenAI/Anthropic/Google SDK keys in `app/`. All LLM calls go through the gateway.

---

## Two-process architecture

| Process | Entry | Port | Role |
|---------|-------|------|------|
| **FastAPI** | `uvicorn app.main:app` | 8000 | REST, SSE, LangGraph, Postgres audit |
| **MCP** | `python -m mcp_server.main` | 8001 | RAG (Qdrant), yfinance, web search |

```text
Web Client → FastAPI → LangGraph → MCP (SSE) → Qdrant / yfinance / SerpApi
                ↓
            Postgres (custom + checkpoints + store)
```

**Rule:** Runtime data access (Qdrant, yfinance, web) lives in `mcp_server/` only. Graph nodes use `app/graph/mcp_client.py`, never `import mcp_server` from `app/` (except `scripts/` for offline ingest).

---

## Quick commands

```bash
# Infrastructure
docker compose up -d          # postgres, qdrant, pgadmin
alembic upgrade head
python scripts/setup_langgraph_tables.py   # LangGraph: checkpoints*, store*

# MCP server (LangGraph / SSE)
python -m mcp_server.main --transport streamable-http --port 8001

# FastAPI
uvicorn app.main:app --reload --port 8000

# MCP for Cursor / Claude Code (stdio)
python -m mcp_server.main

# Offline: letters → Qdrant (see scripts/)
python scripts/upload_to_qdrant.py   # or ingest scripts in repo

# Verification (required after changes — see RULES §12)
python -c "import app.main"
curl http://localhost:8000/health
pytest tests/ -v                   # when tests exist
```

---

## Project layout (current)

```text
zimshire/
├── app/
│   ├── main.py                 # FastAPI app, lifespan (MCP + graph init)
│   ├── core/                   # config, dependencies, prompts, database (duplicate with db/)
│   ├── db/database.py          # AsyncSession — merge into core/ (tech debt)
│   ├── routers/                # users, chats, messages (SSE)
│   ├── services/               # graph_service, chat_service, llm, embedding, langfuse
│   ├── repositories/           # user, chat, message, rag, cache, guardrail
│   ├── models/models.py        # all SQLAlchemy ORM (single file)
│   ├── schemas/                # Pydantic API models
│   └── graph/                  # LangGraph: state, builder, nodes, tools, mcp_client
├── mcp_server/                 # separate package — FastMCP tools
│   ├── main.py
│   ├── core/                   # mcp instance, config
│   ├── rag/                    # search_buffett_letters, Qdrant hybrid search
│   ├── market/                 # yfinance tools
│   ├── search/                 # web_search (SerpApi/DuckDuckGo)
│   └── ui/                     # prefab_ui tools for IDE only — not for LangGraph agent
├── alembic/                    # migrations
├── docs/                       # canonical specs
├── scripts/                    # ingest, chunking, test_market_tools
├── docker-compose.yaml         # postgres, qdrant, pgadmin
├── init.sql
├── requirements.txt
├── .cursor/rules/RULES.mdc     # agent architecture rules
└── cursor.md                   # this file
```

**Target layout:** `app/modules/{users,chats,messages,cache,guardrails,agents}/` — see [`.cursor/rules/RULES.mdc`](.cursor/rules/RULES.mdc) §2–3.

---

## HTTP API (7 endpoints only)

Base URL: `http://localhost:8000`. Full schemas: [`docs/api_endpoints.md`](docs/api_endpoints.md).

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/users` | Create user |
| `GET` | `/users/{user_id}` | User metadata |
| `POST` | `/chats` | Create chat (server generates `chat_id`) |
| `GET` | `/chats/{chat_id}` | Chat metadata |
| `GET` | `/chats/{chat_id}/messages` | Message history |
| `POST` | `/chats/{chat_id}/messages` | Research query — **SSE** (tokens after guardrails) |
| `GET` | `/health` | Postgres + Qdrant + MCP status |

**Do not add:** `/invoke`, client-supplied `thread_id`, or extra public routes without updating docs.

### SSE (`POST .../messages`)

Graph runs to **completion** first; then FastAPI streams approved text.

Events: `token` | `blocked` | `done` (always last).

`done` fields: `message_id`, `grounded` (`true` | `false` | `null`), `sources`, `langfuse_trace_id`, optional `cache_hit`.

---

## Request flow (Stages 1–10)

| Stage | Trigger | Main writes |
|-------|---------|-------------|
| 1 | `POST /users` | `users`, LangGraph `store` profile |
| 2 | `POST /chats` | `chats` |
| 3 | `POST .../messages` (human) | `messages` (human), restore checkpoint |
| 4 | `input_guardrail` | `guardrail_logs`; may END |
| 5 | `semantic_cache_check` | `semantic_cache` R/W; cache hit → skip graph |
| 6 | `load_memory` → `orchestrator` | subagent tools via MCP; `draft_answer` |
| 8 | `output_guardrail` | may retry orchestrator (max 2) |
| 9 | `faithfulness_guardrail` | `grounded`, `sources` |
| 9.5 | FastAPI | SSE token stream |
| 10 | persist | `messages` (assistant), `rag_retrievals`, `semantic_cache`, `store`, `chats.updated_at` |

Multi-turn: skip 1–2; same `chat_id` restores graph via checkpointer.

Details: [`docs/assistant_flow.md`](docs/assistant_flow.md).

---

## LangGraph

### Topology

```text
START → input_guardrail → [blocked] → END
      → semantic_cache_check → [hit] → END
      → load_memory → orchestrator
      → output_guardrail → [retry] → orchestrator (max 2)
                         → [proceed] → faithfulness_guardrail → END
```

### Subagent tools (via MCP)

| Tool | MCP / data |
|------|------------|
| `rag_agent` | `search_buffett_letters` → Qdrant |
| `market_agent` | `get_market_data` + Postgres `market_data_cache` |
| `web_agent` | `web_search` |

### Critical invariants

1. `config["configurable"]["thread_id"]` **===** `str(chat_id)` — never a separate DB column.
2. `thread_id`, `user_id`, `chat_id`, `human_message_id`, `langfuse_trace_id` → **RunnableConfig only**, not in `ZimShireState`.
3. No `AsyncSession` in graph state or tool bodies.
4. No `chat_history: list[str]` in state — use checkpointer `messages`.
5. `rag_retrievals` rows written in **Stage 10** only (after assistant `message_id`).
6. `draft_answer` never sent to client before `output_guardrail` completes.
7. Langfuse trace for **every** request (including cache hits).

Full state spec: [`docs/agent_architecture.md`](docs/agent_architecture.md) §3.

---

## Postgres (custom tables)

| Table | Notes |
|-------|-------|
| `users` | Root identity |
| `chats` | `chat_id` = LangGraph thread (`str(chat_id)`) |
| `messages` | `role`: human \| assistant; `grounded`, `langfuse_trace_id` on assistant |
| `rag_retrievals` | One row per Qdrant point; UK `(message_id, qdrant_collection, qdrant_point_id)` |
| `guardrail_logs` | input \| output \| faithfulness |
| `market_data_cache` | TTL cache for yfinance |
| `semantic_cache` | pgvector query → cached response |

LangGraph-managed (no raw SQL): `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `store`, `store_vectors`.

Schema detail: [`docs/db_schema_reference.md`](docs/db_schema_reference.md).

---

## MCP server (`mcp_server/`)

```bash
python -m mcp_server.main --transport streamable-http --port 8001   # LangGraph
python -m mcp_server.main                                            # stdio (Cursor)
```

**LangGraph agent uses only data tools** (not `*_ui` tools from `mcp_server/ui/`).

Essential tools for orchestrator:

- `search_buffett_letters` — hybrid RAG over `buffett_letters`
- `get_market_data` — yfinance (cache in Postgres from FastAPI side)
- `web_search` — recent news

Full catalog: [`docs/mcp_tools_reference.md`](docs/mcp_tools_reference.md).

---

## Environment variables (root `.env`)

Never commit secrets. Key names:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres (async SQLAlchemy) |
| `QDRANT_URL` | Qdrant HTTP |
| `LITELLM_BASE_URL` | `https://litellm.zimran.net` |
| `LITELLM_API_KEY` | Gateway key |
| `LITELLM_END_USER_ID` | `x-litellm-end-user-id` header |
| `DEFAULT_CHAT_MODEL` | e.g. `gpt-4o-mini` |
| `EMBEDDING_MODEL` | e.g. `text-embedding-3-small` |
| `LANGFUSE_*` | Observability |
| `MCP_BASE_URL` | e.g. `http://localhost:8001` |
| `DUCKDUCKGO_API_KEY` | SerpApi for web search in MCP |

---

## Gateway model whitelist

Use only approved LiteLLM slugs: `gpt-4o-mini`, `gpt-4o`, `claude-haiku-4-5`, `claude-sonnet-4-6`, `gemini-3.1-flash-lite-preview`, `gemini-2.5-flash-lite`, `text-embedding-3-small`.

---

## Architecture rules (summary)

**Call flow:** `Router → Service → Repository | Gateway`

| Layer | Allowed | Forbidden |
|-------|---------|-----------|
| Router | Pydantic, `Depends`, HTTP mapping, SSE | SQL, business logic, direct repo for complex flows |
| Service | Orchestration, `commit` | `Request`/`Response`, `HTTPException` |
| Repository | SQLAlchemy, `flush()` | `commit()`, cross-module business logic |
| Gateway | DTOs between domains / MCP | Prompts, graph routing, SQL |

**Anti-patterns:** import `mcp_server` from `app/`; SQL in graph nodes; router→repo for use-cases; `commit` in repository.

Full rules + migration plan: [`.cursor/rules/RULES.mdc`](.cursor/rules/RULES.mdc).

---

## Mandatory verification (agent)

After **any** code change, verify before marking done. Report a **Verification** block:

```text
Verification:
- [x] python -c "import app.main" — OK
- [x] GET /health — postgres, qdrant, mcp ok
- [ ] pytest — skipped (no DB)
```

| Change type | Minimum check |
|-------------|----------------|
| Python module | Import without error |
| API route | Request per `docs/api_endpoints.md` or TestClient |
| Graph node | Import builder; cases from `docs/agent_architecture.md` §15 |
| MCP tool | `import mcp_server.main` or `scripts/test_market_tools.py` |

Fix root causes; do not suppress errors. See RULES §12.

---

## Refactoring roadmap

1. Merge `app/db/database.py` + `app/core/database.py` → `core/database.py`
2. Add `core/exceptions.py`, `api/deps.py`
3. `UserService`, `ChatService` (remove router→repo)
4. `MessageService` + thin messages router
5. `CacheService` + gateway for graph cache nodes
6. Move `app/graph/` → `modules/agents/`
7. Optional: split `models.py` per domain

---

## External documentation

- Qdrant: https://qdrant.tech/documentation/
- LangGraph persistence / memory: https://docs.langchain.com/oss/python/langgraph/persistence
- Langfuse: https://langfuse.com/docs
- LiteLLM: https://docs.litellm.ai/docs/providers/langgraph

More links: [`docs/links.md`](docs/links.md).

---

## Docker services (`docker-compose.yaml`)

| Service | Port (env) | Image |
|---------|------------|-------|
| postgres | `POSTGRES_PORT` | pgvector/pg16 |
| qdrant | `QDRANT_PORT` | qdrant v1.13.4 |
| pgadmin | `PGADMIN_PORT` | pgAdmin 4 |

FastAPI and MCP are typically run locally or added to compose separately — see `.claude/CLAUDE.md` for full stack notes.
