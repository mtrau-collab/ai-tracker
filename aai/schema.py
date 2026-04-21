"""Data models for the Authentication Authority Index tracker.

Two case types, matching the operational pairing from the paper:

- DIVERGENCE: an attribution dispute where an AI analysis and an institutional
  authority reached different conclusions. Feeds the Money-Weighted
  Divergence Resolution Index.

- HYBRIDIZATION: an institutional attribution that cites AI analysis as
  supporting, supplementary, or corroborating evidence. Feeds the
  Hybridization Index.

A case is stored with a stable `case_id` (hash of artwork + artist + source
URL) so re-running discovery idempotently deduplicates.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CaseType(str, Enum):
    DIVERGENCE = "divergence"
    HYBRIDIZATION = "hybridization"


class Resolution(str, Enum):
    """Resolution categories from Section IV of the paper."""
    AI_PREVAILED = "ai_prevailed"          # Category A: accelerationist signal
    INSTITUTION_PREVAILED = "institution_prevailed"  # Category B: skeptic signal
    UNRESOLVED = "unresolved"              # Category C (mild)
    CRISIS = "crisis"                      # Category C (safetyist signal: litigation, market freeze, etc.)


class HybridizationKind(str, Enum):
    CORROBORATING = "corroborating"        # AI agreed with independent institutional finding
    SUPPLEMENTARY = "supplementary"        # AI provided additional evidence to an institutional determination
    DECISION_SUPPORT = "decision_support"  # Institution used AI as input to its reasoning
    PRIMARY = "primary"                    # Institution relied on AI as its principal basis


class AttributionCase(BaseModel):
    """A single discovered event — either a divergence or a hybridization case."""

    case_id: str = Field(description="Stable hash of artwork + artist + canonical URL")
    case_type: CaseType

    # Identifying fields
    artwork_title: str
    claimed_artist: str
    estimated_value_usd: Optional[float] = Field(
        default=None,
        description="Best-available estimate of the disputed economic value, in USD. "
                    "None when no credible figure exists in the source."
    )

    # Parties and determinations
    ai_tool: Optional[str] = Field(
        default=None,
        description="Name of the AI system, model, or vendor involved (e.g., 'Art Recognition')."
    )
    institution: Optional[str] = Field(
        default=None,
        description="Name of the institutional authority involved (e.g., 'Van Gogh Museum')."
    )

    # Divergence-specific
    resolution: Optional[Resolution] = None

    # Hybridization-specific
    hybridization_kind: Optional[HybridizationKind] = None

    # Provenance
    source_urls: list[str] = Field(default_factory=list)
    reasoning: str = Field(
        default="",
        description="Brief explanation of why the case was classified this way."
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Timestamps
    event_date: Optional[str] = Field(
        default=None,
        description="ISO date of the underlying event (attribution announcement, "
                    "ruling, sale), when extractable from the source."
    )
    discovered_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @classmethod
    def build_case_id(cls, artwork_title: str, claimed_artist: str, primary_url: str) -> str:
        key = f"{artwork_title.strip().lower()}|{claimed_artist.strip().lower()}|{primary_url.strip()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class IndexSnapshot(BaseModel):
    """A snapshot of the two core indices at a point in time.

    Written on every `run_update` invocation so that the dashboard can plot
    the trend. The snapshot is what makes the system continuously monitoring
    rather than a one-time calculation.
    """

    snapshot_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    # Core indices from the paper's operational pairing
    money_weighted_dri: Optional[float] = Field(
        default=None,
        ge=-1.0, le=1.0,
        description="Range [-1, +1]. +1 = AI wins all value-weighted divergences; "
                    "-1 = institutions win all; 0 = balanced. None if no cases."
    )
    hybridization_index: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description="Fraction of observed institutional attribution events that cite AI. "
                    "None if no cases."
    )

    # Diagnostic fields — support for the full AAI framework
    instability_share: Optional[float] = Field(
        default=None,
        description="Safetyist diagnostic: value-weighted share of divergence cases "
                    "that resolved into crisis / litigation / market freeze."
    )

    divergence_cases_total: int = 0
    hybridization_cases_total: int = 0
    window_days: int = 365
