"""Emit the feature frame as JSON for the React app.

Four files land in `data/`:

  features.json    array of records, ascending by date -- what the app reads
  features.jsonl   one record per line -- streams, and diffs one draw per line
  schema.json      JSON Schema for a single record
  summary.json     counts, date range, parameters, code frequency tables

Every file carries the config fingerprint. Two files with different
fingerprints were produced by different parameters and must not be compared
row-for-row.

Null discipline: a missing value is `null`, never `0`, `""`, or `NaN`. The first
retained draw has no predecessor, so its inter-draw fields are genuinely absent
-- "did not move" and "there was nothing to move from" are different facts and
the JSON must not conflate them.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from .config import DEFAULT, Config
from .features import DELTA_COLS, DELTA_DIFF_COLS, build_features
from .validate import NUM_COLS

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# The React app (Phase 5) lives in web/ and is served by Vite, which will not
# import from outside its own project root. Rather than relaxing Vite's
# filesystem rules or adding a build-time copy step, emission writes a second
# copy here and the app fetches it as an ordinary static asset. data/ at the
# repo root stays canonical and committed.
WEB_DATA_DIR = Path(__file__).resolve().parents[1] / "web" / "public" / "data"

FLOAT_PLACES = 2


# ===========================================================================
# Record construction
# ===========================================================================


def _clean(value):
    """pandas NA/NaN -> None, numpy scalars -> plain Python.

    json.dump cannot serialise pd.NA or numpy int64, and NaN would emit the
    literal `NaN`, which is not valid JSON and which JavaScript's JSON.parse
    rejects outright.
    """
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _int_list(row, cols) -> list[int] | None:
    """A list of ints, or None if any element is absent.

    All-or-nothing by design: a partially-null delta vector would be a bug, and
    silently emitting five values with a hole in the middle would hide it.
    """
    values = [_clean(row[c]) for c in cols]
    if any(v is None for v in values):
        return None
    return [int(v) for v in values]


def _round(value) -> float | None:
    value = _clean(value)
    return None if value is None else round(float(value), FLOAT_PLACES)


def to_record(row: pd.Series) -> dict:
    """One draw as the nested record described in PROJECT.md.

    Field order is fixed by this literal, so `git diff` on data/ stays readable
    across regenerations.
    """
    draw_id = row["date"].date().isoformat()
    delta_diff = _int_list(row, DELTA_DIFF_COLS)
    has_prev = bool(row["has_prev"])

    shuffle = (
        {
            "exact": _clean(row["shuffle_code_exact"]),
            "direction": _clean(row["shuffle_code_direction"]),
            "magnitude": _clean(row["shuffle_code_magnitude"]),
        }
        if has_prev
        else None
    )

    shuffle_delta = (
        {
            "exact": _clean(row["shuffle_code_delta_exact"]),
            "direction": _clean(row["shuffle_code_delta_direction"]),
            "magnitude": _clean(row["shuffle_code_delta_magnitude"]),
        }
        if has_prev
        else None
    )

    return {
        "drawId": draw_id,
        "date": draw_id,
        "year": int(row["year"]),
        "month": int(row["month"]),
        "day": int(row["day"]),
        "dayOfWeek": row["day_of_week"],
        "drawOrder": [int(b) for b in row["draw_order"]],
        "numbers": [int(row[c]) for c in NUM_COLS],
        "deltas": [int(row[c]) for c in DELTA_COLS],
        "deltaSum": int(row["delta_sum"]),
        "deltaDiffPrev": delta_diff,
        "deltaSumAvg3": _round(row["delta_sum_avg3"]),
        "deltaCode": {
            "exact": row["delta_code_exact"],
            "bucket": row["delta_code_bucket"],
            "shape": row["delta_code_shape"],
        },
        "shuffleCode": shuffle,
        "shuffleCodeDelta": shuffle_delta,
        "prevDrawId": _clean(row["prev_draw_id"]),
        "prevGapDays": _clean(row["prev_gap_days"]),
        "flags": {
            "hasPrev": has_prev,
            "unusualGap": bool(row["unusual_gap"]),
        },
    }


def to_records(df: pd.DataFrame) -> list[dict]:
    return [to_record(row) for _, row in df.iterrows()]


# ===========================================================================
# Summary
# ===========================================================================


def _frequency_table(values, top: int = 25) -> dict:
    """Observed counts against a uniform baseline.

    The baseline is deliberately included with every table. A raw count is not
    a finding -- "code X appeared 14 times" means nothing without "chance
    predicts ~9.8". See CLAUDE.md.

    Note the baseline here is uniform-over-observed-codes, which is a crude
    null: delta codes are not uniformly likely a priori. It is a floor for
    interpretation, not a hypothesis test. Phase 6 does the real work.
    """
    counts = Counter(v for v in values if v is not None)
    distinct = len(counts)
    total = sum(counts.values())
    uniform = total / distinct if distinct else 0.0
    return {
        "distinctCodes": distinct,
        "totalCoded": total,
        "uniformBaselinePerCode": round(uniform, FLOAT_PLACES),
        "top": [
            {
                "code": code,
                "count": count,
                "vsUniform": round(count / uniform, FLOAT_PLACES) if uniform else None,
            }
            for code, count in counts.most_common(top)
        ],
    }


def build_summary(df: pd.DataFrame, config: Config) -> dict:
    findings = df.attrs.get("findings", [])
    return {
        "generatedUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "configFingerprint": config.fingerprint,
        "parameters": config.to_dict(),
        "drawCount": int(len(df)),
        "dateRange": {
            "first": df["date"].min().date().isoformat(),
            "last": df["date"].max().date().isoformat(),
        },
        "weekdayCounts": {
            k: int(v) for k, v in df["day_of_week"].value_counts().sort_index().items()
        },
        "unusualGapCount": int(df["unusual_gap"].sum()),
        "findings": [str(f) for f in findings],
        "deltaSum": {
            "min": int(df["delta_sum"].min()),
            "max": int(df["delta_sum"].max()),
            "mean": round(float(df["delta_sum"].mean()), FLOAT_PLACES),
        },
        "codeFrequencies": {
            "deltaCodeExact": _frequency_table(df["delta_code_exact"]),
            "deltaCodeBucket": _frequency_table(df["delta_code_bucket"]),
            "deltaCodeShape": _frequency_table(df["delta_code_shape"]),
            "shuffleCodeDirection": _frequency_table(df["shuffle_code_direction"]),
        },
    }


# ===========================================================================
# Schema
# ===========================================================================


def build_schema(config: Config) -> dict:
    """JSON Schema (draft-07) for one record.

    Nullable inter-draw fields are typed `["object", "null"]` rather than left
    loose, so a consumer that forgets to handle the first draw fails validation
    instead of rendering `undefined`.
    """
    code_obj = {
        "type": "object",
        "required": ["exact", "direction", "magnitude"],
        "properties": {
            "exact": {"type": "string"},
            "direction": {"type": "string"},
            "magnitude": {"type": "integer", "minimum": 0},
        },
    }
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Lotto Texas draw feature record",
        "description": (
            f"Generated with config {config.fingerprint}: {config.describe()}. "
            "Descriptive features only -- this file contains no predictions."
        ),
        "type": "object",
        "required": [
            "drawId", "date", "numbers", "deltas", "deltaSum", "deltaCode", "flags",
        ],
        "additionalProperties": False,
        "properties": {
            "drawId": {"type": "string", "format": "date"},
            "date": {"type": "string", "format": "date"},
            "year": {"type": "integer"},
            "month": {"type": "integer", "minimum": 1, "maximum": 12},
            "day": {"type": "integer", "minimum": 1, "maximum": 31},
            "dayOfWeek": {"type": "string"},
            "drawOrder": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 54},
                "minItems": 6, "maxItems": 6,
            },
            "numbers": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 54},
                "minItems": 6, "maxItems": 6,
            },
            "deltas": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "minItems": 5, "maxItems": 5,
            },
            "deltaSum": {"type": "integer", "minimum": 5},
            "deltaDiffPrev": {
                "type": ["array", "null"],
                "items": {"type": "integer"},
                "minItems": 5, "maxItems": 5,
            },
            "deltaSumAvg3": {"type": ["number", "null"]},
            "deltaCode": {
                "type": "object",
                "required": ["exact", "bucket", "shape"],
                "properties": {
                    "exact": {"type": "string"},
                    "bucket": {"type": "string", "pattern": "^[SML]{5}$"},
                    "shape": {"type": "string"},
                },
            },
            "shuffleCode": {"oneOf": [code_obj, {"type": "null"}]},
            "shuffleCodeDelta": {"oneOf": [code_obj, {"type": "null"}]},
            "prevDrawId": {"type": ["string", "null"]},
            "prevGapDays": {"type": ["integer", "null"]},
            "flags": {
                "type": "object",
                "required": ["hasPrev", "unusualGap"],
                "properties": {
                    "hasPrev": {"type": "boolean"},
                    "unusualGap": {"type": "boolean"},
                },
            },
        },
    }


# ===========================================================================
# Writing
# ===========================================================================


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False turns a stray NaN into a loud error rather than emitting
    # invalid JSON that only fails later, in the browser.
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_all(records: list[dict], summary: dict, schema: dict, out_dir: Path) -> None:
    _write_json(out_dir / "features.json", records)

    jsonl = out_dir / "features.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    jsonl.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, allow_nan=False) for r in records)
        + "\n",
        encoding="utf-8",
    )

    _write_json(out_dir / "schema.json", schema)
    _write_json(out_dir / "summary.json", summary)


def emit(
    df: pd.DataFrame | None = None,
    *,
    config: Config = DEFAULT,
    out_dir: Path | str = DATA_DIR,
    also_web: bool = False,
) -> dict:
    """Build every output file. Returns a manifest of what was written.

    `also_web=True` writes an identical copy into web/public/data/ for the Vite
    app to fetch. Same bytes, two locations -- the copy is a serving detail, not
    a second source of truth.
    """
    if df is None:
        from .ingest import ingest

        df = build_features(ingest(config=config, report=False), config=config)

    config = df.attrs.get("config", config)
    out_dir = Path(out_dir)
    records = to_records(df)
    summary = build_summary(df, config)
    schema = build_schema(config)

    written = [str(out_dir)]
    _write_all(records, summary, schema, out_dir)

    if also_web:
        _write_all(records, summary, schema, WEB_DATA_DIR)
        written.append(str(WEB_DATA_DIR))

    return {
        "records": len(records),
        "outDir": str(out_dir),
        "writtenTo": written,
        "fingerprint": config.fingerprint,
        "files": ["features.json", "features.jsonl", "schema.json", "summary.json"],
    }


if __name__ == "__main__":
    import sys

    # `python -m src.emit --web` also refreshes the copy the React app serves.
    result = emit(also_web="--web" in sys.argv)
    print(f"Wrote {result['records']} records")
    print(f"Config fingerprint: {result['fingerprint']}")
    for location in result["writtenTo"]:
        print(f"\n  {location}")
        for name in result["files"]:
            path = Path(location) / name
            print(f"    {name:18} {path.stat().st_size:>10,} bytes")
