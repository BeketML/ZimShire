"""Parse SSE event streams from httpx response bodies."""
from __future__ import annotations

import json


def parse_sse_lines(body: str | bytes) -> list[dict]:
    """Parse SSE 'data: {...}' lines into a list of dicts."""
    if isinstance(body, bytes):
        body = body.decode()
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


def find_event(events: list[dict], event_type: str) -> dict | None:
    return next((e for e in events if e.get("type") == event_type), None)
