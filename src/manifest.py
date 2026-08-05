"""Append-only integrity tracking across repeated ingestions.

The archive grows three times a week (Mon/Wed/Sat), by manual entry. New draws
are appended; history must never change. If a past draw comes back different on
a later ingestion, that is a data incident, not a routine update -- every
feature derived from that draw and its successor is silently wrong.

This module records a digest of the retained history after each ingestion and
verifies on the next run that the previously-seen portion is byte-identical.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pandas as pd

from .validate import NUM_COLS, ValidationError

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "data" / "manifest.json"


def digest_rows(df: pd.DataFrame) -> str:
    """Deterministic SHA-256 over date + sorted balls.

    Canonical form is one line per draw: `YYYY-MM-DD:n1,n2,n3,n4,n5,n6`.
    Deliberately excludes draw order and every derived feature, so the digest
    tracks the source data only and does not churn when feature logic changes.
    """
    lines = [
        f"{d.date().isoformat()}:" + ",".join(str(int(v)) for v in row)
        for d, row in zip(df["date"], df[NUM_COLS].to_numpy())
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def read_manifest(path: Path | str = DEFAULT_MANIFEST) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(df: pd.DataFrame, path: Path | str = DEFAULT_MANIFEST) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "lastIngestUtc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rowCount": int(len(df)),
        "firstDate": df["date"].min().date().isoformat(),
        "lastDate": df["date"].max().date().isoformat(),
        "historyDigest": digest_rows(df),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def check_append_only(df: pd.DataFrame, manifest: dict) -> dict:
    """Verify the archive only grew since the last ingestion.

    Returns a summary of what changed. Raises ValidationError if history moved.
    """
    prev_last = pd.Timestamp(manifest["lastDate"])
    prev_count = int(manifest["rowCount"])

    if df["date"].max() < prev_last:
        raise ValidationError(
            f"Archive went backwards: last draw is {df['date'].max().date()}, "
            f"but the previous ingestion saw {prev_last.date()}. The source file "
            "may have been replaced with an older copy."
        )

    history = df[df["date"] <= prev_last]

    if len(history) != prev_count:
        raise ValidationError(
            f"History changed size: {prev_count} draws up to {prev_last.date()} "
            f"previously, {len(history)} now. Draws were inserted or removed from "
            "the past. Do not proceed -- reconcile against the source."
        )

    current = digest_rows(history)
    if current != manifest["historyDigest"]:
        raise ValidationError(
            "History digest mismatch. The same date range now yields different "
            "numbers than the previous ingestion, meaning a past draw was "
            f"revised upstream.\n  expected {manifest['historyDigest'][:16]}...\n"
            f"  got      {current[:16]}...\n"
            "Every feature derived from the changed draw and the draw after it "
            "is invalid. Reconcile before regenerating data/."
        )

    new_rows = df[df["date"] > prev_last]
    return {
        "newDraws": int(len(new_rows)),
        "newDates": [d.date().isoformat() for d in new_rows["date"]],
        "previousLastDate": prev_last.date().isoformat(),
        "currentLastDate": df["date"].max().date().isoformat(),
    }


def verify_and_update(
    df: pd.DataFrame, path: Path | str = DEFAULT_MANIFEST
) -> dict:
    """Check append-only integrity, then record the new state.

    On first run there is nothing to compare against, so it just records.
    """
    manifest = read_manifest(path)
    if manifest is None:
        write_manifest(df, path)
        return {"firstRun": True, "rowCount": int(len(df))}

    summary = check_append_only(df, manifest)
    write_manifest(df, path)
    return summary
