# ZimShire Agent Architecture

Technical reference for the LangGraph multi-agent research system.

**Related docs:**

- [assistant_flow.md](assistant_flow.md) — end-to-end request lifecycle and DB read/write per stage
- [db_schema_reference.md](db_schema_reference.md) — Postgres, Qdrant, LangGraph table schemas
- [api_endpoints.md](api_endpoints.md) — HTTP API and SSE event shapes

---

## 1. Overview

ZimShire answers investment research questions through a **Buffett-first lens**, combining:

- Warren Buffett shareholder letters (RAG over Qdrant via MCP)
- Live market data (yfinance via MCP, cached in Postgres)
- Current web search (DuckDuckGo via MCP)

The intelligence layer is implemented as **one compiled LangGraph `StateGraph`** with a ReAct orchestrator that dynamically calls three subagent tools. MCP server runs as a **separate process** and is consumed both by LangGraph (via SSE) and external clients (Cursor, Claude Code).

---

## 2. Two-Process Architecture

| Process | Entry point | Port | Responsibility |
|---|---|---|---|
| **FastAPI** | `uvicorn app.main:app` | 8000 | REST API, SSE streaming, LangGraph execution, Postgres audit |
| **MCP (FastMCP)** | `python -m mcp_server.main` | 8001 | Three data tools: RAG, market, web search |

**Rule:** All data access (Qdrant, yfinance, web search) lives exclusively in `mcp_server/services/`. Graph nodes and subagent tools never import these directly — they always go through `mcp_client.py` via SSE transport.

```mermaid
flowchart LR
    WebClient[Web_Client]
    MCPClient[MCP_Client_Cursor]
    API[FastAPI]
    MCPProc[MCP_FastMCP_8001]
    Graph[LangGraph]
    PG[(Postgres)]
    QD[(Qdrant)]

    WebClient -->|POST messages SSE| API
    MCPClient -->|stdio or SSE| MCPProc
    API --> Graph
    Graph -->|subagent tools| MCPProc
    MCPProc --> QD
    API --> PG
    Graph --> PG
```

---

## 3. Graph State (`ZimShireState`)

All nodes return partial dicts. LangGraph merges updates into full state. Conversation history uses `add_messages` reducer so new messages append without overwriting prior turns.

```python
from typing import Annotated, NotRequired
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ZimShireState(TypedDict):
    # --- Core ---
    messages: Annotated[list[BaseMessage], add_messages]
    query: str

    # --- Memory context (load_memory) ---
    user_profile: NotRequired[dict]
    # Structured long-term user profile from store, e.g.:
    # {
    #   "tracked_companies": ["AAPL", "NVDA"],
    #   "research_interests": ["moat analysis", "capital allocation"],
    # }

    # --- Collected context (subagent results) ---
    # Explicit dict so each subagent writes to its own key.
    # Easier to debug than separate top-level fields per source.
    collected_context: NotRequired[dict]
    # Keys populated by subagent tools via closure accumulator:
    # {
    #   "rag":     str,          # formatted Buffett letter passages
    #   "market":  str,          # formatted yfinance JSON
    #   "web":     str,          # formatted search snippets
    # }

    # --- Raw subagent artifacts (for faithfulness + audit) ---
    rag_agent_chunks: NotRequired[list[dict]]   # raw: letter_year, passage_snippet, similarity_score, qdrant_point_id
    rag_invoked: NotRequired[bool]              # early-exit signal for faithfulness_guardrail
    web_agent_sources: NotRequired[list[dict]]  # raw: title, url, snippet

    # --- Orchestrator result ---
    draft_answer: NotRequired[str]
    grounded: NotRequired[bool | None]          # None if RAG not invoked
    sources: NotRequired[list[dict]]            # citations for SSE done event

    # --- Output guardrail feedback loop ---
    feedback_message: NotRequired[str | None]   # Guardrail critique written back to orchestrator
    retry_count: NotRequired[int]               # Incremented on each guardrail-triggered retry

    # --- Guardrail flags ---
    cache_hit: NotRequired[bool]
    input_blocked: NotRequired[bool]
    input_blocked_reason: NotRequired[str | None]
    output_blocked: NotRequired[bool]
    output_blocked_reason: NotRequired[str | None]
    output_rewritten: NotRequired[bool]
```

### Field reference

| Section | Field | Set by | Purpose |
|---|---|---|---|
| Core | `messages` | FastAPI + orchestrator | Thread; restored by checkpointer each turn |
| Core | `query` | `input_guardrail` | Latest user text for embed, store, tools |
| Memory | `user_profile` | `load_memory` | Structured long-term profile from `store` |
| Collected | `collected_context` | subagent tools (closure) | Named dict of formatted results per source |
| Raw | `rag_agent_chunks` | `rag_agent` tool | Raw Qdrant hits for faithfulness scoring + `rag_retrievals` audit |
| Raw | `rag_invoked` | orchestrator return | `True` if `rag_agent` ran this turn |
| Raw | `web_agent_sources` | `web_agent` tool | Raw search hits for `rag_retrievals`-equivalent audit |
| Orchestrator | `draft_answer` | orchestrator or cache | Final text before guardrail pass |
| Orchestrator | `grounded` | `faithfulness_guardrail` or cache | Letter grounding flag |
| Orchestrator | `sources` | `faithfulness_guardrail` or cache | `letter_year`, `passage`, `score`, `point_id` |
| Feedback | `feedback_message` | `output_guardrail` | Critique text sent back when guardrail fails |
| Feedback | `retry_count` | `output_guardrail` | Loop counter; caps at 2 retries |
| Guardrail | `cache_hit` | `semantic_cache_check` | Skip orchestrator when true |
| Guardrail | `input_blocked` / `input_blocked_reason` | `input_guardrail` | Early exit |
| Guardrail | `output_blocked` / `output_blocked_reason` | `output_guardrail` | Rewrite path |
| Guardrail | `output_rewritten` | `output_guardrail` | Answer was replaced |

### Why `collected_context` replaces separate `*_result` fields

Previously the state had three flat string fields: `rag_agent_result`, `web_agent_result`, `market_agent_result`. Consolidating them into `collected_context: dict` has two advantages:

