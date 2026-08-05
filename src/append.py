"""Validated append path for manually-entered draws.

New draws are keyed in by hand three times a week, so this module is an input
guard, not a formality. A typo that reaches the CSV corrupts the deltas for the
new draw and every inter-draw feature of the draw after it.

The GUI calls `validate_new_draw` to check input before the user commits, then
`append_draw` to write. `append_draw` re-validates -- never trust that the caller
checked. `ingest()` validates the whole archive again on the next run, so a row
edited into the CSV outside this path is still caught.

Balls are entered in DRAW ORDER, exactly as the CSV stores them. They are never
sorted on the way in; sorting happens downstream in ingest.sort_balls.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .ingest import DEFAULT_CSV, GAME_NAME, SCOPE_START, ingest
from .validate import (
    BALLS_PER_DRAW,
    MAX_BALL,
    MIN_BALL,
    OBSERVED_GAP_DAYS,
    OBSERVED_WEEKDAYS,
    Finding,
    ValidationError,
)


class DrawRejected(ValidationError):
    """A proposed draw failed validation and was not written."""


def validate_new_draw(
    date: dt.date,
    balls: list[int],
    existing: pd.DataFrame | None = None,
) -> dict:
    """Check a proposed draw.

    Raises DrawRejected for physical impossibilities -- a ball outside the
    matrix, a repeated ball, a duplicate or back-dated entry. Those cannot
    describe a real draw, so no amount of confirmation makes them valid.

    Returns findings for things that are merely unusual: an unfamiliar weekday,
    an unexpected gap. The operator can change the schedule, so the GUI should
    show these and let the user confirm rather than blocking the entry.

    Returns a summary the GUI can display: `{..., "findings": [...]}`.
    """
    problems: list[str] = []
    findings: list[Finding] = []

    # --- the draw itself -------------------------------------------------
    if len(balls) != BALLS_PER_DRAW:
        problems.append(f"Need {BALLS_PER_DRAW} balls, got {len(balls)}.")
    if not all(isinstance(b, (int, float)) and float(b).is_integer() for b in balls):
        problems.append("All balls must be whole numbers.")
    else:
        balls = [int(b) for b in balls]
        out = [b for b in balls if b < MIN_BALL or b > MAX_BALL]
        if out:
            problems.append(
                f"Ball(s) {sorted(out)} outside the {MIN_BALL}..{MAX_BALL} matrix."
            )
        dupes = sorted({b for b in balls if balls.count(b) > 1})
        if dupes:
            problems.append(
                f"Ball(s) {dupes} entered more than once. A draw has six distinct "
                "balls -- check for a transcription slip."
            )

    # --- the date --------------------------------------------------------
    if date < SCOPE_START:
        problems.append(
            f"{date} precedes the analysis cutoff {SCOPE_START}. Draws before "
            "the cutoff are out of scope and must not be added."
        )

    weekday = date.strftime("%a")
    if weekday not in OBSERVED_WEEKDAYS:
        findings.append(
            Finding(
                "new-draw-day",
                f"{date} is a {weekday}; the game has drawn "
                f"{sorted(OBSERVED_WEEKDAYS)} to date. Most likely a mistyped "
                "date -- but if the schedule changed, this is correct and you "
                "should widen OBSERVED_WEEKDAYS.",
                (date.isoformat(),),
            )
        )

    # --- position in the sequence ---------------------------------------
    gap = None
    if existing is not None and len(existing):
        last = existing["date"].max().date()
        if date == last:
            problems.append(f"A draw for {date} already exists.")
        elif date < last:
            problems.append(
                f"{date} is before the latest draw on record ({last}). Draws are "
                "appended in order; back-filling would break the delta chain."
            )
        else:
            gap = (date - last).days
            if gap not in OBSERVED_GAP_DAYS:
                findings.append(
                    Finding(
                        "unusual-gap",
                        f"{gap} days since the last draw ({last}); usually "
                        f"{sorted(OBSERVED_GAP_DAYS)}. Either a draw is missing "
                        "from the archive or the schedule changed. Add the "
                        "missing draw first if one was skipped.",
                        (date.isoformat(),),
                    )
                )

    if problems:
        raise DrawRejected(
            "Draw rejected -- nothing was written:\n  - " + "\n  - ".join(problems)
        )

    return {
        "date": date.isoformat(),
        "weekday": weekday,
        "drawOrder": list(balls),
        "sorted": sorted(balls),
        "deltas": _preview_deltas(sorted(balls)),
        "daysSinceLast": gap,
        "findings": findings,
        "needsConfirmation": bool(findings),
    }


def _preview_deltas(sorted_balls: list[int]) -> list[int]:
    """Deltas the draw will produce -- shown for confirmation, not stored here."""
    return [sorted_balls[i + 1] - sorted_balls[i] for i in range(BALLS_PER_DRAW - 1)]


def format_row(date: dt.date, balls: list[int]) -> str:
    """Render one CSV line in the archive's exact format.

    No zero-padding on month/day: the file uses `7,22,2026` and `11,14,1992`.
    """
    return ",".join(
        [GAME_NAME, str(date.month), str(date.day), str(date.year)]
        + [str(int(b)) for b in balls]
    )


def append_draw(
    date: dt.date,
    balls: list[int],
    csv_path: Path | str = DEFAULT_CSV,
    *,
    dry_run: bool = False,
    confirm_unusual: bool = False,
) -> dict:
    """Validate then append a draw to the archive.

    Re-validates against the current file regardless of what the caller checked.
    With `dry_run=True` nothing is written -- use it to preview from the GUI.

    If validation returns findings (unfamiliar weekday, unusual gap) the write is
    held until `confirm_unusual=True`. This is a speed bump for the likely typo,
    not a wall against the legitimate schedule change.
    """
    csv_path = Path(csv_path)
    existing = ingest(csv_path, check_append_only=False, report=False)
    summary = validate_new_draw(date, balls, existing)
    line = format_row(date, balls)
    summary["csvLine"] = line

    if dry_run:
        summary["written"] = False
        return summary

    if summary["needsConfirmation"] and not confirm_unusual:
        summary["written"] = False
        summary["heldForConfirmation"] = True
        return summary

    text = csv_path.read_text(encoding="utf-8")
    separator = "" if text.endswith("\n") or not text else "\n"
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        fh.write(separator + line + "\n")

    # Prove the archive still parses and satisfies every invariant after the
    # write. If this raises, the row is on disk and must be removed by hand --
    # loud and recoverable beats silent and wrong.
    after = ingest(csv_path, check_append_only=False, report=False)
    summary["written"] = True
    summary["rowCount"] = int(len(after))
    return summary
