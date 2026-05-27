# Техническое задание: рефакторинг Multi-Agent + Memory modules + Langfuse

Документ описывает **что изменить** относительно текущей реализации.

---

## 0. Контекст: что есть сейчас

| Компонент | Текущее состояние | Проблема для цели |
|-----------|-------------------|-------------------|
| Subagents | `@tool` в `subagents.py` → прямой вызов MCP | Нет отдельного LLM-агента на источник |
| MCP | Один процесс `mcp:8001`, все tools в одном FastMCP | Нет разделения по категориям / серверам |
| Orchestrator | Один `create_react_agent` + 3 tools | «Multi-agent» только по именам; вызывает все tools подряд |
| Prompts | Один `SYSTEM_BUFFETT` в `prompts.py` | Нет промптов RAG/Market/Web/Orchestrator |
| Models | Один `default_chat_model` (`gpt-4o-mini`) для всех узлов | Нет разделения orchestrator / subagents; Claude не используется |
| Short-term memory | `[-20:]` в system prompt + полный thread в `ainvoke` | Нужно **5 turn-пар** (user + финальный AI); убрать дублирование |
| Long-term memory | `load_memory` + heuristic `store.aput` по market tickers | Нет LLM extraction preferences; нет модуля |
| Langfuse | `new_trace()` создаёт handler, но **не используется** | Трейсов в UI нет |

---

## 1. Целевая архитектура

### 1.1 Multi-agent (настоящие subagents)

```text
LangGraph
  input_guardrail
  semantic_cache_check
  load_context          ← short_term + long_term (chat_history module)
  orchestrator_planner  ← решает КАКИХ subagents вызвать (0..3) и с каким query
  ├─ rag_subagent       ← create_react_agent + RAG_PROMPT + MCP RAG server + Claude
  ├─ market_subagent    ← create_react_agent + MARKET_PROMPT + MCP Market server + Claude
  └─ web_subagent       ← create_react_agent + WEB_PROMPT + MCP Web server + Claude
  merge_context
  synthesizer           ← ORCHESTRATOR_SYNTH_PROMPT + Claude: draft_answer из collected_context
  output_guardrail → faithfulness_guardrail → END
```

**Контракт subagent → orchestrator:**

```python
class SubagentResult(TypedDict):
    agent_name: str           # "rag" | "market" | "web"
    sub_query: str            # query, который передал orchestrator
    formatted_context: str    # текст для synthesizer
    raw_artifacts: dict       # chunks / sources / tickers payload
```

Orchestrator **не** вызывает MCP напрямую — только subagent nodes/services.

### 1.2 Три MCP-сервера (по категориям)

| Сервис | Порт (dev) | Tools | Зависимости |
|--------|------------|-------|-------------|
| `mcp-rag` | 8001 | `search_buffett_letters` (+ ui опционально) | Qdrant, LiteLLM embed |
| `mcp-market` | 8002 | `lookup_ticker`, `get_stock_*`, … | yfinance, Postgres cache read-only опционально |
| `mcp-web` | 8003 | `web_search`, `web_search_news`, `web_search_knowledge` | SerpApi |

**Docker:** три сервиса из одного `Dockerfile`, разный `command`:

```yaml
mcp-rag:    python -m mcp_server.rag_main --port 8001
mcp-market: python -m mcp_server.market_main --port 8002
mcp-web:    python -m mcp_server.web_main --port 8003
```

Текущий монолит `mcp_server/main.py` оставить для Cursor/stdio или удалить после split.

**FastAPI env:**

```env
MCP_RAG_URL=http://localhost:8001
MCP_MARKET_URL=http://localhost:8002
MCP_WEB_URL=http://localhost:8003
```

### 1.3 Модуль `chat_history`

