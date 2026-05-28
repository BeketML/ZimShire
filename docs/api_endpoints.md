# ZimShire API Endpoints

**13 HTTP endpoints.** Base URL: `http://localhost:8000`

All LLM orchestration, guardrails, and persistence happen server-side. Models are configured in `app/core/config.py` — clients do not pass model overrides.

---

## Endpoint overview

| # | Method | Path | Description |
|---|--------|------|-------------|
| 1 | `POST` | `/users` | Create a user identity |
| 2 | `GET` | `/users/{user_id}` | Get user metadata |
| 3 | `POST` | `/chats` | Create a new chat session |
| 4 | `GET` | `/chats/{chat_id}` | Get chat metadata |
| 5 | `GET` | `/chats/{chat_id}/messages?user_id=` | Conversation history |
| 6 | `POST` | `/chats/{chat_id}/messages` | **Streaming research turn (SSE)** |
| 7 | `GET` | `/users/{user_id}/memory/long-term` | Long-term user profile |
| 8 | `GET` | `/users/{user_id}/chats/{chat_id}/memory/short-term` | Short-term turn pairs |
| 9 | `GET` | `/health` | Health check |
| 10 | `GET` | `/debug/semantic-cache` | Inspect semantic cache rows |
| 11 | `GET` | `/debug/market-data-cache` | Inspect market TTL cache rows |
| 12 | `GET` | `/debug/chats/{chat_id}/rag-retrievals` | RAG chunks for a chat |
| 13 | `GET` | `/debug/chats/{chat_id}/guardrail-logs` | Guardrail decisions for a chat |

---

## `POST /users`

**Request body:** `{}` or `{"name": "Alice", "surname": "Smith"}` (all optional)

**Response `201`**
```json
{"user_id": "uuid", "name": "Alice", "surname": "Smith", "created_at": "2026-05-28T10:00:00Z"}
```

---

## `GET /users/{user_id}`

**Response `200`** — `{user_id, name, surname, created_at}` — `404` if not found.

---

## `POST /chats`

Server generates `chat_id`; LangGraph uses `str(chat_id)` as `thread_id`.

**Request**
```json
{"user_id": "uuid", "chat_title": "Apple moat analysis"}
```

**Response `201`**
```json
{
  "chat_id": "uuid",
  "user_id": "uuid",
  "chat_title": "Apple moat analysis",
  "model": "gpt-4o-mini",
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:00Z"
}
```

| Code | Meaning |
|------|---------|
| `201` | Created |
| `404` | `user_id` not found |
| `422` | Validation error |

---

## `GET /chats/{chat_id}`

**Response `200`** — same shape as `POST /chats` response — `404` if not found.

---

## `GET /chats/{chat_id}/messages`

Retrieve conversation history. Requires `user_id` query param for ownership check.

**Query params:** `?user_id=<uuid>` (required)

**Response `200`**
```json
{
  "chat_id": "uuid",
  "messages": [
    {
      "message_id": "uuid",
      "role": "human",
      "content": "How would Buffett evaluate Apple's moat?",
      "grounded": null,
      "sources": [],
      "langfuse_trace_id": null,
      "created_at": "2026-05-28T10:00:00Z"
    },
    {
      "message_id": "uuid",
      "role": "assistant",
      "content": "Warren Buffett consistently emphasized…",
      "grounded": true,
      "sources": [
        {"letter_year": 1993, "passage": "brand names…", "similarity_score": 0.47, "qdrant_point_id": "abc"}
      ],
      "langfuse_trace_id": "abc123",
      "created_at": "2026-05-28T10:01:30Z"
    }
  ]
}
```

| Code | Meaning |
|------|---------|
| `200` | History returned (may be empty) |
| `403` | `user_id` doesn't match chat owner |
| `404` | Chat not found |

---

## `POST /chats/{chat_id}/messages`

The core endpoint — streaming research turn.

**Request**
```json
{
  "user_id": "uuid",
  "query": "How would Buffett evaluate Apple's economic moat based on his letters?"
}
```

### SSE event types

All events: `data: <json>\n\n`

#### `progress` — stage boundary

Emitted before slow stages. One event per enabled subagent when orchestrator plan lands, then one when subagents complete.

```
data: {"type":"progress","stage":"rag","message":"Searching Buffett letters…"}
data: {"type":"progress","stage":"market","message":"Fetching market data…"}
data: {"type":"progress","stage":"synthesizing","message":"Composing answer…"}
```

`stage` values: `"rag"` / `"market"` / `"web"` / `"synthesizing"`

#### `token` — real-time LLM token

Actual model output fragments from the synthesizer, streamed as they're generated.

```
data: {"type":"token","content":"Warren Buffett has consistently"}
data: {"type":"token","content":" emphasized that Apple's ecosystem…"}
```

#### `replace` — guardrail rewrote streamed content

Sent when output guardrail exhausted retries and replaced the answer. Client should discard all prior `token` events and display this content.

```
data: {"type":"replace","content":"ZimShire can help you research companies…"}
```

#### `blocked` — input guardrail rejection

```
data: {"type":"blocked","reason":"Explicitly asks for personalized investment advice"}
```

Followed by `done` with `message_id: null`.

#### `error` — unhandled exception

