"""Phase 4 tests: JSON emission and config parameterisation.

The React app reads these files directly, so the contract under test is the
serialised output, not the DataFrame behind it.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.config import Config
from src.emit import build_schema, build_summary, emit, to_record, to_records
from src.features import build_features
from src.ingest import ingest

REFERENCE = "2026-07-22"
FIRST_DRAW = "2006-04-26"


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return build_features(ingest(report=False))


@pytest.fixture(scope="module")
def records(df) -> list[dict]:
    return to_records(df)


def _by_id(records: list[dict], draw_id: str) -> dict:
    return next(r for r in records if r["drawId"] == draw_id)


# ------------------------------------------------------- record shape ----


def test_record_count_matches_frame(df, records):
    assert len(records) == len(df)


def test_records_ascending_by_date(records):
    dates = [r["date"] for r in records]
    assert dates == sorted(dates)


def test_golden_record(records):
    """The reference draw, end to end through serialisation."""
    r = _by_id(records, REFERENCE)
    assert r["numbers"] == [14, 33, 35, 44, 53, 54]
    assert r["drawOrder"] == [14, 33, 54, 53, 44, 35]
    assert r["deltas"] == [19, 2, 9, 9, 1]
    assert r["deltaSum"] == 40
    assert r["deltaDiffPrev"] == [12, 0, 3, -5, -9]
    assert r["deltaSumAvg3"] == 40.33
    assert r["deltaCode"] == {
        "exact": "19-02-09-09-01",
        "bucket": "LSMMS",
        "shape": "01-02-09-09-19",
    }
    assert r["shuffleCode"] == {
        "exact": "U02.U14.U14.U17.U12.U03",
        "direction": "UUUUUU",
        "magnitude": 62,
    }
    assert r["shuffleCodeDelta"] == {
        "exact": "U12.S00.U03.D05.D09",
        "direction": "USUDD",
        "magnitude": 29,
    }
    assert r["prevDrawId"] == "2026-07-20"
    assert r["prevGapDays"] == 2
    assert r["flags"] == {"hasPrev": True, "unusualGap": False}


# ------------------------------------------------------ null discipline ----


def test_first_draw_inter_draw_fields_are_null(records):
    """Absent, not zero. 'Did not move' and 'nothing to move from' differ."""
    r = _by_id(records, FIRST_DRAW)
    assert r["deltaDiffPrev"] is None
    assert r["deltaSumAvg3"] is None
    assert r["shuffleCode"] is None
    assert r["shuffleCodeDelta"] is None
    assert r["prevDrawId"] is None
    assert r["prevGapDays"] is None
    assert r["flags"]["hasPrev"] is False


def test_first_draw_intra_draw_fields_are_present(records):
    """deltaCode needs no predecessor, so it must still be populated."""
    r = _by_id(records, FIRST_DRAW)
    assert r["deltas"] == [2, 6, 9, 9, 20]
    assert r["deltaSum"] == 46
    assert r["deltaCode"]["exact"] == "02-06-09-09-20"


def test_exactly_one_record_lacks_a_predecessor(records):
    assert sum(1 for r in records if not r["flags"]["hasPrev"]) == 1


def test_no_nan_leaks_into_json(records):
    """NaN is not valid JSON -- JSON.parse rejects it outright."""
    text = json.dumps(records, allow_nan=False)  # raises if any NaN survived
    assert "NaN" not in text
    assert "Infinity" not in text


def test_nulls_are_none_not_strings(records):
    for r in records:
        assert r["deltaSumAvg3"] is None or isinstance(r["deltaSumAvg3"], float)
        assert r["shuffleCode"] is None or isinstance(r["shuffleCode"], dict)


# ------------------------------------------------------------- typing ----


def test_integers_are_ints_not_floats(records):
    """-5, not -5.0. Int64 columns must not serialise as floats."""
    for r in records:
        assert all(isinstance(v, int) for v in r["numbers"])
        assert all(isinstance(v, int) for v in r["deltas"])
        assert isinstance(r["deltaSum"], int)
        if r["deltaDiffPrev"] is not None:
            assert all(isinstance(v, int) for v in r["deltaDiffPrev"])
        if r["shuffleCode"] is not None:
            assert isinstance(r["shuffleCode"]["magnitude"], int)


def test_floats_rounded_to_two_places(records):
    for r in records:
        if r["deltaSumAvg3"] is not None:
            assert r["deltaSumAvg3"] == round(r["deltaSumAvg3"], 2)


def test_field_order_is_stable(records):
    """Keeps git diffs on data/ readable across regenerations."""
    keys = list(records[0].keys())
    assert all(list(r.keys()) == keys for r in records)
    assert keys[0] == "drawId"


# -------------------------------------------------------------- files ----


def test_emit_writes_all_four_files(df):
    with tempfile.TemporaryDirectory() as tmp:
        result = emit(df, out_dir=tmp)
        for name in ["features.json", "features.jsonl", "schema.json", "summary.json"]:
            assert (Path(tmp) / name).exists(), name
        assert result["records"] == len(df)


def test_jsonl_matches_json_exactly(df):
    with tempfile.TemporaryDirectory() as tmp:
        emit(df, out_dir=tmp)
        array = json.loads((Path(tmp) / "features.json").read_text(encoding="utf-8"))
        lines = [
            json.loads(line)
            for line in (Path(tmp) / "features.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert lines == array


def test_emitted_json_is_strict_parseable(df):
    with tempfile.TemporaryDirectory() as tmp:
        emit(df, out_dir=tmp)
        text = (Path(tmp) / "features.json").read_text(encoding="utf-8")
        json.loads(text)  # raises on NaN / trailing commas / bad escapes


# ------------------------------------------------------------- schema ----


def test_every_record_validates_against_emitted_schema(df, records):
    jsonschema = pytest.importorskip("jsonschema")
    schema = build_schema(df.attrs["config"])
    validator = jsonschema.Draft7Validator(schema)
    errors = [
        (r["drawId"], e.message) for r in records for e in validator.iter_errors(r)
    ]
    assert errors == []


def test_schema_allows_null_shuffle_code(df):
    jsonschema = pytest.importorskip("jsonschema")
    schema = build_schema(df.attrs["config"])
    first = _by_id(to_records(df), FIRST_DRAW)
    jsonschema.Draft7Validator(schema).validate(first)


def test_schema_rejects_a_malformed_bucket_code(df):
    jsonschema = pytest.importorskip("jsonschema")
    schema = build_schema(df.attrs["config"])
    bad = _by_id(to_records(df), REFERENCE)
    bad["deltaCode"] = {**bad["deltaCode"], "bucket": "XXXXX"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft7Validator(schema).validate(bad)


# ------------------------------------------------------------ summary ----


def test_summary_reports_counts_and_range(df):
    s = build_summary(df, df.attrs["config"])
    assert s["drawCount"] == len(df)
    assert s["dateRange"]["first"] == FIRST_DRAW
    assert s["configFingerprint"] == df.attrs["config"].fingerprint


def test_summary_frequency_tables_include_a_baseline(df):
    """A count without a baseline is not a finding -- see CLAUDE.md."""
    s = build_summary(df, df.attrs["config"])
    for name, table in s["codeFrequencies"].items():
        assert "uniformBaselinePerCode" in table, name
        assert table["distinctCodes"] > 0
        for entry in table["top"]:
            assert "vsUniform" in entry


def test_bucket_codespace_is_smaller_than_exact(df):
    """Bucketing exists to make recurrence observable at all."""
    s = build_summary(df, df.attrs["config"])
    exact = s["codeFrequencies"]["deltaCodeExact"]["distinctCodes"]
    bucket = s["codeFrequencies"]["deltaCodeBucket"]["distinctCodes"]
    assert bucket < exact
    assert bucket <= 243


# -------------------------------------------------------------- config ----


def test_config_fingerprint_changes_with_parameters():
    assert Config().fingerprint != Config(avg_window=5).fingerprint
    assert Config().fingerprint != Config(bucket_small_max=4).fingerprint


def test_config_fingerprint_is_stable_across_instances():
    assert Config().fingerprint == Config().fingerprint


def test_avg_window_actually_changes_the_feature():
    """Proves the parameter is threaded through, not merely accepted."""
    base = build_features(ingest(report=False), config=Config())
    wide = build_features(ingest(report=False), config=Config(avg_window=5))
    assert not base["delta_sum_avg3"].equals(wide["delta_sum_avg3"])
    # A wider window needs more history before it can produce a value.
    assert wide["delta_sum_avg3"].head(5).isna().all()


def test_bucket_thresholds_actually_change_the_codes():
    base = build_features(ingest(report=False), config=Config())
    coarse = build_features(
        ingest(report=False), config=Config(bucket_small_max=5, bucket_medium_max=15)
    )
    assert not base["delta_code_bucket"].equals(coarse["delta_code_bucket"])


def test_config_rejects_inverted_bucket_thresholds():
    """An empty M class would silently collapse the code space."""
    with pytest.raises(ValueError, match="must exceed"):
        Config(bucket_small_max=9, bucket_medium_max=3)


def test_config_rejects_nonsense_window():
    with pytest.raises(ValueError, match="avg_window"):
        Config(avg_window=0)


def test_emitted_files_carry_the_fingerprint(df):
    with tempfile.TemporaryDirectory() as tmp:
        emit(df, out_dir=tmp)
        summary = json.loads((Path(tmp) / "summary.json").read_text(encoding="utf-8"))
        schema = json.loads((Path(tmp) / "schema.json").read_text(encoding="utf-8"))
        fp = df.attrs["config"].fingerprint
        assert summary["configFingerprint"] == fp
        assert fp in schema["description"]


def test_scope_start_is_configurable_and_enforced():
    """A later cutoff must actually drop the earlier draws."""
    later = ingest(config=Config(scope_start=dt.date(2020, 1, 1), min_rows=None),
                   report=False)
    assert later["date"].min().date() >= dt.date(2020, 1, 1)
    assert len(later) < len(ingest(report=False))