```text
app/modules/chat_history/
├── __init__.py
├── short_term/
│   ├── __init__.py
│   ├── service.py      # load_thread_messages, format_for_prompt
│   ├── gateways.py     # адаптер checkpointer → agents
│   └── schemas.py      # ShortTermContext DTO
└── long_term/
    ├── __init__.py
    ├── service.py      # load_profile, persist_from_turn, merge_extraction
    ├── extraction.py   # memory_extraction — лёгкий LLM, structured output
    ├── gateways.py     # адаптер AsyncPostgresStore → agents
    └── schemas.py      # UserProfile, MemoryExtraction DTO
```

**Импорт в agents:**

```python
from app.modules.chat_history.short_term.service import ShortTermMemoryService
from app.modules.chat_history.long_term.service import LongTermMemoryService
```

Удалить/упростить `app/modules/agents/nodes/memory.py` — node вызывает только gateways.

---

## 2. Этапы реализации

### Этап A — Prompts (`app/core/prompts.py`)

Добавить **6 отдельных промптов** (не один `SYSTEM_BUFFETT`):

| Константа | Назначение |
|-----------|------------|
| `ORCHESTRATOR_PLANNER_PROMPT` | Решает: **какие** subagents вызвать (0..3), sub_query для каждого, tickers, years; **явно запрещает** вызывать лишних |
| `RAG_SUBAGENT_PROMPT` | Buffett letters specialist: search strategy, cite years, no hallucination |
| `MARKET_SUBAGENT_PROMPT` | Market data specialist: pick data_type, interpret metrics, no buy/sell |
| `WEB_SUBAGENT_PROMPT` | News/events specialist: recency, snippets, no predictions |
| `ORCHESTRATOR_SYNTH_PROMPT` | Синтез финального ответа из `collected_context` + profile + history |
| `MEMORY_EXTRACTION_PROMPT` | Извлечение tickers, topics, preferences для long-term store (B.2a) |

`SYSTEM_BUFFETT` → deprecated или alias для `ORCHESTRATOR_SYNTH_PROMPT`.

**Критерий:** каждый subagent использует **только свой** prompt; orchestrator planner/synth — свои.

---

### Этап A.1 — Модели LLM (LiteLLM + Claude)

**Текущее:** `app/services/llm.py` — один `get_chat_model()` с `default_chat_model = "gpt-4o-mini"`.

**Цель:** все агенты работают через LiteLLM proxy; orchestrator и subagents используют **Claude**.

#### Конфиг (`app/core/config.py` + `.env`)

```env
# LiteLLM gateway (уже есть)
LITELLM_BASE_URL=...
LITELLM_API_KEY=...
LITELLM_END_USER_ID=...

# Модели — имена как в LiteLLM model list
ORCHESTRATOR_MODEL=claude-sonnet-4-6          # planner + synthesizer
SUBAGENT_MODEL=claude-sonnet-4-6              # rag, market, web subagents
GUARDRAIL_MODEL=claude-sonnet-4-6             # или более лёгкая модель — на выбор
MEMORY_MODEL=claude-haiku-4-5                 # memory extraction (B.2a), лёгкая модель
DEFAULT_CHAT_MODEL=claude-sonnet-4-6          # fallback если chat.model не задан
```

> **Важно:** точное имя модели (`claude-sonnet-4-6`, `claude-3-5-sonnet-20241022`, …) — сверить с LiteLLM proxy `/v1/models`. Использовать то имя, которое прокси принимает.

#### Изменения в `app/services/llm.py`

```python
def get_orchestrator_model(model_override: str | None = None) -> ChatOpenAI:
    """Planner + synthesizer — Claude via LiteLLM."""
    return get_chat_model(model_override or settings.orchestrator_model, temperature=0.2)

def get_subagent_model(model_override: str | None = None) -> ChatOpenAI:
    """RAG / Market / Web subagents — Claude via LiteLLM."""
    return get_chat_model(model_override or settings.subagent_model, temperature=0.1)

def get_guardrail_model(model_override: str | None = None) -> ChatOpenAI:
    """Guardrail nodes — Claude (или отдельная лёгкая модель)."""
    return get_chat_model(model_override or settings.guardrail_model, temperature=0.0)

def get_memory_model() -> ChatOpenAI:
    """Memory extraction (B.2a) — лёгкая модель."""
    return get_chat_model(settings.memory_model, temperature=0.0)
```

