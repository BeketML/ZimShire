# Q&A and runtime configuration

## Original Q&A (Zimran)

**Question:** Will I get a virtual API key? Does LiteLLM mean dropping raw SDKs in favor of LangGraph?

**Answer:**

- Yes — virtual key with ~$20 daily budget; model list comes with the key.
- SDK choice is flexible; what matters is `base_url` and request headers.
- Agent framework is flexible; **LangGraph is preferred** but not mandatory.

---

## Project stack (this repo)

| Layer | Choice | Role |
|-------|--------|------|
| **Orchestration** | [LangGraph](https://docs.langchain.com/oss/python/langgraph/quickstart) | Memory load + orchestrator with RAG/market/web subagent tools (MCP), guardrails, checkpointing |
| **LLM access** | [LiteLLM](https://docs.litellm.ai/) via Zimran gateway | Provider-agnostic chat, orchestrator ReAct loop, embeddings — no direct OpenAI/Anthropic/Google SDK keys |
| **HTTP API** | FastAPI (async + SSE) | 7 REST endpoints; SSE streaming of guardrail-approved text after graph completion |
| **Vector DB** | Qdrant | Buffett letters RAG (accessed via MCP tool) |
| **Observability** | Langfuse | Traces per user message — including cache hits |
| **MCP** | FastMCP | Separate process; SSE transport for internal graph calls (concurrent-safe); stdio for Cursor |

All LLM and embedding calls go through **`https://litellm.zimran.net`** with header **`x-litellm-end-user-id`** (your Gmail for budget tracking). Graph nodes receive `model` from chat config / `DEFAULT_CHAT_MODEL`.

---

## Available models (gateway whitelist)

Use only these model slugs when calling the gateway (chat or embeddings):

| Model | Typical use |
|-------|-------------|
| `gpt-4o-mini` | Default chat (fast, cheap) |
| `gpt-4o` | Higher-quality chat |
| `claude-haiku-4-5` | Chat |
| `claude-sonnet-4-6` | Chat |
| `gemini-3.1-flash-lite-preview` | Chat |
| `gemini-2.5-flash-lite` | Chat |
| `text-embedding-3-small` | RAG ingest and query embeddings |

Runtime override: `POST /chats/{chat_id}/messages` body field `model` must stay within this list.

---

## Secrets and environment variables

**All sensitive values live in the project root `.env` file (not committed to git).** Do not copy real keys into markdown or source code.

| Variable | Purpose |
|----------|---------|
| `LITELLM_BASE_URL` | Gateway base URL (`https://litellm.zimran.net`) |
| `LITELLM_API_KEY` | Virtual API key from Zimran |
| `LITELLM_END_USER_ID` | Gmail for `x-litellm-end-user-id` header |
| `DEFAULT_CHAT_MODEL` | Default slug, e.g. `gpt-4o-mini` |
| `EMBEDDING_MODEL` | e.g. `text-embedding-3-small` |
| `OPENAI_API_BASE` | Optional alias for OpenAI-compatible clients (`.../v1`) |
| `OPENAI_API_KEY` | Optional alias (same value as `LITELLM_API_KEY`) |
| `LANGFUSE_PUBLIC_KEY` | Langfuse tracing |
| `LANGFUSE_SECRET_KEY` | Langfuse tracing |
| `LANGFUSE_BASE_URL` | Langfuse host |

Additional variables (`DATABASE_URL`, `QDRANT_URL`, `DUCKDUCKGO_API_KEY`, etc.) are documented in [implementation_plan.md](implementation_plan.md) and [.env.example](../.env.example).

Copy from `.env.example` (if present) and fill in your own values locally.

---

## Integration pattern (no secrets in code)

OpenAI-compatible client pointed at the gateway (values from `os.environ` / `pydantic-settings`):

```python
from langchain_openai import ChatOpenAI
from app.config import settings

model = ChatOpenAI(
    model=settings.default_chat_model,  # e.g. gpt-4o-mini
    openai_api_key=settings.litellm_api_key,
    openai_api_base=settings.litellm_base_url,
    default_headers={
        "x-litellm-end-user-id": settings.litellm_end_user_id,
    },
)

# Pass `model` into LangGraph nodes (orchestrator, guardrails, etc.)
```

Alternatively: `langchain-litellm` / `litellm.completion` with the same `api_base`, `api_key`, and `extra_headers`.

---

## Gateway contract (reference)

| Setting | Value |
|---------|--------|
| Base URL | `https://litellm.zimran.net` |
| Auth | Virtual API key in `LITELLM_API_KEY` |
| Required header | `x-litellm-end-user-id: <your Gmail>` |
| Budget | ~$20/day (per Zimran) |

---

## MCP transport

Two transport modes depending on client:

| Client | Transport | Address / Command |
|--------|-----------|-------------------|
| LangGraph graph (internal) | SSE / streamable HTTP | `http://mcp:8001` (docker) or `http://localhost:8001` (local) |
| Cursor / Claude Code | stdio | `python -m mcp_server.main` (spawned by Cursor) |

**Why SSE for internal use:** stdio transport is a single stdin/stdout pipe — not safe for concurrent FastAPI requests. SSE allows multiple simultaneous graph executions to call the MCP server without conflicts.

**`.env` variable for internal URL:**
```
MCP_BASE_URL=http://localhost:8001   # local dev
# MCP_BASE_URL=http://mcp:8001      # docker
```

`app/graph/mcp_client.py` reads `MCP_BASE_URL` via `app/core/config.py`.

**Web search:** `DUCKDUCKGO_API_KEY` in `.env` — used only in `mcp_server/services/search.py` (not in the FastAPI app).

**App must not import data tools directly:** Qdrant, yfinance, and web search live only in `mcp_server/services/` and are exposed via MCP tools (`search_buffett_letters`, `get_market_data`, `web_search`). The FastAPI app calls them only through `mcp_client` over SSE.
