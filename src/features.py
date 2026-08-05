"""Feature computation: F1-F6.

Pure functions. DataFrame in, DataFrame out, no hidden state. Each takes the
output of `ingest()` (or of an earlier feature step) and returns a new frame.

The deltas are the subject of this project, not an intermediate. They are
POSITIONAL: d1 is the gap between the two lowest balls, d5 between the two
highest. They are never sorted, never canonicalised, never reordered. Sorting
them would collapse exactly the structure we are looking for -- see CLAUDE.md.

Ball numbers are sorted ascending upstream in `ingest.sort_balls`. That is the
one sort in this project.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DEFAULT, Config
from .encode import (
    decode_delta_code_exact,
    decode_shuffle_code_exact,
    delta_code_bucket,
    delta_code_exact,
    delta_code_shape,
    shuffle_code_direction,
    shuffle_code_exact,
    shuffle_code_magnitude,
)
from .validate import DELTAS_PER_DRAW, NUM_COLS, ValidationError

DELTA_COLS = [f"d{i}" for i in range(1, DELTAS_PER_DRAW + 1)]
DELTA_DIFF_COLS = [f"dd{i}" for i in range(1, DELTAS_PER_DRAW + 1)]
NUM_DIFF_COLS = [f"nd{i}" for i in range(1, len(NUM_COLS) + 1)]

AVG_WINDOW = 3


# ===========================================================================
# F1 -- deltas
# ===========================================================================


def compute_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Five positional gaps between six ascending balls.

        d[i] = n[i+1] - n[i]

    np.diff preserves position by construction. Do not replace it with anything
    that sorts, and do not "tidy" the result into a sorted multiset.
    """
    df = df.copy()
    gaps = np.diff(df[NUM_COLS].to_numpy(), axis=1)
    if gaps.shape[1] != DELTAS_PER_DRAW:
        raise ValidationError(
            f"Expected {DELTAS_PER_DRAW} deltas per draw, got {gaps.shape[1]}."
        )
    df[DELTA_COLS] = gaps
    return df


# ===========================================================================
# F2 -- deltaSum
# ===========================================================================


def compute_delta_sum(df: pd.DataFrame) -> pd.DataFrame:
    """Total spread of the draw. Telescopes to n6 - n1."""
    df = df.copy()
    df["delta_sum"] = df[DELTA_COLS].sum(axis=1)
    return df


# ===========================================================================
# F3 -- deltaDiffPrev
# ===========================================================================


def compute_delta_diff_prev(df: pd.DataFrame) -> pd.DataFrame:
    """Signed, positional change in each gap versus the previous draw.

        dd[i] = d[i](t) - d[i](t-1)

    Null for the first retained draw. `shift(1)` cannot reach past row 0, and
    row 0 is 2006-04-26 because ingest already dropped everything earlier, so
    the cutoff is respected structurally rather than by a special case.

    Int64 (nullable) rather than float: these are counts of balls, and -5 should
    not render as -5.0 in the JSON the React app reads.
    """
    df = df.copy()
    diffs = df[DELTA_COLS].astype("Int64") - df[DELTA_COLS].astype("Int64").shift(1)
    df[DELTA_DIFF_COLS] = diffs.to_numpy()
    df[DELTA_DIFF_COLS] = df[DELTA_DIFF_COLS].astype("Int64")

    df["prev_draw_id"] = df["date"].shift(1).dt.strftime("%Y-%m-%d")
    df["prev_gap_days"] = df["date"].diff().dt.days.astype("Int64")
    df["has_prev"] = df["prev_draw_id"].notna()
    return df


def compute_num_diff_prev(df: pd.DataFrame) -> pd.DataFrame:
    """Positional movement of each ball versus the previous draw.

        nd[i] = n[i](t) - n[i](t-1)      six signed values

    This is number space, not gap space: how far the i-th smallest ball moved.
    It is the input to shuffleCode. Null for the first retained draw.
    """
    df = df.copy()
    nums = df[NUM_COLS].astype("Int64")
    df[NUM_DIFF_COLS] = (nums - nums.shift(1)).to_numpy()
    df[NUM_DIFF_COLS] = df[NUM_DIFF_COLS].astype("Int64")
    return df


