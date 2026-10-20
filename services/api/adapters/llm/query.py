"""The language model parses an assistant question into a `QueryIntent` (plan Section 4: assistant).

The model only maps the farm user's words to the schema. It sees the farm's animal ids and names as data, never
writes the answer, and its output is validated again by `domain.assistant` (animal refs outside the farm are
dropped). Any failure returns None so the caller uses the offline parser.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from adapters.llm.client import LLMResult, structured_call
from config import Settings

Intent = Literal["animal_lookup", "location_lookup", "alert_lookup", "coverage_lookup", "unknown"]
Want = Literal["passport", "location", "coverage", "alerts"]


class QueryIntent(BaseModel):
    intent: Intent
    animal_refs: list[str] = Field(default_factory=list,
                                   description="Ids of animals from <records> that the question is about.")
    wants: list[Want] = Field(default_factory=list)


SYSTEM_PROMPT = """You map a farm user's question about their own livestock to the QueryIntent schema.
- intent: animal_lookup (details or passport of specific animals), location_lookup (where an animal was seen on \
camera), alert_lookup (alerts or warnings), coverage_lookup (insurance policies or coverage), or unknown.
- animal_refs: the ids of the animals the question names, by id or by name. Only use ids listed in <records>. \
Leave it empty for farm-wide questions.
- wants: every kind of information asked for: passport, location, coverage, alerts. A question may want several.
Return intent unknown with empty lists when you are unsure or the question is not about these records."""


def parse_with_llm(settings: Settings, text: str, animals: list[dict[str, str]], *,
                      client: Any | None = None) -> LLMResult[QueryIntent]:
    records = json.dumps([{"id": a["id"], "name": a["name"]} for a in animals], ensure_ascii=False)
    user = f"<records>\n{records}\n</records>\n<user_text>\n{text}\n</user_text>"
    return structured_call(settings, system=SYSTEM_PROMPT, user=user, output_model=QueryIntent, effort="low",
                           max_tokens=1000, client=client)