1. **Debuggability** — a single state key shows at a glance which sources were populated for a given turn.
2. **Extensibility** — adding a fourth data source (e.g. SEC filings) only requires a new key, not a new top-level state field.

Raw artifacts (`rag_agent_chunks`, `web_agent_sources`) remain as separate top-level fields because they serve a different purpose: structured data consumed by guardrails and the DB persist layer, not the LLM.

### What is NOT in state

`thread_id`, `user_id`, `chat_id`, `model`, `provider`, `human_message_id`, `langfuse_trace_id` live in `RunnableConfig["configurable"]` — stable across checkpoint serialization.

```python
config = {
    "configurable": {
        "thread_id": str(chat.chat_id),
        "user_id": str(chat.user_id),
        "chat_id": str(chat.chat_id),
        "model": chat.model,
        "provider": chat.provider,
        "human_message_id": str(human_message.message_id),
    }
}
```

### Why `chat_history: list[str]` is NOT in state

`state["messages"]` is restored automatically by the LangGraph checkpointer on every turn. Duplicating it as a formatted string list in state wastes context window and creates inconsistency. `load_memory` formats history for the system prompt on-the-fly but does not store the result in state.

---

## 4. Graph Topology

### Nodes

| Node | Purpose |
|---|---|
| `input_guardrail` | Block off-topic queries and prompt injection |
| `semantic_cache_check` | Return cached answer for semantically similar queries |
| `load_memory` | Load structured user profile from store; format short-term context |
| `orchestrator` | ReAct loop calling `rag_agent`, `market_agent`, `web_agent` tools |
| `output_guardrail` | Block or rewrite buy/sell recommendations; write feedback for retry |
| `faithfulness_guardrail` | Set `grounded` and `sources` from `rag_agent_chunks` vs `draft_answer` |

### Routing

```python
def route_after_input(state: ZimShireState) -> str:
    return "blocked" if state.get("input_blocked") else "continue"

def route_after_cache(state: ZimShireState) -> str:
    return "hit" if state.get("cache_hit") else "miss"

def route_after_output_guardrail(state: ZimShireState) -> str:
    """
    If the output guardrail found a violation AND we have retries left,
    send the orchestrator back for a self-correcting rewrite.
    Otherwise proceed to faithfulness check.
    """
    if state.get("output_blocked") and state.get("retry_count", 0) < 2:
        return "retry"
    return "proceed"
```

### Edge map

```
START → input_guardrail
input_guardrail →[blocked]→ END
input_guardrail →[continue]→ semantic_cache_check
semantic_cache_check →[hit]→ END
semantic_cache_check →[miss]→ load_memory
load_memory → orchestrator
orchestrator → output_guardrail
output_guardrail →[retry]→ orchestrator      # self-correction loop (max 2 retries)
output_guardrail →[proceed]→ faithfulness_guardrail
faithfulness_guardrail → END
```

```mermaid
flowchart TB
    START([START])
    ING[input_guardrail]
    CACHE{semantic_cache_check}
    MEM[load_memory]
    ORCH[orchestrator]
    OUTG[output_guardrail]
    FAITH[faithfulness_guardrail]
    ENDNODE([END])

    START --> ING
    ING -->|blocked| ENDNODE
    ING -->|continue| CACHE
    CACHE -->|hit| ENDNODE
    CACHE -->|miss| MEM
    MEM --> ORCH
    ORCH --> OUTG
    OUTG -->|retry| ORCH
    OUTG -->|proceed| FAITH
    FAITH --> ENDNODE
```

### Graph builder

```python
from langgraph.graph import END, START, StateGraph

from app.graph.state import ZimShireState
from app.graph.routing import route_after_cache, route_after_input, route_after_output_guardrail
from app.graph.nodes.guardrails import (
    faithfulness_guardrail,
    input_guardrail,
    output_guardrail,
)
from app.graph.nodes.memory import load_memory
from app.graph.nodes.orchestrator import orchestrator
from app.graph.nodes.cache import semantic_cache_check


def build_graph(checkpointer, store):
    builder = StateGraph(ZimShireState)

    builder.add_node("input_guardrail", input_guardrail)
    builder.add_node("semantic_cache_check", semantic_cache_check)
    builder.add_node("load_memory", load_memory)
    builder.add_node("orchestrator", orchestrator)
    builder.add_node("output_guardrail", output_guardrail)
    builder.add_node("faithfulness_guardrail", faithfulness_guardrail)

    builder.add_edge(START, "input_guardrail")
    builder.add_conditional_edges(
        "input_guardrail",
        route_after_input,
        {"blocked": END, "continue": "semantic_cache_check"},
    )
    builder.add_conditional_edges(
        "semantic_cache_check",
        route_after_cache,
        {"hit": END, "miss": "load_memory"},
    )
    builder.add_edge("load_memory", "orchestrator")
    builder.add_conditional_edges(
        "output_guardrail",
        route_after_output_guardrail,
        {"retry": "orchestrator", "proceed": "faithfulness_guardrail"},
    )
    builder.add_edge("orchestrator", "output_guardrail")
    builder.add_edge("faithfulness_guardrail", END)

    return builder.compile(checkpointer=checkpointer, store=store)
```

---

## 5. Node Specifications

### 5.1 `input_guardrail`

**Reads:** `state["messages"][-1].content` (also used to set `query`)

**Approach:** Two-layer pipeline using **Guardrails AI** validators. No custom LLM prompt needed — Guardrails AI Hub provides purpose-built validators for both concerns.

**What it catches:**

| Category | Validator | How |
|---|---|---|
| Prompt injection / jailbreak | `DetectJailbreak` | ML classifier trained on jailbreak dataset — no LLM call |
| Off-topic queries | `RestrictToTopic` | LLM-based topic classifier |
| Personal advice requests | `RestrictToTopic` (invalid_topics) | Caught as off-topic for ZimShire |

**Why two validators in sequence:** `DetectJailbreak` is ML-based — runs in milliseconds with no LLM call. It fires first so injection attempts are blocked before spending tokens on topic classification.