# ===========================================================================
# F4 -- deltaSumAvg3
# ===========================================================================


def compute_delta_sum_avg3(df: pd.DataFrame, window: int = AVG_WINDOW) -> pd.DataFrame:
    """Mean deltaSum of the previous `window` draws, excluding the current one.

    shift(1) first, then roll: rolling(N) alone would include the current draw
    and make the feature partly self-referential. Null until `window` prior
    retained draws exist.

    The column name keeps the `avg3` suffix regardless of window size -- it is
    the field name in the emitted schema. The window actually used is recorded
    in the config fingerprint on every output file.
    """
    df = df.copy()
    df["delta_sum_avg3"] = (
        df["delta_sum"].shift(1).rolling(window=window, min_periods=window).mean()
    )
    return df


# ===========================================================================
# Invariants
# ===========================================================================


def check_delta_invariants(df: pd.DataFrame) -> None:
    """Physical facts about deltas. Violations mean the computation is wrong.

    Asserted in the pipeline, not only in tests, per CLAUDE.md.
    """
    deltas = df[DELTA_COLS].to_numpy()

    if (deltas < 1).any():
        bad = df[(df[DELTA_COLS] < 1).any(axis=1)]
        raise ValidationError(
            f"{len(bad)} draw(s) have a delta below 1. Distinct ascending balls "
            "cannot produce a gap of 0 -- the input has duplicate balls or the "
            "sort did not run.\n\n"
            f"{bad[['date', *NUM_COLS, *DELTA_COLS]].head().to_string()}"
        )

    telescoped = df[NUM_COLS[-1]] - df[NUM_COLS[0]]
    mismatch = df[df["delta_sum"] != telescoped]
    if not mismatch.empty:
        raise ValidationError(
            f"{len(mismatch)} draw(s) where deltaSum != n6 - n1. The deltas do "
            "not span the draw, meaning positions were lost or reordered.\n\n"
            f"{mismatch[['date', *DELTA_COLS, 'delta_sum']].head().to_string()}"
        )

    if "dd1" in df.columns:
        first = df.iloc[0]
        if first[DELTA_DIFF_COLS].notna().any():
            raise ValidationError(
                f"First retained draw ({first['date'].date()}) has a non-null "
                "deltaDiffPrev. It must have no predecessor -- the draw before "
                "it is in the excluded bonus-ball era."
            )


def check_code_invariants(df: pd.DataFrame) -> None:
    """Codes must round-trip back to the values they encode.

    A code is a record of the deltas, not a summary of them. If decoding does
    not reproduce the original positions and magnitudes exactly, the encoding
    has lost or reordered information and every grouping built on it is
    untrustworthy. Checked across the whole archive, not sampled.
    """
    deltas = df[DELTA_COLS].to_numpy().tolist()
    for i, (code, original) in enumerate(zip(df["delta_code_exact"], deltas)):
        if decode_delta_code_exact(code) != list(original):
            raise ValidationError(
                f"deltaCode.exact does not round-trip at row {i} "
                f"({df.iloc[i]['date'].date()}): {code!r} -> "
                f"{decode_delta_code_exact(code)}, expected {list(original)}."
            )

    pairs = [
        ("shuffle_code_exact", NUM_DIFF_COLS),
        ("shuffle_code_delta_exact", DELTA_DIFF_COLS),
    ]
    for col, source in pairs:
        values = df[source].to_numpy(na_value=None).tolist()
        for i, (code, original) in enumerate(zip(df[col], values)):
            if code is None:
                if any(v is not None for v in original):
                    raise ValidationError(
                        f"{col} is null at row {i} but its inputs are not."
                    )
                continue
            if decode_shuffle_code_exact(code) != list(original):
                raise ValidationError(
                    f"{col} does not round-trip at row {i} "
                    f"({df.iloc[i]['date'].date()}): {code!r} -> "
                    f"{decode_shuffle_code_exact(code)}, expected {list(original)}."
                )

    # Magnitude must equal total absolute travel, independently recomputed.
    for col, source in [
        ("shuffle_code_magnitude", NUM_DIFF_COLS),
        ("shuffle_code_delta_magnitude", DELTA_DIFF_COLS),
    ]:
        expected = df[source].abs().sum(axis=1, skipna=False).astype("Int64")
        mismatch = df[col].notna() & (df[col] != expected)
        if mismatch.any():
            raise ValidationError(
                f"{col} disagrees with the sum of absolute movement on "
                f"{int(mismatch.sum())} row(s)."
            )


