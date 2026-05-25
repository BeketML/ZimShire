# ZimShire Database Schema Reference

All tables live in a single Postgres database. The schema divides into two groups: **Custom tables** (your business logic) and **LangGraph built-in tables** (managed by `langgraph-checkpoint-postgres` and `langgraph.store.postgres` from the `langgraph` package).

---

## Custom Tables

### `users`

The root identity table. Every chat and memory object traces back to a `user_id`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | `uuid` | PK | Unique identifier for the user |
| `created_at` | `timestamp` | | Account creation time |

---

### `chats`

Represents a single named conversation session. Each chat maps 1-to-1 with a LangGraph checkpointer thread: pass `str(chat_id)` as `config["configurable"]["thread_id"]` — no separate column in Postgres.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `chat_id` | `uuid` | PK | Also used as LangGraph `thread_id` (`str(chat_id)`) for checkpoint restore |
| `user_id` | `uuid` | FK → `users.user_id` | Owner of the conversation |
| `chat_title` | `text` | | Human-readable name for the conversation |
| `model` | `text` | | LiteLLM model slug chosen at chat creation (e.g. `openai/gpt-4o`) |
| `provider` | `text` | | Provider name (e.g. `openai`, `anthropic`) |
| `created_at` | `timestamp` | | |
| `updated_at` | `timestamp` | | |

---

### `messages`

Individual turns in a conversation. Every `assistant` message links to its Langfuse trace for observability.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `message_id` | `uuid` | PK | |
| `chat_id` | `uuid` | FK → `chats.chat_id` | |
| `role` | `text` | | `"human"` or `"assistant"` |
| `content` | `text` | | Raw message body |
| `grounded` | `bool` | | For assistant messages: `true` if the answer was grounded in retrieved Buffett letter context; `false` when retrieval could not support a claim; `NULL` for human messages |
| `langfuse_trace_id` | `text` | | Langfuse trace ID attached to this turn; `NULL` for human messages |
| `created_at` | `timestamp` | | |

---

### `rag_retrievals`