**Allowed through:** Any genuine research question about companies, markets, Buffett's letters, valuations, moats, financials — including simple phrasing like "Is Coca-Cola a good business?".

**Dependencies:**
```bash
pip install guardrails-ai
guardrails hub install hub://guardrails/detect_jailbreak
guardrails hub install hub://tryolabs/restricttotopic
```

**Implementation:**

```python
from guardrails.hub import DetectJailbreak, RestrictToTopic
from guardrails import Guard, OnFailAction

# Built once at app startup (lifespan), reused across requests
input_guard = Guard().use_many(
    DetectJailbreak(on_fail=OnFailAction.EXCEPTION),
    RestrictToTopic(
        valid_topics=[
            "investment research", "stock analysis", "Warren Buffett",
            "company valuation", "financial markets", "economic moats",
            "shareholder letters", "capital allocation", "intrinsic value",
        ],
        invalid_topics=[
            "cooking", "weather", "politics", "entertainment",
            "personal investment advice", "portfolio recommendations",
        ],
        llm_callable="gpt-4o-mini",
        on_fail=OnFailAction.EXCEPTION,
    ),
)


async def input_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    query = state["messages"][-1].content

    try:
        # Guardrails AI runs validators in sequence; raises on first failure
        await asyncio.to_thread(input_guard.validate, query)

        await write_guardrail_log(config, guardrail_type="input", result="passed")
        return {"query": query, "input_blocked": False, "input_blocked_reason": None}

    except Exception as e:
        reason = str(e)
        await write_guardrail_log(
            config, guardrail_type="input",
            result="blocked", blocked_reason=reason,
        )
        safe_message = AIMessage(
            content=(
                "I can only help with investment research questions grounded in "
                "Warren Buffett's philosophy and public market data. "
                "Try asking: 'How did Buffett evaluate Coca-Cola's moat?' or "
                "'What does Apple's P/E ratio say about its margin of safety?'"
            )
        )
        return {
            "query": query,
            "input_blocked": True,
            "input_blocked_reason": reason,
            "messages": [safe_message],
        }
```

**Flow:**
```
query arrives
    │
    ▼
[DetectJailbreak — ML, no LLM call]
    ├── injection detected → Exception → blocked → END
    └── clean
            │
            ▼
        [RestrictToTopic — LLM gpt-4o-mini]
            ├── off-topic → Exception → blocked → END
            └── valid investment research → pass → semantic_cache
```

**Writes to state:** `query: str`, `input_blocked: bool`, `input_blocked_reason: str | None`

**Writes to DB:** `guardrail_logs` row with `guardrail_type="input"`

**On block:** adds safe `AIMessage` to state with example questions, routes to END.

---

### 5.2 `semantic_cache_check`

**Reads:** `state["query"]` → embeds → pgvector similarity search on `semantic_cache`

**Threshold:** cosine similarity ≥ 0.92

**On hit:** returns `cache_hit=True`, `draft_answer`, `sources`, `grounded` from cache. Graph ends without touching orchestrator or MCP.

**On miss:** returns `cache_hit=False`.

**SQL pattern:**

```sql
SELECT id, cached_response, sources, grounded
FROM semantic_cache
WHERE (expires_at IS NULL OR expires_at > NOW())
ORDER BY query_embedding <=> :embedding
LIMIT 1;
```

---

### 5.3 `load_memory`

**Reads:** `state["messages"]` (for short-term context formatting), `store` (for long-term user profile)

**Long-term lookup:** `store.asearch(("users", user_id, "interests"), query=state["query"], limit=5)`

**Writes to state:** `user_profile: dict`

```python
# user_profile shape
{
    "tracked_companies": ["AAPL", "NVDA"],        # tickers seen in past turns
    "research_interests": ["moat analysis"],       # topics extracted from past queries
}
```

**Does NOT store `chat_history` in state** — history is already in `state["messages"]` restored by checkpointer. The formatted string is built inline for the orchestrator system prompt only.

```python
def build_system_prompt(state: ZimShireState) -> str:
    profile = state.get("user_profile") or {}
    companies = ", ".join(profile.get("tracked_companies", [])) or "(none)"
    interests  = ", ".join(profile.get("research_interests", [])) or "(none)"

    history_lines = []
    for m in state["messages"][-20:]:
        role = "User" if m.type == "human" else "Assistant"
        history_lines.append(f"{role}: {m.content}")

    feedback = state.get("feedback_message")
    feedback_section = (
        f"\n\n## Guardrail feedback — rewrite required\n{feedback}"
        if feedback else ""
    )

    return (
        "## User profile (long-term)\n"
        f"- Tracked companies: {companies}\n"
        f"- Research interests: {interests}\n"
        "\n## Conversation (short-term)\n"
        + "\n".join(history_lines)
        + feedback_section
    )
```

Note: when `feedback_message` is present (retry path), the system prompt includes the guardrail critique so the orchestrator corrects its answer without rerunning tool calls.

---

### 5.4 `orchestrator`

**Core pattern:** ReAct loop via `create_react_agent`. Receives full `messages` + system prompt built from `user_profile`, formatted chat history, and optional guardrail feedback.

**Key design — closure accumulator:**

Subagent tools write raw results into a shared `accumulated` dict and into `collected_context` via closure. After `agent.ainvoke()` completes, the orchestrator node returns everything in one dict — this is the only correct way to propagate tool outputs into LangGraph state without direct mutation.

On a guardrail retry, `collected_context` is already populated from the previous pass. The orchestrator receives it via the system prompt and generates a corrected answer without re-calling MCP tools unless necessary.

```python
async def orchestrator(state: ZimShireState, config: RunnableConfig) -> dict:
    # Inherit context already collected (populated on retry, empty on first pass)
    existing_context = state.get("collected_context") or {}

    accumulated = {
        "rag_chunks": list(state.get("rag_agent_chunks") or []),
        "web_sources": list(state.get("web_agent_sources") or []),
        "collected_context": dict(existing_context),
    }

    tools = build_tools_with_accumulator(accumulated, config)

    llm = get_llm(config)
    agent = create_react_agent(llm, tools)
    result = await agent.ainvoke({
        "messages": [
            SystemMessage(content=build_system_prompt(state)),
            *state["messages"],
        ]
    })

    draft = result["messages"][-1].content

    return {
        "draft_answer": draft,
        "collected_context": accumulated["collected_context"],
        "rag_agent_chunks": accumulated["rag_chunks"],
        "rag_invoked": len(accumulated["rag_chunks"]) > 0,
        "web_agent_sources": accumulated["web_sources"],
        "messages": [AIMessage(content=draft)],
        # Clear feedback after consuming it
        "feedback_message": None,
    }
```

