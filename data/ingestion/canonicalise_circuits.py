"""
Merge duplicate circuit rows that point to the same physical track.

FastF1 stores the same circuit under different EventName/Location keys across
seasons (e.g., "Monaco" and "Monte Carlo", "Yas Marina" and "Yas Island",
"São Paulo" and "Interlagos"). When grouping queries by circuit_id, results
get split, breaking analyses like Q19 (quali predictiveness) and Q15 (overtaking).

This script:
  1. Identifies sets of circuit_ids that share the same canonical track
  2. Picks one survivor per set (the lowest circuit_id)
  3. UPDATEs races.circuit_id to point to the survivor
  4. DELETEs the now-orphaned duplicate circuit rows

Idempotent — safe to re-run. After running, every track is exactly one circuit_id.
"""
from __future__ import annotations

from .config import setup_logging
from .db import connect

log = setup_logging("canonicalise_circuits")

# Each value list is a set of FastF1 keys that map to the same physical circuit.
# The first entry in each list is the canonical name (used to update circuits.name).
CIRCUIT_SYNONYMS: list[tuple[str, list[str]]] = [
    ("Bahrain",       ["Bahrain", "Sakhir"]),
    ("Monaco",        ["Monaco", "Monte Carlo"]),
    ("Montréal",      ["Montréal", "Montreal"]),
    ("Yas Marina",    ["Yas Marina", "Yas Island"]),
    ("Interlagos",    ["Interlagos", "São Paulo", "Sao Paulo"]),
    ("Singapore",     ["Singapore", "Marina Bay"]),
    ("Red Bull Ring", ["Red Bull Ring", "Spielberg"]),
    ("Paul Ricard",   ["Paul Ricard", "Le Castellet"]),
    ("Nürburgring",   ["Nürburgring", "Nurburgring"]),
    ("Portimão",      ["Portimão", "Portimao"]),
]


def run() -> dict:
    stats = {"merged_groups": 0, "races_updated": 0, "circuits_deleted": 0}

    with connect() as conn:
        for canonical_name, synonyms in CIRCUIT_SYNONYMS:
            # Find all circuit_id rows whose fastf1_key OR name matches a synonym
            placeholders = ",".join("?" * len(synonyms))
            rows = conn.execute(
                f"SELECT circuit_id, fastf1_key, name FROM circuits"
                f" WHERE fastf1_key IN ({placeholders}) OR name IN ({placeholders})",
                synonyms + synonyms,
            ).fetchall()

            if len(rows) <= 1:
                continue

            survivor = min(r["circuit_id"] for r in rows)
            duplicates = [r["circuit_id"] for r in rows if r["circuit_id"] != survivor]

            log.info("Merging %s into circuit_id=%d (%s) — duplicates: %s",
                     canonical_name, survivor,
                     [r["name"] for r in rows], duplicates)

            # Repoint races
            for dup in duplicates:
                cur = conn.execute(
                    "UPDATE races SET circuit_id = ? WHERE circuit_id = ?",
                    (survivor, dup),
                )
                stats["races_updated"] += cur.rowcount

            # Delete duplicates
            for dup in duplicates:
                conn.execute("DELETE FROM circuits WHERE circuit_id = ?", (dup,))
                stats["circuits_deleted"] += 1

            # Set canonical name on survivor
            conn.execute(
                "UPDATE circuits SET name = ? WHERE circuit_id = ?",
                (canonical_name, survivor),
            )

            stats["merged_groups"] += 1

    log.info("Canonicalisation result: %s", stats)
    return stats


if __name__ == "__main__":
    run()
