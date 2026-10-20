"""Request and response models for the in-app VEYRA agent conversations (`/agent/conversations`).

A card is `{type, data}`: the type names which data-backed block the web renders (domain/agent_chat.py builds each
from records). Kept apart from the other schema modules so parallel work does not collide.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from schemas import UTCDateTime

Intent = Literal["find_insurance", "file_claim", "track_claim"]
CardType = Literal["passport_summary", "eligibility_questions", "plan_comparison", "recommendation",
                   "application_draft", "action_review", "status_steps", "claim_checklist", "missing_items",
                   "receipt", "claim_status"]


class ConversationCreate(BaseModel):
    animal_id: str = Field(min_length=1)
    intent: Intent


class ChoicePick(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    value: str | None = Field(default=None, max_length=2000)


class MessageCreate(BaseModel):
    """Exactly one of `text` (the farmer's words, kept as data) or `choice` (one the agent offered)."""

    text: str | None = Field(default=None, max_length=1000)
    choice: ChoicePick | None = None

    @model_validator(mode="after")
    def _one_input(self) -> "MessageCreate":
        if (self.text is None) == (self.choice is None):
            raise ValueError("send exactly one of text or choice")
        return self


class AgentCard(BaseModel):
    type: CardType
    data: dict[str, Any]


class AgentChoice(BaseModel):
    key: str
    value: str | None
    label: str
    style: Literal["primary", "secondary", "link"]
    # A choice with an href is a link to another screen, not an answer.
    href: str | None


class AgentMessageOut(BaseModel):
    id: str
    seq: int
    role: Literal["agent", "user"]
    text: str
    cards: list[AgentCard]
    choices: list[AgentChoice]
    # `live` when the model phrased a verified template, `simulated` for the template itself, `user` for the farmer.
    source: Literal["live", "simulated", "user"]
    created_at: UTCDateTime


class ConversationAnimal(BaseModel):
    id: str
    name: str
    breed: str
    identity_status: str
    coverage_status: Literal["active", "pending", "none"]
    coverage_label: str
    product_name: str | None
    policy_id: str | None


class ConversationOut(BaseModel):
    id: str
    intent: Intent
    animal_id: str
    animal: ConversationAnimal
    created_by: str
    created_at: UTCDateTime
    updated_at: UTCDateTime
    messages: list[AgentMessageOut]
