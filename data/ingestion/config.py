"""
F1 Strategy Intelligence — central config.

Windows-friendly paths (PowerShell users: all paths are pathlib.Path, forward/backslash agnostic).
Change SEASONS to [2024] for first run (Week 1 deliverable); expand to full range for Week 2.
"""
from __future__ import annotations

import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — everything anchored to the repo root (two levels up from this file)
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]
DATABASE_DIR = ROOT_DIR / "database"
DB_PATH = DATABASE_DIR / "f1_analytics.db"
SCHEMA_PATH = DATABASE_DIR / "schema.sql"
QUERIES_DIR = DATABASE_DIR / "queries"

# FastF1 cache — persistent across runs. ~5 GB for full 7 seasons.
CACHE_DIR = ROOT_DIR / "data" / "fastf1_cache"

LOG_DIR = ROOT_DIR / "logs"

# ---------------------------------------------------------------------------
# Ingestion scope
# ---------------------------------------------------------------------------
# Week 1: just 2024. Week 2: full backfill.
SEASONS: list[int] = [2024]

# Session types to pull per event.
# Race (R) is mandatory. Q adds quali-race delta. Sprint + SQ added post-2021.
SESSION_TYPES: list[str] = ["Q", "R"]

# Lap validity bounds (Rule 7 of is_valid_lap): lap can't be slower than driving
# ~80 km/h average around the circuit. Tweak per track if needed.
MIN_AVG_SPEED_KMH = 80.0

# Pit stop duration sanity bounds (seconds). Outside → NULL, excluded from analytics.
PIT_DURATION_MIN_SEC = 1.8
PIT_DURATION_MAX_SEC = 60.0

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(name: str = "f1_ingest") -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S")
    fh = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def ensure_dirs() -> None:
    for d in (DATABASE_DIR, CACHE_DIR, LOG_DIR, QUERIES_DIR):
        d.mkdir(parents=True, exist_ok=True)