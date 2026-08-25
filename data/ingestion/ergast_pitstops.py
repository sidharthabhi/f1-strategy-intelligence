"""
Ergast API pit-stop enrichment.

FastF1 doesn't reliably expose pit-stop duration. Ergast publishes clean
stop timings from 2012 onward. This script UPDATEs existing pit_stops rows
with real durations and re-classifies stop_type.

Ergast endpoint:
    https://ergast.com/api/f1/{year}/{round}/pitstops.json

Rate limits: 4 requests/sec, 200/hour anonymous. We throttle at 2.5/sec.

Run AFTER fastf1 ingestion:
    python -m data.ingestion.ergast_pitstops          # all seasons in DB
    python -m data.ingestion.ergast_pitstops 2024     # single season
    python -m data.ingestion.ergast_pitstops 2018 2024  # range
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

from .config import (PIT_DURATION_MAX_SEC, PIT_DURATION_MIN_SEC,
                     setup_logging)
from .db import connect
from .validity import classify_stop_type

log = setup_logging("ergast_pitstops")

ERGAST_BASE = "https://api.jolpi.ca/ergast/f1"  # Ergast.com retired; Jolpica mirror
# Fallback: "https://ergast.com/api/f1" — kept as const if user overrides
REQUEST_DELAY_SEC = 0.4  # 2.5 req/sec
REQUEST_TIMEOUT_SEC = 15


def _fetch_pitstops(year: int, round_num: int) -> list[dict]:
    """Fetch all pit stops for one race from Ergast. Returns [] on failure."""
    url = f"{ERGAST_BASE}/{year}/{round_num}/pitstops.json?limit=1000"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SEC)
    except requests.RequestException as exc:
        log.warning("HTTP error for %s R%s: %s", year, round_num, exc)
        return []

    if resp.status_code != 200:
        log.warning("Ergast returned %s for %s R%s", resp.status_code, year, round_num)
        return []

    try:
        data = resp.json()
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if not races:
            return []
        return races[0].get("PitStops", [])
    except (ValueError, KeyError) as exc:
        log.warning("JSON parse failed for %s R%s: %s", year, round_num, exc)
        return []


def _duration_to_sec(duration_str: str) -> float | None:
    """
    Ergast duration formats seen in the wild:
      "23.678"       - seconds only
      "0:23.678"     - M:SS.mmm
      "00:23.678"    - MM:SS.mmm
    Returns float seconds or None if unparseable.
    """
    if not duration_str:
        return None
    s = duration_str.strip()
    try:
        if ":" in s:
            parts = s.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(s)
    except (ValueError, IndexError):
        return None


def enrich_season(year: int) -> dict:
    """Fetch and UPDATE all pit stops for one season."""
    stats = {"races_tried": 0, "races_ok": 0, "stops_updated": 0, "stops_unmatched": 0}

    with connect() as conn:
        race_rows = conn.execute(
            "SELECT race_id, round FROM races WHERE year = ? ORDER BY round",
            (year,),
        ).fetchall()

    for rr in race_rows:
        race_id = rr["race_id"]
        round_num = rr["round"]
        stats["races_tried"] += 1

        stops = _fetch_pitstops(year, round_num)
        time.sleep(REQUEST_DELAY_SEC)

        if not stops:
            continue

        stats["races_ok"] += 1

        with connect() as conn:
            for s in stops:
                driver_ref = s.get("driverId")       # "max_verstappen"
                lap = int(s.get("lap", 0) or 0)
                stop_num = int(s.get("stop", 0) or 0)
                duration = _duration_to_sec(s.get("duration", ""))

                if not driver_ref or lap == 0:
                    continue

                # Ergast driverId → our driver code requires a mapping layer.
                # Strategy: match by (race_id, lap_number, stop_number) which
                # is unique — driver-agnostic. This avoids the Ergast→FastF1
                # driver ID mapping altogether.
                cur = conn.execute(
                    "SELECT pit_id, stop_duration_sec FROM pit_stops"
                    " WHERE race_id = ? AND lap_number = ? AND stop_number = ?",
                    (race_id, lap, stop_num),
                )
                matches = cur.fetchall()

                if len(matches) == 0:
                    stats["stops_unmatched"] += 1
                    continue

                # If multiple matches (double-stack on same lap), skip — ambiguous.
                if len(matches) > 1:
                    stats["stops_unmatched"] += 1
                    continue

                pit_id = matches[0]["pit_id"]
                new_type = classify_stop_type(duration)
                conn.execute(
                    "UPDATE pit_stops SET stop_duration_sec = ?, stop_type = ?"
                    " WHERE pit_id = ?",
                    (duration, new_type, pit_id),
                )
                stats["stops_updated"] += 1

        log.info("  %s R%s: %d stops from Ergast", year, round_num, len(stops))

    log.info("Season %s: %s", year, stats)
    return stats


def resolve_seasons(args_seasons: list[int]) -> list[int]:
    if not args_seasons:
        # Default: every season in DB
        with connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT year FROM races ORDER BY year"
            ).fetchall()
        return [r["year"] for r in rows]
    if len(args_seasons) == 2 and args_seasons[0] <= args_seasons[1]:
        return list(range(args_seasons[0], args_seasons[1] + 1))
    return args_seasons


def main() -> None:
    parser = argparse.ArgumentParser(description="Ergast pit-stop enrichment")
    parser.add_argument("seasons", type=int, nargs="*")
    args = parser.parse_args()

    totals = {"races_tried": 0, "races_ok": 0, "stops_updated": 0, "stops_unmatched": 0}
    for year in resolve_seasons(args.seasons):
        if year < 2012:
            log.info("Skipping %s: Ergast pit data starts in 2012", year)
            continue
        log.info("=== Enriching %s ===", year)
        s = enrich_season(year)
        for k in totals:
            totals[k] += s[k]

    log.info("All done: %s", totals)


if __name__ == "__main__":
    main()
