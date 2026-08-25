"""
FastF1 → SQLite ingestion.

Usage:
    python -m data.ingestion.fastf1_ingest           # ingests config.SEASONS
    python -m data.ingestion.fastf1_ingest 2024      # override: specific season(s)
    python -m data.ingestion.fastf1_ingest 2018 2024 # range (inclusive)

Per event: pulls Qualifying + Race, writes circuits/races/teams/drivers/laps/
pit_stops/race_results. Telemetry NOT loaded here — separate script in Week 4
(selective load, fastest lap only).

Idempotency: a re-run of the same race wipes its child rows and re-ingests.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

# Silence the pandas 3.0 downcasting FutureWarnings on .fillna(...).astype(int).
pd.set_option("future.no_silent_downcasting", True)

try:
    import fastf1
    from fastf1.core import Session
    from fastf1.exceptions import RateLimitExceededError
except ImportError:
    print("fastf1 not installed. Run: pip install fastf1", file=sys.stderr)
    raise


def _rows_for_sqlite(df: pd.DataFrame, cols: list[str]) -> list[tuple]:
    """
    Convert a DataFrame slice into row tuples sqlite3 can bind.

    sqlite3 rejects: pd.NA, numpy.int64 (sometimes), numpy.float64 NaN, pd.NaT.
    This coerces every cell to a sqlite-friendly Python primitive or None.
    """
    sub = df[cols]
    out: list[tuple] = []
    for row in sub.itertuples(index=False, name=None):
        clean = []
        for v in row:
            # pd.NA / NaN / NaT  → None
            if v is None or v is pd.NA:
                clean.append(None)
                continue
            try:
                if pd.isna(v):
                    clean.append(None)
                    continue
            except (TypeError, ValueError):
                pass  # non-scalar — fall through to type conversions
            # numpy scalars → Python primitives
            if hasattr(v, "item"):
                try:
                    v = v.item()
                except (ValueError, AttributeError):
                    pass
            clean.append(v)
        out.append(tuple(clean))
    return out

from .config import CACHE_DIR, SEASONS, SESSION_TYPES, ensure_dirs, setup_logging
from .db import (clear_race_data, connect, init_db, upsert_circuit,
                 upsert_driver, upsert_race, upsert_team)
from .validity import (classify_stop_type, compute_is_valid_lap,
                       tag_undercut_attempts)

log = setup_logging("f1_ingest")


# ---------------------------------------------------------------------------
# FastF1 bootstrap
# ---------------------------------------------------------------------------
def setup_fastf1() -> None:
    ensure_dirs()
    fastf1.Cache.enable_cache(str(CACHE_DIR))


# ---------------------------------------------------------------------------
# Per-session extractors
# ---------------------------------------------------------------------------
def _timedelta_to_sec(td: pd.Series) -> pd.Series:
    """FastF1 returns lap/sector times as pandas Timedelta. Convert to float seconds."""
    return td.dt.total_seconds()


@dataclass
class SessionFrames:
    laps: pd.DataFrame
    results: pd.DataFrame
    session_info: dict


def extract_session(session: Session, session_type: str) -> SessionFrames:
    """Pull laps + results from a loaded FastF1 session into clean DataFrames."""
    laps = session.laps.copy()

    # Column normalisation — FastF1 uses TitleCase, we use snake_case.
    out = pd.DataFrame({
        "driver_code":      laps["Driver"],
        "lap_number":       laps["LapNumber"].astype("Int64"),
        "lap_time_sec":     _timedelta_to_sec(laps["LapTime"]),
        "sector1_sec":      _timedelta_to_sec(laps["Sector1Time"]),
        "sector2_sec":      _timedelta_to_sec(laps["Sector2Time"]),
        "sector3_sec":      _timedelta_to_sec(laps["Sector3Time"]),
        "compound":         laps["Compound"],
        "tyre_life":        laps["TyreLife"].astype("Int64"),
        "stint":            laps["Stint"].astype("Int64"),
        "position":         laps["Position"].astype("Int64") if "Position" in laps else pd.NA,
        "track_status":     laps["TrackStatus"].astype(str),
        "is_personal_best": laps["IsPersonalBest"].fillna(False).astype(int) if "IsPersonalBest" in laps else 0,
        "speed_trap_kmh":   laps["SpeedST"] if "SpeedST" in laps else pd.NA,
        "is_pit_lap":       (laps["PitInTime"].notna() | laps["PitOutTime"].notna()).astype(int),
        "deleted":          laps["Deleted"].fillna(False).astype(int) if "Deleted" in laps else 0,
        "session_type":     session_type,
    })

    # FastF1 TrackStatus is a multi-char string where each char is an event:
    # '1' = Green, '2' = Yellow, '4' = SC, '5' = Red, '6'/'7' = VSC.
    # A value like '14' means "Green then SC during this lap" — the lap is NOT
    # clean. Only laps where EVERY character is '1' count as fully green.
    raw = out["track_status"].fillna("1").astype(str)

    def _classify(s: str) -> str:
        if not s:
            return "Green"
        if all(ch == "1" for ch in s):
            return "Green"
        if "5" in s:
            return "Red"
        if "4" in s:
            return "SC"
        if "6" in s or "7" in s:
            return "VSC"
        if "2" in s:
            return "Yellow"
        return "Green"

    out["track_status"] = raw.map(_classify)

    # Results — for race_results table
    results = pd.DataFrame()
    if hasattr(session, "results") and session.results is not None and not session.results.empty:
        r = session.results
        results = pd.DataFrame({
            "driver_code":    r["Abbreviation"],
            "full_name":      r["FullName"] if "FullName" in r else r["Abbreviation"],
            "team_name":      r["TeamName"] if "TeamName" in r else None,
            "team_color":     r["TeamColor"] if "TeamColor" in r else None,
            "number":         r["DriverNumber"].astype("Int64") if "DriverNumber" in r else pd.NA,
            "grid_position":  r["GridPosition"].astype("Int64") if "GridPosition" in r else pd.NA,
            "final_position": r["Position"].astype("Int64") if "Position" in r else pd.NA,
            "finish_status":  r["Status"] if "Status" in r else None,
            "points_scored":  r["Points"].astype(float) if "Points" in r else 0.0,
        })

    info = {
        "event_name":  session.event.EventName,
        "round":       int(session.event.RoundNumber),
        "date":        pd.Timestamp(session.event.EventDate).strftime("%Y-%m-%d"),
        "total_laps":  int(laps["LapNumber"].max()) if len(laps) else None,
        "circuit_key": session.event.Location,
        "country":     session.event.Country,
    }
    return SessionFrames(laps=out, results=results, session_info=info)


def extract_pit_stops(race_laps: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct pit stops from lap data.

    FastF1 exposes pit stops via PitInTime/PitOutTime markers on laps rather
    than a dedicated pit-stop endpoint. Duration = PitOutTime of next lap -
    PitInTime of current lap (approximate — includes slow in-lap segment).
    """
    df = race_laps.copy()
    if "driver_code" not in df.columns:
        return pd.DataFrame()

    df = df.sort_values(["driver_code", "lap_number"]).reset_index(drop=True)

    pit_in_rows = df[df["is_pit_lap"] == 1]
    if pit_in_rows.empty:
        return pd.DataFrame()

    # Stop number per driver
    df["_stop_num"] = df.groupby("driver_code")["is_pit_lap"].cumsum()
    stops = df[df["is_pit_lap"] == 1].copy()

    # Compound change: compare compound to prev lap per driver
    df["_prev_compound"] = df.groupby("driver_code")["compound"].shift(1)
    compound_map = df.set_index(["driver_code", "lap_number"])[["_prev_compound", "compound"]]

    pit_stops = pd.DataFrame({
        "driver_code":    stops["driver_code"],
        "lap_number":     stops["lap_number"].astype(int),
        "stop_number":    stops["_stop_num"].astype(int),
        "compound_in":    stops["compound"].map(lambda c: None),  # filled below
        "compound_out":   stops["compound"],
        "position_before": stops["position"].astype("Int64"),
    })
    # compound_in = previous lap's compound
    pit_stops["compound_in"] = stops.apply(
        lambda r: compound_map.loc[(r["driver_code"], r["lap_number"]), "_prev_compound"]
                  if (r["driver_code"], r["lap_number"]) in compound_map.index else None,
        axis=1,
    )
    return pit_stops.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Per-event writer
