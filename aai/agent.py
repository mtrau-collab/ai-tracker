"""Agentic discovery and classification of attribution cases.

This module is the "agentic Claude Code" layer the assignment asks for.
On each update cycle the agent is given a search query and autonomously:

  1. Calls the web_search tool (server-side, handled by the Anthropic API)
     as many times as it needs to gather evidence.
  2. Reads the results and identifies candidate attribution events.
  3. Classifies each candidate as DIVERGENCE, HYBRIDIZATION, or NOT_RELEVANT.
  4. Returns a structured JSON array of AttributionCase objects.

The model is configurable via the AAI_MODEL env var (default: claude-sonnet-4-6).
The Anthropic API key must be set in ANTHROPIC_API_KEY.

Because the web_search tool runs server-side, we don't need to implement
tool-result handling — Claude's final text block contains the synthesized
JSON output after all searches have completed.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from .schema import AttributionCase, CaseType, HybridizationKind, Resolution
from .sources import SearchQuery


DEFAULT_MODEL = os.environ.get("AAI_MODEL", "claude-sonnet-4-6")


SYSTEM_PROMPT = """You are a research agent helping to maintain an academic index \
that tracks how authority in art authentication is migrating between AI systems \
and traditional institutions (foundations, major museums, established connoisseurs).

You classify real-world attribution events into two categories:

DIVERGENCE: A specific artwork where an AI analysis and an institutional authority \
reached different attribution conclusions. Extract:
  - artwork_title: the name of the specific work
  - claimed_artist: the artist the AI or the claimant asserts painted it
  - estimated_value_usd: best-available USD estimate of the disputed value (null if none)
  - ai_tool: name of the AI system or vendor (e.g., "Art Recognition")
  - institution: name of the institution disputing (e.g., "Van Gogh Museum")
  - resolution: one of:
      "ai_prevailed"          — the AI determination ultimately controlled the outcome
      "institution_prevailed" — the institutional determination controlled
      "unresolved"            — no clear winner yet
      "crisis"                — litigation, market freeze, insurer withdrawal, or regulatory action
  - source_urls: URLs of the articles supporting the classification
  - reasoning: one or two sentences explaining your classification
  - confidence: 0.0-1.0 calibrated to how confidently you could defend the classification
  - event_date: ISO date of the underlying event if extractable, else null

HYBRIDIZATION: An institutional attribution announcement that explicitly cites AI \
analysis as supporting, supplementary, or corroborating evidence. Extract:
  - artwork_title, claimed_artist, estimated_value_usd, ai_tool, institution (as above)
  - hybridization_kind: one of:
      "corroborating"     — AI confirmed an independent institutional finding
      "supplementary"     — AI added weight to an institutional determination
      "decision_support"  — institution used AI as an input to its reasoning
      "primary"           — institution relied on AI as its principal basis
  - source_urls, reasoning, confidence, event_date (as above)

HARD REQUIREMENTS:
- Only include cases about SPECIFIC artworks. General articles about AI in the art market \
are not cases.
- Only include cases where you can identify the specific AI tool AND the specific \
institution involved. If either is generic or missing, skip the case.
- Be conservative with confidence. 0.9+ only when source reporting is unambiguous. \
Use 0.5 for cases that are plausible but under-documented.
- Do not invent source URLs. Only cite URLs that actually appeared in your search results.
- Do not classify opinion pieces, speculation, or general commentary as cases.

OUTPUT FORMAT: After running your searches, end your response with a single fenced \
JSON block containing an array of case objects. If no valid cases are found, return \
an empty array. No other text after the JSON block.
"""


def _build_user_prompt(sq: SearchQuery) -> str:
    target_guidance = {
        "divergence": "Focus on divergence cases.",
        "hybridization": "Focus on hybridization cases.",
        "mixed": "Include both divergence and hybridization cases.",
    }[sq.target]

    notes_block = f"\n\nContext: {sq.notes}" if sq.notes else ""

    return (
        f"Search the web using the query: \"{sq.query}\"\n\n"
        f"{target_guidance} Run additional follow-up searches if needed to verify "
        f"details (estimated values, outcomes, institutions).{notes_block}\n\n"
        f"Return a JSON array of case objects per the schema in the system prompt. "
        f"Limit output to at most 8 cases per query."
    )


def _extract_json_array(text: str) -> list[dict]:
    """Pull the final JSON array out of Claude's text output.

    Accepts fenced code blocks (```json ... ```) or a bare array. If no
    array is found, returns [].
    """
    fenced = re.findall(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        raw = fenced[-1]
    else:
        # Fall back to the last bare array in the text.
        bare = re.findall(r"(\[\s*\{.*?\}\s*\])", text, re.DOTALL)
        if not bare:
            return []
        raw = bare[-1]
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _coerce_to_case(raw: dict) -> Optional[AttributionCase]:
    """Convert a raw JSON case from the agent into a validated AttributionCase."""
    try:
        title = (raw.get("artwork_title") or "").strip()
        artist = (raw.get("claimed_artist") or "").strip()
        urls = raw.get("source_urls") or []
        if not title or not artist or not urls:
            return None

        primary_url = urls[0]
        case_id = AttributionCase.build_case_id(title, artist, primary_url)

        # Determine case type from the presence of type-specific fields.
        has_resolution = raw.get("resolution") not in (None, "", "null")
        has_hyb_kind = raw.get("hybridization_kind") not in (None, "", "null")

        if has_resolution and not has_hyb_kind:
            case_type = CaseType.DIVERGENCE
            resolution = Resolution(raw["resolution"])
            hyb_kind = None
        elif has_hyb_kind and not has_resolution:
            case_type = CaseType.HYBRIDIZATION
            hyb_kind = HybridizationKind(raw["hybridization_kind"])
            resolution = None
        else:
            # Ambiguous or missing typing; skip.
            return None

        value = raw.get("estimated_value_usd")
        if isinstance(value, str):
            # Agent occasionally stringifies numbers; attempt coercion.
            try:
                value = float(re.sub(r"[^0-9.]", "", value)) or None
            except ValueError:
                value = None

        return AttributionCase(
            case_id=case_id,
            case_type=case_type,
            artwork_title=title,
            claimed_artist=artist,
            estimated_value_usd=value,
            ai_tool=(raw.get("ai_tool") or None),
            institution=(raw.get("institution") or None),
            resolution=resolution,
            hybridization_kind=hyb_kind,
            source_urls=list(urls),
            reasoning=(raw.get("reasoning") or "").strip(),
            confidence=float(raw.get("confidence") or 0.0),
            event_date=(raw.get("event_date") or None),
        )
    except (ValueError, KeyError, TypeError):
        return None


def run_discovery(sq: SearchQuery, model: str = DEFAULT_MODEL) -> list[AttributionCase]:
    """Run one agentic discovery turn for a search query.

    Uses the Anthropic Messages API with the server-side web_search tool.
    Returns the list of validated AttributionCase objects the agent found.
    """
    try:
        from anthropic import Anthropic
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "The 'anthropic' package is required. Install it with: "
            "pip install anthropic"
        ) from e

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Either export it, or use --seed "
            "to populate the database with illustrative cases for demo."
        )

    client = Anthropic()

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": _build_user_prompt(sq)}],
    )

    # Concatenate all text blocks from the final assistant message.
    text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text += block.text + "\n"

    raw_cases = _extract_json_array(text)
    cases: list[AttributionCase] = []
    for raw in raw_cases:
        case = _coerce_to_case(raw)
        if case is not None:
            cases.append(case)
    return cases
