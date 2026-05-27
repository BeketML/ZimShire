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
      prompts.py                 # all prompts: orchestrator, subagents, guardrails, memory
    services/
      llm.py                     # get_chat_model / get_orchestrator_model / get_subagent_model / get_guardrail_model
      embedding.py               # embed_text(text) → list[float]
      langfuse_service.py        # new_trace, make_callback_handler, observe_graph_state, observe_tool_call
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
        service.py               # list_history, persist_turn, stream_turn
        router.py                # GET + POST /chats/{id}/messages (SSE)
      cache/
        repository.py            # find_similar, upsert_market, list_semantic, list_market
        gateways.py              # lookup_market, store_market, lookup_semantic, write_semantic
      guardrails/
        repository.py            # log, list_for_chat
        gateways.py              # write_guardrail_log — opens own AsyncSessionLocal
      rag_retrievals/
        repository.py            # bulk_create (ON CONFLICT DO NOTHING), list_for_chat
      inspect/
        router.py                # GET /debug/semantic-cache, /debug/market-data-cache,
                                 # /debug/chats/{id}/rag-retrievals, /debug/chats/{id}/guardrail-logs
      chat_history/
        router.py                # GET /users/{id}/memory/long-term, /users/{id}/chats/{id}/memory/short-term
      agents/
        state.py                 # ZimShireState TypedDict
        routing.py               # route_after_input, route_after_cache, route_after_output_guardrail
        builder.py               # build_graph(checkpointer, store) → CompiledGraph
        mcp_client.py            # MultiServerMCPClient; init/close/get_mcp_tools
        mcp_registry.py          # tag-based tool filtering, market cache wrapper, Langfuse tracer
        service.py               # init_graph, close_graph, get_graph, get_store
        gateways.py              # Chat → RunnableConfig; final_state → persist DTO
        schemas.py               # OrchestratorPlan, SubagentPlanItem, SubagentResult
        observability.py         # wrap_node — Langfuse span per LangGraph node
        nodes/
          guardrails.py          # input_guardrail, output_guardrail, faithfulness_guardrail
          cache.py               # semantic_cache_check
          memory.py              # load_memory (AsyncPostgresStore short+long-term)
          orchestrator.py        # planner node with structured output (OrchestratorPlan)
          subagent_runner.py     # run_subagents — parallel asyncio.gather
          synthesizer.py         # synthesizer node — final answer from collected context
        subagents/
          base.py                # run_react_subagent + extract_artifacts (rag/web/market chunks)
          rag_subagent.py
          market_subagent.py
          web_subagent.py
    models/
      models.py                  # central ORM registry for Alembic / FK refs
  mcp_server/                    # separate process (never import from app/)
    main.py
    core/
      mcp.py                    # shared FastMCP instance
      config.py
    rag/tools.py                # search_buffett_letters (hybrid RAG)
    market/tools.py             # 12 yfinance tools
    search/tools.py             # web_search, web_search_news, web_search_knowledge
    ui/                         # prefab_ui DataTable tools (Claude Code)
  scripts/
    ingest_letters.py
  tests/
  docs/
  docker-compose.yaml
```

---

## Quick commands

```bash
# Full stack
docker compose up -d            # postgres, qdrant, mcp (8001), api (8000)
alembic upgrade head
python scripts/ingest_letters.py
pytest tests/ -v

# Local dev (no Docker for app services)
docker compose up -d postgres qdrant
python -m mcp_server.main --transport streamable-http --port 8001
uvicorn app.main:app --reload --port 8000
```

---

## Environment variables

All real values go in root `.env` (never commit). Variable names only:

| Variable | Purpose |
|----------|---------|
| `LITELLM_BASE_URL` | `https://litellm.zimran.net` |
| `LITELLM_API_KEY` | Virtual key from Zimran |
| `LITELLM_END_USER_ID` | Gmail for `x-litellm-end-user-id` header |
| `DEFAULT_CHAT_MODEL` | e.g. `gpt-4o-mini` |
| `EMBEDDING_MODEL` | e.g. `text-embedding-3-small` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse |
| `LANGFUSE_SECRET_KEY` | Langfuse |
| `LANGFUSE_BASE_URL` | Langfuse |
| `DATABASE_URL` | Postgres |
| `QDRANT_URL` | Qdrant |
| `DUCKDUCKGO_API_KEY` | SerpApi/DuckDuckGo key |
| `MCP_BASE_URL` | e.g. `http://localhost:8001` |
| `MCP_PORT` | MCP listen port (default `8001`) |

