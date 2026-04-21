"""Render index snapshots and cases as a static HTML dashboard.

The dashboard is a single self-contained HTML file with embedded PNG plots.
Keeping it static means it can be committed, previewed locally without a
server, or hosted on GitHub Pages when the GitHub Actions workflow runs.
"""

from __future__ import annotations

import base64
import io
import json
from datetime import datetime
from html import escape
from pathlib import Path

from .schema import AttributionCase, CaseType, IndexSnapshot, Resolution
from .storage import DEFAULT_DB_PATH, list_cases, list_snapshots
from .indices import compute_indices, interpret


REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _plot_indices_png(snapshots: list[IndexSnapshot]) -> str:
    """Return a base64-encoded PNG of the index history."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        return ""

    if not snapshots:
        return ""

    times = [datetime.fromisoformat(s.snapshot_at.replace("Z", "+00:00")) for s in snapshots]
    mwdri = [s.money_weighted_dri for s in snapshots]
    hi = [s.hybridization_index for s in snapshots]
    inst = [s.instability_share for s in snapshots]

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

    ax1 = axes[0]
    ax1.axhline(0.0, color="#888", linewidth=0.8, linestyle="--")
    ax1.plot(times, mwdri, marker="o", color="#b33", label="Money-Weighted DRI")
    ax1.set_ylabel("MWDRI  [−1, +1]")
    ax1.set_ylim(-1.05, 1.05)
    ax1.set_title("Authentication Authority Index — operational core")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper left")

    ax2 = axes[1]
    ax2.plot(times, hi, marker="s", color="#237", label="Hybridization Index")
    if any(x is not None for x in inst):
        ax2.plot(times, inst, marker="^", color="#d80", label="Instability Share", alpha=0.7)
    ax2.set_ylabel("[0, 1]")
    ax2.set_ylim(-0.05, 1.05)
    ax2.set_xlabel("Snapshot date")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper left")

    for ax in axes:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _plot_resolution_breakdown_png(cases: list[AttributionCase]) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return ""

    divergences = [c for c in cases if c.case_type == CaseType.DIVERGENCE]
    if not divergences:
        return ""

    buckets = {"ai_prevailed": 0.0, "institution_prevailed": 0.0,
               "crisis": 0.0, "unresolved": 0.0}
    for c in divergences:
        from .indices import _log_weight
        w = _log_weight(c.estimated_value_usd)
        key = c.resolution.value if c.resolution else "unresolved"
        buckets[key] = buckets.get(key, 0.0) + w

    labels = ["AI prevailed\n(accelerationist)",
              "Institution prevailed\n(skeptic)",
              "Crisis\n(safetyist)",
              "Unresolved"]
    vals = [buckets["ai_prevailed"], buckets["institution_prevailed"],
            buckets["crisis"], buckets["unresolved"]]
    colors = ["#2a9d8f", "#264653", "#e76f51", "#bbb"]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, vals, color=colors)
    ax.set_ylabel("Log-weighted value")
    ax.set_title("Divergence outcomes — value-weighted")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _case_row_html(c: AttributionCase) -> str:
    if c.case_type == CaseType.DIVERGENCE:
        kind = f"DIVERGENCE — {c.resolution.value if c.resolution else 'unresolved'}"
    else:
        kind = f"HYBRIDIZATION — {c.hybridization_kind.value if c.hybridization_kind else 'unspecified'}"

    value = f"${c.estimated_value_usd:,.0f}" if c.estimated_value_usd else "—"
    urls_html = " ".join(
        f'<a href="{escape(u)}" target="_blank" rel="noopener">src</a>'
        for u in c.source_urls[:3]
    )

    return f"""
    <tr>
      <td>{escape(c.event_date or c.discovered_at[:10])}</td>
      <td><strong>{escape(c.artwork_title)}</strong><br><em>{escape(c.claimed_artist)}</em></td>
      <td>{escape(kind)}</td>
      <td>{value}</td>
      <td>{escape(c.ai_tool or '—')} vs. {escape(c.institution or '—')}</td>
      <td>{c.confidence:.2f}</td>
      <td>{urls_html}</td>
    </tr>
    """


def render_dashboard(db_path: Path = DEFAULT_DB_PATH,
                     out_dir: Path = REPORTS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshots = list_snapshots(db_path=db_path)
    cases = list_cases(db_path=db_path)
    # Use the most recently written snapshot rather than recomputing with
    # defaults — this way the dashboard reflects whatever window the last
    # update/seed/compute call used.
    if snapshots:
        current = snapshots[-1]
    else:
        current = compute_indices(db_path=db_path)
    interpretation = interpret(current)

    idx_png = _plot_indices_png(snapshots)
    res_png = _plot_resolution_breakdown_png(cases)

    rows = "\n".join(_case_row_html(c) for c in cases[:50])

    mwdri_str = f"{current.money_weighted_dri:+.3f}" if current.money_weighted_dri is not None else "—"
    hi_str = f"{current.hybridization_index:.3f}" if current.hybridization_index is not None else "—"
    inst_str = f"{current.instability_share:.3f}" if current.instability_share is not None else "—"

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Authentication Authority Index — Dashboard</title>
<style>
  body {{ font: 14px/1.5 "Helvetica Neue", system-ui, sans-serif;
         max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  h1, h2 {{ font-weight: 600; }}
  h1 {{ border-bottom: 2px solid #222; padding-bottom: 0.4rem; }}
  .card {{ background: #f7f7f7; padding: 1rem; border-radius: 6px; margin: 1rem 0; }}
  .metric {{ display: inline-block; margin-right: 2rem; }}
  .metric .label {{ display: block; font-size: 0.8rem; color: #666; text-transform: uppercase; }}
  .metric .value {{ display: block; font-size: 1.8rem; font-weight: 600; }}
  .interp {{ white-space: pre-line; font-family: ui-monospace, "SF Mono", Menlo, monospace;
             background: #fff; padding: 0.8rem; border-left: 3px solid #237; }}
  img {{ max-width: 100%; height: auto; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid #ddd; vertical-align: top; }}
  th {{ background: #eee; }}
  .foot {{ color: #888; font-size: 0.8rem; margin-top: 2rem; }}
</style>
</head>
<body>

<h1>Authentication Authority Index</h1>
<p>Continuously-updated indicator from <em>Authenticating the Debate</em>.
Tracks the migration of authentication authority between AI systems and
institutional authorities in the art world.</p>

<div class="card">
  <div class="metric">
    <span class="label">Money-Weighted DRI</span>
    <span class="value">{mwdri_str}</span>
  </div>
  <div class="metric">
    <span class="label">Hybridization Index</span>
    <span class="value">{hi_str}</span>
  </div>
  <div class="metric">
    <span class="label">Instability Share</span>
    <span class="value">{inst_str}</span>
  </div>
  <div class="metric">
    <span class="label">Cases (div / hyb)</span>
    <span class="value">{current.divergence_cases_total} / {current.hybridization_cases_total}</span>
  </div>
</div>

<h2>Triad reading</h2>
<div class="interp">{escape(interpretation) or 'Insufficient data.'}</div>

<h2>Index history</h2>
{'<img src="data:image/png;base64,' + idx_png + '" alt="index history">' if idx_png else '<p><em>No snapshots yet.</em></p>'}

<h2>Divergence outcomes — value-weighted</h2>
{'<img src="data:image/png;base64,' + res_png + '" alt="resolution breakdown">' if res_png else '<p><em>No divergence cases yet.</em></p>'}

<h2>Recent cases</h2>
<table>
  <thead>
    <tr><th>Date</th><th>Work</th><th>Type</th><th>Value</th><th>Parties</th><th>Conf.</th><th>Sources</th></tr>
  </thead>
  <tbody>
    {rows if rows else '<tr><td colspan="7"><em>No cases yet. Run <code>python -m aai.cli update</code>.</em></td></tr>'}
  </tbody>
</table>

<p class="foot">Generated {datetime.utcnow().isoformat(timespec='seconds')}Z.
Methodology: see §IV of the accompanying paper.</p>

</body>
</html>
"""
    out_file = out_dir / "dashboard.html"
    out_file.write_text(html, encoding="utf-8")

    # Also emit a machine-readable snapshot for CI / further analysis.
    (out_dir / "latest.json").write_text(
        json.dumps(current.model_dump(), indent=2, default=str),
        encoding="utf-8",
    )
    return out_file
