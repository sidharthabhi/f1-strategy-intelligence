"""
Database helpers: connection, schema bootstrap, upsert.

Upsert strategy: natural keys per table (year+round for races, season+code for drivers,
etc.). If a run re-ingests an event, existing rows are updated, not duplicated.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DB_PATH, SCHEMA_PATH


def init_db(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    """Create the DB file and apply schema.sql if missing."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    first_time = not db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        if first_time:
            with open(schema_path, encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Context-managed connection with FK + WAL enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lookups — idempotent: return existing id or insert-and-return.
# ---------------------------------------------------------------------------
def upsert_circuit(conn: sqlite3.Connection, fastf1_key: str, name: str,
                   country: str | None = None, city: str | None = None) -> int:
    row = conn.execute(
        "SELECT circuit_id FROM circuits WHERE fastf1_key = ?", (fastf1_key,)
    ).fetchone()
    if row:
        return row["circuit_id"]
    cur = conn.execute(
        "INSERT INTO circuits (fastf1_key, name, country, city) VALUES (?, ?, ?, ?)",
        (fastf1_key, name, country, city),
    )
    return cur.lastrowid


def upsert_race(conn: sqlite3.Connection, circuit_id: int, year: int, round_num: int,
                event_name: str, date: str | None, total_laps: int | None) -> int:
    row = conn.execute(
        "SELECT race_id FROM races WHERE year = ? AND round = ?", (year, round_num)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE races SET event_name = ?, date = ?, total_laps = ?, circuit_id = ?"
            " WHERE race_id = ?",
            (event_name, date, total_laps, circuit_id, row["race_id"]),
        )
        return row["race_id"]
    cur = conn.execute(
        "INSERT INTO races (circuit_id, year, round, event_name, date, total_laps)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (circuit_id, year, round_num, event_name, date, total_laps),
    )
    return cur.lastrowid


def upsert_team(conn: sqlite3.Connection, season: int, constructor_name: str,
                short_name: str | None = None) -> int:
    row = conn.execute(
        "SELECT team_id FROM teams WHERE season = ? AND constructor_name = ?",
        (season, constructor_name),
    ).fetchone()
    if row:
        return row["team_id"]
    cur = conn.execute(
        "INSERT INTO teams (season, constructor_name, short_name) VALUES (?, ?, ?)",
        (season, constructor_name, short_name or constructor_name),
    )
    return cur.lastrowid


def upsert_driver(conn: sqlite3.Connection, season: int, team_id: int, code: str,
                  full_name: str, number: int | None = None,
                  nationality: str | None = None) -> int:
    row = conn.execute(
        "SELECT driver_id FROM drivers WHERE season = ? AND code = ? AND team_id = ?",
        (season, code, team_id),
    ).fetchone()
    if row:
        return row["driver_id"]
    cur = conn.execute(
        "INSERT INTO drivers (season, team_id, code, full_name, number, nationality)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (season, team_id, code, full_name, number, nationality),
    )
    return cur.lastrowid


def clear_race_data(conn: sqlite3.Connection, race_id: int) -> None:
    """Wipe laps/pit_stops/results for a race before re-ingesting (idempotency)."""
    conn.execute("DELETE FROM laps         WHERE race_id = ?", (race_id,))
    conn.execute("DELETE FROM pit_stops    WHERE race_id = ?", (race_id,))
    conn.execute("DELETE FROM race_results WHERE race_id = ?", (race_id,))