#### Проброс модели в graph config

```python
config = {
    "configurable": {
        "thread_id": str(chat_id),
        "model": chat_model,                    # per-chat override из POST body
        "orchestrator_model": settings.orchestrator_model,
        "subagent_model": settings.subagent_model,
        ...
    }
}
```

**Правила:**
- Orchestrator planner/synthesizer → `get_orchestrator_model(config["configurable"].get("model"))`
- Каждый subagent → `get_subagent_model(...)` — **не** orchestrator model
- Guardrails → `get_guardrail_model(...)` — отдельная настройка для стабильности
- Per-turn override (`body.model` / `chat.model`) переопределяет **orchestrator**; subagents по умолчанию остаются на `SUBAGENT_MODEL` (или тот же override — зафиксировать в docs)

**Критерий приёмки:**
- [ ] Planner, synthesizer, subagents, guardrails используют LiteLLM → Claude (видно в Langfuse spans: `model` = claude-*)
- [ ] Нет hardcoded `gpt-4o-mini` в agent nodes

---

### Этап B — `chat_history` module

#### B.1 Short-term (`modules/chat_history/short_term/`)

**Ответственность:**
- Чтение истории из LangGraph checkpointer (`thread_id = str(chat_id)`)
- Форматирование для prompt planner/synthesizer (не дублировать в state отдельным `chat_history`)

**API:**

```python
class ShortTermMemoryService:
    async def format_recent_turns(
        self, *, thread_id: str, limit_turn_pairs: int = 5
    ) -> str: ...

    async def get_recent_turn_messages(
        self, *, thread_id: str, limit_turn_pairs: int = 5
    ) -> list[BaseMessage]: ...
```

**Важно:** short-term **не пишет** в БД — checkpointer делает это автоматически при `graph.astream`. Модуль только **read/format**.

#### B.1a — Short-term context для orchestrator (5 turn-пар)

**Требование:** в контекст planner/synthesizer попадают только последние **5 пар** сообщений:

| Роль | Содержимое |
|------|------------|
| Human | user query за turn |
| Assistant | итоговый `draft_answer` за turn (тот же `AIMessage`, что пишет узел orchestrator/synthesizer в checkpointer) |

**Не включать:**
- tool messages, промежуточные ReAct-шаги внутри turn (они не в graph state)
- сообщения старше 5 пар (на turn 6+ turn 1 не виден в prompt)

**Реализация:**
- `ShortTermMemoryService.format_recent_turns(limit_turn_pairs=5)` — из `state["messages"]` checkpointer или через gateway к checkpointer
- Заменить `[-20:]` в `orchestrator._build_system_prompt` на вызов сервиса
- **Убрать дублирование:** не передавать в `ainvoke` полный thread **и** ту же историю в system prompt. Вариант по умолчанию:
  - formatted block «Recent conversation» в system prompt (5 пар);
  - в `messages[]` для текущего turn — только текущий `HumanMessage` (+ system), либо урезанный список из `get_recent_turn_messages`

**Откуда перенести код:**
- `_build_system_prompt()` history section из `orchestrator.py` → `short_term/service.py`

**Критерий приёмки:**
- [ ] В prompt orchestrator/planner — не более 5 пар User/Assistant
- [ ] Turn 6+ не содержит turn 1 в контексте
- [ ] Нет двойной подачи полной истории (system + full `state["messages"]`)

#### B.2 Long-term (`modules/chat_history/long_term/`)

**Ответственность:**
- `load_profile(user_id, query)` → `UserProfile`
- `persist_interests(user_id, tickers, query)` → `store.aput`
- `init_user_profile(user_id)` при `POST /users` (bonus из assistant_flow Stage 1)