**Why `ainvoke` not `astream`:** Output guardrail and faithfulness guardrail need the complete `draft_answer`. Streaming is handled at the FastAPI layer after the full graph completes.

---

### 5.5 Subagent MCP Tools (tag-based)

Subagents are separate ReAct agents in `app/modules/agents/subagents/`. Each receives MCP tools filtered by FastMCP tags via `app/modules/agents/mcp_registry.py`:

| Subagent | Primary tag | Exclude |
|---|---|---|
| RAG | `rag` | `ui` |
| Market | `market` | `ui` |
| Web | `web` | `ui` |

- Single MCP server (`mcp_server.main`, port 8001) — `init_mcp_client(base_url)` in lifespan.
- `get_agent_tools(agent, data_type=...)` returns LangChain tools from `langchain_mcp_adapters` (no local `@tool` wrappers).
- Market tools optionally wrapped with Postgres cache (`lookup_market` / `store_market`).
- Artifacts (`rag_chunks`, `web_sources`, `market_data`) extracted from `ToolMessage` in `subagents/base.py` after `ainvoke`.

Legacy `build_tools_with_accumulator` in `tools/subagents.py` is removed; orchestrator is planner-only (structured output), subagents run in `run_subagents` node.

#### `rag_agent` (historical reference — orchestrator tool pattern, deprecated)

```python
@tool
async def rag_agent(query: str, years: list[int] | None = None) -> str:
    """Search Buffett shareholder letters for investment philosophy, moats, intrinsic value."""
    hits = await get_mcp_tools()["search_buffett_letters"].ainvoke({
        "query": query, "top_k": 5, "letter_years_filter": years
    })
    accumulated["rag_chunks"].extend(hits)
    formatted = "\n\n".join(
        f"[{h['letter_year']}] score={h['similarity_score']:.3f}\n{h['passage_snippet']}"
        for h in hits
    ) if hits else "No relevant Buffett letter passages found."
    accumulated["collected_context"]["rag"] = formatted
    return formatted
```

| | |
|---|---|
| MCP tool | `search_buffett_letters(query, top_k, letter_years_filter)` |
| Returns to LLM | Formatted passages string |
| State (via return) | `rag_agent_chunks`, `collected_context["rag"]`, `rag_invoked` |

#### `market_agent`

```python
@tool
async def market_agent(tickers: list[str]) -> str:
    """Get live market data: P/E, financials, price for ticker symbols."""
    result = {}
    data_type = "info"
    for ticker in tickers:
        cached = await MarketDataCacheRepo.get_valid(ticker=ticker, data_type=data_type)
        if cached:
            result[ticker] = cached.payload
        else:
            payload = await get_mcp_tools()["get_market_data"].ainvoke({
                "ticker": ticker, "data_type": data_type,
            })
            await MarketDataCacheRepo.upsert(ticker=ticker, data_type=data_type, payload=payload)
            result[ticker] = payload
    text = json.dumps(result, indent=2)[:4000]
    accumulated["collected_context"]["market"] = text
    return text
```

Cache-first: checks `market_data_cache` in Postgres before calling MCP.

#### `web_agent`

```python
@tool
async def web_agent(query: str) -> str:
    """Search the web for recent news and events not covered in Buffett letters."""
    results = await get_mcp_tools()["web_search"].ainvoke({"query": query, "max_results": 5})
    accumulated["web_sources"].extend(results)
    text = "\n".join(f"- {r['title']}: {r['snippet']}" for r in results)
    accumulated["collected_context"]["web"] = text
    return text
```

---

### 5.6 `output_guardrail`

**Reads:** `state["draft_answer"]`, `state["collected_context"]`, `state["user_profile"]`, `state["messages"]`, `state["retry_count"]`

**Approach:** Single LLM call that runs **two independent checks simultaneously** against the full collected context:

- **Check 1 — Factual consistency:** Are all claims in `draft_answer` supported by what the subagents actually found? Compares against RAG context, market data, web results, user profile, and short-term conversation history.
- **Check 2 — Safety compliance:** Does the answer contain buy/sell recommendations, price targets, personalized portfolio advice, or predictions stated as facts? (Hard requirement per ZimShire policy.)

**Why full context, not just draft_answer alone:** An output-only safety check cannot detect factual hallucinations — the orchestrator might correctly avoid buy/sell language but still invent a P/E ratio that doesn't appear in the yfinance data. Passing all `collected_context` + memory lets the classifier catch both classes of violation in one pass.

**What it catches:**

| Check | Category | Examples |
|---|---|---|
| Factual | Invented market data | P/E stated as 28x when yfinance returned 35x |
| Factual | Hallucinated Buffett quote | "In 1995 Buffett wrote..." — not found in RAG context |
| Factual | Misrepresented web news | Wrong earnings date, wrong acquisition price |
| Safety | Buy/sell recommendation | "Buy AAPL", "I recommend selling", "Strong buy" |
| Safety | Explicit price target | "Target price $150", "Fair value is $200" |
| Safety | Personalized portfolio advice | "You should allocate 20% to...", "Given your risk tolerance..." |
| Safety | Prediction as fact | "This stock will go up", "Earnings will beat estimates" |

**What is NOT a violation:**

- Describing what Buffett said or believed (historical/philosophical)
- Presenting market data factually as retrieved ("P/E is 28x per yfinance")
- Discussing valuation frameworks without a specific buy/sell call
- Framing analysis with uncertainty ("Buffett's framework would suggest...")

**System prompt:**

