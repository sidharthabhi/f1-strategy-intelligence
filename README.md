# F1 Strategy Intelligence Dashboard

End-to-end race analytics platform — 7 seasons of Formula 1 data (2018–2024)
ingested from FastF1, stored in a normalised SQLite database, and surfaced
through a 7-page Power BI dashboard answering 20 business questions.

## Status — Week 1 Deliverable

- ✅ Schema defined (7 tables + race_results, 3NF, FK-constrained)
- ✅ FastF1 → SQLite ingestion with the 7-condition `is_valid_lap` flag
- ✅ Q4 consistency query (the Week 1 gate)
- ✅ Smoke test harness
- 🔜 Week 2: full 2018–2024 backfill
- 🔜 Week 3–4: remaining 19 SQL queries
- 🔜 Week 5–8: Power BI dashboard + live mode

## Setup — Windows

```powershell
# 1. Clone and enter
cd C:\code
git clone <your-repo> f1-strategy-intelligence
cd f1-strategy-intelligence

# 2. Virtual env
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Deps
pip install -r requirements.txt

# 4. Initialise DB (creates database/f1_analytics.db)
python -c "from data.ingestion.db import init_db; init_db()"

# 5. Ingest 2024 (Week 1 scope — ~20 min, ~2 GB FastF1 cache)
python -m data.ingestion.fastf1_ingest 2024

# 6. Gate check
python -m data.ingestion.smoke_test
```

If PowerShell blocks the activation script:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## Project Structure

```
f1-strategy-intelligence/
├── data/
│   ├── ingestion/
│   │   ├── config.py          # paths, seasons, logging
│   │   ├── db.py              # SQLite connection + upsert helpers
│   │   ├── validity.py        # is_valid_lap 7-condition logic
│   │   ├── fastf1_ingest.py   # main ingestion entry point
│   │   └── smoke_test.py      # Week 1 gate check
│   └── fastf1_cache/          # FastF1 local cache (gitignored)
├── database/
│   ├── schema.sql             # CREATE TABLE statements
│   ├── queries/
│   │   └── Q4_driver_consistency.sql
│   └── f1_analytics.db        # SQLite DB (gitignored)
├── logs/                      # ingestion logs (gitignored)
├── requirements.txt
└── README.md
```

## Week 1 Commands Cheat Sheet

| Task | Command |
|------|---------|
| Initialise empty DB | `python -c "from data.ingestion.db import init_db; init_db()"` |
| Ingest 2024 season | `python -m data.ingestion.fastf1_ingest 2024` |
| Ingest a single year | `python -m data.ingestion.fastf1_ingest 2023` |
| Ingest a range | `python -m data.ingestion.fastf1_ingest 2018 2024` |
| Run Week 1 gate | `python -m data.ingestion.smoke_test` |
| Inspect DB in shell | `python -c "from data.ingestion.db import connect; c=connect().__enter__(); print(c.execute('SELECT COUNT(*) FROM laps').fetchone())"` |

## The 7-Condition `is_valid_lap` Flag

Set to 1 only when ALL of:
1. `lap_number > 1` (excludes formation lap)
2. `is_pit_lap = 0` (excludes in-laps)
3. Previous lap `is_pit_lap = 0` (excludes out-laps with cold tires)
4. `track_status = 'Green'` (excludes SC / VSC / Yellow / Red)
5. `deleted = 0` (excludes track-limits violations)
6. `lap_time_sec IS NOT NULL` (excludes partial DNF laps)
7. `lap_time_sec < circuit_length_km / 80 × 3600` (rejects impossibly slow laps)

Every analytical query filters on `is_valid_lap = 1` — this is what makes
downstream insights trustworthy.

## Troubleshooting

**`ModuleNotFoundError: No module named 'data'`**
Run commands from the repo root, not from inside `data/ingestion/`.

**FastF1 cache errors on first run**
Normal for pre-2020 events. The ingestion loop catches these per-session and
logs a warning — does not crash. Check `logs/f1_ingest.log` for skipped events.

**`sqlite3.IntegrityError: UNIQUE constraint failed: races.year, races.round`**
You're re-ingesting an event that's already loaded. This is fine — the upsert
logic catches it. If you see this error raised, update to latest `db.py`.

**Smoke test fails on "VER 2024 consistency < 1.5s"**
Indicates a validity logic problem. Check: (a) are `track_status` values being
mapped correctly from FastF1's digit codes, (b) is `is_pit_lap` set correctly?
Run: `python -c "from data.ingestion.db import connect; [print(dict(r)) for r in connect().__enter__().execute('SELECT track_status, COUNT(*) FROM laps GROUP BY track_status').fetchall()]"`
