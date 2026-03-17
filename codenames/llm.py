"""LLM provider abstraction using litellm for multi-provider support."""

from __future__ import annotations

import os
from dataclasses import dataclass

import litellm


@dataclass
class LLMConfig:
    """Configuration for an LLM-backed team.

    model: a litellm model string, e.g.
        "anthropic/claude-sonnet-4-20250514"
        "openai/gpt-4o"
        "google/gemini-2.0-flash"
    temperature: sampling temperature
    """

    model: str
    temperature: float = 0.7
    max_tokens: int = 1024

    @property
    def provider(self) -> str:
        return self.model.split("/")[0] if "/" in self.model else "openai"

    @property
    def display_name(self) -> str:
        return self.model.split("/")[-1] if "/" in self.model else self.model


def chat(config: LLMConfig, messages: list[dict], response_format: dict | None = None) -> str:
    """Send a chat completion request and return the assistant's text reply."""
    kwargs: dict = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content.strip()
