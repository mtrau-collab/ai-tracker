"""Search query configuration for agent discovery runs.

Each query is targeted at one of the two observable case types. The agent
runs every query in sequence on each update cycle; new cases are added
and known cases are refreshed.

The queries are intentionally general enough to pick up newly-surfaced
cases the author of this code hasn't anticipated. Add new queries here
to expand coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SearchQuery:
    label: str
    query: str
    target: Literal["divergence", "hybridization", "mixed"]
    # Notes for the classifier about what's likely to appear for this query.
    notes: str = ""


DIVERGENCE_QUERIES: list[SearchQuery] = [
    SearchQuery(
        label="art-recognition-disputes",
        query="Art Recognition AI painting attribution dispute museum",
        target="divergence",
        notes="Art Recognition is the most publicly-covered AI authentication vendor; "
              "its disputes with museums and foundations are the central divergence "
              "case type.",
    ),
    SearchQuery(
        label="foundation-rejection-ai",
        query="artist foundation rejects AI attribution authentication",
        target="divergence",
    ),
    SearchQuery(
        label="museum-ai-attribution-contested",
        query="museum contested AI attribution painting",
        target="divergence",
    ),
    SearchQuery(
        label="neural-network-authentication-dispute",
        query="neural network painting authentication disputed attribution",
        target="divergence",
    ),
    SearchQuery(
        label="ai-van-gogh-rubens-attribution",
        query="AI attribution Van Gogh Rubens Rembrandt disputed",
        target="divergence",
        notes="Historically the most AI-contested artists.",
    ),
]


HYBRIDIZATION_QUERIES: list[SearchQuery] = [
    SearchQuery(
        label="auction-catalog-ai-cited",
        query="auction catalog cites AI analysis attribution",
        target="hybridization",
    ),
    SearchQuery(
        label="museum-attribution-neural-network",
        query="museum announces attribution supported by AI analysis",
        target="hybridization",
    ),
    SearchQuery(
        label="catalogue-raisonne-ai-supplementary",
        query="catalogue raisonné AI supplementary evidence attribution",
        target="hybridization",
    ),
    SearchQuery(
        label="christies-sothebys-ai",
        query="Christie's Sotheby's AI authentication painting provenance",
        target="hybridization",
    ),
]


MIXED_QUERIES: list[SearchQuery] = [
    SearchQuery(
        label="recent-ai-art-authentication",
        query="AI art authentication news",
        target="mixed",
        notes="General sweep for recent developments.",
    ),
    SearchQuery(
        label="machine-learning-attribution-announcement",
        query="machine learning artwork attribution announcement",
        target="mixed",
    ),
]


ALL_QUERIES: list[SearchQuery] = (
    DIVERGENCE_QUERIES + HYBRIDIZATION_QUERIES + MIXED_QUERIES
)
