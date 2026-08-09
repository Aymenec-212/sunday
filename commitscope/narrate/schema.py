"""Strict schema for the model's narration response."""

from __future__ import annotations

from pydantic import BaseModel


class NarrationItem(BaseModel):
    id: str
    text: str


class NarrationResponse(BaseModel):
    narrations: list[NarrationItem]
