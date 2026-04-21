"""Illustrative seed cases for demo mode.

These are loosely modeled on public reporting of well-known attribution
events (Elimar, Samson and Delilah, etc.). They are intentionally labeled
[SEED] in the case ID space and carry a moderate confidence score so that
the user can see the indices take meaningful values on first run without
requiring an API key.

Real cases discovered by the agent will coexist with these; the seed cases
can be filtered out of production analyses by checking case_id prefix.

No facts invented beyond what is publicly reported. Values are order-of-
magnitude estimates. Users should replace or extend this list with
cases documented from primary sources before relying on the output.
"""

from __future__ import annotations

from .schema import AttributionCase, CaseType, HybridizationKind, Resolution


def seed_cases() -> list[AttributionCase]:
    """Return a small set of illustrative cases.

    Each case is keyed with 'seed-' in the case_id so production filters
    can exclude them.
    """

    def _c(**kwargs) -> AttributionCase:
        title = kwargs["artwork_title"]
        artist = kwargs["claimed_artist"]
        seed_id = "seed-" + AttributionCase.build_case_id(
            title, artist, kwargs["source_urls"][0]
        )[:12]
        kwargs["case_id"] = seed_id
        return AttributionCase(**kwargs)

    return [
        # Divergence — the paper's framing case
        _c(
            case_type=CaseType.DIVERGENCE,
            artwork_title="Elimar",
            claimed_artist="Vincent van Gogh",
            estimated_value_usd=15_000_000,  # order-of-magnitude; Van Goghs are high-stakes
            ai_tool="Art Recognition",
            institution="Van Gogh Museum",
            resolution=Resolution.INSTITUTION_PREVAILED,
            source_urls=["https://www.nytimes.com/"],  # placeholder; replace with primary source
            reasoning="Publicly reported: Art Recognition assigned high confidence as Van Gogh; "
                      "Van Gogh Museum disagreed; market did not accept the work as an autograph "
                      "Van Gogh.",
            confidence=0.85,
            event_date="2023-11-15",
        ),
        # Divergence — a safetyist-type outcome: unresolved, long-running institutional contest
        _c(
            case_type=CaseType.DIVERGENCE,
            artwork_title="Samson and Delilah",
            claimed_artist="Peter Paul Rubens",
            estimated_value_usd=60_000_000,
            ai_tool="Art Recognition",
            institution="The National Gallery, London",
            resolution=Resolution.UNRESOLVED,
            source_urls=["https://www.theguardian.com/"],
            reasoning="Decades-long attribution controversy; AI analyses have publicly disputed "
                      "the National Gallery's Rubens attribution. The institution has maintained "
                      "its position; the matter remains contested.",
            confidence=0.70,
            event_date="2021-10-01",
        ),
        # Hybridization — institution explicitly treats AI as corroborating support
        _c(
            case_type=CaseType.HYBRIDIZATION,
            artwork_title="(illustrative auction lot)",
            claimed_artist="Old Master (workshop attribution)",
            estimated_value_usd=2_500_000,
            ai_tool="(proprietary ML analysis)",
            institution="Major auction house",
            hybridization_kind=HybridizationKind.SUPPLEMENTARY,
            source_urls=["https://www.theartnewspaper.com/"],
            reasoning="Illustrative hybridization case: auction catalog cites machine-learning "
                      "analysis as supporting a workshop attribution. Replace with documented cases.",
            confidence=0.50,
            event_date="2024-03-01",
        ),
    ]