# ===========================================================================
# Pipeline
# ===========================================================================


def compute_codes(df: pd.DataFrame, config: Config = DEFAULT) -> pd.DataFrame:
    """F5 and F6. Encoders are applied row-wise over plain lists.

    Row-wise rather than vectorised on purpose: these produce strings, the
    archive is a few thousand rows, and legibility matters more here than
    microseconds. Someone should be able to read this against PROJECT.md.
    """
    df = df.copy()

    deltas = df[DELTA_COLS].to_numpy().tolist()
    df["delta_code_exact"] = [delta_code_exact(d) for d in deltas]
    df["delta_code_bucket"] = [
        delta_code_bucket(d, config.bucket_small_max, config.bucket_medium_max)
        for d in deltas
    ]
    df["delta_code_shape"] = [delta_code_shape(d) for d in deltas]

    df["shuffle_code_exact"] = _encode_or_none(df, NUM_DIFF_COLS, shuffle_code_exact)
    df["shuffle_code_direction"] = _encode_or_none(
        df, NUM_DIFF_COLS, shuffle_code_direction
    )
    df["shuffle_code_magnitude"] = pd.array(
        _encode_or_none(df, NUM_DIFF_COLS, shuffle_code_magnitude), dtype="Int64"
    )

    df["shuffle_code_delta_exact"] = _encode_or_none(
        df, DELTA_DIFF_COLS, shuffle_code_exact
    )
    df["shuffle_code_delta_direction"] = _encode_or_none(
        df, DELTA_DIFF_COLS, shuffle_code_direction
    )
    df["shuffle_code_delta_magnitude"] = pd.array(
        _encode_or_none(df, DELTA_DIFF_COLS, shuffle_code_magnitude), dtype="Int64"
    )
    return df


def _encode_or_none(df: pd.DataFrame, cols: list[str], fn) -> list:
    """Apply an encoder row-wise, yielding None where any input is null.

    The first retained draw has no predecessor, so every inter-draw code is
    None rather than a fabricated zero-movement code. A draw that did not move
    and a draw with nothing to move from are different facts.
    """
    out = []
    for values in df[cols].to_numpy(na_value=None).tolist():
        out.append(None if any(v is None for v in values) else fn(values))
    return out


def build_features(
    df: pd.DataFrame, *, config: Config = DEFAULT, validate: bool = True
) -> pd.DataFrame:
    """F1 -> F6 in order. Each step consumes the previous step's output.

    The config is attached to `.attrs` so downstream emission can stamp the
    parameters into the output without them being passed separately and
    drifting out of sync with the data they describe.
    """
    df = compute_deltas(df)
    df = compute_delta_sum(df)
    df = compute_delta_diff_prev(df)
    df = compute_num_diff_prev(df)
    df = compute_delta_sum_avg3(df, window=config.avg_window)
    df = compute_codes(df, config)
    if validate:
        check_delta_invariants(df)
        check_code_invariants(df)
    df.attrs["config"] = config
    return df


if __name__ == "__main__":
    from .ingest import ingest

    frame = build_features(ingest(report=False))
    numeric = ["date", *DELTA_COLS, "delta_sum", *DELTA_DIFF_COLS, "delta_sum_avg3"]
    codes = [
        "date",
        "delta_code_exact",
        "delta_code_bucket",
        "delta_code_shape",
        "shuffle_code_exact",
        "shuffle_code_direction",
        "shuffle_code_magnitude",
    ]
    print(f"Computed F1-F6 for {len(frame)} draws\n")
    print("Numeric features, first two and last two draws:")
    print(frame[numeric].head(2).to_string(index=False))
    print(frame[numeric].tail(2).to_string(index=False))
    print("\nCodes, first two and last two draws:")
    print(frame[codes].head(2).to_string(index=False))
    print(frame[codes].tail(2).to_string(index=False))
