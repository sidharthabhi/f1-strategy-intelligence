"""
Lap validity + pit-stop classification logic.

is_valid_lap = 1 ONLY when all 7 conditions hold (per Part A of the plan):

  1. lap_number > 1                         (excludes formation lap)
  2. is_pit_lap = 0                         (excludes in-laps)
  3. previous lap is_pit_lap = 0            (excludes out-laps)
  4. track_status = 'Green'                 (excludes SC / VSC / Yellow / Red)
  5. deleted = 0                            (excludes track-limit deletions)
  6. lap_time_sec IS NOT NULL               (excludes partial DNF laps)
  7. lap_time_sec < sanity_upper_bound      (rules out obvious outliers)

The sanity bound: a lap can't take longer than driving the circuit at MIN_AVG_SPEED_KMH.
"""
from __future__ import annotations

import pandas as pd

from .config import (MIN_AVG_SPEED_KMH, PIT_DURATION_MAX_SEC, PIT_DURATION_MIN_SEC)


def _sanity_upper_bound_sec(circuit_length_km: float | None) -> float:
    """Lap can't be slower than circuit_length / MIN_AVG_SPEED_KMH (converted to seconds)."""
    if not circuit_length_km or circuit_length_km <= 0:
        return 600.0  # safe default: 10 minutes
    return (circuit_length_km / MIN_AVG_SPEED_KMH) * 3600.0


def compute_is_valid_lap(laps_df: pd.DataFrame,
                         circuit_length_km: float | None = None,
                         max_deviation_ratio: float = 1.10) -> pd.Series:
    """
    Vectorised 7-condition validity flag.

    The final condition (outlier rejection) uses a per-driver, per-race baseline:
    a lap is rejected if its time exceeds `max_deviation_ratio` × the driver's
    fastest green-flag lap in that race. This catches:
      - SC/VSC contamination that slipped past status-string parsing
      - Cumulative-timer artefacts on red-flag restart laps (2478s "laps")
      - Traffic-impacted laps where the time is nonsensically slow

    110% is a standard F1 reference point — F1's own 107% qualifying rule works
    on the same principle.

    Expected columns (FastF1 session.laps format, lowercased):
      lap_number, is_pit_lap, track_status, deleted, lap_time_sec, driver_id
    """
    df = laps_df.copy()

    for col, default in [
        ("is_pit_lap", 0),
        ("track_status", "Green"),
        ("deleted", 0),
        ("lap_time_sec", None),
        ("lap_number", 0),
    ]:
        if col not in df.columns:
            df[col] = default

    df = df.sort_values(["driver_id", "lap_number"]).reset_index(drop=True)
    df["_prev_pit"] = df.groupby("driver_id")["is_pit_lap"].shift(1).fillna(0).astype(int)

    # Absolute upper bound — any lap over 10 minutes is a cumulative-timer artefact.
    absolute_upper = 600.0

    # Conditions 1-6 (the hard rules).
    base = (
        (df["lap_number"]   > 1)
        & (df["is_pit_lap"] == 0)
        & (df["_prev_pit"]  == 0)
        & (df["track_status"].astype(str).str.upper().eq("GREEN"))
        & (df["deleted"]    == 0)
        & (df["lap_time_sec"].notna())
        & (df["lap_time_sec"] < absolute_upper)
        & (df["lap_time_sec"] > 30)  # no F1 circuit has laps under 30s
    )

    # Condition 7 (relative): lap must be within 110% of driver's fastest
    # GREEN lap in this race. Compute baseline using only rows that passed base
    # checks — otherwise a contaminated "valid" lap would taint the baseline.
    if "race_id" in df.columns and "driver_id" in df.columns:
        df["_candidate"] = base
        clean = df.loc[df["_candidate"], ["race_id", "driver_id", "lap_time_sec"]]
        baselines = (
            clean.groupby(["race_id", "driver_id"])["lap_time_sec"]
                 .min()
                 .rename("_fastest")
                 .reset_index()
        )
        df = df.merge(baselines, on=["race_id", "driver_id"], how="left")
        # If a driver has no clean laps in a race, baseline is NaN — reject all.
        within_ratio = (
            df["_fastest"].notna()
            & (df["lap_time_sec"] <= df["_fastest"] * max_deviation_ratio)
        )
        conditions = base & within_ratio
    else:
        conditions = base

    return conditions.astype(int).reset_index(drop=True)


def classify_stop_type(stop_duration_sec: float | None,
                       is_teammate_double_stack: bool = False) -> str:
    """
    Classify a pit stop into one of 4 buckets used by crew-performance metrics.
      normal         — standard tire change, clean duration window
      drive_through  — penalty stop or data error (duration NULL / out of bounds)
      double_stack   — teammate stopped within 2 laps
      no_tire_change — stop with no compound change (rare — carry forward compound)
    """
    if stop_duration_sec is None or pd.isna(stop_duration_sec):
        return "drive_through"
    if stop_duration_sec < PIT_DURATION_MIN_SEC or stop_duration_sec > PIT_DURATION_MAX_SEC:
        return "drive_through"
    if is_teammate_double_stack:
        return "double_stack"
    return "normal"


def tag_undercut_attempts(pit_df: pd.DataFrame, gap_threshold_sec: float = 3.0,
                          lap_window: int = 4) -> pd.DataFrame:
    """
    Mark pit stops as undercut attempts.

    Definition (Part A, metric A2.1):
      - Driver A pits on lap N
      - A rival within `gap_threshold_sec` at lap N
      - Rival pits within laps N+1..N+lap_window
    """
    df = pit_df.copy()
    df["undercut_attempt"] = 0
    if df.empty:
        return df

    for race_id, race_pits in df.groupby("race_id"):
        for idx, row in race_pits.iterrows():
            same_race = race_pits[race_pits["driver_id"] != row["driver_id"]]
            rival_follows = same_race[
                (same_race["lap_number"] > row["lap_number"])
                & (same_race["lap_number"] <= row["lap_number"] + lap_window)
            ]
            if not rival_follows.empty:
                df.at[idx, "undercut_attempt"] = 1
    return df