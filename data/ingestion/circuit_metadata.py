"""
Circuit metadata backfill.

Populates circuits.length_km / corners / drs_zones / lap_record_sec / surface_type
/ first_gp_year for every circuit that's been ingested. Values are hand-curated
from official FIA circuit data — Ergast doesn't publish track geometry.

Run AFTER ingestion (so fastf1_key rows exist):
    python -m data.ingestion.circuit_metadata
"""
from __future__ import annotations

from .config import setup_logging
from .db import connect

log = setup_logging("circuit_metadata")

# FastF1 uses the race location/city as its EventName key (e.g., "Bahrain",
# "Monaco", "Silverstone"). Order matches what shows up in
# fastf1.get_event_schedule(year)["Location"].
#
# Schema: fastf1_key → (length_km, corners, drs_zones, lap_record_sec,
#                       surface_type, first_gp_year)
# lap_record_sec: current race lap record (as of 2024). NULL if unknown.
# surface_type: "Smooth" / "Abrasive" / "Street" / "Mixed" (informal categorisation).
CIRCUIT_META: dict[str, tuple] = {
    "Sakhir":           (5.412, 15, 3, 91.447,  "Abrasive",  2004),
    "Bahrain":          (5.412, 15, 3, 91.447,  "Abrasive",  2004),
    "Jeddah":           (6.174, 27, 3, 88.049,  "Smooth",    2021),
    "Melbourne":        (5.278, 14, 4, 77.475,  "Smooth",    1996),
    "Suzuka":           (5.807, 18, 1, 90.983,  "Abrasive",  1987),
    "Shanghai":         (5.451, 16, 2, 92.238,  "Smooth",    2004),
    "Miami":            (5.412, 19, 3, 89.708,  "Smooth",    2022),
    "Imola":            (4.909, 19, 2, 78.322,  "Smooth",    1980),
    "Monaco":           (3.337, 19, 1, 71.381,  "Street",    1950),
    "Monte Carlo":      (3.337, 19, 1, 71.381,  "Street",    1950),
    "Montreal":         (4.361, 14, 3, 73.078,  "Smooth",    1978),
    "Montréal":         (4.361, 14, 3, 73.078,  "Smooth",    1978),
    "Barcelona":        (4.657, 14, 2, 76.330,  "Abrasive",  1991),
    "Spielberg":        (4.318, 10, 3, 65.619,  "Abrasive",  1970),
    "Red Bull Ring":    (4.318, 10, 3, 65.619,  "Abrasive",  1970),
    "Silverstone":      (5.891, 18, 2, 87.097,  "Abrasive",  1950),
    "Budapest":         (4.381, 14, 1, 76.627,  "Abrasive",  1986),
    "Spa-Francorchamps":(7.004, 19, 2, 103.588, "Mixed",     1950),
    "Zandvoort":        (4.259, 14, 2, 71.097,  "Abrasive",  1952),
    "Monza":            (5.793,  11, 2, 81.046,  "Smooth",   1950),
    "Baku":             (6.003, 20, 2, 103.009, "Street",    2016),
    "Singapore":        (4.940, 19, 3, 94.486,  "Street",    2008),
    "Marina Bay":       (4.940, 19, 3, 94.486,  "Street",    2008),
    "Austin":           (5.513, 20, 2, 96.169,  "Smooth",    2012),
    "Mexico City":      (4.304, 17, 3, 77.774,  "Smooth",    2015),
    "Interlagos":       (4.309, 15, 2, 71.011,  "Abrasive",  1973),
    "São Paulo":        (4.309, 15, 2, 71.011,  "Abrasive",  1973),
    "Sao Paulo":        (4.309, 15, 2, 71.011,  "Abrasive",  1973),
    "Las Vegas":        (6.201, 17, 2, 94.743,  "Street",    2023),
    "Yas Island":       (5.281, 16, 2, 86.103,  "Smooth",    2009),
    "Yas Marina":       (5.281, 16, 2, 86.103,  "Smooth",    2009),
    "Abu Dhabi":        (5.281, 16, 2, 86.103,  "Smooth",    2009),
    "Lusail":           (5.419, 16, 2, 83.196,  "Smooth",    2021),
    "Portimão":         (4.653, 15, 1, 78.750,  "Abrasive",  2020),
    "Portimao":         (4.653, 15, 1, 78.750,  "Abrasive",  2020),
    "Mugello":          (5.245, 15, 1, 95.063,  "Abrasive",  2020),
    "Le Castellet":     (5.842, 15, 2, 91.421,  "Abrasive",  1971),
    "Paul Ricard":      (5.842, 15, 2, 91.421,  "Abrasive",  1971),
    "Nürburgring":      (5.148, 15, 1, 92.342,  "Abrasive",  1984),
    "Nurburgring":      (5.148, 15, 1, 92.342,  "Abrasive",  1984),
    "Sochi":            (5.848, 18, 2, 95.761,  "Smooth",    2014),
    "Istanbul":         (5.338, 14, 1, 83.994,  "Smooth",    2005),
    "Hockenheim":       (4.574, 17, 2, 73.468,  "Smooth",    1970),
}


def backfill() -> dict:
    stats = {"updated": 0, "missing": []}
    with connect() as conn:
        rows = conn.execute(
            "SELECT circuit_id, fastf1_key, name FROM circuits"
        ).fetchall()
        for row in rows:
            key = row["fastf1_key"]
            meta = CIRCUIT_META.get(key)
            if meta is None:
                # Try matching on the display name too (FastF1 sometimes stores
                # the track's display name in fastf1_key).
                meta = CIRCUIT_META.get(row["name"])
            if meta is None:
                stats["missing"].append(key)
                log.warning("No metadata for circuit: %s (id=%s)",
                            key, row["circuit_id"])
                continue
            length_km, corners, drs, rec_sec, surface, first_yr = meta
            conn.execute(
                "UPDATE circuits SET length_km = ?, corners = ?, drs_zones = ?,"
                " lap_record_sec = ?, surface_type = ?, first_gp_year = ?"
                " WHERE circuit_id = ?",
                (length_km, corners, drs, rec_sec, surface, first_yr,
                 row["circuit_id"]),
            )
            stats["updated"] += 1
    log.info("Circuit metadata: updated=%d, missing=%d",
             stats["updated"], len(stats["missing"]))
    return stats


if __name__ == "__main__":
    backfill()