**API:**

```python
class LongTermMemoryService:
    def __init__(self, store: BaseStore): ...

    async def load_profile(self, user_id: str, query: str) -> UserProfile: ...
    async def persist_from_turn(self, user_id: str, query: str, market_context: str) -> None: ...
    async def merge_extraction(self, user_id: str, extraction: MemoryExtraction) -> None: ...
    async def init_user(self, user_id: str) -> None: ...
```

**Откуда перенести:**
- `load_memory` node body → `long_term/service.load_profile`
- `persist_assistant_turn` блок `store.aput` → `long_term/service.persist_from_turn` + вызов extraction

#### B.2a — Memory extraction (long-term, лёгкий LLM)

**Назначение:** после финального ответа извлекать из диалога tickers, topics и **user preferences** и сохранять в `AsyncPostgresStore`. Это **не** ReAct subagent (без MCP/tools) — один вызов LLM с structured output.

**Компоненты:**
- `app/modules/chat_history/long_term/extraction.py` — `extract_memory_from_turn(...)`
- `MEMORY_EXTRACTION_PROMPT` в `app/core/prompts.py`
- `MEMORY_MODEL` в `app/core/config.py` (лёгкая модель via LiteLLM, напр. `claude-haiku-*` или `gpt-4o-mini`)

**Когда запускать (рекомендуется):**
- **Stage 10** в `persist_assistant_turn` — **после** `output_guardrail` и `faithfulness_guardrail` (вход: финальный `draft_answer`)
- Альтернатива: узел графа `extract_long_term_memory` сразу **после** `faithfulness_guardrail` → END (тогда не писать при cache hit / input_blocked)

**Не запускать при:**
- `cache_hit=True`
- `input_blocked=True`
- `should_update=false` (greeting, meta «кто ты», пустой query)

**Вход extraction:**

```python
user_query: str
draft_answer: str
recent_turns: list[TurnMessage]   # те же 5 пар, что в B.1a
current_profile: UserProfile      # из store до merge
collected_context_summary: str | None  # кратко rag/market/web, опционально
```

**Выход (Pydantic `MemoryExtraction`):**

```python
class MemoryExtraction(BaseModel):
    should_update: bool
    tickers: list[str] = []
    research_topics: list[str] = []
    preferences: dict = {}           # style, depth, language, focus_areas
    explicit_memories: list[str] = []  # «запомни, что…»
    deprecate_keys: list[str] = []
```

**Запись в store:**

| Namespace | Key | Value |
|-----------|-----|--------|
| `("users", user_id, "profile")` | `"meta"` | `preferences`, `topics`, `updated_at` |
| `("users", user_id, "interests")` | ticker | `{company, interest, last_seen}` |

`LongTermMemoryService.merge_extraction()` — merge с существующим profile, без слепого перезаписывания.

**Сосуществование с текущим heuristic:**
- Оставить быстрый `aput` по tickers из `collected_context["market"]` как **fallback**
- LLM extraction **дополняет** preferences/topics; при конфликте ticker — merge по `last_seen`

**Промпт extraction (правила):**
- Обновлять store только при явных сигналах: тикер, тема, «запомни», повторяющийся интерес, стиль ответа
- Не выдумывать тикеры; не сохранять buy/sell advice как preference

**Langfuse:** span `memory_extraction` — `should_update`, count tickers/topics (без полного текста preferences в metadata).

**Критерий приёмки:**
- [ ] Turn с «запомни, меня интересуют moats» → `preferences` или `explicit_memories` в store
- [ ] Greeting → `should_update=false`, store не меняется
- [ ] Turn с AAPL + market tool → ticker в store (heuristic и/или LLM)
- [ ] `load_profile` на следующем turn подтягивает сохранённое в planner prompt

#### B.3 Node `load_context` (замена `load_memory`)