```
data: {"type":"error","detail":"graph run failed: …"}
```

Followed by `done`.

#### `done` — always the final event

```json
{
  "type": "done",
  "message_id": "uuid",
  "grounded": true,
  "sources": [
    {"letter_year": 1993, "passage": "brand names…", "similarity_score": 0.47, "qdrant_point_id": "abc"}
  ],
  "langfuse_trace_id": "f44f26569830cd5f504de6689d41acc8",
  "cache_hit": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `message_id` | `uuid\|null` | Persisted assistant message ID; `null` if input was blocked |
| `grounded` | `bool\|null` | `true` = grounded in letters; `false` = RAG ran but couldn't support claims; `null` = RAG not used |
| `sources` | `array` | Letter citations; empty when `grounded` is `false` or `null` |
| `langfuse_trace_id` | `string` | Langfuse trace ID; always present |
| `cache_hit` | `bool` | `true` when semantic cache served the answer |

### Typical stream sequence

```
data: {"type":"progress","stage":"rag","message":"Searching Buffett letters…"}
data: {"type":"progress","stage":"synthesizing","message":"Composing answer…"}
data: {"type":"token","content":"## GEICO's Underwriting Discipline\n\n"}
data: {"type":"token","content":"Buffett returned to GEICO's discipline…"}
…
data: {"type":"done","message_id":"uuid","grounded":true,"sources":[…],"cache_hit":false}
```

### Multi-turn

```bash
# Turn 1
POST /chats/abc123/messages {"query": "How would Buffett view Apple's moat?"}

# Turn 2 — same chat_id; graph restores full history automatically
POST /chats/abc123/messages {"query": "Compare that to Coca-Cola in 1988."}
```

| Code | Meaning |
|------|---------|
| `200` | Stream started; blocked/error events inside the stream |
| `403` | Chat does not belong to user |
| `404` | Chat not found |
| `422` | Request body validation failed |

### curl example

```bash
curl -N -X POST http://localhost:8000/chats/CHAT_ID/messages \
  -H "Content-Type: application/json" \
  -d '{"user_id": "USER_ID", "query": "How would Buffett evaluate Apple'\''s moat?"}'
```

---

## `GET /users/{user_id}/memory/long-term`

**Response `200`**
```json
{
  "user_id": "uuid",
  "profile": {
    "tracked_companies": ["AAPL", "KO"],
    "research_interests": ["economic moats", "capital allocation"],
    "preferences": {},
    "explicit_memories": []
  }
}
```

| Code | Meaning |
|------|---------|
| `200` | Profile returned (may have empty lists on first run) |
| `404` | User not found |

---

## `GET /users/{user_id}/chats/{chat_id}/memory/short-term`

**Query params:** `?limit_turn_pairs=5` (1–20)

**Response `200`**
```json
{
  "user_id": "uuid",
  "chat_id": "uuid",
  "thread_id": "uuid",
  "turn_pairs": [{"human": "…", "assistant": "…"}],
  "formatted": "User: …\nAssistant: …",
  "message_count": 2
}
```

| Code | Meaning |
|------|---------|
| `200` | Memory returned (empty on new chat) |
| `403` | Chat does not belong to user |
| `404` | Chat not found |

---

## `GET /health`

**Response `200`** `{"status":"ok","postgres":"ok","qdrant":"ok","mcp":"ok"}`

**Response `503`** `{"status":"degraded","postgres":"ok","qdrant":"ok","mcp":"error: …"}`

---

## `GET /debug/semantic-cache`

Read-only view of semantic cache entries.

**Query params:** `?limit=50` (1–500)

**Response `200`** — array of:
```json
{"id":"uuid","original_query":"What did Buffett write about moats?","hit_count":3,"expires_at":"2026-06-04T…"}
```

---

## `GET /debug/market-data-cache`

Read-only view of market data TTL cache.

**Query params:** `?limit=100` (1–500)

**Response `200`** — array of:
```json
{"id":"uuid","ticker":"AAPL","data_type":"info","fetched_at":"2026-05-28T10:00:00Z","expires_at":"2026-05-28T11:00:00Z"}
```

---

## `GET /debug/chats/{chat_id}/rag-retrievals`

RAG chunks retrieved for all assistant turns in a chat.

**Query params:** `?limit=200` (1–1000)

**Response `200`** — array of:
```json
{
  "id": "uuid",
  "message_id": "uuid",
  "letter_year": 1993,
  "passage_snippet": "brand names the attributes of their products…",
  "similarity_score": 0.469996,
  "used_in_response": true,
  "created_at": "2026-05-28T10:01:30Z"
}
```

---

## `GET /debug/chats/{chat_id}/guardrail-logs`

All guardrail check results for a chat.

**Query params:** `?limit=200` (1–1000)

**Response `200`** — array of:
```json
{
  "id": "uuid",
  "message_id": "uuid",
  "guardrail_type": "faithfulness",
  "result": "passed",
  "confidence": 0.9,
  "blocked_reason": null,
  "checked_at": "2026-05-28T10:01:28Z"
}
```

`guardrail_type`: `"input"` / `"output"` / `"faithfulness"` — `result`: `"passed"` / `"blocked"`

---

## Error response (non-stream)

```json
{"detail": "chat not found"}
```