```python
OUTPUT_GUARDRAIL_SYSTEM = """
You are a compliance and factuality guardrail for ZimShire, an AI investment research assistant.

You will receive:
- COLLECTED CONTEXT: everything the research agents found (RAG letters, market data, web search,
  user profile, conversation history)
- DRAFT ANSWER: what the orchestrator wrote based on that context

Run TWO independent checks:

═══ CHECK 1: FACTUAL CONSISTENCY ═══
Are all factual claims in the draft answer traceable to the collected context?
Flag if you find:
- Numbers, prices, ratios, or dates not present in any context source
- Statements attributed to Buffett not found in RAG context
- Market figures (prices, P/E, earnings) not matching market context
- Web facts that were misrepresented or invented

═══ CHECK 2: SAFETY COMPLIANCE ═══
Does the draft answer contain any of the following (HARD violations per ZimShire policy):
1. Direct buy/sell/hold recommendations ("buy AAPL", "sell now", "I recommend holding")
2. Explicit price targets ("target price $150", "fair value is $200", "will reach $X")
3. Personalized portfolio advice ("you should allocate", "given your situation, invest in")
4. Predictions stated as facts ("this stock will go up", "earnings will beat estimates")

CLEAN if the response describes Buffett's philosophy, presents retrieved data factually,
or frames analysis with appropriate uncertainty.

If any violation found, write a specific rewrite instruction so the orchestrator can fix
the answer using only the already-collected context — no new data needed.

Respond ONLY with JSON, no markdown:
{
  "factual_consistent": bool,
  "unsupported_claims": ["claim1", "claim2"],
  "safety_violation": bool,
  "safety_category": "buy_sell" | "price_target" | "portfolio_advice" | "prediction" | null,
  "safety_reason": "explanation or null",
  "feedback": "specific rewrite instruction if any violation, else null"
}
"""
```

**Implementation:**

```python
async def output_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:
    draft = state["draft_answer"]
    retry_count = state.get("retry_count", 0)

    # Build full context for the classifier
    ctx = state.get("collected_context") or {}
    profile = state.get("user_profile") or {}
    history = "\n".join(
        f"{'User' if m.type == 'human' else 'Assistant'}: {m.content}"
        for m in state["messages"][-10:]
    )

    full_context = f"""
=== RAG CONTEXT (Buffett Letters) ===
{ctx.get("rag", "(not used this turn)")}

=== MARKET DATA CONTEXT (yfinance) ===
{ctx.get("market", "(not used this turn)")}

=== WEB SEARCH CONTEXT ===
{ctx.get("web", "(not used this turn)")}

=== USER PROFILE (long-term memory) ===
Tracked companies: {", ".join(profile.get("tracked_companies", [])) or "(none)"}
Research interests: {", ".join(profile.get("research_interests", [])) or "(none)"}

=== CONVERSATION HISTORY (short-term memory) ===
{history}
"""

    llm = get_llm(config)  # cheap model — haiku or gpt-4o-mini
    result = await llm.ainvoke([
        SystemMessage(content=OUTPUT_GUARDRAIL_SYSTEM),
        HumanMessage(content=f"COLLECTED CONTEXT:\n{full_context}\n\nDRAFT ANSWER:\n{draft}"),
    ])
    raw = result.content.strip().replace("```json", "").replace("```", "").strip()
    check = json.loads(raw)

    any_violation = not check["factual_consistent"] or check["safety_violation"]

    if not any_violation:
        await write_guardrail_log(config, guardrail_type="output", result="passed")
        return {"output_blocked": False, "output_rewritten": False, "feedback_message": None}

    # Violation confirmed — determine reason
    if check["safety_violation"]:
        reason = f"[{check['safety_category']}] {check['safety_reason']}"
    else:
        reason = f"[factual] Unsupported claims: {'; '.join(check['unsupported_claims'])}"

    await write_guardrail_log(
        config, guardrail_type="output",
        result="blocked", blocked_reason=reason,
    )

    if retry_count < 2:
        return {
            "output_blocked": True,
            "output_blocked_reason": reason,
            "feedback_message": check["feedback"],
            "retry_count": retry_count + 1,
            # draft_answer NOT replaced — orchestrator will overwrite on retry
        }

    # Retry limit reached — safe fallback
    safe_text = (
        "ZimShire can help you research companies through Buffett's philosophy "
        "and public market data, but cannot provide investment recommendations "
        "or unverified claims. "
        "Try: 'How did Buffett evaluate Coca-Cola's moat?' or "
        "'What does Apple's P/E ratio suggest about margin of safety?'"
    )
    return {
        "output_blocked": True,
        "output_blocked_reason": reason,
        "output_rewritten": True,
        "draft_answer": safe_text,
        "feedback_message": None,
        "retry_count": retry_count + 1,
    }
```

**Flow summary:**

```
draft_answer ready
    │
    ▼
[LLM classifier — full context passed]
    checks: factual_consistent + safety_violation
    │
    ├── no violation ──► passed → faithfulness_guardrail
    │
    └── violation (factual OR safety)
            ├── retry_count < 2
            │       ├── feedback_message = check["feedback"]
            │       ├── retry_count += 1
            │       └── route → orchestrator (rewrites using same collected_context)
            │
            └── retry_count >= 2
                    ├── draft_answer = safe fallback text
                    ├── output_rewritten = True
                    └── route → faithfulness_guardrail
```

**Writes to state:** `output_blocked`, `output_blocked_reason`, `output_rewritten`, `feedback_message`, `retry_count`, optionally `draft_answer` (on fallback).

**Writes to DB:** `guardrail_logs` row with `guardrail_type="output"` on every violation.

---

### 5.7 `faithfulness_guardrail`

**When it runs:** Always — but exits early if `rag_invoked=False`.

**Reads:** `state["rag_agent_chunks"]`, `state["rag_agent_result"]` (via `collected_context["rag"]`), `state["query"]`

**Approach:** **RAGAS `Faithfulness` metric** via LiteLLM gateway. RAGAS performs atomic sentence-level verification — each sentence in the RAG agent's output is independently checked against the retrieved chunks. This is significantly more precise than a similarity score threshold.