# ---------------------------------------------------------------------------
def _event_already_loaded(year: int, round_num: int) -> bool:
    """Return True if this race has laps already in the DB (resume support)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM laps l JOIN races r ON l.race_id = r.race_id"
            " WHERE r.year = ? AND r.round = ? AND l.session_type = 'R'",
            (year, round_num),
        ).fetchone()
        return row[0] > 50  # >50 race laps = fully loaded (20 drivers × ~3 laps min)


def ingest_event(year: int, round_num: int, skip_loaded: bool = True) -> bool:
    """Ingest one race weekend. Returns True on success, False on skip.

    Raises RateLimitExceededError immediately on API limit — caller should
    stop the whole run (further events will only waste time).
    """
    if skip_loaded and _event_already_loaded(year, round_num):
        log.info("Skipping %s R%s — already loaded", year, round_num)
        return True

    try:
        event = fastf1.get_event(year, round_num)
    except RateLimitExceededError:
        raise
    except Exception as exc:
        log.warning("get_event failed for %s R%s: %s", year, round_num, exc)
        return False

    race_frames: SessionFrames | None = None
    quali_frames: SessionFrames | None = None

    for stype in SESSION_TYPES:
        try:
            session = event.get_session(stype)
            session.load(laps=True, telemetry=False, weather=False, messages=False)
        except RateLimitExceededError:
            raise  # fatal — stop the orchestrator
        except Exception as exc:
            log.warning("load %s %s %s failed: %s", year, round_num, stype, exc)
            continue
        frames = extract_session(session, stype)
        if stype == "R":
            race_frames = frames
        elif stype == "Q":
            quali_frames = frames

    if race_frames is None:
        log.warning("No race data for %s R%s — skipping", year, round_num)
        return False

    with connect() as conn:
        # 1. Circuit + race
        circuit_id = upsert_circuit(
            conn,
            fastf1_key=race_frames.session_info["circuit_key"],
            name=race_frames.session_info["circuit_key"],
            country=race_frames.session_info["country"],
        )
        race_id = upsert_race(
            conn,
            circuit_id=circuit_id,
            year=year,
            round_num=race_frames.session_info["round"],
            event_name=race_frames.session_info["event_name"],
            date=race_frames.session_info["date"],
            total_laps=race_frames.session_info["total_laps"],
        )

        # Wipe child rows so the re-run is idempotent.
        clear_race_data(conn, race_id)

        # 2. Results → teams + drivers + race_results
        driver_id_map: dict[str, int] = {}  # code → driver_id
        if not race_frames.results.empty:
            for _, r in race_frames.results.iterrows():
                team_id = upsert_team(
                    conn,
                    season=year,
                    constructor_name=r["team_name"] or "Unknown",
                    short_name=r["team_name"],
                )
                d_id = upsert_driver(
                    conn,
                    season=year,
                    team_id=team_id,
                    code=str(r["driver_code"]),
                    full_name=str(r["full_name"]),
                    number=int(r["number"]) if pd.notna(r["number"]) else None,
                )
                driver_id_map[str(r["driver_code"])] = d_id
                conn.execute(
                    "INSERT INTO race_results (race_id, driver_id, grid_position,"
                    " final_position, finish_status, points_scored)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        race_id, d_id,
                        int(r["grid_position"])  if pd.notna(r["grid_position"])  else None,
                        int(r["final_position"]) if pd.notna(r["final_position"]) else None,
                        r["finish_status"],
                        float(r["points_scored"]) if pd.notna(r["points_scored"]) else 0.0,
                    ),
                )

        # 3. Laps (race + quali) — compute is_valid_lap per session
        for frames in (race_frames, quali_frames):
            if frames is None or frames.laps.empty:
                continue
            laps = frames.laps.copy()
            # Resolve driver_id per code — fall back to inserting a placeholder driver.
            laps["driver_id"] = laps["driver_code"].map(driver_id_map)
            missing = laps[laps["driver_id"].isna()]["driver_code"].unique()
            for code in missing:
                team_id = upsert_team(conn, season=year, constructor_name="Unknown")
                d_id = upsert_driver(conn, season=year, team_id=team_id,
                                     code=str(code), full_name=str(code))
                driver_id_map[str(code)] = d_id
                laps.loc[laps["driver_code"] == code, "driver_id"] = d_id

            laps["race_id"] = race_id
            laps["is_valid_lap"] = compute_is_valid_lap(laps)

            insert_cols = [
                "race_id", "driver_id", "session_type", "lap_number",
                "lap_time_sec", "sector1_sec", "sector2_sec", "sector3_sec",
                "compound", "tyre_life", "stint", "position",
                "track_status", "is_valid_lap", "is_personal_best",
                "speed_trap_kmh", "is_pit_lap", "deleted",
            ]
            conn.executemany(
                f"INSERT INTO laps ({', '.join(insert_cols)}) VALUES"
                f" ({', '.join(['?'] * len(insert_cols))})",
                _rows_for_sqlite(laps, insert_cols),
            )

        # 4. Pit stops (race only)
        pit_df = extract_pit_stops(race_frames.laps)
        if not pit_df.empty:
            pit_df["race_id"] = race_id
            pit_df["driver_id"] = pit_df["driver_code"].map(driver_id_map)
            pit_df = pit_df.dropna(subset=["driver_id"])
            # FastF1 doesn't expose stop_duration directly — leave NULL for now,
            # classify as drive_through (excluded from crew analytics). Week 4
            # layer adds duration from Ergast where available.
            pit_df["stop_duration_sec"] = None
            pit_df["stop_type"] = pit_df["stop_duration_sec"].apply(classify_stop_type)
            pit_df = tag_undercut_attempts(pit_df)

            cols = ["race_id", "driver_id", "lap_number", "stop_number",
                    "stop_duration_sec", "compound_in", "compound_out",
                    "position_before", "stop_type", "undercut_attempt"]
            conn.executemany(
                f"INSERT INTO pit_stops ({', '.join(cols)}) VALUES"
                f" ({', '.join(['?'] * len(cols))})",
                _rows_for_sqlite(pit_df, cols),
            )

    log.info("Ingested %s R%s: %s", year, round_num, race_frames.session_info["event_name"])
    return True


# ---------------------------------------------------------------------------
# Season driver
# ---------------------------------------------------------------------------
def ingest_season(year: int) -> dict:
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
    except RateLimitExceededError:
        raise
    results = {"ok": 0, "skipped": 0, "failed": 0}
    for _, event in schedule.iterrows():
        round_num = int(event["RoundNumber"])
        if round_num == 0:  # testing / pre-season
            continue
        try:
            ok = ingest_event(year, round_num)
            results["ok" if ok else "skipped"] += 1
        except RateLimitExceededError:
            raise  # stop immediately; budget is spent
        except Exception as exc:
            log.exception("event %s R%s failed: %s", year, round_num, exc)
            results["failed"] += 1
    return results


def resolve_seasons(args_seasons: Iterable[int]) -> list[int]:
    s = list(args_seasons)
    if not s:
        return SEASONS
    if len(s) == 2 and s[0] <= s[1]:
        return list(range(s[0], s[1] + 1))
    return s


def main() -> None:
    parser = argparse.ArgumentParser(description="FastF1 → SQLite ingestion")
    parser.add_argument("seasons", type=int, nargs="*",
                        help="Season year(s). Two args = inclusive range.")
    args = parser.parse_args()

    init_db()
    setup_fastf1()

    for year in resolve_seasons(args.seasons):
        log.info("=== Season %s ===", year)
        totals = ingest_season(year)
        log.info("Season %s done: %s", year, totals)


if __name__ == "__main__":
    main()