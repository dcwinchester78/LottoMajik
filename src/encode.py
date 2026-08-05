"""Encoders: deltaCode (F5) and shuffleCode (F6).

Every function here takes plain lists of ints and returns a string, so encoders
can be tested without pandas or the archive -- see CLAUDE.md.

Two different questions, two different codes:

  deltaCode   describes ONE draw's own five gaps. Intra-draw. Groups draws whose
              internal spread pattern matches.
  shuffleCode describes the MOVEMENT between two consecutive number sets --
              direction and distance, position by position. Inter-draw.

They are never conflated. `shuffleCodeDelta` applies the shuffleCode encoding to
the delta-to-delta differences, so movement is observable in gap space as well
as number space.

Positional throughout. `delta_code_shape` is the single exception: it sorts a
COPY to build a multiset key, and exists only as a secondary grouping aid. It
never substitutes for the positional codes.
"""

from __future__ import annotations

from typing import Sequence

# --- bucket thresholds ------------------------------------------------------
# S <= 3 < M <= 9 < L. Set against the observed distribution of all 11,850
# deltas in the archive: this split yields 29.9% / 39.0% / 31.0%, close to
# equal thirds. Exact terciles (1-4 / 5-9 / 10+) give 37.9 / 31.0 / 31.0 --
# marginally more balanced, not enough to justify losing round boundaries.
# Deltas are discrete and lumpy, so no split is clean. Changing these changes
# the meaning of every stored bucket code: regenerate data/ if you touch them.
BUCKET_SMALL_MAX = 3
BUCKET_MEDIUM_MAX = 9

UP, DOWN, SAME = "U", "D", "S"


# ===========================================================================
# F5 -- deltaCode (intra-draw)
# ===========================================================================


def delta_code_exact(deltas: Sequence[int]) -> str:
    """Positional, zero-padded. `[19, 2, 9, 9, 1]` -> `'19-02-09-09-01'`.

    Zero padding keeps codes lexicographically sortable and fixed-width, so
    `'02'` and `'20'` never collide when parsed back apart.
    """
    return "-".join(f"{int(d):02d}" for d in deltas)


def bucket_of(delta: int) -> str:
    """Size class of a single gap."""
    if delta <= BUCKET_SMALL_MAX:
        return "S"
    if delta <= BUCKET_MEDIUM_MAX:
        return "M"
    return "L"


def delta_code_bucket(deltas: Sequence[int]) -> str:
    """Positional size classes. `[19, 2, 9, 9, 1]` -> `'LSMMS'`.

    Coarser than `exact`, so recurrence is observable: 3^5 = 243 possible codes
    against thousands of draws, versus tens of thousands of exact codes.
    """
    return "".join(bucket_of(int(d)) for d in deltas)


def delta_code_shape(deltas: Sequence[int]) -> str:
    """Sorted multiset key. `[19, 2, 9, 9, 1]` -> `'01-02-09-09-19'`.

    SECONDARY grouping key only. Answers "same set of gaps, different
    arrangement?" and nothing else. It sorts a copy; the caller's list is
    untouched and the positional codes above remain the primary keys.
    """
    return "-".join(f"{int(d):02d}" for d in sorted(deltas))


def delta_code(deltas: Sequence[int]) -> dict[str, str]:
    return {
        "exact": delta_code_exact(deltas),
        "bucket": delta_code_bucket(deltas),
        "shape": delta_code_shape(deltas),
    }


# ===========================================================================
# F6 -- shuffleCode (inter-draw)
# ===========================================================================


def direction_of(diff: int) -> str:
    if diff > 0:
        return UP
    if diff < 0:
        return DOWN
    return SAME


def shuffle_code_exact(diffs: Sequence[int]) -> str:
    """Direction and distance per position, dot-separated.

    `[2, 14, 14, 17, 12, 3]` -> `'U02.U14.U14.U17.U12.U03'`
    `[12, 0, 3, -5, -9]`     -> `'U12.S00.U03.D05.D09'`

    Magnitude is always the absolute value; the sign lives in the letter, so
    `D05` and `U05` share a magnitude and differ only in direction.
    """
    return ".".join(f"{direction_of(int(d))}{abs(int(d)):02d}" for d in diffs)


def shuffle_code_direction(diffs: Sequence[int]) -> str:
    """Sign pattern only. `[12, 0, 3, -5, -9]` -> `'USUDD'`."""
    return "".join(direction_of(int(d)) for d in diffs)


def shuffle_code_magnitude(diffs: Sequence[int]) -> int:
    """Total travel: sum of absolute movement across all positions."""
    return int(sum(abs(int(d)) for d in diffs))


def shuffle_code(diffs: Sequence[int] | None) -> dict | None:
    """None in, None out -- the first retained draw has no predecessor."""
    if diffs is None or any(d is None for d in diffs):
        return None
    return {
        "exact": shuffle_code_exact(diffs),
        "direction": shuffle_code_direction(diffs),
        "magnitude": shuffle_code_magnitude(diffs),
    }


# ===========================================================================
# Decoding -- codes must round-trip, or they are not faithful records
# ===========================================================================


def decode_delta_code_exact(code: str) -> list[int]:
    return [int(part) for part in code.split("-")]


def decode_shuffle_code_exact(code: str) -> list[int]:
    out = []
    for part in code.split("."):
        letter, magnitude = part[0], int(part[1:])
        out.append(0 if letter == SAME else magnitude * (1 if letter == UP else -1))
    return out