**Why RAGAS over score threshold:** Score threshold (`similarity_score >= 0.75`) measures retrieval quality, not faithfulness. A chunk can be highly similar to the query but the RAG agent can still hallucinate a sentence that isn't in that chunk. RAGAS breaks the answer into atomic claims and verifies each one independently.

**Why RAGAS + LiteLLM works:** RAGAS ships a native `LiteLLMStructuredLLM` adapter — it routes all internal LLM calls through the same gateway as the rest of the system. No separate API keys or providers needed.

**RAGAS setup:**
```python
import litellm
from ragas.llms import llm_factory
from ragas.metrics import Faithfulness
from ragas import evaluate
from datasets import Dataset

# Initialised once at app startup (lifespan)
ragas_llm = llm_factory(
    "gpt-4o-mini",
    provider="litellm",
    client=litellm.completion,  # routes through internal gateway
)
faithfulness_metric = Faithfulness(llm=ragas_llm)
```

**What RAGAS does internally:**
```
rag_agent_result (what RAG agent wrote):
  "In his 1988 letter, Buffett argued that moats come from brand loyalty.
   He also noted that management quality is paramount.
   Capital allocation is the single most important metric."

→ Split into atomic sentences:
   S1: "moats come from brand loyalty"
   S2: "management quality is paramount"
   S3: "Capital allocation is the single most important metric"

→ Each sentence embedded → top-k chunks retrieved → LLM classifies:
   S1: found in chunk [1988, score=0.91] → SUPPORTED ✓
   S2: found in chunk [2001, score=0.83] → SUPPORTED ✓
   S3: not found in any chunk           → HALLUCINATED ✗

→ faithfulness_score = 2/3 = 0.67 → grounded_in_letters = False
```

**Implementation:**

```python
async def faithfulness_guardrail(state: ZimShireState, config: RunnableConfig) -> dict:

    # Early exit — RAG not used this turn
    if not state.get("rag_invoked"):
        await write_guardrail_log(config, guardrail_type="faithfulness", result="passed")
        return {"grounded": None, "sources": []}

    chunks = state.get("rag_agent_chunks") or []

    if not chunks:
        await write_guardrail_log(
            config, guardrail_type="faithfulness", result="blocked",
            blocked_reason="RAG invoked but returned no chunks",
        )
        return {"grounded": False, "sources": []}

    rag_result = (state.get("collected_context") or {}).get("rag", "")

    # --- RAGAS faithfulness check ---
    dataset = Dataset.from_dict({
        "question": [state["query"]],
        "answer":   [rag_result],          # what RAG agent wrote
        "contexts": [[c["passage_snippet"] for c in chunks]],
    })

    result = await asyncio.to_thread(
        evaluate, dataset, metrics=[faithfulness_metric]
    )
    score = result["faithfulness"]         # 0.0 → 1.0
    grounded_in_letters = score >= 0.7

    # Build sources from chunks with highest similarity scores
    strong_hits = sorted(chunks, key=lambda c: c["similarity_score"], reverse=True)[:5]
    sources = [
        {
            "letter_year":      h["letter_year"],
            "passage":          h["passage_snippet"],
            "similarity_score": h["similarity_score"],
            "qdrant_point_id":  h["qdrant_point_id"],
        }
        for h in strong_hits
        if h["similarity_score"] >= 0.75
    ]

    await write_guardrail_log(
        config,
        guardrail_type="faithfulness",
        result="passed" if grounded_in_letters else "blocked",
        blocked_reason=None if grounded_in_letters else (
            f"RAGAS faithfulness score {score:.2f} below threshold 0.70"
        ),
    )

    return {
        "grounded": grounded_in_letters,
        "sources": sources if grounded_in_letters else [],
    }
```

**Score threshold:** `>= 0.7` — RAGAS faithfulness is a ratio of supported claims, so 0.7 means at least 70% of sentences in the RAG agent's answer are traceable to retrieved chunks. Below this, the answer is flagged as not grounded.

**What happens when `grounded=False`:** The answer is NOT blocked or rewritten — this is a reporting flag, not a safety gate. The SSE `done` event carries `grounded: false` and `sources: []`. The UI can display a disclaimer. Blocking would require an extra retry loop separate from the output guardrail; for this assignment, transparent reporting is the correct tradeoff.

**Writes to state:** `grounded: bool | None`, `sources: list[dict]`

**Writes to DB:** `guardrail_logs` row with `guardrail_type="faithfulness"`

---

## 6. Grounding Flow (End-to-End)

```
rag_agent tool called
    └─ Qdrant returns hits via MCP
    └─ hits → rag_agent_chunks in state
    └─ formatted text → collected_context["rag"] + orchestrator LLM

orchestrator LLM synthesizes draft_answer using all collected_context

output_guardrail [LLM — full context check]:
    └─ Check 1: draft_answer vs collected_context + user_profile + history
    │       → factual_consistent? unsupported claims?
    └─ Check 2: draft_answer safety
    │       → buy/sell, price targets, portfolio advice, predictions?
    └─ [any violation + retry < 2] → feedback_message → back to orchestrator
    └─ [any violation + retry >= 2] → safe fallback text
    └─ [pass] → faithfulness_guardrail

faithfulness_guardrail [RAGAS Faithfulness via LiteLLM]:
    └─ query + rag_agent_result + rag_agent_chunks → RAGAS evaluate()
    └─ atomic sentence-level verification
    └─ score >= 0.7 → grounded=True, sources=strong_hits
    └─ score < 0.7  → grounded=False, sources=[]

FastAPI persist:
    └─ writes assistant message with grounded flag
    └─ writes rag_retrievals rows (one per chunk)
    └─ writes to semantic_cache (for future hits)
    └─ writes to store (long-term user interests)
```

---

## 7. Short-Term Memory (Multi-Turn)

LangGraph persists `state["messages"]` to Postgres after each node via `AsyncPostgresSaver`. Key is `configurable["thread_id"]` = `str(chat_id)`.

On turn 2, checkpointer restores full message history automatically. `load_memory` formats the last N turns into the system prompt. Orchestrator sees full context.

| Turn | User | Orchestrator behavior |
|---|---|---|
| 1 | How would Buffett view Apple's moat? | calls `rag_agent(query=...)` |
| 2 | Now compare that to banks in 1990 | messages include turn 1; calls `rag_agent(..., years=[1990])` |