---

## Gateway models (whitelist)

| Slug | Use |
|------|-----|
| `gpt-4o-mini` | Default guardrails (fast, cheap) |
| `gpt-4o` | Higher-quality chat |
| `claude-haiku-4-5` | Subagents (RAG/market/web ReAct loops) |
| `claude-sonnet-4-6` | Orchestrator planner + synthesizer |
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
orchestrator → run_subagents
run_subagents → synthesizer
synthesizer → output_guardrail
output_guardrail →[retry, retry_count < 3]→ synthesizer
output_guardrail →[proceed]→ faithfulness_guardrail
faithfulness_guardrail → END
```

**Orchestrator** uses `with_structured_output(OrchestratorPlan)` — selects 0–3 subagents, sets `direct_answer_possible` for follow-ups.

**Subagents** run in parallel via `asyncio.gather` in `run_subagents` node:
- `rag_subagent` → `search_buffett_letters` MCP tool
- `market_subagent` → granular yfinance MCP tools, cache-first via `_wrap_market_tool`
- `web_subagent` → `web_search` / `web_search_news` MCP tools

**Guardrails** — lightweight LLM classifiers (`gpt-4o-mini`, single JSON call each):
- `input_guardrail`: off-topic / injection check; fails open on LLM error
- `output_guardrail`: buy/sell/price-target safety + factual consistency; max 2 retries; safe fallback on exhaustion
- `faithfulness_guardrail`: grounding check against `rag_agent_chunks`; `grounded=None` when RAG not invoked

---

## Graph state (`ZimShireState`)

```python
class ZimShireState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    query: NotRequired[str]
    user_profile: NotRequired[dict]
    subagent_plan: NotRequired[dict]          # serialised OrchestratorPlan
    subagent_results: NotRequired[list[dict]]
    collected_context: NotRequired[dict]       # {"rag": str, "market": str, "web": str}
    rag_agent_chunks: NotRequired[list[dict]]
    rag_invoked: NotRequired[bool]
    web_agent_sources: NotRequired[list[dict]]
    draft_answer: NotRequired[str]
    grounded: NotRequired[bool | None]
    sources: NotRequired[list[dict]]
    feedback_message: NotRequired[str | None]
    retry_count: NotRequired[int]
    cache_hit: NotRequired[bool]
    input_blocked: NotRequired[bool]
    input_blocked_reason: NotRequired[str | None]
    output_blocked: NotRequired[bool]
    output_blocked_reason: NotRequired[str | None]
    output_rewritten: NotRequired[bool]
