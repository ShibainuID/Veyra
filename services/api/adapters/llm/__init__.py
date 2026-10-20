"""Language-model adapter (plan: Claude for explanations and query parsing, offline fallback).

The model explains decisions the rules already made; it never decides them.
"""

import os

from config import Settings


def resolve_llm_mode(settings: Settings) -> str:
    if settings.llm_mode in ("live", "offline"):
        return settings.llm_mode
    has_credentials = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return "live" if has_credentials else "offline"