**Alignment rule:** FastAPI also writes human/assistant rows to the custom `messages` table for the UI API. Keep graph `messages` and the custom table consistent by always passing the new human message into `astream` input.

---

## 8. Long-Term Memory

Stored in `AsyncPostgresStore` under namespace `("users", user_id, "interests")`.

| Operation | When | API |
|---|---|---|
| Read | `load_memory` node | `store.asearch(namespace, query=state["query"], limit=5)` |
| Write | FastAPI Stage 10 | `store.aput` per ticker / interest |

```python
async def persist_interests(store, user_id: str, state: dict):
    namespace = ("users", user_id, "interests")

    # Extract tickers from market context
    tickers: list[str] = []
    market_text = (state.get("collected_context") or {}).get("market", "")
    if market_text:
        try:
            tickers = list(json.loads(market_text).keys())
        except json.JSONDecodeError:
            pass

    for ticker in tickers:
        await store.aput(namespace, key=ticker, value={
            "company": ticker,
            "interest": state.get("query", ""),
        })
```

---

## 9. FastAPI SSE Streaming

Graph runs to **full completion** before streaming begins. This is required because `output_guardrail` and `faithfulness_guardrail` must see the complete `draft_answer`.

```
graph.astream(input, config, stream_mode="values")
    → final_state collected

approved_text = final_state["draft_answer"]
    → chunked into ~4-word SSE token events
    → streamed to client

done event:
    {message_id, grounded, sources, cache_hit, langfuse_trace_id}
```

Pseudo-SSE: not token-by-token LLM streaming during graph execution; tokens are emitted only after guardrails pass.

---

## 10. MCP Server

Separate FastMCP process exposing three tools, optional resources, and optional prompts.

| MCP surface | Name | Service |
|---|---|---|
| Tool | `search_buffett_letters` | `mcp_server/services/qdrant.py` |
| Tool | `get_market_data` | `mcp_server/services/yfinance_market.py` |
| Tool | `web_search` | `mcp_server/services/search.py` |
| Resource | `zimshire://letters/years` | Indexed letter years |
| Resource | `zimshire://policy/research` | No buy/sell advice policy |
| Prompt | `analyze_moat` | Moat analysis template |

| Transport | Consumer |
|---|---|
| SSE `http://mcp:8001` | LangGraph via `mcp_client.py` |
| stdio | Cursor / Claude Code |

**Rule:** Subagent tools call MCP via `mcp_client.py`. `mcp_server/services/` is only imported inside `mcp_server/server.py`.

### `mcp_client.py` (sketch)

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

async def init_mcp_client(base_url: str = "http://localhost:8001") -> None:
    _client = MultiServerMCPClient({
        "zimshire": {"url": f"{base_url}/mcp", "transport": "streamable_http"}
    })
    tool_list = await _client.get_tools()
    _tools = {t.name: t for t in tool_list}
```

Initialise once in FastAPI lifespan; reuse across requests.

---

## 11. Observability (Langfuse)

One trace per user message. Spans per expensive node.

| Node / tool | Span | Captures |
|---|---|---|
| `load_memory` | `load_memory` | profile keys present, context length |
| `orchestrator` | `orchestrator` | model, tokens, tool calls made, retry_count |
| `rag_agent` | `rag_retrieval` | hit count, top score |
| `market_agent` | `market_data` | tickers, cache hit/miss |
| `web_agent` | `web_search` | result count |
| `output_guardrail` | `output_guardrail` | violation detected, retry triggered |
| `faithfulness_guardrail` | `faithfulness` | grounded, strong hit count |

`langfuse_trace_id` stored on assistant `messages` row for audit. Create a trace for every request including cache hits (minimal span `cache_hit`).

---

## 12. Storage Reference

| Node | Postgres (custom) | LangGraph tables | Qdrant | External |
|---|---|---|---|---|
| `input_guardrail` | `guardrail_logs` | checkpoint | — | Guardrails AI (`DetectJailbreak`, `RestrictToTopic`) |
| `semantic_cache_check` | `semantic_cache` R/W | checkpoint | — | embed |
| `load_memory` | — | `store` R | — | — |
| `orchestrator` | `market_data_cache` R/W (via `market_agent`) | checkpoint | — | LiteLLM, MCP |
| `rag_agent` (tool) | — | — | R via MCP | — |
| `output_guardrail` | `guardrail_logs` | checkpoint | — | LLM classifier (full context check) |
| `faithfulness_guardrail` | `guardrail_logs` | checkpoint | — | RAGAS via LiteLLM gateway |
| FastAPI persist | `messages`, `rag_retrievals`, `semantic_cache`, `chats` | `store` W | — | Langfuse |

---

## 13. Key Design Decisions

| Decision | Rationale | Tradeoff |
|---|---|---|
| ReAct orchestrator (not Supervisor/Specialist pattern) | One LLM decides tool order dynamically; simpler graph, fewer LLM calls | Less explicit control over tool sequencing vs Supervisor pattern |
| Input guardrail: Guardrails AI (`DetectJailbreak` + `RestrictToTopic`) | Purpose-built validators: `DetectJailbreak` is ML-based (no LLM call), `RestrictToTopic` handles semantics; no custom prompt to maintain | Extra dependency (guardrails-ai); `RestrictToTopic` still makes an LLM call for off-topic check |
| `DetectJailbreak` fires before `RestrictToTopic` | Injection attempts blocked with zero LLM cost; topic check only runs on clean queries | Sequential — adds small latency vs parallel; acceptable since most queries are clean |
| Output guardrail: full context passed to LLM classifier | Single pass catches both factual hallucinations (vs collected_context) and safety violations (buy/sell, price targets); avoids two separate checks | Larger prompt = more tokens per guardrail call; mitigated by cheap model (haiku / gpt-4o-mini) |
| Output guardrail checks `collected_context` + `user_profile` + history | Orchestrator can hallucinate facts not in any subagent result; checking only `draft_answer` alone misses this class of error | Full context can be verbose; truncate history to last 10 messages to control token count |
| Output guardrail `feedback` from classifier, not hardcoded | Specific rewrite instruction is more actionable than a generic policy reminder; orchestrator corrects without re-calling MCP | Relies on classifier prompt quality |
| Output guardrail feedback loop (max 2 retries) | Gives orchestrator a chance to self-correct before falling back to a canned response | Adds up to 2 extra LLM calls on violations; capped to avoid infinite loops |
| Faithfulness guardrail: RAGAS `Faithfulness` metric | Atomic sentence-level claim verification against retrieved chunks; far more precise than similarity score threshold which only measures retrieval quality | Extra LiteLLM calls inside RAGAS per RAG-invoked turn; RAGAS is async-compatible via `asyncio.to_thread` |
| RAGAS via LiteLLM gateway | `LiteLLMStructuredLLM` adapter routes all RAGAS internal calls through the same gateway as the rest of the system; no separate API keys | Must configure `ragas_llm` at startup; model must support structured outputs |
| `grounded=False` does not block the answer | Faithfulness is a transparency/citation flag, not a safety gate; blocking would require a separate retry loop and significantly increase latency | Client must handle `grounded=false` gracefully (e.g. disclaimer in UI) |
| No Guardrails AI for output guardrail | `financial_tone` validator checks tone, not content; `llm_critic` is flexible but adds another dependency; custom LLM prompt gives full control over both factual + safety checks in one call | Must maintain output guardrail prompt quality manually |
| `collected_context` dict instead of flat `*_result` fields | Single state key is easier to debug and extend; each source has a named slot | Slightly more indirection when reading a specific source |
| `user_profile` dict instead of `user_preferences: list[str]` | Structured profile (tracked companies + research interests) is richer and extensible | Requires structured `store.aput` on persist; more schema discipline |
| Closure accumulator for tool outputs | Only correct way to propagate tool data into LangGraph state without direct mutation | Tools must be rebuilt per request |
| `ainvoke` in orchestrator (not `astream`) | Guardrails need complete `draft_answer` | User waits silently during graph execution; mitigated by SSE chunking after |
| `messages` not duplicated as `chat_history` | Checkpointer restores it automatically; duplication wastes context | `load_memory` must format it inline for system prompt |
| MCP as separate process | External clients (Cursor) can consume same tools; clean service boundary | Extra network hop per subagent call (up to 3 SSE roundtrips) |
| `grounded=None` for market-only answers | Matches assignment semantics; RAG grounding does not apply | Client must handle three states: true, false, null |

---

## 14. Recommended project layout

```
app/
  graph/
    state.py
    routing.py
    builder.py
    mcp_client.py           # single MultiServerMCPClient
    mcp_registry.py         # get_agent_tools() by tag
    subagents/
      base.py               # run_react_subagent + artifact extraction
      rag_subagent.py
      market_subagent.py
      web_subagent.py
    nodes/
      guardrails.py         # input_guardrail, output_guardrail, faithfulness_guardrail
      cache.py
      memory.py
      orchestrator.py
  repositories/
    cache_repo.py           # market_data_cache + semantic_cache
