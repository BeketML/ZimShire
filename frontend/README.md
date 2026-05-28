# ZimShire Frontend

Standalone React 18 + TypeScript + Vite frontend for the ZimShire investment research assistant.

## Prerequisites

- Node.js 18+
- ZimShire backend running at `http://localhost:8000`

## Quick start

```bash
cd frontend
npm install
npm run dev
```

Opens at **http://localhost:5173** — proxies all `/api/*` requests to `http://localhost:8000`.

## Stack

| Layer | Choice |
|-------|--------|
| Framework | React 18 + TypeScript |
| Build | Vite 5 |
| Styles | Tailwind CSS (no component library) |
| SSE | Native `fetch` + `ReadableStream` |
| Markdown | `marked` + `DOMPurify` |
| State | React hooks + localStorage |

## Environment

Copy `.env.example` to `.env` for custom API URL:

```bash
cp .env.example .env
```

The Vite proxy (`/api → http://localhost:8000`) handles CORS during development — no env var needed for local dev.

## SSE event handling

The frontend handles all 6 SSE event types:

| Event | Behavior |
|-------|----------|
| `progress` | Animated badge: "Searching Buffett letters…" |
| `token` | Append to message bubble in real-time |
| `replace` | Replace all streamed content (output guardrail rewrite) |
| `blocked` | Show amber warning bubble |
| `error` | Show red error bubble |
| `done` | Show grounded badge + sources citation panel |

## Structure

```
src/
  api/          # Typed API wrappers
  hooks/        # useUser, useChat, useStream logic
  components/   # Pure presentational components
  types/        # Shared TypeScript interfaces
  styles/       # Tailwind globals + markdown prose styles
```
