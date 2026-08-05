"""Phase 3 tests: encoders, on plain lists.

No pandas and no archive here -- encoders are pure functions over sequences of
ints and are tested as such. Pipeline-level integration lives in
test_features.py.

Golden values are the worked examples in PROJECT.md for draw 2026-07-22.
"""

from __future__ import annotations

import itertools
import random

import pytest

from src.encode import (
    BUCKET_MEDIUM_MAX,
    BUCKET_SMALL_MAX,
    bucket_of,
    decode_delta_code_exact,
    decode_shuffle_code_exact,
    delta_code,
    delta_code_bucket,
    delta_code_exact,
    delta_code_shape,
    direction_of,
    shuffle_code,
    shuffle_code_direction,
    shuffle_code_exact,
    shuffle_code_magnitude,
)

# 2026-07-22: sorted balls [14, 33, 35, 44, 53, 54]
DELTAS = [19, 2, 9, 9, 1]
NUM_DIFFS = [2, 14, 14, 17, 12, 3]  # vs 2026-07-20 [12, 19, 21, 27, 41, 51]
DELTA_DIFFS = [12, 0, 3, -5, -9]  # vs 2026-07-20 deltas [7, 2, 6, 14, 10]


# ------------------------------------------------------- deltaCode (F5) ----


def test_delta_code_exact_golden():
    assert delta_code_exact(DELTAS) == "19-02-09-09-01"


def test_delta_code_bucket_golden():
    assert delta_code_bucket(DELTAS) == "LSMMS"


def test_delta_code_shape_golden():
    assert delta_code_shape(DELTAS) == "01-02-09-09-19"


def test_delta_code_returns_all_three():
    assert delta_code(DELTAS) == {
        "exact": "19-02-09-09-01",
        "bucket": "LSMMS",
        "shape": "01-02-09-09-19",
    }


def test_exact_is_positional_shape_is_not():
    """The distinction the whole project rests on.

    Two draws with the same gaps in a different arrangement share a shape but
    must NOT share an exact code -- position is the information.
    """
    a, b = [19, 2, 9, 9, 1], [1, 9, 9, 2, 19]
    assert delta_code_shape(a) == delta_code_shape(b)
    assert delta_code_exact(a) != delta_code_exact(b)


def test_shape_does_not_mutate_caller_list():
    """`shape` sorts a copy. If it sorts in place, deltas are destroyed."""
    deltas = [19, 2, 9, 9, 1]
    delta_code_shape(deltas)
    assert deltas == [19, 2, 9, 9, 1]


def test_all_encoders_leave_input_untouched():
    for fn in (delta_code_exact, delta_code_bucket, delta_code_shape):
        deltas = [19, 2, 9, 9, 1]
        fn(deltas)
        assert deltas == [19, 2, 9, 9, 1]


def test_zero_padding_prevents_collision():
    """Without padding, [2, 20] and [22, 0] could both render as '2-20'."""
    assert delta_code_exact([2, 20, 1, 1, 1]) == "02-20-01-01-01"
    assert delta_code_exact([20, 2, 1, 1, 1]) == "20-02-01-01-01"


# --------------------------------------------------------------- buckets ----


@pytest.mark.parametrize(
    "delta,expected",
    [
        (1, "S"),
        (BUCKET_SMALL_MAX, "S"),
        (BUCKET_SMALL_MAX + 1, "M"),
        (BUCKET_MEDIUM_MAX, "M"),
        (BUCKET_MEDIUM_MAX + 1, "L"),
        (39, "L"),
    ],
)
def test_bucket_boundaries(delta, expected):
    assert bucket_of(delta) == expected


def test_bucket_code_length_matches_delta_count():
    assert len(delta_code_bucket(DELTAS)) == len(DELTAS)


def test_bucket_codespace_is_243():
    """3 classes over 5 positions. Small enough that recurrence is observable."""
    assert len({"".join(c) for c in itertools.product("SML", repeat=5)}) == 243


# ----------------------------------------------------- shuffleCode (F6) ----


def test_shuffle_code_exact_golden_number_space():
    assert shuffle_code_exact(NUM_DIFFS) == "U02.U14.U14.U17.U12.U03"


def test_shuffle_code_direction_golden_number_space():
    assert shuffle_code_direction(NUM_DIFFS) == "UUUUUU"


def test_shuffle_code_magnitude_golden_number_space():
    assert shuffle_code_magnitude(NUM_DIFFS) == 62 == sum(abs(d) for d in NUM_DIFFS)


def test_shuffle_code_exact_golden_gap_space():
    assert shuffle_code_exact(DELTA_DIFFS) == "U12.S00.U03.D05.D09"


def test_shuffle_code_direction_golden_gap_space():
    assert shuffle_code_direction(DELTA_DIFFS) == "USUDD"


def test_shuffle_code_magnitude_golden_gap_space():
    assert shuffle_code_magnitude(DELTA_DIFFS) == 29


@pytest.mark.parametrize("value,expected", [(5, "U"), (-5, "D"), (0, "S")])
def test_direction_of(value, expected):
    assert direction_of(value) == expected


def test_sign_lives_in_the_letter_not_the_magnitude():
    """D05 and U05 differ only in direction -- magnitudes are absolute."""
    assert shuffle_code_exact([5]) == "U05"
    assert shuffle_code_exact([-5]) == "D05"


def test_zero_movement_encodes_as_same():
    assert shuffle_code_exact([0, 0]) == "S00.S00"
    assert shuffle_code_direction([0, 0]) == "SS"
    assert shuffle_code_magnitude([0, 0]) == 0


def test_shuffle_code_none_in_none_out():
    """The first retained draw has no predecessor.

    Null is not the same fact as zero movement: one means "did not move", the
    other means "there was nothing to move from".
    """
    assert shuffle_code(None) is None
    assert shuffle_code([1, None, 3]) is None
    assert shuffle_code([0, 0, 0]) is not None


# ------------------------------------------------------------ round-trip ----


def test_delta_code_round_trips_golden():
    assert decode_delta_code_exact(delta_code_exact(DELTAS)) == DELTAS


def test_shuffle_code_round_trips_golden():
    assert decode_shuffle_code_exact(shuffle_code_exact(NUM_DIFFS)) == NUM_DIFFS
    assert decode_shuffle_code_exact(shuffle_code_exact(DELTA_DIFFS)) == DELTA_DIFFS


def test_delta_code_round_trips_randomly():
    rng = random.Random(20260725)
    for _ in range(2000):
        deltas = [rng.randint(1, 53) for _ in range(5)]
        assert decode_delta_code_exact(delta_code_exact(deltas)) == deltas


def test_shuffle_code_round_trips_randomly_including_negatives_and_zero():
    rng = random.Random(20260726)
    for _ in range(2000):
        diffs = [rng.randint(-53, 53) for _ in range(6)]
        assert decode_shuffle_code_exact(shuffle_code_exact(diffs)) == diffs