```python
async def load_context(state, config, *, short_term_svc, long_term_svc):
    thread_id = config["configurable"]["thread_id"]
    user_id = config["configurable"]["user_id"]
    query = state.get("query") or ""

    profile = await long_term_svc.load_profile(user_id, query)
    return {"user_profile": profile.model_dump()}
```

Short-term history (5 пар) подтягивается в planner/synthesizer через `ShortTermMemoryService`, не через state field.

---

### Этап C — Subagents (полноценные агенты)

#### C.1 Структура

```text
app/modules/agents/
├── subagents/
│   ├── __init__.py
│   ├── base.py              # SubagentRunner, SubagentResult
│   ├── rag/
│   │   ├── agent.py         # run_rag_subagent(query, years, config)
│   │   └── mcp_client.py    # init/get только RAG MCP
│   ├── market/
│   │   ├── agent.py
│   │   └── mcp_client.py
│   └── web/
│       ├── agent.py
│       └── mcp_client.py
├── nodes/
│   ├── orchestrator.py      # planner: selective subagent invocation
│   ├── synthesizer.py       # draft_answer
│   └── subagent_nodes.py    # rag_node, market_node, web_node (conditional)
```

#### C.2 Поведение каждого subagent

Каждый subagent:

1. `create_react_agent(get_subagent_model(), tools_from_its_mcp_server)`
2. System prompt = свой из `prompts.py`
3. Human message = `sub_query` от orchestrator
4. `ainvoke` → последнее сообщение = **formatted_context** для synthesizer
5. Side effect: raw artifacts в `SubagentResult.raw_artifacts`
6. `config["callbacks"]` пробрасывается для Langfuse

**Пример RAG subagent (псевдокод):**

```python
async def run_rag_subagent(sub_query: str, years: list[int] | None, config) -> SubagentResult:
    llm = get_subagent_model(config["configurable"].get("subagent_model"))
    tools = get_rag_mcp_tools()
    agent = create_react_agent(llm, tools)
    result = await agent.ainvoke({...}, config=config)
    return SubagentResult(...)
```

#### C.3 Orchestrator (planner) — selective routing

**Главное требование:** orchestrator **качественно** решает, **кого вызывать**, и **может не вызывать никого**.

Planner **не синтезирует ответ** — только план с `enabled: true/false` per subagent.

**Structured output (Pydantic):**

```python
class SubagentPlanItem(BaseModel):
    name: Literal["rag", "market", "web"]
    enabled: bool
    query: str = ""
    years: list[int] | None = None
    tickers: list[str] | None = None
    data_type: Literal["info", "financials", "history"] | None = None
    reason: str  # для Langfuse debug: почему enabled/disabled

class OrchestratorPlan(BaseModel):
    subagents: list[SubagentPlanItem]
    direct_answer_possible: bool = False  # True → subagents skip, synthesizer only
```

**Пример плана:**

```json
{
  "subagents": [
    {"name": "rag", "enabled": true, "query": "Buffett on economic moats", "years": [1988, 2008], "reason": "philosophy question"},
    {"name": "market", "enabled": false, "query": "", "reason": "no ticker or metrics requested"},
    {"name": "web", "enabled": false, "query": "", "reason": "no recent events needed"}
  ],
  "direct_answer_possible": false
}
```

**Матрица routing (в `ORCHESTRATOR_PLANNER_PROMPT`):**

| Сигнал в запросе | RAG | Market | Web |
|------------------|-----|--------|-----|
| Buffett philosophy, moat, intrinsic value, letter quotes | ✅ | ❌ | ❌ |
| Ticker / P/E / financials / price history | ❌ | ✅ | ❌ |
| «This year», «last quarter», recent news, earnings | ❌ | optional | ✅ |
| Philosophy + current data (e.g. «Would Buffett buy AAPL today?») | ✅ | ✅ | optional |
| Greeting, meta («who are you»), clarification | ❌ | ❌ | ❌ → `direct_answer_possible: true` |
| Follow-up on prior turn (short-term context enough) | ❌ | ❌ | ❌ → synthesizer only |