mcp_server/                 # separate from app/ — never imported by FastAPI directly
  main.py
  server.py
  core/
    config.py
  services/
    qdrant.py
    yfinance_market.py
    search.py

# Key external dependencies for guardrails:
# guardrails-ai            → DetectJailbreak, RestrictToTopic (input)
# ragas                    → Faithfulness metric (faithfulness_guardrail)
# Both route LLM calls through LiteLLM gateway — no separate API keys needed
```

---

## 15. Testing checklist

| Test | Assert |
|---|---|
| Input guardrail — `DetectJailbreak` blocks injection | `input_blocked=True` for "ignore your instructions", "pretend you are DAN" — no LLM call made |
| Input guardrail — `RestrictToTopic` blocks off-topic | `input_blocked=True` for "Write me a poem", "What's the weather?" |
| Input guardrail — allows borderline research | `input_blocked=False` for "Is Coca-Cola a good business?" |
| Input guardrail — blocks personal advice | `input_blocked=True` for "Should I buy AAPL right now?" |
| Cache hit | `cache_hit=True`, graph ends before `load_memory` |
| Orchestrator tool choice | Mock tools; `collected_context["rag"]` populated only when `rag_agent` called |
| Collected context keys | After market+web turn: `collected_context` has `"market"` and `"web"` keys, no `"rag"` |
| User profile load | `user_profile["tracked_companies"]` populated from store on second turn |
| Output guardrail — passes clean answer | `output_blocked=False`, no `feedback_message`, `retry_count` unchanged |
| Output guardrail — catches buy/sell | `output_blocked=True`, `safety_category="buy_sell"`, `feedback_message` set, `retry_count=1` |
| Output guardrail — catches price target | `output_blocked=True`, `safety_category="price_target"`, orchestrator re-invoked |
| Output guardrail — catches factual hallucination | `output_blocked=True`, `factual_consistent=False`, `unsupported_claims` non-empty |
| Output guardrail — full context used | Mock: yfinance returns P/E=35x; draft says P/E=28x → `factual_consistent=False` |
| Output guardrail — retry loop | Violation attempt 0 → `retry_count=1` → orchestrator rewrites → guardrail passes |
| Output guardrail — fallback | Violation attempts 0,1,2 → `output_rewritten=True`, `draft_answer` = safe fallback text |
| Output guardrail — logs violation | `guardrail_logs` row with `guardrail_type="output"` and `result="blocked"` |
| Faithfulness — RAGAS score >= 0.7 | `grounded=True`, `sources` list non-empty with `similarity_score >= 0.75` hits |
| Faithfulness — RAGAS score < 0.7 | `grounded=False`, `sources=[]`, `guardrail_logs` blocked row |
| Faithfulness — RAG not invoked | `grounded=None`, `sources=[]`, early exit before RAGAS call |
| Faithfulness — answer not blocked on grounded=False | `draft_answer` unchanged; only `grounded` flag set to False |
| RAG persist | N `rag_retrievals` rows for N items in `rag_agent_chunks` |
| Multi-turn | Turn 2 `messages` in checkpoint include turn 1 |