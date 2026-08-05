"""Load the Lotto Texas archive into a validated DataFrame.

Scope: 2006-04-26 onward only. See PROJECT.md ("Scope") and MEMORY.md for why
everything earlier is excluded -- briefly, the 2003-2006 period is a 5/44 game
with a bonus ball from a second pool, not a six-ball draw.

Output columns
--------------
date                    datetime64, ascending, unique
draw_order              list[int]  -- balls in the order drawn (physical artifact)
n1..n6                  int        -- balls sorted ascending (basis for all deltas)
year, month, day        int
day_of_week             str        -- 'Mon' | 'Wed' | 'Sat'
unusual_gap             bool       -- True if the gap from the previous draw falls
                                      outside the observed schedule (see validate.py)
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .config import Config
from .validate import (
    NUM_COLS,
    RAW_COLS,
    Finding,
    flag_schedule_anomalies,
    validate_all,
)

GAME_NAME = "Lotto Texas"

# --------------------------------------------------------------------------
# The cutoff. First draw of the current uninterrupted 6/54 regime.
# The preceding draw (2006-04-22) is the last of the 5/44 + bonus-ball era and
# must never be used as a predecessor. See MEMORY.md.
# --------------------------------------------------------------------------
SCOPE_START = dt.date(2006, 4, 26)

# Floor, not a target. The archive gains a draw every Mon/Wed/Sat, so this is the
# count observed at the 2026-07-22 snapshot and must never be exceeded downward.
# Growth beyond it is expected and is checked for append-only integrity in
# manifest.py rather than by an exact-count assertion here.
MIN_ROWS = 2370

DEFAULT_CSV = Path(__file__).resolve().parents[1] / "lottotexas.csv"

CSV_COLUMNS = ["game", "month", "day", "year", *RAW_COLS]


def load_raw(csv_path: Path | str = DEFAULT_CSV) -> pd.DataFrame:
    """Read the headerless CSV into a frame. No filtering, no validation."""
    df = pd.read_csv(csv_path, header=None, names=CSV_COLUMNS)
    if len(df.columns) != len(CSV_COLUMNS):
        raise ValueError(
            f"Expected {len(CSV_COLUMNS)} columns, found {len(df.columns)}"
        )
    df["date"] = pd.to_datetime(df[["year", "month", "day"]])
    return df.sort_values("date", ignore_index=True)


def apply_scope(df: pd.DataFrame, start: dt.date = SCOPE_START) -> pd.DataFrame:
    """Drop every draw before the cutoff.

    Applied before validation, deliberately: the excluded rows would fail the
    distinct-ball check, and that failure is expected rather than informative.
    """
    return df[df["date"] >= pd.Timestamp(start)].reset_index(drop=True)


def sort_balls(df: pd.DataFrame) -> pd.DataFrame:
    """Sort each draw's balls ascending into n1..n6, preserving draw order.

    THE one sort in this project. Balls are sorted so gaps between adjacent
    numbers are well defined. The deltas computed from them are never sorted --
    see CLAUDE.md.

    The archive stores balls in draw order; only ~3% happen to be ascending
    already, so skipping this silently corrupts every delta.
    """
    df = df.copy()
    raw = df[RAW_COLS].to_numpy()
    df["draw_order"] = [row.tolist() for row in raw]
    df[NUM_COLS] = pd.DataFrame(
        [sorted(row.tolist()) for row in raw], index=df.index, columns=NUM_COLS
    )
    return df


def add_date_parts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["day"] = df["date"].dt.day
    df["day_of_week"] = df["date"].dt.strftime("%a")
    return df


def ingest(
    csv_path: Path | str = DEFAULT_CSV,
    *,
    config: "Config | None" = None,
    min_rows: int | None = MIN_ROWS,
    validate: bool = True,
    check_append_only: bool = False,
    strict: bool = False,
    report: bool = True,
) -> pd.DataFrame:
    """Full ingestion: load, scope, sort, validate.

    Raises ValidationError if a physical invariant is violated. Soft findings --
    an unfamiliar draw day, an unusual gap -- are reported and attached to the
    frame's `.attrs["findings"]`, not raised, because the operator is allowed to
    change the schedule and correct data must not halt the pipeline. Pass
    `strict=True` (CI) to escalate findings to failures.

    Set `check_append_only=True` for routine re-ingestion of updated source data
    (the Mon/Wed/Sat cycle). It verifies that previously-seen draws are unchanged
    and records the new state. Left off by default so tests and one-off analysis
    do not mutate the manifest.
    """
    # An explicit config overrides the module defaults for scope and floor.
    scope_start = config.scope_start if config is not None else SCOPE_START
    if config is not None:
        min_rows = config.min_rows

    df = load_raw(csv_path)
    df = apply_scope(df, scope_start)
    df = sort_balls(df)
    df = add_date_parts(df)

    keep = ["date", "year", "month", "day", "day_of_week", "draw_order", *NUM_COLS]
    # RAW_COLS are retained through validation -- check_distinct_balls and
    # check_ball_range read the as-drawn values, not the sorted ones.
    df = df[keep + RAW_COLS]

    findings: list[Finding] = []
    if validate:
        findings = validate_all(df, min_rows=min_rows, strict=strict)

    df = df.drop(columns=RAW_COLS).reset_index(drop=True)
    df["unusual_gap"] = flag_schedule_anomalies(df)
    df.attrs["findings"] = findings

    if report and findings:
        print(f"{len(findings)} finding(s) -- data accepted, review advised:")
        for f in findings:
            print(f"  {f}")

    if check_append_only:
        from .manifest import verify_and_update

        summary = verify_and_update(df)
        _report_update(summary)

    return df


def _report_update(summary: dict) -> None:
    if summary.get("firstRun"):
        print(f"Manifest initialised at {summary['rowCount']} draws.")
    elif summary["newDraws"] == 0:
        print(f"No new draws since {summary['previousLastDate']}.")
    else:
        print(
            f"{summary['newDraws']} new draw(s): "
            f"{', '.join(summary['newDates'])}  "
            f"(history verified unchanged through {summary['previousLastDate']})"
        )


if __name__ == "__main__":
    import sys

    # `python -m src.ingest --update` is the Mon/Wed/Sat entry point: it verifies
    # that history did not change and reports which draws are new.
    frame = ingest(check_append_only="--update" in sys.argv)
    print(f"Ingested {len(frame)} draws")
    print(f"Range   {frame['date'].min().date()} -> {frame['date'].max().date()}")
    print(f"Balls   {frame[NUM_COLS].to_numpy().min()}..{frame[NUM_COLS].to_numpy().max()}")
    print()
    print(frame.head(3).to_string())
    print("...")
    print(frame.tail(3).to_string())
