"""Langfuse instrumentation — minimal stub for Phase 2.

Real spans per node are added in Phase 3. For now we expose `new_trace_id()`
so assistant messages get a stable id stored in `messages.langfuse_trace_id`.
"""
from __future__ import annotations

import uuid


def new_trace_id() -> str:
    """Generate a placeholder trace id; will be replaced with Langfuse.trace.id in Phase 3."""
    return f"local-{uuid.uuid4()}"
