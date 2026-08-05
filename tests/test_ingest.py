"""Phase 1 tests: ingestion, scoping, sorting, validation.

Golden values are hand-verified against the archive and recorded in MEMORY.md.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from src.ingest import MIN_ROWS, SCOPE_START, ingest, load_raw, sort_balls
from src.manifest import check_append_only, digest_rows, write_manifest
from src.validate import (
    NUM_COLS,
    RAW_COLS,
    ValidationError,
    check_distinct_balls,
    check_invariants,
    survey_draw_gaps,
    survey_expectations,
    validate_all,
)


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return ingest()


# ---------------------------------------------------------------- shape ----


def test_row_count_at_or_above_floor(df):
    """The archive grows Mon/Wed/Sat, so this is a floor, not an equality."""
    assert len(df) >= MIN_ROWS == 2370


def test_date_range(df):
    assert df["date"].min().date() == dt.date(2006, 4, 26)
    # Upper bound only -- new draws push this forward three times a week.
    assert df["date"].max().date() >= dt.date(2026, 7, 22)


def test_dates_unique_and_ascending(df):
    assert df["date"].is_unique
    assert df["date"].is_monotonic_increasing


def test_nothing_before_cutoff(df):
    assert (df["date"] >= pd.Timestamp(SCOPE_START)).all()


def test_cutoff_drops_exactly_the_pre_2006_history(df):
    """1,403 excluded draws is a permanent constant -- the past cannot grow."""
    raw = load_raw()
    assert len(raw) >= 3773
    assert len(raw) - len(df) == 1403


# ------------------------------------------------------------- sorting ----


def test_numbers_strictly_ascending(df):
    vals = df[NUM_COLS].to_numpy()
    assert (vals[:, 1:] > vals[:, :-1]).all()


def test_draw_order_preserved_as_multiset(df):
    """Sorting must not lose or alter any ball -- only reorder it."""
    for order, row in zip(df["draw_order"], df[NUM_COLS].to_numpy()):
        assert sorted(order) == list(row)


def test_draw_order_is_not_already_sorted(df):
    """Guards the assumption that motivated the sort step.

    If the archive ever arrives pre-sorted, `drawOrder` stops carrying
    information and this test should fail loudly rather than pass silently.
    """
    already = sum(1 for o in df["draw_order"] if o == sorted(o))
    assert already < len(df) * 0.10, (
        f"{already}/{len(df)} draws are already ascending -- the source format "
        "may have changed from draw order to sorted order."
    )


def test_all_balls_in_matrix(df):
    vals = df[NUM_COLS].to_numpy()
    assert vals.min() == 1
    assert vals.max() == 54


def test_six_distinct_balls(df):
    assert (df[NUM_COLS].nunique(axis=1) == 6).all()


# -------------------------------------------------------------- cadence ----


def test_current_archive_has_no_findings(df):
    """Documents today's state without hard-coding it as a rule.

    If this goes red the schedule probably changed -- read the finding, widen
    the observed set, note it in MEMORY.md. It is news, not a bug.
    """
    assert survey_expectations(df) == []


def test_monday_draws_start_2021_08_23(df):
    mondays = df[df["day_of_week"] == "Mon"]
    assert mondays["date"].min().date() == dt.date(2021, 8, 23)
    assert len(mondays) >= 257


# --------------------------------------------- schedule changes are news ----
#
# The original design treated Mon/Wed/Sat and 2-4 day gaps as invariants. Texas
# added Monday draws on 2021-08-23; that design would have halted ingestion on
# correct data. These tests pin the corrected behaviour: soft checks report.


def test_new_draw_day_reports_and_does_not_raise(df):
    """A Tuesday draw must be surfaced, not fatal."""
    changed = df.copy()
    changed.loc[changed.index[-1], "day_of_week"] = "Tue"
    findings = survey_expectations(changed)
    assert [f.code for f in findings] == ["new-draw-day"]


def test_unusual_gap_reports_and_does_not_raise(df):
    """A schedule change alters gaps too -- also a finding, not a crash."""
    changed = df.copy()
    last = changed.index[-1]
    changed.loc[last, "date"] = changed.loc[last, "date"] + pd.Timedelta(days=10)
    findings = survey_draw_gaps(changed)
    assert [f.code for f in findings] == ["unusual-gap"]


def test_invariants_still_pass_when_schedule_changes(df):
    """The physical checks are indifferent to when the game is drawn."""
    changed = df.copy()
    changed.loc[changed.index[-1], "day_of_week"] = "Tue"
    check_invariants(changed)  # must not raise


def test_strict_mode_escalates_findings(df):
    """CI opts in to failing on unreviewed schedule changes."""
    changed = df.copy()
    changed.loc[changed.index[-1], "day_of_week"] = "Tue"
    assert validate_all(changed) != []
    with pytest.raises(ValidationError, match="strict mode"):
        validate_all(changed, strict=True)


def test_unusual_gap_column_flags_affected_rows(df):
    """Rows after a discontinuity are marked so features can exclude them."""
    assert "unusual_gap" in df.columns
    assert not df["unusual_gap"].any()


# --------------------------------------------------------- golden values ----


def test_golden_first_retained_draw(df):
    """2006-04-26 -- the boundary case. Its predecessor is in the bonus-ball era."""
    row = df.iloc[0]
    assert row["date"].date() == dt.date(2006, 4, 26)
    assert list(row[NUM_COLS]) == [6, 8, 14, 23, 32, 52]
    assert row["draw_order"] == [32, 6, 23, 14, 8, 52]
    assert row["day_of_week"] == "Wed"


def test_golden_reference_draw(df):
    """2026-07-22 -- the reference case used throughout the feature specs.

    Looked up by date, never by position: new draws arrive Mon/Wed/Sat and this
    row stops being the last one as soon as the archive updates.
    """
    row = df[df["date"] == pd.Timestamp("2026-07-22")].iloc[0]
    assert list(row[NUM_COLS]) == [14, 33, 35, 44, 53, 54]
    assert row["draw_order"] == [14, 33, 54, 53, 44, 35]
    assert row["day_of_week"] == "Wed"


def test_golden_reference_predecessors(df):
    """The three draws feeding deltaSumAvg3 for the reference case."""
    idx = df.index[df["date"] == pd.Timestamp("2026-07-22")][0]
    prior = df.loc[idx - 3 : idx - 1, NUM_COLS].to_numpy().tolist()
    assert prior == [
        [3, 13, 16, 27, 32, 37],
        [2, 25, 27, 32, 40, 50],
        [12, 19, 21, 27, 41, 51],
    ]


# ------------------------------------------------------ validator guards ----


def test_distinct_ball_check_catches_bonus_ball_era():
    """The regression test for the finding in MEMORY.md.

    Ingesting without the cutoff pulls in the 2003-2006 bonus-ball format, where
    the sixth column repeats a main ball in 34 of 311 draws. Validation must
    reject it rather than silently computing a zero delta.
    """
    raw = sort_balls(load_raw())
    with pytest.raises(ValidationError, match="distinct balls"):
        check_distinct_balls(raw)


def test_distinct_ball_check_reports_34_offenders():
    raw = load_raw()
    counts = raw[RAW_COLS].nunique(axis=1)
    offenders = raw[counts != 6]
    assert len(offenders) == 34
    # Every one falls inside the bonus-ball window, and nowhere else.
    assert offenders["date"].min().date() >= dt.date(2003, 5, 3)
    assert offenders["date"].max().date() <= dt.date(2006, 4, 22)


def test_row_floor_breach_fails_loudly():
    """A truncated source must be rejected. Growth must not be."""
    with pytest.raises(ValidationError, match="below the known floor"):
        ingest(min_rows=999_999)


# ------------------------------------------------- append-only integrity ----


def test_append_only_accepts_unchanged_archive(df):
    manifest = write_manifest(df, tmp_manifest := _tmp())
    summary = check_append_only(df, manifest)
    assert summary["newDraws"] == 0
    tmp_manifest.unlink()


def test_append_only_accepts_new_draws(df):
    """Simulate the routine case: history intact, fresh draws appended."""
    history = df.iloc[:-3]
    manifest = write_manifest(history, tmp := _tmp())
    summary = check_append_only(df, manifest)
    assert summary["newDraws"] == 3
    tmp.unlink()


def test_append_only_rejects_revised_history(df):
    """The failure this whole mechanism exists to catch."""
    manifest = write_manifest(df, tmp := _tmp())
    tampered = df.copy()
    tampered.loc[10, "n1"] = 99
    with pytest.raises(ValidationError, match="digest mismatch"):
        check_append_only(tampered, manifest)
    tmp.unlink()


def test_append_only_rejects_shrunken_archive(df):
    manifest = write_manifest(df, tmp := _tmp())
    with pytest.raises(ValidationError, match="went backwards|History changed size"):
        check_append_only(df.iloc[:-5], manifest)
    tmp.unlink()


def test_digest_ignores_draw_order(df):
    """The digest tracks source values, not presentation or derived features."""
    shuffled = df.copy()
    shuffled["draw_order"] = [list(reversed(o)) for o in shuffled["draw_order"]]
    assert digest_rows(shuffled) == digest_rows(df)


def _tmp():
    import tempfile

    return Path(tempfile.mkdtemp()) / "manifest.json"
