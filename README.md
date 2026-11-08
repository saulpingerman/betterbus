# betterbus

An independent evaluation of the WMATA Better Bus Network Redesign (launched 2025-06-29): how Metrobus ridership responded to the redesign's reallocation of scheduled service, and how transit access to jobs changed by income, race, car ownership and disability. Everything is built from public data.

## Install

```
uv sync --locked
cp .env.example .env   # then fill in the API keys
```

## Data

Downloaded data goes to `data/` (git-ignored) and is rebuilt by the scripts in `scripts/`.

| Source | Script | Notes |
|---|---|---|
| WMATA bus GTFS archive (Mobility Database `mdb-1846`) | `uv run scripts/fetch_mdb_gtfs.py mdb-1846` | Schedules from 2024-07 onward, SHA-256 verified |

## Tests

```
uv run pytest
```

## Results

None yet. Every result and decision is recorded in `records/ledger.md`.
