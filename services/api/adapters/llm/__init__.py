"""Language-model adapter: OpenAI (default, gpt-6-luna) or Anthropic for explanations and query parsing.

The model explains decisions the rules already made; it never decides them. Without the selected provider's
key the app runs offline with labeled template answers.
"""

import os

from config import Settings

# Environment variables that hold each provider's credentials.
CREDENTIAL_VARS = {"openai": ("OPENAI_API_KEY",), "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}


def resolve_llm_mode(settings: Settings) -> str:
    if settings.llm_mode in ("live", "offline"):
        return settings.llm_mode
    has_credentials = any(os.environ.get(name) for name in CREDENTIAL_VARS[settings.llm_provider])
    return "live" if has_credentials else "offline"
