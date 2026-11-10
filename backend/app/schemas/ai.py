"""Schemas for the AI assistant endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AiChatRequest(BaseModel):
    """Request body for ``POST /ai/chat``.

    Validation is schema-driven like every other endpoint: an absent,
    empty, or whitespace-only prompt is a 422 from OpenAPI-backed
    validation, not a hand-written 400 inside the route.
    """

    prompt: str = Field(min_length=1, max_length=2000)

    @field_validator('prompt')
    @classmethod
    def prompt_is_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError('prompt must not be blank')
        return stripped


__all__ = ['AiChatRequest']
