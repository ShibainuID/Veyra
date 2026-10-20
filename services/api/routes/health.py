"""Health check: service version, perception capabilities, and the resolved LLM mode."""

from fastapi import APIRouter

from adapters.llm import resolve_llm_mode
from adapters.perception import effective_capabilities, probe_capabilities
from config import get_settings

VERSION = "0.1.0"

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": VERSION,
        "perception": {"mode": settings.perception_mode, "capabilities": probe_capabilities(),
                       "effective": effective_capabilities(settings)},
        "llm": {"mode": resolve_llm_mode(settings), "model": settings.llm_model},
    }
