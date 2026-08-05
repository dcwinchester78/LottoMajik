"""Phase 2 (F1-F4) and Phase 3 (F5-F6) tests.

Golden values are hand-verified against the archive and recorded in MEMORY.md.
Reference draw is 2026-07-22, looked up by date -- never by position, since new
draws arrive three times a week.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.encode import decode_delta_code_exact, decode_shuffle_code_exact
from src.features import (
    DELTA_COLS,
    DELTA_DIFF_COLS,
    NUM_DIFF_COLS,
    build_features,
    check_code_invariants,
    check_delta_invariants,
    compute_delta_sum_avg3,
    compute_deltas,
)
from src.ingest import ingest
from src.validate import NUM_COLS, ValidationError

REFERENCE = pd.Timestamp("2026-07-22")
FIRST_DRAW = pd.Timestamp("2006-04-26")


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return build_features(ingest(report=False))


def _row(df: pd.DataFrame, when: pd.Timestamp) -> pd.Series:
    return df[df["date"] == when].iloc[0]


# ------------------------------------------------------- golden values ----


def test_golden_deltas(df):
    """F1. Sorted balls [14, 33, 35, 44, 53, 54] -> gaps [19, 2, 9, 9, 1]."""
    row = _row(df, REFERENCE)
    assert list(row[NUM_COLS]) == [14, 33, 35, 44, 53, 54]
    assert list(row[DELTA_COLS]) == [19, 2, 9, 9, 1]


def test_golden_delta_sum(df):
    """F2."""
    assert _row(df, REFERENCE)["delta_sum"] == 40


def test_golden_delta_diff_prev(df):
    """F3. Against 2026-07-20 deltas [7, 2, 6, 14, 10]."""
    row = _row(df, REFERENCE)
    assert list(row[DELTA_DIFF_COLS]) == [12, 0, 3, -5, -9]
    assert row["prev_draw_id"] == "2026-07-20"
    assert row["prev_gap_days"] == 2
    assert bool(row["has_prev"]) is True


def test_golden_delta_sum_avg3(df):
    """F4. Mean of 34, 48, 39."""
    assert _row(df, REFERENCE)["delta_sum_avg3"] == pytest.approx(121 / 3)


def test_golden_first_retained_draw(df):
    """2006-04-26: deltas exist, everything inter-draw is null."""
    row = _row(df, FIRST_DRAW)
    assert list(row[DELTA_COLS]) == [2, 6, 9, 9, 20]
    assert row["delta_sum"] == 46
    assert row[DELTA_DIFF_COLS].isna().all()
    assert pd.isna(row["prev_draw_id"])
    assert pd.isna(row["delta_sum_avg3"])
    assert bool(row["has_prev"]) is False


# ------------------------------------------------------ delta ordering ----


def test_deltas_are_not_sorted(df):
    """The core commitment. Position carries the information.

    The reference draw's gaps are [19, 2, 9, 9, 1] -- strongly non-monotonic.
    If some refactor ever sorts them, this fails first.
    """
    assert list(_row(df, REFERENCE)[DELTA_COLS]) == [19, 2, 9, 9, 1]


def test_most_draws_have_unsorted_deltas(df):
    """Guards against a sort slipping in that happens to pass the case above."""
    vals = df[DELTA_COLS].to_numpy()
    ascending = (np.diff(vals, axis=1) >= 0).all(axis=1).sum()
    assert ascending < len(df) * 0.05, (
        f"{ascending}/{len(df)} draws have ascending deltas -- suspiciously many. "
        "Something is sorting the deltas."
    )


def test_delta_position_matches_ball_position(df):
    """d[i] is the gap between ball i and ball i+1, for every draw."""
    balls = df[NUM_COLS].to_numpy()
    deltas = df[DELTA_COLS].to_numpy()
    assert (deltas == np.diff(balls, axis=1)).all()


# ----------------------------------------------------------- invariants ----


def test_all_deltas_at_least_one(df):
    assert (df[DELTA_COLS].to_numpy() >= 1).all()


def test_delta_sum_telescopes(df):
    assert (df["delta_sum"] == df["n6"] - df["n1"]).all()


def test_delta_sum_equals_sum_of_deltas(df):
    assert (df["delta_sum"] == df[DELTA_COLS].sum(axis=1)).all()


def test_zero_delta_raises():
    """A repeated ball produces a zero gap and must fail loudly."""
    bad = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-22")],
            **{c: [v] for c, v in zip(NUM_COLS, [14, 14, 35, 44, 53, 54])},
        }
    )
    with pytest.raises(ValidationError, match="delta below 1"):
        check_delta_invariants(compute_deltas(bad).assign(delta_sum=40))


def test_delta_sum_mismatch_raises():
    """A deltaSum that does not span the draw means positions were lost."""
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-22")],
            **{c: [v] for c, v in zip(NUM_COLS, [14, 33, 35, 44, 53, 54])},
        }
    )
    frame = compute_deltas(frame).assign(delta_sum=999)
    with pytest.raises(ValidationError, match="deltaSum != n6 - n1"):
        check_delta_invariants(frame)


# ------------------------------------------------- windowing edge cases ----


def test_avg3_null_for_first_three_draws(df):
    assert df["delta_sum_avg3"].head(3).isna().all()


def test_avg3_present_from_fourth_draw(df):
    """First computable value: mean of 46, 39, 37."""
    assert df["delta_sum_avg3"].iloc[3] == pytest.approx((46 + 39 + 37) / 3)


def test_avg3_excludes_current_draw():
    """The feature must look strictly backwards.

    Constructed so that including the current draw gives a different answer:
    prior sums are 10, 20, 30 (mean 20); with the current 100 the mean of the
    last three would be 50.
    """
    frame = pd.DataFrame({"delta_sum": [10, 20, 30, 100]})
    out = compute_delta_sum_avg3(frame)
    assert out["delta_sum_avg3"].iloc[3] == pytest.approx(20.0)


def test_avg3_uses_exactly_three_priors():
    frame = pd.DataFrame({"delta_sum": [10, 20, 30, 40, 50]})
    out = compute_delta_sum_avg3(frame)
    assert out["delta_sum_avg3"].iloc[4] == pytest.approx((20 + 30 + 40) / 3)


def test_delta_diff_prev_matches_manual_shift(df):
    """dd[i](t) == d[i](t) - d[i](t-1), across the whole archive."""
    expected = df[DELTA_COLS].astype("Int64") - df[DELTA_COLS].astype("Int64").shift(1)
    actual = df[DELTA_DIFF_COLS].astype("Int64")
    assert actual.to_numpy(na_value=-999).tolist() == expected.to_numpy(
        na_value=-999
    ).tolist()


def test_delta_diff_prev_is_integer_not_float(df):
    """-5, not -5.0. The React app reads these directly."""
    for col in DELTA_DIFF_COLS:
        assert str(df[col].dtype) == "Int64"


# ---------------------------------------------------------------- purity ----


def test_build_features_does_not_mutate_input():
    """Pure functions: DataFrame in, DataFrame out, no hidden state."""
    source = ingest(report=False)
    before = source.copy(deep=True)
    build_features(source)
    pd.testing.assert_frame_equal(source, before)


def test_feature_columns_added(df):
    for col in [*DELTA_COLS, *DELTA_DIFF_COLS, "delta_sum", "delta_sum_avg3"]:
        assert col in df.columns


# ===========================================================================
# Phase 3 -- F5 deltaCode, F6 shuffleCode, wired into the pipeline
# ===========================================================================

CODE_COLS = [
    "delta_code_exact",
    "delta_code_bucket",
    "delta_code_shape",
    "shuffle_code_exact",
    "shuffle_code_direction",
    "shuffle_code_magnitude",
    "shuffle_code_delta_exact",
    "shuffle_code_delta_direction",
    "shuffle_code_delta_magnitude",
]


def test_code_columns_added(df):
    for col in CODE_COLS:
        assert col in df.columns


def test_golden_delta_code(df):
    """F5. [19, 2, 9, 9, 1] -> exact, bucket, shape."""
    row = _row(df, REFERENCE)
    assert row["delta_code_exact"] == "19-02-09-09-01"
    assert row["delta_code_bucket"] == "LSMMS"
    assert row["delta_code_shape"] == "01-02-09-09-19"


def test_golden_shuffle_code_number_space(df):
    """F6. Movement of sorted balls vs 2026-07-20 [12, 19, 21, 27, 41, 51]."""
    row = _row(df, REFERENCE)
    assert row["shuffle_code_exact"] == "U02.U14.U14.U17.U12.U03"
    assert row["shuffle_code_direction"] == "UUUUUU"
    assert row["shuffle_code_magnitude"] == 62


def test_golden_shuffle_code_delta_space(df):
    """F6 applied to deltaDiffPrev instead of raw ball movement."""
    row = _row(df, REFERENCE)
    assert row["shuffle_code_delta_exact"] == "U12.S00.U03.D05.D09"
    assert row["shuffle_code_delta_direction"] == "USUDD"
    assert row["shuffle_code_delta_magnitude"] == 29


def test_golden_first_retained_draw_codes_null_where_no_predecessor(df):
    """2006-04-26: deltaCode exists (intra-draw), shuffleCode is null (no prev)."""
    row = _row(df, FIRST_DRAW)
    assert row["delta_code_exact"] == "02-06-09-09-20"
    assert row["delta_code_bucket"] == "SMMML"
    assert pd.isna(row["shuffle_code_exact"])
    assert pd.isna(row["shuffle_code_direction"])
    assert pd.isna(row["shuffle_code_magnitude"])
    assert pd.isna(row["shuffle_code_delta_exact"])


def test_shuffle_code_null_iff_no_predecessor(df):
    """Null tracks 'no prior draw', not 'no movement' -- these must coincide
    exactly with has_prev, not merely correlate with it."""
    assert (df["shuffle_code_exact"].isna() == ~df["has_prev"]).all()


# ------------------------------------------------ round-trip across all ----


def test_delta_code_round_trips_across_archive(df):
    """Every stored code must decode back to the deltas it was built from."""
    deltas = df[DELTA_COLS].to_numpy().tolist()
    for code, original in zip(df["delta_code_exact"], deltas):
        assert decode_delta_code_exact(code) == list(original)


def test_shuffle_code_round_trips_across_archive(df):
    with_prev = df[df["has_prev"]]
    diffs = with_prev[NUM_DIFF_COLS].to_numpy().tolist()
    for code, original in zip(with_prev["shuffle_code_exact"], diffs):
        assert decode_shuffle_code_exact(code) == [int(x) for x in original]


def test_shuffle_code_delta_round_trips_across_archive(df):
    with_prev = df[df["has_prev"]]
    diffs = with_prev[DELTA_DIFF_COLS].to_numpy().tolist()
    for code, original in zip(with_prev["shuffle_code_delta_exact"], diffs):
        assert decode_shuffle_code_exact(code) == [int(x) for x in original]


def test_check_code_invariants_passes_on_real_pipeline_output(df):
    """The assertion that runs inside build_features must accept its own
    output -- otherwise every ingestion would be raising already."""
    check_code_invariants(df)  # must not raise


def test_check_code_invariants_catches_a_corrupted_exact_code():
    """If deltaCode.exact is tampered with, decoding no longer matches the
    deltas it claims to describe, and that must be fatal."""
    frame = pd.DataFrame(
        {
            "date": [FIRST_DRAW],
            "delta_code_exact": ["99-99-99-99-99"],
            **{c: [v] for c, v in zip(DELTA_COLS, [2, 6, 9, 9, 20])},
        }
    )
    with pytest.raises(ValidationError, match="does not round-trip"):
        check_code_invariants(_stub_code_cols(frame))


def _stub_code_cols(frame: pd.DataFrame) -> pd.DataFrame:
    """Fill in the remaining code columns check_code_invariants expects,
    so the deltaCode corruption above is the only thing under test."""
    frame = frame.copy()
    for col in NUM_DIFF_COLS + DELTA_DIFF_COLS:
        frame[col] = pd.array([pd.NA], dtype="Int64")
    for col in [
        "shuffle_code_exact",
        "shuffle_code_delta_exact",
        "shuffle_code_magnitude",
        "shuffle_code_delta_magnitude",
    ]:
        frame[col] = [None]
    return frame


# ---------------------------------------------------- code determinism ----


def test_codes_are_deterministic_given_same_input(df):
    """Recomputing must not depend on row order, index, or run-to-run state."""
    rerun = build_features(ingest(report=False))
    pd.testing.assert_series_equal(
        df["delta_code_exact"].reset_index(drop=True),
        rerun["delta_code_exact"].reset_index(drop=True),
    )
    pd.testing.assert_series_equal(
        df["shuffle_code_exact"].reset_index(drop=True),
        rerun["shuffle_code_exact"].reset_index(drop=True),
    )
