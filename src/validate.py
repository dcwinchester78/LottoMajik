"""Checks on the Lotto Texas archive, split by what can legitimately change.

Two tiers, deliberately:

INVARIANTS are physical facts about the game. Six distinct balls, all within
the matrix, one draw per date, ascending order after sorting. These cannot be
violated by any real draw, so a violation means the data is wrong. They raise.

EXPECTATIONS are regularities we have observed but the world controls. Which
weekdays the game draws on, how many days fall between draws, how many rows the
archive holds. These describe operator policy, not physics.

The distinction matters because we got it wrong once already. The original
version treated the Mon/Wed/Sat schedule as an invariant. Texas added Monday
draws on 2021-08-23; under that design, correct data would have halted the
pipeline. An expectation that fails is news to be surfaced, not an error to
crash on -- so expectations return findings and let a human judge.

Nothing here silently repairs anything, in either tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# --- physical constants of the 6/54 game -----------------------------------
BALLS_PER_DRAW = 6
MIN_BALL = 1
MAX_BALL = 54
DELTAS_PER_DRAW = BALLS_PER_DRAW - 1

NUM_COLS = [f"n{i}" for i in range(1, BALLS_PER_DRAW + 1)]
RAW_COLS = [f"raw{i}" for i in range(1, BALLS_PER_DRAW + 1)]

# --- observed regularities, NOT invariants ---------------------------------
# Current as of the 2026-07-22 archive. If the operator changes the schedule
# these become stale, which is expected and is why they only produce findings.
OBSERVED_GAP_DAYS = {2, 3, 4}
OBSERVED_WEEKDAYS = {"Mon", "Wed", "Sat"}


class ValidationError(AssertionError):
    """A physical invariant was violated. The data is wrong."""


@dataclass(frozen=True)
class Finding:
    """An expectation that did not hold. Informational, not fatal."""

    code: str
    message: str
    dates: tuple[str, ...] = field(default=())

    def __str__(self) -> str:
        where = ""
        if self.dates:
            shown = ", ".join(self.dates[:5])
            more = f" (+{len(self.dates) - 5} more)" if len(self.dates) > 5 else ""
            where = f"\n      affected: {shown}{more}"
        return f"[{self.code}] {self.message}{where}"


def _fail(msg: str, offenders: pd.DataFrame | None = None) -> None:
    detail = ""
    if offenders is not None and not offenders.empty:
        detail = f"\n\nFirst offending rows:\n{offenders.head(10).to_string()}"
    raise ValidationError(msg + detail)


def _dates_of(df: pd.DataFrame) -> tuple[str, ...]:
    return tuple(d.date().isoformat() for d in df["date"])


# ===========================================================================
# Tier 1 -- invariants. These raise.
# ===========================================================================


def check_distinct_balls(df: pd.DataFrame) -> None:
    """Six distinct balls per draw.

    This is the check that exposed the 2003-2006 bonus-ball format. A draw whose
    sixth column repeats an earlier ball is not a six-ball draw, and a delta
    computed across it compares two different machines. Never relax this.
    """
    cols = RAW_COLS if set(RAW_COLS) <= set(df.columns) else NUM_COLS
    bad = df[df[cols].nunique(axis=1) != BALLS_PER_DRAW]
    if not bad.empty:
        _fail(
            f"{len(bad)} draw(s) do not contain {BALLS_PER_DRAW} distinct balls. "
            "This usually means the source includes a bonus ball drawn from a "
            "separate pool (see MEMORY.md, 2003-05-03 to 2006-04-22). Do not "
            "dedupe -- determine which columns are main balls.",
            bad,
        )


def check_ball_range(df: pd.DataFrame) -> None:
    """All balls within the 6/54 matrix.

    A matrix change would be a genuine format change, not a schedule tweak: it
    would invalidate cross-era comparison outright, exactly as the 2003 change
    did. Correct behaviour is to stop and redraw the scope boundary by hand.
    """
    cols = RAW_COLS if set(RAW_COLS) <= set(df.columns) else NUM_COLS
    bad = df[(df[cols] < MIN_BALL).any(axis=1) | (df[cols] > MAX_BALL).any(axis=1)]
    if not bad.empty:
        _fail(
            f"{len(bad)} draw(s) contain a ball outside {MIN_BALL}..{MAX_BALL}. "
            "Within the analyzed scope the matrix is fixed at 6/54 -- an "
            "out-of-range ball means the matrix changed, the cutoff is wrong, or "
            "the row was mis-entered.",
            bad,
        )


def check_unique_dates(df: pd.DataFrame) -> None:
    """One draw per date."""
    dupes = df[df.duplicated("date", keep=False)]
    if not dupes.empty:
        _fail(
            f"{dupes['date'].nunique()} date(s) appear more than once. Do not "
            "silently dedupe -- find out why the archive has them.",
            dupes,
        )


def check_sorted_ascending(df: pd.DataFrame) -> None:
    """n1..n6 strictly ascending after the sort step."""
    vals = df[NUM_COLS].to_numpy()
    bad = df[(vals[:, 1:] <= vals[:, :-1]).any(axis=1)]
    if not bad.empty:
        _fail(f"{len(bad)} draw(s) are not strictly ascending after sorting.", bad)


def check_not_shrunk(df: pd.DataFrame, min_rows: int | None = None) -> None:
    """The archive never loses draws.

    A floor rather than an equality: rows arrive three times a week, so an exact
    count would fail on every routine update. Falling below the floor means a
    truncated download or the wrong file -- that is data loss, so it raises.
    """
    if min_rows is not None and len(df) < min_rows:
        _fail(
            f"Only {len(df)} rows after the cutoff, below the known floor of "
            f"{min_rows}. The archive can only grow -- a smaller count means a "
            "truncated file or the wrong source."
        )


def check_invariants(df: pd.DataFrame, min_rows: int | None = None) -> None:
    """Every physical invariant. Raises on the first violation."""
    check_unique_dates(df)
    check_distinct_balls(df)
    check_ball_range(df)
    check_sorted_ascending(df)
    check_not_shrunk(df, min_rows)


# ===========================================================================
# Tier 2 -- expectations. These report.
# ===========================================================================


def survey_draw_gaps(df: pd.DataFrame) -> list[Finding]:
    """Report gaps outside the observed pattern.

    An unusual gap has two possible causes and this code cannot tell them apart:
    a draw is missing from the archive, or the operator changed the schedule.
    The first corrupts inter-draw features; the second is normal. So it reports
    and flags the affected rows rather than guessing.
    """
    gaps = df["date"].diff().dt.days.dropna()
    odd = gaps[~gaps.isin(OBSERVED_GAP_DAYS)]
    if odd.empty:
        return []
    return [
        Finding(
            "unusual-gap",
            f"{len(odd)} gap(s) outside the usual {sorted(OBSERVED_GAP_DAYS)} days "
            f"(saw {sorted(odd.unique().astype(int).tolist())}). Either a draw is "
            "missing from the archive, or the draw schedule changed. Inter-draw "
            "features across these points may not mean what they usually mean.",
            _dates_of(df.loc[odd.index]),
        )
    ]


def survey_weekdays(df: pd.DataFrame) -> list[Finding]:
    """Report draws on days outside the observed schedule.

    Monday draws were added on 2021-08-23. A new draw day would land here, and
    the correct response is to widen OBSERVED_WEEKDAYS -- not to reject the data.
    """
    unexpected = df[~df["day_of_week"].isin(OBSERVED_WEEKDAYS)]
    if unexpected.empty:
        return []
    days = sorted(set(unexpected["day_of_week"]))
    return [
        Finding(
            "new-draw-day",
            f"{len(unexpected)} draw(s) on {days}, outside the observed "
            f"{sorted(OBSERVED_WEEKDAYS)} schedule. If the operator added a draw "
            "day, widen OBSERVED_WEEKDAYS and note the change date in MEMORY.md.",
            _dates_of(unexpected),
        )
    ]


def survey_expectations(df: pd.DataFrame) -> list[Finding]:
    """Every soft check. Returns findings; never raises."""
    return survey_draw_gaps(df) + survey_weekdays(df)


def flag_schedule_anomalies(df: pd.DataFrame) -> pd.Series:
    """Boolean per row: is this draw's gap from its predecessor unusual?

    Carried into the feature records so analysis can exclude inter-draw features
    computed across a schedule discontinuity, instead of silently trusting them.
    """
    gaps = df["date"].diff().dt.days
    return ~gaps.isin(OBSERVED_GAP_DAYS) & gaps.notna()


def validate_all(
    df: pd.DataFrame,
    min_rows: int | None = None,
    *,
    strict: bool = False,
) -> list[Finding]:
    """Invariants then expectations.

    Returns findings. With `strict=True` a finding is escalated to a raise --
    use that in CI, where an unreviewed schedule change should stop the build,
    but not in the routine ingest path, where it should just be reported.
    """
    check_invariants(df, min_rows)
    findings = survey_expectations(df)
    if strict and findings:
        _fail(
            "Expectations not met (strict mode):\n  "
            + "\n  ".join(str(f) for f in findings)
        )
    return findings
