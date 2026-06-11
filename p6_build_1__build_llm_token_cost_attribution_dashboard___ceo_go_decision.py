"""Core data model and cost calculation for LLM Token Cost Attribution."""

import sys
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ModelRate:
    """Pricing rates for a specific LLM model."""
    model_key: str
    input_price_per_1k: float   # USD
    output_price_per_1k: float  # USD


@dataclass(frozen=True)
class UsageRecord:
    """A single LLM usage event to be costed."""
    model_key: str
    input_tokens: int