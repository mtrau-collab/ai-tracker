# Notes for Claude Code agents

This file exists so that when you (Claude) are asked to extend this project
via Claude Code, you have the conventions in one place.

## Project in one sentence

A continuously-updated indicator that tracks two metrics — the
Money-Weighted Divergence Resolution Index and the Hybridization Index —
to empirically test which of three predictions about AI in art
authentication (accelerationist, safetyist, skeptical) is becoming more
accurate over time.

## Mental model

- The **cases table** is the primary data: each row is either a DIVERGENCE
  (AI vs institution disagreed on a specific artwork) or a HYBRIDIZATION
  (institution cited AI as supporting evidence).
- The **snapshots table** is append-only and forms the time series. Never
  backfill or rewrite snapshots; write a new one on every update.
- **Indices are derived**, not stored as primary data. If you change the
  computation logic in `indices.py`, the entire history can be recomputed
  from the cases table.

## Conventions

- **No new dependencies without strong reason.** stdlib sqlite3, pydantic,
  anthropic, matplotlib. That's it. If you reach for pandas, stop and ask.
- **All user-facing output goes through `cli.py`.** Don't add `print()`
  calls inside `agent.py`, `indices.py`, etc.; keep those modules importable
  and side-effect-free on import.
- **`case_id` is a hash, not a UUID.** Re-running discovery for the same
  artwork/source URL must produce the same id, so `upsert_case` is
  idempotent.
- **Confidence is how the agent expresses uncertainty.** Never raise
  confidence artificially to make indices look more populated. If the
  classifier is unsure, let it say 0.4 and let `min_confidence` filter
  it out of reports.
- **Seed cases are prefixed `seed-`** in the case_id so production
  filters can exclude them. Do not seed cases that aren't based on
  publicly-reported events.

## Adding a new sub-index

The paper identifies seven sub-indices; only two are implemented. To add
another (for example, the Legal Deference Index):

1. Decide whether it needs new per-case fields. If so, add them to
   `AttributionCase` in `schema.py` and to the `cases` table in
   `storage.py` (as a migration — don't break existing databases).
2. Add search queries to `sources.py` targeting the new signal.
3. Extend the system prompt in `agent.py` to teach the classifier what
   to extract.
4. Add a computation function in `indices.py` and extend `IndexSnapshot`
   to carry the new value.
5. Surface the new value in `report.py` (both the dashboard HTML and
   the machine-readable `latest.json`).
6. Update this file and the README's extension section.

## What NOT to do

- Don't replace SQLite with Postgres. The point is that this is a small,
  self-contained academic project, not a service.
- Don't add ad-based or auction-house-proprietary data sources without
  first thinking about terms of service.
- Don't invent case values or outcomes. If the agent can't find a
  figure in its search results, `estimated_value_usd` is null.
- Don't change the resolution enum without migrating historical data.
  The four categories (AI_PREVAILED, INSTITUTION_PREVAILED, UNRESOLVED,
  CRISIS) map directly onto the Triad predictions in the paper.

## Testing the pipeline

```bash
python -m aai.cli seed       # populate illustrative cases
python -m aai.cli compute    # recompute indices (no network)
python -m aai.cli report     # render dashboard (no network)
python -m aai.cli list       # inspect
```

These three commands exercise every module except `agent.py`. To test
`agent.py` end-to-end you need an ANTHROPIC_API_KEY and a live run
(`python -m aai.cli update --queries 1`).
