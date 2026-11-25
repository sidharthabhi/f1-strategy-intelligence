# F1 Strategy Intelligence

An end-to-end analytics project on seven seasons of Formula 1 race data (2018–2024). Raw timing data is ingested from the FastF1 and Ergast APIs, cleaned and validated in Python, modelled in a normalised SQLite database, analysed with 21 SQL queries, and presented in an interactive single-file HTML dashboard.

## At a glance

| Metric | Value |
|---|---|
| Seasons | 7 (2018–2024) |
| Races | 149 |
| Circuits | 31 |
| Drivers | 40 |
| Laps ingested | 208,962 |
| Clean race laps (after validity filtering) | 128,590 |
| Pit stops | 10,319 |
| Analytical SQL queries | 21, built on 3 shared views |

## What it does

The project answers 20 strategy and performance questions, such as:

- Which teams are fastest in the pits, and has that changed over time?
- Does pole position convert to a win, and at which circuits does it matter most?
- Which circuits are hardest on tyres? (calculated as a linear regression of lap time against tyre age, written in plain SQLite)
- Does an undercut or an overcut gain more positions, and where?
- Which teams recover the most positions after a safety car?
- Does rain make the finishing order more random?
- Which driver gets the most pace out of their car, relative to the best lap that car achieved?
- How closely matched is each pair of teammates in qualifying, race pace and reliability?

## Architecture

```
FastF1 API ─┐
            ├─> Python ingestion ─> validity + cleaning ─> SQLite (3NF) ─> SQL views ─> 21 queries
Ergast API ─┘                                                    │
                                                                 └─> rollup tables ─> JSON export ─> HTML dashboard
```

1. **Ingestion** (`fastf1_ingest.py`): pulls qualifying and race sessions for each event and writes circuits, races, teams, drivers, laps, pit stops and results. Re-running is idempotent: an event that is ingested again replaces its own rows and creates no duplicates.
2. **Enrichment**: `ergast_pitstops.py` fills in accurate pit-stop durations from Ergast, with requests throttled to stay inside the rate limits. `circuit_metadata.py` adds track length, corners and DRS zones.
3. **Cleaning**: `canonicalise_circuits.py` merges circuits that FastF1 stores under different names (for example Monaco and Monte Carlo), so each track has exactly one ID.
4. **Validation**: `quality_audit.py`, `data_overview.py` and `smoke_test.py` check the data against known real-world F1 results.
5. **SQL layer**: three views provide a single definition of a clean lap, normalise tyre compounds across seasons, and give one row per driver per season. The 21 queries build on these views.
6. **Rollups**: `build_driver_fingerprints.py` and `build_rollups.py` precompute driver profile scores, head-to-head summaries and pit-window models, so the dashboard loads quickly.
7. **Dashboard**: `export_dashboard_data.py` embeds the data into a single HTML file that needs no server.

## Data quality: the 7-condition clean-lap filter

A lap counts toward analysis only if all seven of these hold:

1. It is not lap 1, which is distorted by the race start.
2. It is not a pit in-lap.
3. It is not a pit out-lap, when the tyres are still cold.
4. It was run under green-flag conditions, with no safety car, virtual safety car, yellow or red flag.
5. It was not deleted for exceeding track limits.
6. It has a recorded lap time.
7. It is not impossibly slow for the circuit's length.

Every query reads clean laps from `v_clean_laps`, so this rule is defined in only one place.

Data is validated against well-known F1 moments: season champions, points totals and famous races. This catches subtle pipeline bugs that unit tests miss. For example, `diagnose_q4.py` traced an anomaly in the consistency ranking to drivers who had more than one row in a single season.

## Dashboard

`dashboard/index.html` is a self-contained page built with HTML, CSS, JavaScript and Chart.js. To view it, open it in a browser.

| Page | What it shows |
|---|---|
| Overview | Season summaries, champions and headline numbers |
| Constructors | Championship evolution race by race, and reliability |
| Driver DNA | Driver profile radar charts scoring race pace, consistency, qualifying pace, racecraft, tyre management and wet-weather performance |
| Head to Head | Teammate comparisons across qualifying, race finishes, pace gap and DNFs |
| Circuits | Tyre degradation, overtaking and how often pole converts to a win |
| Race Replay | Lap-by-lap position chart for any of the 149 races |

## Database schema

`circuits`, `races`, `teams`, `drivers`, `race_results`, `laps`, `pit_stops`, `telemetry`. The schema is normalised to third normal form, uses foreign-key constraints, and is indexed for the access patterns the queries need. See `database/schema.sql`.

## Setup

Requires Python 3.10 or later.

```powershell
git clone https://github.com/sidharthabhi/f1-strategy-intelligence.git
cd f1-strategy-intelligence
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Build the database
python -c "from data.ingestion.db import init_db; init_db()"
python -m data.ingestion.fastf1_ingest 2018 2024     # long first run; FastF1 caches locally
python -m data.ingestion.ergast_pitstops 2018 2024
python -m data.ingestion.circuit_metadata
python -m data.ingestion.canonicalise_circuits
python -m data.ingestion.install_views

# Validate
python -m data.ingestion.smoke_test
python -m data.ingestion.quality_audit

# Rollups and dashboard
python -m data.ingestion.build_driver_fingerprints
python -m data.ingestion.build_rollups
python -m data.ingestion.export_dashboard_data
```

Run the queries:

```powershell
python -m data.ingestion.run_query Q5           # a single query
python -m data.ingestion.run_query --all        # every query, summary mode
```

Run all commands from the repository root. The database and the FastF1 cache are excluded from git (see `.gitignore`).

## Project structure

```
f1-strategy-intelligence/
├── data/ingestion/      # ingestion, enrichment, cleaning, validation, rollups, export
├── database/
│   ├── schema.sql
│   ├── views/           # v_clean_laps, v_compound_normalised, v_driver_seasons
│   └── queries/         # Q1–Q20 and Q4b
├── dashboard/           # single-file HTML dashboard and its exported data
└── requirements.txt
```

## Tech stack

Python (pandas, NumPy), FastF1, Ergast API, SQLite, SQL, HTML/CSS/JavaScript, Chart.js

## Roadmap

- Power BI report on top of the same SQLite database and rollup tables

## Author

Sidhartha Tummanapally — [LinkedIn](https://www.linkedin.com/in/sidhartha-tummanapally-a79136288) · [Portfolio](https://sidharthabhi.github.io/portfolio/)