**Реализация:**
- **Structured output** LLM call (`with_structured_output(OrchestratorPlan)`) — предпочтительно, детерминированнее ReAct
- Модель: `get_orchestrator_model()` (Claude)
- После planner — **только enabled subagents**, параллельно через `asyncio.gather`
- Если все `enabled: false` и `direct_answer_possible: true` → skip subagents, synthesizer отвечает из history + profile

**Anti-patterns (запретить в prompt):**
- Вызывать все три subagents «на всякий случай»
- Вызывать web для исторических вопросов про Buffett letters
- Вызывать market без упоминания ticker/компании/метрик

**Langfuse:** span `orchestrator_planner` с input=query, output=plan JSON, metadata=enabled_count.

#### C.4 Synthesizer node

- Input: `collected_context`, `user_profile`, short-term history (via service)
- Prompt: `ORCHESTRATOR_SYNTH_PROMPT`
- Model: `get_orchestrator_model()`
- Output: `draft_answer`, `messages: [AIMessage(...)]`
- Если subagents не вызывались — synthesizer работает только с history + profile + query

Guardrails остаются без изменений по контракту.

#### C.5 Удалить / deprecate

- `app/modules/agents/tools/subagents.py` — заменить на `subagents/*/agent.py`
- Прямые вызовы `get_mcp_tools()` из одного клиента — заменить на 3 клиента

---

### Этап D — MCP split

#### D.1 Новые entry points

| Файл | Регистрирует |
|------|--------------|
| `mcp_server/rag_main.py` | только `mcp_server/rag/tools.py` |
| `mcp_server/market_main.py` | только `mcp_server/market/tools.py` |
| `mcp_server/web_main.py` | только `mcp_server/search/tools.py` |

#### D.2 Docker Compose

- `mcp-rag`, `mcp-market`, `mcp-web` — три сервиса
- `api` depends_on все три
- `GET /health` — проверять все 3 URL

#### D.3 Lifespan FastAPI

```python
await init_rag_mcp_client(settings.mcp_rag_url)
await init_market_mcp_client(settings.mcp_market_url)
await init_web_mcp_client(settings.mcp_web_url)
```

---

### Этап E — Langfuse

#### E.0 Prerequisite — Langfuse AI Skill (ОБЯЗАТЕЛЬНО перед началом)

**Перед любой работой с Langfuse** выполнить:

1. Установить Langfuse AI skill из репозитория:
   - https://github.com/langfuse/skills
   > Install the Langfuse AI skill from github.com/langfuse/skills and use it to add tracing to this application with Langfuse following best practices.

3. Следовать принципам skill:
   - **Documentation First** — не писать код по памяти; сначала fetch актуальную документацию Langfuse
   - **Best practices** — см. `references/instrumentation.md` в skill
   - **Latest SDK** — использовать актуальную версию `langfuse` Python SDK
   - **CLI для проверки** — `npx langfuse-cli api traces list` после тестового turn

4. Credentials в `.env` (без лишних кавычек):

   ```env
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_BASE_URL=https://cloud.langfuse.com
   ```

#### E.1 Диагностика (текущий баг)

В `messages/router.py`:

```python
trace_id, _handler = new_trace(...)   # handler выбрасывается!
config = {"configurable": {...}}      # нет callbacks
async for chunk in graph.astream(inputs, config=config, ...):
```

`langfuse_service.new_trace()` **создаёт** `CallbackHandler`, но он **никогда не передаётся** в graph/subagents.

Дополнительно: после turn нет `langfuse_service.flush()`.

#### E.2 Исправления (обязательные, по best practices из Langfuse skill)