Audit log of every Qdrant **point** returned for one assistant message. One search returns top-k hits; you insert **k rows** here (same `message_id`, different `qdrant_point_id`). Postgres does not store the corpus — only a snapshot of what was retrieved for citations and faithfulness checks.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `uuid` | PK | |
| `message_id` | `uuid` | FK → `messages.message_id` | Assistant message this retrieval belongs to |
| `qdrant_collection` | `text` | NOT NULL | Collection name, e.g. `"buffett_letters"` (point ids are unique only within a collection) |
| `qdrant_point_id` | `text` | NOT NULL | Qdrant point id as string — UUID or uint64 per [Qdrant point IDs](https://qdrant.tech/documentation/concepts/points/#point-ids) |
| `rank` | `smallint` | | Position in top-k results (`0` = best match) |
| `letter_year` | `int` | | Denormalized from Qdrant payload; Buffett letter year (e.g. `1988`) |
| `passage_snippet` | `text` | | Short excerpt for user-facing citation (not full chunk text) |
| `similarity_score` | `float` | | Score returned by Qdrant at retrieval time |
| `used_in_response` | `bool` | | `true` if this passage was cited or relied on in the final answer |
| `created_at` | `timestamp` | | |

**Unique constraint:** `(message_id, qdrant_collection, qdrant_point_id)` — prevents logging the same hit twice for one message.

---

### `guardrail_logs`

Records every guardrail evaluation against a message (input, output, and faithfulness). Allows offline analysis of block rates and confidence distributions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `uuid` | PK | |
| `message_id` | `uuid` | FK → `messages.message_id` | |
| `guardrail_type` | `text` | | One of `"input"`, `"output"`, `"faithfulness"` |
| `result` | `text` | | `"passed"` or `"blocked"` |
| `confidence` | `float` | | Classifier confidence score (0–1) |
| `blocked_reason` | `text` | | Human-readable explanation when `result = "blocked"`; `NULL` otherwise |
| `checked_at` | `timestamp` | | |

---

### `market_data_cache`

TTL cache for yfinance API responses. Avoids redundant network calls within a single session window.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `uuid` | PK | |
| `ticker` | `text` | | Stock symbol, e.g. `"AAPL"` |
| `data_type` | `text` | | What was fetched, e.g. `"financials"`, `"info"`, `"history"` |
| `payload` | `jsonb` | | Raw yfinance response serialised to JSON |
| `fetched_at` | `timestamp` | | |
| `expires_at` | `timestamp` | | Cache is stale after this point; application checks before reading |

---

### `semantic_cache`

Stores embeddings of past queries and their full responses. Before calling the LLM, the system checks this table for a semantically similar hit above a threshold.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `uuid` | PK | |
| `query_embedding` | `vector` | | pgvector embedding of `original_query` |
| `original_query` | `text` | | Exact user query string that was cached |
| `cached_response` | `text` | | Full assistant response text |
| `sources` | `jsonb` | | Source attribution metadata (letter years, snippets) from the original response |
| `hit_count` | `int` | | How many times this cache entry has been served |
| `expires_at` | `timestamp` | | Absolute expiry; `NULL` means it never expires |

---

## Qdrant integration (Buffett letters RAG)

Qdrant and Postgres serve different roles. Do not confuse **payload indexes** or the collection **HNSW index** with “one index per chunk.”

| Concept in Qdrant | What it is | Count for ZimShire |
|-------------------|------------|-------------------|
| **Collection** | Container for all letter chunks | One, e.g. `buffett_letters` |
| **HNSW index** | Vector search structure inside the collection | One per collection (shared by all chunks) |
| **Payload index** | Fast filter on a payload field | Optional per field (`letter_year`, etc.) |
| **Point** | One chunk = one `id` + vector + payload | Many (one per chunk) |

Full chunk text and embeddings live in Qdrant. `rag_retrievals` stores only retrieval-time metadata so citations work even if Qdrant is temporarily unavailable.

### Ingestion (offline, once)

`scripts/ingest_letters.py` may import embedding/upsert helpers from `mcp.services.qdrant` (allowed offline path). The FastAPI app must not import `mcp.services` directly.

```python
import uuid
from qdrant_client import QdrantClient
from qdrant_client import models

COLLECTION = "buffett_letters"
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # fixed namespace for idempotent ids


def point_id_for_chunk(letter_year: int, chunk_index: int) -> str:
    """Deterministic id so re-ingestion upserts the same point."""
    return str(uuid.uuid5(NAMESPACE, f"{letter_year}:{chunk_index}"))


client = QdrantClient(url="http://localhost:6333")

client.create_collection(
    collection_name=COLLECTION,
    vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
)

client.create_payload_index(
    collection_name=COLLECTION,
    field_name="letter_year",
    field_schema=models.PayloadSchemaType.INTEGER,
)

client.upsert(
    collection_name=COLLECTION,
    points=[
        models.PointStruct(
            id=point_id_for_chunk(chunk.letter_year, chunk.chunk_index),
            vector=chunk.embedding,
            payload={
                "letter_year": chunk.letter_year,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "source_file": chunk.source_file,
            },
        )
        for chunk in all_chunks
    ],
)
```

### Search and persist to `rag_retrievals`

```python
from qdrant_client import QdrantClient

COLLECTION = "buffett_letters"


async def retrieve_and_log(session, assistant_message_id: uuid.UUID, query_vector: list[float], top_k: int = 5):
    client = QdrantClient(url="http://localhost:6333")
    hits = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    ).points

    for rank, hit in enumerate(hits):
        await session.execute(
            insert(RagRetrieval).values(
                message_id=assistant_message_id,
                qdrant_collection=COLLECTION,
                qdrant_point_id=str(hit.id),
                rank=rank,
                letter_year=hit.payload["letter_year"],
                passage_snippet=hit.payload["text"][:500],
                similarity_score=hit.score,
                used_in_response=False,
            )
        )
    return hits
```

### Optional: one best chunk per letter

Use the [Grouping API](https://qdrant.tech/documentation/search/search/#grouping-api) with `group_by="letter_year"` when you want diversity across years instead of many chunks from the same letter.

```python
groups = client.query_points_groups(
    collection_name=COLLECTION,
    query=query_vector,
    group_by="letter_year",
    limit=5,
    group_size=1,
)
```

---

## LangGraph Built-in Tables

These tables are created automatically by `langgraph-checkpoint-postgres` and `AsyncPostgresStore.setup()` (`langgraph.store.postgres`). You do **not** write SQL against them directly; use the LangGraph Python API.

### Short-term memory — checkpointer tables

Three tables managed by `AsyncPostgresSaver`:

| Table | Columns | Purpose |
|-------|---------|---------|
| `checkpoints` | `thread_id` PK, `checkpoint_ns` PK, `checkpoint_id` PK, `parent_checkpoint_id`, `checkpoint` jsonb, `metadata` jsonb | One row per graph snapshot |
| `checkpoint_blobs` | `thread_id` PK, `checkpoint_ns` PK, `channel` PK, `version` PK, `blob` bytea | Binary channel state |
| `checkpoint_writes` | `thread_id` PK, `checkpoint_ns` PK, `checkpoint_id` PK, `task_id` PK, `idx` PK, `channel`, `blob` bytea | Pending node outputs before a checkpoint is committed |

**How to interact:**

```python
import uuid

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import psycopg

DB_URI = "postgresql://user:pass@localhost:5432/zimshire"


async def run_graph_turn(chat_id: uuid.UUID, user_input: str):
    async with await psycopg.AsyncConnection.connect(DB_URI) as conn:
        checkpointer = AsyncPostgresSaver(conn)
        await checkpointer.setup()  # creates tables if absent

        graph = build_zimshire_graph(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": str(chat_id)}}

        async for chunk in graph.astream(
            {"messages": [{"role": "human", "content": user_input}]},
            config=config,
            stream_mode="values",
        ):
            yield chunk


async def get_conversation_state(chat_id: uuid.UUID):
    async with await psycopg.AsyncConnection.connect(DB_URI) as conn:
        checkpointer = AsyncPostgresSaver(conn)
        config = {"configurable": {"thread_id": str(chat_id)}}
        snapshot = await checkpointer.aget(config)
        return snapshot  # contains .values (state dict) and .metadata
```

---

### Long-term memory — store tables

Two tables managed by `AsyncPostgresStore` (requires `pgvector` extension):

| Table | Columns | Purpose |
|-------|---------|---------|
| `store` | `prefix` PK, `key` PK, `value` jsonb, `created_at`, `updated_at` | Key-value namespace store |
| `store_vectors` | `prefix` PK, `key` PK, `field_name` PK, `embedding` vector | Vector index over stored items for semantic search |

The `prefix` is a slash-separated namespace path, e.g. `"users/abc123/interests"`. The `key` is an item identifier within that namespace.

**How to interact:**

```python
from langgraph.store.postgres.aio import AsyncPostgresStore
from langchain_openai import OpenAIEmbeddings

DB_URI = "postgresql://user:pass@localhost:5432/zimshire"


async def setup_store() -> AsyncPostgresStore:
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    store = AsyncPostgresStore.from_conn_string(
        DB_URI,
        index={
            "dims": 1536,
            "embed": embeddings.aembed_documents,
            "fields": ["interest", "company"],  # jsonb fields to index
        },
    )
    await store.setup()  # creates store + store_vectors tables
    return store


# --- Write a user memory item ---
async def save_user_interest(store, user_id: str, company: str, notes: str):
    namespace = ("users", user_id, "interests")
    await store.aput(
        namespace,
        key=company,
        value={"company": company, "interest": notes},
    )


# --- Read a specific item by key ---
async def get_user_interest(store, user_id: str, company: str):
    namespace = ("users", user_id, "interests")
    item = await store.aget(namespace, key=company)
    return item.value if item else None


# --- Semantic search across a user's memories ---
async def search_user_memories(store, user_id: str, query: str, top_k: int = 5):
    namespace = ("users", user_id, "interests")
    results = await store.asearch(namespace, query=query, limit=top_k)
    return [{"key": r.key, "value": r.value, "score": r.score} for r in results]


# --- List all memories for a user ---
async def list_user_memories(store, user_id: str):
    namespace = ("users", user_id, "interests")
    return await store.alist(namespace)


# --- Delete a memory item ---
async def delete_user_interest(store, user_id: str, company: str):
    namespace = ("users", user_id, "interests")
    await store.adelete(namespace, key=company)
```

**Using the store inside a graph node (injected via `RunnableConfig`):**

```python
from langgraph.store.base import BaseStore
from langchain_core.runnables import RunnableConfig


async def personalization_node(state: dict, config: RunnableConfig, store: BaseStore):
    user_id = config["configurable"]["user_id"]
    namespace = ("users", user_id, "interests")

    # Retrieve top-3 relevant memories for the current query
    memories = await store.asearch(namespace, query=state["messages"][-1]["content"], limit=3)
    context = "\n".join(m.value.get("interest", "") for m in memories)

    # Pass context downstream in state
    return {"user_memory_context": context}
```

---

## Entity Relationships

```mermaid
erDiagram
    users ||--o{ chats : "has"
    chats ||--o{ messages : "contains"
    messages ||--o{ rag_retrievals : "has"
    messages ||--o{ guardrail_logs : "checked_by"
    chats {
        uuid chat_id PK
        uuid user_id FK
    }
    messages {
        uuid message_id PK
        uuid chat_id FK
        bool grounded
        text langfuse_trace_id
    }
    rag_retrievals {
        uuid id PK
        uuid message_id FK
        text qdrant_collection
        text qdrant_point_id
        smallint rank
        int letter_year
    }
    guardrail_logs {
        uuid id PK
        uuid message_id FK
        text guardrail_type
    }
    market_data_cache {
        uuid id PK
        text ticker
        timestamp expires_at
    }
    semantic_cache {
        uuid id PK
        vector query_embedding
        timestamp expires_at
    }
```