```

**NOT in state** (goes in `RunnableConfig["configurable"]`): `thread_id`, `user_id`, `chat_id`, `model`, `human_message_id`, `langfuse_trace_id`.

---

## Critical invariants

1. **`config["configurable"]["thread_id"]` === `str(chat_id)`** — derived from chat PK.
2. `rag_agent_chunks` live in graph state; **`rag_retrievals` rows written in FastAPI Stage 10 only** (after `assistant_message_id` exists).
3. **`grounded = false`** when `rag_invoked` but chunks empty or fewer than 2 strong hits (score ≥ 0.75).
4. MCP tools = data only. Guardrails, `grounded`, synthesis stay in FastAPI + LangGraph.
5. **Direct import of anything under `mcp_server/` in `app/` is forbidden.**
6. **`draft_answer` never reaches the client before `output_guardrail` completes.**
7. **Langfuse trace created for every request** — including cache hits.
8. Market cache write: MCP returns `list[{type, text}]` blocks — parse text before `isinstance(result, dict)` check in `_wrap_market_tool`.

---

## API surface (13 endpoints)

| Method | Path | Action |
|--------|------|--------|
| `POST` | `/users` | Create user (body optional) |
| `GET` | `/users/{user_id}` | Get user metadata |
| `POST` | `/chats` | Create chat |
| `GET` | `/chats/{chat_id}` | Chat metadata |
| `GET` | `/chats/{chat_id}/messages` | Conversation history |
| `POST` | `/chats/{chat_id}/messages` | Streaming research turn (SSE) |
| `GET` | `/users/{user_id}/memory/long-term` | Long-term user profile from store |
| `GET` | `/users/{user_id}/chats/{chat_id}/memory/short-term` | Recent turn pairs from checkpoint |
| `GET` | `/debug/semantic-cache` | Inspect semantic cache rows |
| `GET` | `/debug/market-data-cache` | Inspect market TTL cache rows |
| `GET` | `/debug/chats/{chat_id}/rag-retrievals` | RAG chunks for a chat |
| `GET` | `/debug/chats/{chat_id}/guardrail-logs` | Guardrail decisions for a chat |
| `GET` | `/health` | Postgres + Qdrant + MCP health |

SSE events: `token`, `blocked`, `error`, `done`. `done` always last.

Done event shape:
```json
{ "type": "done", "message_id": "uuid", "grounded": true, "sources": [...], "langfuse_trace_id": "...", "cache_hit": false }
```

---

## Request flow (stages)

| Stage | What |
|-------|------|
| 1 | `POST /users` → `users` table |
| 2 | `POST /chats` → `chats` row |
| 3 | Human message → `messages` (human); restore checkpoint |
| 4 | `input_guardrail` → `guardrail_logs`; may END early |
| 5 | `semantic_cache_check` → optional skip graph; Langfuse trace created even on hit |
| 6 | `load_memory` → `orchestrator` (OrchestratorPlan) |
| 6.5 | `run_subagents` — parallel RAG/market/web |
| 7 | `synthesizer` produces full `draft_answer` |
| 8 | `output_guardrail` → `guardrail_logs`; may rewrite |
| 9 | `faithfulness_guardrail` → `grounded`, `sources` |
| 9.5 | FastAPI streams approved `draft_answer` as SSE tokens |
| 10 | Persist: `messages` (assistant), `rag_retrievals`, `semantic_cache`, `store.aput`, `chats.updated_at` |

---

## Postgres custom tables

| Table | Key notes |
|-------|-----------|
| `users` | `user_id` UUID PK |
| `chats` | `chat_id` PK = LangGraph `thread_id` |
| `messages` | `role` human/assistant; `grounded` + `langfuse_trace_id` on assistant rows |
| `rag_retrievals` | One row per Qdrant point; UK `(message_id, qdrant_collection, qdrant_point_id)` |
| `guardrail_logs` | `guardrail_type` ∈ {input, output, faithfulness}; `result` ∈ {passed, blocked} |
| `market_data_cache` | TTL 1h keyed by `(ticker, data_type)`; UK `uq_market_cache_ticker_type` |
| `semantic_cache` | pgvector `query_embedding`; similarity threshold 0.92; TTL 7d |

**LangGraph-managed (no direct SQL):** `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `store`, `store_vectors`.

---

## Qdrant — Buffett letters

- Collection: `buffett_letters`, cosine distance
- Vector spaces: `dense` (1536, text-embedding-3-small), `sparse` (BM25), `multi` (ColBERT dim=96)
- Chunk size: 800–1200 tokens, overlap 100–150 tokens
- Point ID: `uuid5(namespace, f"{letter_year}:{chunk_index}")` — deterministic
- Payload fields: `letter_year`, `chunk_index`, `text`, `source_file`
- Search result fields: `letter_year`, `passage_snippet`, `similarity_score`, `rerank_score`, `qdrant_point_id`
- **NEVER run `docker compose down -v`** — destroys `qdrantdata` volume with all indexed chunks

---

## Coding rules

- Match existing patterns when adding code; minimal diff per change.
- Commits only when explicitly asked.
- No comments unless the WHY is non-obvious.
- No emoji in code or comments.
- Do not import `mcp_server.*` from `app/` (forbidden at runtime).
- `AsyncSession` never passed into LangGraph nodes or tool functions.
- Prompts live in `app/core/prompts.py` — not inline in node files.
- Market cache write must handle MCP list content blocks: extract `block["text"]` and `json.loads()` before `isinstance(result, dict)`.

---

## Verification checklist (after any change)

```bash
python -c "import app.main"          # no ImportError
pytest tests/ -v                     # 16+ passed
curl http://localhost:8000/health    # {"status":"ok",...}
```

End-to-end smoke:
- RAG query → `done.grounded` not null, `GET /debug/chats/{id}/rag-retrievals` has rows
- Same query twice → `done.cache_hit: true` on second call
- Market query (fresh ticker) → `GET /debug/market-data-cache` has row
- Personal advice query → `{"type":"blocked"}` SSE event