1. **Проброс callbacks в graph config:**

   ```python
   trace_id, handler = new_trace(user_id=..., session_id=str(chat_id))
   config = {
       "configurable": {...},
       "callbacks": [handler] if handler else [],
       "metadata": {"langfuse_trace_id": trace_id},
   }
   ```

2. **Проброс callbacks в subagents** — каждый `agent.ainvoke(..., config=config)`.

3. **Иерархия spans** (рекомендуется skill):
   - Trace: `zimshire_turn` (session_id = chat_id, user_id)
   - Span: `orchestrator_planner` (output = plan JSON)
   - Span per subagent: `rag_subagent`, `market_subagent`, `web_subagent` (только если enabled)
   - Span: `synthesizer`
   - Spans guardrails: `input_guardrail`, `output_guardrail`, `faithfulness_guardrail`
   - Span: `cache_hit` / `input_blocked` при соответствующих ветках

4. **`flush()` после завершения turn:**

   ```python
   from app.services.langfuse_service import flush
   flush()
   ```

5. **Metadata на spans:** `model`, `enabled_subagents`, `subagent_count`, `direct_answer_possible`.

6. **Проверить `.env`:** ключи парсятся pydantic без лишних кавычек.

7. **Версия SDK:** `CallbackHandler(trace_id=..., langfuse_client=...)` — сверить с актуальной документацией Langfuse v3 через skill.

#### E.3 Критерий приёмки Langfuse

- [ ] После `POST /chats/{id}/messages` в Langfuse UI виден trace `zimshire_turn`
- [ ] Spans: planner, только вызванные subagents, synthesizer, guardrails
- [ ] `langfuse_trace_id` в SSE `done` совпадает с trace id в UI
- [ ] Turn без subagents — trace содержит `orchestrator_planner` + `synthesizer`, subagent spans отсутствуют
- [ ] `npx langfuse-cli api traces list` возвращает trace после тестового запроса

---

## 3. Изменения в `ZimShireState`

```python
subagent_plan: NotRequired[dict]            # OrchestratorPlan
subagent_results: NotRequired[list[dict]]   # SubagentResult[] (только enabled)
direct_answer_possible: NotRequired[bool]
```

`collected_context` остаётся — заполняется из `subagent_results` в merge step.

---

## 4. Изменения топологии графа (`builder.py`)

**Было:**

```text
load_memory → orchestrator → output_guardrail
```

**Станет:**

```text
load_context → orchestrator_planner
orchestrator_planner → [rag_subagent | market_subagent | web_subagent]  # conditional, 0..3
→ merge_context → synthesizer → output_guardrail
```

Routing: `builder.py` + `routing.py` — conditional edges по `subagent_plan[].enabled`.

**Обновить:** `docs/agent_architecture.md` §4 (topology) — обязательно по RULES.

---

## 5. Таблица миграции файлов

| Сейчас | Куда / что |
|--------|------------|
| `agents/nodes/memory.py` | → `chat_history/long_term` + thin `load_context` node |
| History formatting in `orchestrator.py` | → `chat_history/short_term/service.py` |
| `store.aput` in `messages/service.py` | → `long_term/service.persist_from_turn` + `extraction.extract_memory_from_turn` |
| `orchestrator [-20:]` | → `short_term` `format_recent_turns(limit=5)` |
| — | `long_term/extraction.py`, `MEMORY_EXTRACTION_PROMPT`, `MEMORY_MODEL` |
| `agents/tools/subagents.py` | → `agents/subagents/{rag,market,web}/agent.py` |
| `agents/mcp_client.py` (monolith) | → 3 файла `mcp_client.py` per subagent |
| `core/prompts.py` (1 prompt) | → 6 prompts + routing rules в planner |
| `services/llm.py` (1 model) | → `get_orchestrator_model`, `get_subagent_model`, `get_guardrail_model` |
| `core/config.py` | → `orchestrator_model`, `subagent_model`, `guardrail_model`, `memory_model` |
| `messages/router.py` langfuse | → callbacks + flush + metadata |
| `mcp_server/main.py` | → split `rag_main`, `market_main`, `web_main` |

