"""Typed exception hierarchy for ZimShire — raise at the right layer."""


class ZimShireError(Exception):
    """Base for all application-level exceptions."""


class DomainError(ZimShireError):
    """Business rule / invariant violation."""


class NotFoundError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class RepositoryError(ZimShireError):
    """Database / persistence failure."""


class CacheError(ZimShireError):
    """Semantic or market cache failure."""


class LLMError(ZimShireError):
    """LLM gateway / model call failure."""


class GuardrailError(ZimShireError):
    """Guardrail evaluation failure (e.g. malformed LLM response)."""


class AgentPlanError(ZimShireError):
    """Orchestrator failed to produce a valid plan."""
