"""Pipeline parameters, in one place.

These were constants scattered across modules. They are choices, not facts:
the bucket thresholds, the averaging window, and the scope cutoff all change
what the features mean. Sweeping them is a legitimate thing to want to do --
"does a 5-draw average separate the data better than a 3-draw one?" -- so they
live here, get threaded through the pipeline, and get stamped into every
emitted file.

Every output carries `fingerprint`. Two files with different fingerprints were
built by different parameters and must not be compared row-for-row.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Config:
    """Immutable so a config cannot drift mid-run."""

    # --- scope -------------------------------------------------------------
    # First draw of the current uninterrupted 6/54 regime. Moving this earlier
    # pulls in the 5/44 + bonus-ball era and WILL fail the distinct-ball
    # invariant -- that is the intended behaviour, not a bug. See MEMORY.md.
    scope_start: dt.date = dt.date(2006, 4, 26)

    # Floor, not a target. The archive grows Mon/Wed/Sat.
    min_rows: int | None = 2370

    # --- F4 ----------------------------------------------------------------
    # "Average of the delta sums of the previous N drawings."
    avg_window: int = 3

    # --- F5 bucket thresholds ---------------------------------------------
    # S <= small_max < M <= medium_max < L. Defaults checked against the
    # observed delta distribution: 29.9% / 39.0% / 31.0%, close to equal
    # thirds. Changing these changes the meaning of every stored bucket code.
    bucket_small_max: int = 3
    bucket_medium_max: int = 9

    def __post_init__(self) -> None:
        if self.avg_window < 1:
            raise ValueError(f"avg_window must be >= 1, got {self.avg_window}")
        if self.bucket_small_max < 1:
            raise ValueError("bucket_small_max must be >= 1")
        if self.bucket_medium_max <= self.bucket_small_max:
            raise ValueError(
                f"bucket_medium_max ({self.bucket_medium_max}) must exceed "
                f"bucket_small_max ({self.bucket_small_max}) -- otherwise the "
                "M class is empty and the code space silently collapses."
            )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scope_start"] = self.scope_start.isoformat()
        return d

    @property
    def fingerprint(self) -> str:
        """Short stable hash of the parameter set.

        Stamped into every emitted file so a JSON can always be traced back to
        the parameters that produced it.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    def describe(self) -> str:
        return (
            f"scope>={self.scope_start}  avg_window={self.avg_window}  "
            f"buckets=S<={self.bucket_small_max}<M<={self.bucket_medium_max}<L  "
            f"[{self.fingerprint}]"
        )


DEFAULT = Config()
