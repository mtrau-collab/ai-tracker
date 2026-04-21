"""Compute the operational indices from stored cases.

The Money-Weighted Divergence Resolution Index (MWDRI) and the Hybridization
Index (HI) are the pair identified in Section IV of the paper as the tractable
operational core of the Authentication Authority Index.

MWDRI is computed over divergence cases whose resolution is known (AI_PREVAILED
or INSTITUTION_PREVAILED). Each case is weighted by log(1 + estimated_value_usd)
— log-weighting prevents a single mega-value case (e.g., a disputed Leonardo)
from drowning out the broader pattern, while still giving high-stakes cases
proportionally more influence than low-stakes ones.

MWDRI = (W_ai - W_inst) / (W_ai + W_inst)

where W_ai = sum of log-weights for AI-prevailed cases and W_inst likewise.
Range: [-1, +1]. +1 means AI prevailed on every value-weighted case, -1 means
institutions did, 0 means perfect balance.

INSTABILITY SHARE is tracked separately as the safetyist diagnostic:
  share = W_crisis / (W_ai + W_inst + W_crisis + W_unresolved)

HYBRIDIZATION INDEX is the fraction of observed institutional attribution
events in the window that cite AI:
  HI = N_hybridization / (N_hybridization + N_divergence)

The denominator is limited to the events we actually observe. This is a
proxy — a true Hybridization Index would use the population of all
institutional attribution events — but the relative trend over time is
the informative signal, not the absolute value.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .schema import AttributionCase, CaseType, IndexSnapshot, Resolution
from .storage import DEFAULT_DB_PATH, list_cases


def _log_weight(value_usd: Optional[float]) -> float:
    """Log-weight a case by its estimated disputed value.

    Cases without a known value get weight 1.0 (treated as a baseline
    small case) rather than dropped; otherwise any un-priced case would
    silently disappear from the index.
    """
    if value_usd is None or value_usd <= 0:
        return 1.0
    # log10(1 + usd). A $1M case → ~6, a $100M case → ~8, a $10k case → ~4.
    return math.log10(1.0 + value_usd)


def _within_window(case: AttributionCase, window_days: int) -> bool:
    ref = case.event_date or case.discovered_at
    if not ref:
        return True
    try:
        dt = datetime.fromisoformat(ref.replace("Z", "+00:00"))
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=window_days)


def compute_indices(
    window_days: int = 365,
    db_path: Path = DEFAULT_DB_PATH,
    min_confidence: float = 0.4,
) -> IndexSnapshot:
    """Compute MWDRI, Hybridization Index, and Instability Share.

    The window defaults to 365 days. min_confidence filters out cases the
    classifier flagged as low-confidence, which is important because the
    agent will occasionally misclassify ambiguous articles.
    """
    all_cases = list_cases(db_path=db_path, min_confidence=min_confidence)
    cases = [c for c in all_cases if _within_window(c, window_days)]

    divergences = [c for c in cases if c.case_type == CaseType.DIVERGENCE]
    hybridizations = [c for c in cases if c.case_type == CaseType.HYBRIDIZATION]

    # --- MWDRI ---
    w_ai = 0.0
    w_inst = 0.0
    w_crisis = 0.0
    w_unresolved = 0.0
    for c in divergences:
        w = _log_weight(c.estimated_value_usd)
        if c.resolution == Resolution.AI_PREVAILED:
            w_ai += w
        elif c.resolution == Resolution.INSTITUTION_PREVAILED:
            w_inst += w
        elif c.resolution == Resolution.CRISIS:
            w_crisis += w
        else:  # UNRESOLVED or None
            w_unresolved += w

    resolved = w_ai + w_inst
    if resolved > 0:
        mwdri: Optional[float] = (w_ai - w_inst) / resolved
    else:
        mwdri = None

    total_div_weight = w_ai + w_inst + w_crisis + w_unresolved
    instability_share: Optional[float] = (
        w_crisis / total_div_weight if total_div_weight > 0 else None
    )

    # --- Hybridization Index ---
    n_hyb = len(hybridizations)
    n_div = len(divergences)
    if (n_hyb + n_div) > 0:
        hi: Optional[float] = n_hyb / (n_hyb + n_div)
    else:
        hi = None

    return IndexSnapshot(
        money_weighted_dri=mwdri,
        hybridization_index=hi,
        instability_share=instability_share,
        divergence_cases_total=n_div,
        hybridization_cases_total=n_hyb,
        window_days=window_days,
    )


def interpret(snap: IndexSnapshot) -> str:
    """Return a short prose interpretation mapping the current snapshot onto
    the three Triad predictions, following Section IV of the paper.
    """
    lines: list[str] = []

    if snap.money_weighted_dri is None:
        lines.append("No resolved divergence cases in the window; MWDRI undefined.")
    else:
        mw = snap.money_weighted_dri
        if mw > 0.25:
            lines.append(
                f"MWDRI = {mw:+.2f}: AI determinations are prevailing on value-weighted "
                f"divergences. This is the accelerationist signal."
            )
        elif mw < -0.25:
            lines.append(
                f"MWDRI = {mw:+.2f}: institutional determinations are prevailing on "
                f"value-weighted divergences. This is the skeptical signal."
            )
        else:
            lines.append(
                f"MWDRI = {mw:+.2f}: no dominant party in value-weighted divergences."
            )

    if snap.hybridization_index is None:
        lines.append("No hybridization or divergence cases observed; HI undefined.")
    else:
        hi = snap.hybridization_index
        if hi > 0.5:
            lines.append(
                f"HI = {hi:.2f}: majority of observed institutional attribution events "
                f"cite AI. Hybridization is the dominant adoption mode."
            )
        elif hi > 0.2:
            lines.append(
                f"HI = {hi:.2f}: AI is being cited in a meaningful minority of "
                f"institutional attributions. Hybridization is underway but not dominant."
            )
        else:
            lines.append(
                f"HI = {hi:.2f}: AI is rarely cited in institutional attributions. "
                f"Authority remains in purely institutional hands."
            )

    if snap.instability_share is not None and snap.instability_share > 0.25:
        lines.append(
            f"Instability share = {snap.instability_share:.2f}: a substantial "
            f"value-weighted fraction of divergences produced crisis outcomes. "
            f"This is the safetyist signal."
        )

    # Composite Triad reading
    if snap.money_weighted_dri is not None and snap.hybridization_index is not None:
        mw = snap.money_weighted_dri
        hi = snap.hybridization_index
        if hi > 0.3 and mw < -0.1:
            lines.append(
                "Composite reading: skeptics' world — AI is being absorbed by "
                "institutions without being empowered."
            )
        elif hi > 0.3 and mw > 0.1:
            lines.append(
                "Composite reading: accelerationists' world — AI is both being "
                "adopted and winning on the value-weighted record."
            )
        elif snap.instability_share is not None and snap.instability_share > 0.25:
            lines.append(
                "Composite reading: safetyists' world — instability dominates the "
                "value-weighted divergence record."
            )

    return "\n".join(lines)