---

## 6. Порядок работ (рекомендуемый)

| # | Этап | Результат |
|---|------|-----------|
| 0 | **Langfuse skill install (E.0)** | Skill установлен, docs прочитаны |
| 1 | **Langfuse fix (E)** | Трейсы видны до большого рефакторинга |
| 2 | **Models (A.1)** | Claude для orchestrator + subagents через LiteLLM |
| 3 | **prompts.py (A)** | 6 промптов + routing matrix в planner |
| 4 | **chat_history module (B)** | short/long term изолированы |
| 4a | **Short-term 5 пар (B.1a)** | orchestrator/planner видит только 5 turn-пар |
| 4b | **Memory extraction (B.2a)** | LLM сохраняет preferences в store (Stage 10) |
| 5 | **MCP split (D)** | 3 сервера в docker |
| 6 | **Subagents + selective orchestrator (C)** | полноценные agents, 0..3 вызовов |
| 7 | **Graph topology (C.4)** | planner + conditional subagents + synthesizer |
| 8 | **Tests + docs update** | §15 checklist, `agent_architecture.md` |

---

## 7. Verification checklist

```text
Verification:
- [ ] Langfuse skill установлен; instrumentation по best practices
- [ ] docker compose up — mcp-rag, mcp-market, mcp-web healthy
- [ ] POST /messages — Langfuse trace с spans (planner + только нужные subagents)
- [ ] Greeting turn — 0 subagents, direct synthesizer answer
- [ ] Philosophy-only turn — только rag_subagent span
- [ ] Ticker-only turn — только market_subagent span
- [ ] All models in Langfuse spans = claude-* via LiteLLM
- [ ] Turn 6+ — в prompt только последние 5 пар (turn 1 отсутствует)
- [ ] Turn 2 same chat_id — short_term history (5 пар) в synthesizer/planner prompt
- [ ] market turn — long_term store row для ticker в pgAdmin (store table)
- [ ] «Запомни…» / явная тема — `memory_extraction` span + обновление `store` profile
- [ ] Greeting — `should_update=false`, store без изменений
- [ ] collected_context заполнен subagent_results, не прямым MCP из orchestrator
- [ ] output_guardrail retry — subagents не перезапускаются без нужды
- [ ] pytest tests/subagents/, tests/chat_history/, tests/orchestrator_routing/
```

---

## 8. Риски

| Риск | Митигация |
|------|-----------|
| Planner вызывает лишних subagents | Structured output + routing matrix + `reason` field для debug |
| 3x LLM calls на turn (дорого) | Selective routing: 0..1 subagent для простых запросов |
| Latency | Parallel `asyncio.gather` только для enabled subagents |
| Claude rate limits / cost | `SUBAGENT_MODEL` можно сделать легче orchestrator при необходимости |
| Docs drift | обновить `agent_architecture.md` в том же PR |
| MCP split ломает Cursor stdio | оставить `mcp_server/main.py` для dev |
| Langfuse SDK drift | всегда сверять через Langfuse skill docs перед изменениями |
| Memory extraction пишет до guardrails | Только Stage 10 или node после `faithfulness_guardrail` |
| Лишние LLM-вызовы на каждый turn | `should_update=false` для meta/greeting; лёгкая `MEMORY_MODEL` |

---

## 9. Почему Langfuse сейчас «пустой» (кратко)

1. `CallbackHandler` создаётся, но **не передаётся** в `graph.astream(config=...)`.
2. Нет `flush()` после request.
3. Subagents/orchestrator/guardrails не получают `callbacks`.
4. Trace id пишется в БД (`messages.langfuse_trace_id`), но **spans не отправляются** — поэтому в UI пусто.

**Fix:** установить Langfuse skill → следовать `references/instrumentation.md` → callbacks + flush + hierarchical spans.
