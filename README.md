# Authentication Authority Index (AAI) Tracker

Companion implementation to *Authenticating the Debate: A Triadic Framework
for Measuring AI's Impact on Art Attribution*.

This project operationalizes the paper's measurement framework as a
continuously-updated indicator. On each scheduled run, an agent powered by
Claude searches the public web, identifies new attribution events,
classifies them as either divergence cases or hybridization cases, and
refreshes two indices:

- **Money-Weighted Divergence Resolution Index (MWDRI)** — who prevails when
  AI analyses and institutional authorities disagree, weighted by the
  disputed economic value of the work. Range `[-1, +1]`. `+1` = AI prevails
  on every value-weighted divergence; `-1` = institutions do; `0` = balanced.

- **Hybridization Index (HI)** — the fraction of observed institutional
  attribution events that cite AI analysis as supporting, supplementary, or
  corroborating evidence. Range `[0, 1]`.

A separate **Instability Share** is tracked as the safetyist diagnostic:
the value-weighted share of divergence cases that resolved into litigation,
market freeze, insurer withdrawal, or regulatory action.

## How the three indices distinguish the Triad

| Observed pattern                                       | Triad reading                                           |
|--------------------------------------------------------|---------------------------------------------------------|
| HI rising, MWDRI stays negative                        | Skeptics' world: AI absorbed, not empowered             |
| HI rising, MWDRI rising                                | Accelerationists' world: AI adopted *and* winning       |
| MWDRI tipping into crisis, Instability Share climbing  | Safetyists' world: arms race breaking the system        |

See §IV of the paper for the full theoretical grounding.

## Architecture

```
aai-tracker/
├── aai/
│   ├── schema.py     # Pydantic models for cases and snapshots
│   ├── storage.py    # SQLite persistence (data/cases.db)
│   ├── sources.py    # Registered search queries
│   ├── agent.py      # Claude + web_search tool → discovered cases
│   ├── indices.py    # MWDRI, Hybridization Index, Instability Share
│   ├── report.py     # Static HTML dashboard with matplotlib plots
│   ├── cli.py        # Command-line entry point
│   └── seed.py       # Illustrative seed cases (demo mode)
├── scripts/run_update.sh        # Shell wrapper for scheduled runs
├── .github/workflows/update.yml # GitHub Actions weekly cron
├── data/cases.db                # Generated on first run
└── reports/dashboard.html       # Generated on each run
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
```

## Usage

### Quick demo (no API key)

```bash
python -m aai.cli seed       # load illustrative cases
python -m aai.cli compute    # recompute indices
python -m aai.cli report     # render the dashboard
open reports/dashboard.html  # macOS; use xdg-open on Linux
```

### Live update (requires API key)

```bash
python -m aai.cli update             # run all search queries
python -m aai.cli update --queries 3 # only the first 3 (cheap test run)
```

The agent runs each configured search query (see `aai/sources.py`), gathers
evidence through server-side web search, and classifies what it finds.
Cases are deduplicated by a hash of `(artwork_title, claimed_artist,
source_url)`. Indices are recomputed and a snapshot is written to the
database on every call, so the time series grows with each run.

### Listing cases

```bash
python -m aai.cli list
python -m aai.cli list --type divergence --min-confidence 0.7
```

### Scheduling

**Cron (Linux/macOS):**

```cron
0 6 * * 1 /path/to/aai-tracker/scripts/run_update.sh >> /var/log/aai.log 2>&1
```

**GitHub Actions:** the provided `.github/workflows/update.yml` runs weekly.
Set `ANTHROPIC_API_KEY` as a repository secret; the workflow commits the
refreshed `data/cases.db`, `reports/dashboard.html`, and `reports/latest.json`
back to the repository, giving the project a continuously-evolving public
history.

## Classification confidence and manual review

The agent is conservative but not infallible. Each case carries a
`confidence` score in `[0, 1]`; index computation defaults to filtering
out cases below `0.4`. For research-grade use, you should:

1. Periodically run `aai list` and spot-check recent cases.
2. Edit the database directly (`sqlite3 data/cases.db`) to correct or
   remove miscalibrated cases. Set `confidence = 0.0` to exclude a case
   from indices without deleting it.
3. Add new queries to `aai/sources.py` when you notice coverage gaps.

## Limitations (explicit)

This is a proof-of-concept for an academic paper, not a production market
tool. Specific limitations to flag in any published analysis:

- **Coverage is biased toward the English-language press** and the
  institutions it covers. Non-English-language authentication disputes
  (substantial in European and Asian markets) are under-sampled.
- **The Hybridization Index has a proxy denominator.** It measures
  hybridization cases as a share of observed institutional attribution
  events, not of the full institutional attribution population. Absolute
  values are therefore not directly interpretable; trends over time are.
- **Silent Adoption Rate is not implemented.** Section IV of the paper
  proposes this as part of the full AAI framework, but it requires
  procurement or survey data that is not on the public web. Extend by
  loading such data into the `cases` table directly as HYBRIDIZATION cases
  with `hybridization_kind = decision_support`.
- **Economic values are best-effort estimates.** When source reporting
  gives a range, the agent picks a midpoint; when no figure is given, the
  case is weighted as a baseline (`weight = 1.0`).
- **The agent can hallucinate.** Use `min_confidence` aggressively and
  review cases before citing them in published work.

## Extending

Add a new sub-index (for example, a Legal Deference Index) by:

1. Adding a `case_type` value or a new table in `aai/storage.py`.
2. Writing a computation function in `aai/indices.py`.
3. Adding queries to `aai/sources.py`.
4. Extending the classifier prompt in `aai/agent.py`.
5. Surfacing the new index in `aai/report.py`.

See `CLAUDE.md` for conventions to follow when extending the project
using Claude Code.
