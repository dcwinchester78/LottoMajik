# Project Memory

Accumulated findings. Append, dated. Record dead ends as prominently as successes.
See `CLAUDE.md` for how to write entries.

---

## Repo relocated — 2026-07-25

**This repo was rebuilt at `C:\Users\Chris\source\repos\LotteryMajik` after the original
working copy on a D: drive became inaccessible** ("Location is not available... the file
or directory is corrupted and unreadable"). `chkdsk /f` did not resolve it within the
session, and the decision was made to stop depending on that drive rather than wait it
out. All content in this file and in `PROJECT.md`/`CLAUDE.md` was reconstructed from the
working conversation, not recovered from the old disk, so it is a faithful rebuild but
git history from the original repo (7 commits, Phases 0–2 plus most of Phase 3) does not
carry over. This file starts a fresh log from that point.

**Nothing about the findings below changed** — they were re-derived, not re-guessed, and
match the original archive exploration exactly.

---

## The most important thing in this file

**The 2003–2006 data is NOT a 6/44 game. It is 5/44 plus a bonus ball from a second,
independent pool.**

Found by asserting that all six balls in a draw are distinct. 34 draws failed. Every one
of them falls between 2003-05-03 and 2006-04-22, and in **all 34 the duplicate is the
sixth column repeating one of the first five**. Zero violations anywhere else in the
3,773-row archive.

The collision-rate test settles it. If the sixth column were a bonus ball drawn
independently from 1..44, it would coincide with one of the five main balls with
probability 5/44 = 11.36%. Over the 311 draws in that window that predicts **35.3**
collisions. Observed: **34**.

Confirmed against the public record: the format changed to five-from-44 plus a bonus
ball from a separate 44-ball pool on 2003-05-07, and reverted to 6/54 on 2006-04-26.

**Why this was a trap.** The naive read of the era is "6/44" — the max ball observed is
44, the row has six numbers, and summaries of Texas Lottery history list a matrix change
in 2003. Computing deltas on those rows produces five plausible-looking numbers with no
error raised, and one of them is silently garbage: the sixth column is not a member of
the same spatial draw, so the delta between ball 5 and the "bonus" compares two different
machines. A delta of 0 would have been the only visible symptom, and that only shows up
in 34 of 311 draws.

**The lesson that generalizes:** assert the physical invariants (six distinct balls, all
deltas ≥ 1) at ingestion rather than trusting the shape of the file. The assertion is
what surfaced this; nothing about the CSV looked wrong.

---

## Scope decision

**Analyze 2006-04-26 → present only. 2,370 draws** as of the 2026-07-22 snapshot.

Everything before the cutoff is filtered out at ingestion. This single cut removes:

- the 6/50 era (1992-11-14 → 2000-07-15)
- the first 6/54 era (2000-07-19 → 2003-04-30)
- the 5/44 + bonus-ball era (2003-05-03 → 2006-04-22)

leaving one uninterrupted 6/54 regime. Consequence: **the pipeline needs no era
machinery.** No era tagging, no matrix lookup, no conditional delta arity. Every retained
draw is directly comparable to every other.

The source CSV is not modified. The cutoff lives in `ingest.py` as a constant.

Rationale for excluding the two pre-2003 6/54 eras as well, even though they are the same
matrix as today: they are separated from the current regime by a three-year format
change, different ball sets, and different drawing equipment. Continuity of the physical
apparatus is the premise of the whole project, so a multi-year gap in that continuity is
not something to paper over.

---

## Data facts — verified

**Retained slice, all checks green (as of the 2026-07-22 snapshot).**

| Check | Result |
|-------|--------|
| Rows in CSV / retained after cutoff | 3,773 / **2,370** |
| Date range retained | 2006-04-26 → 2026-07-22 |
| All six balls distinct | ✅ every draw |
| Ball range | 1..54, none out of range |
| Duplicate dates | 0 |
| Gaps between consecutive draws | only 2, 3, or 4 days — no missing draws |

Row count is a **floor**, not an equality — the archive grows three times a week by
manual entry. See "Invariants vs. expectations" below.

**Numbers are stored in DRAW ORDER, not sorted.**
Only 106 of 3,773 rows are already ascending — about what chance predicts. **Sort
ascending before computing deltas or every delta is garbage.** The first few rows *look*
sorted (`13,16,22,29,32,36`), which makes this an easy trap when eyeballing `head`. It is
coincidence, not a format change.

Draw order is not noise — it is the sequence the balls physically emerged in — so it is
preserved as `drawOrder` in the output rather than discarded.

**Draw cadence changed mid-scope.**
Wed/Sat from 2006-04-26. **Monday draws added 2021-08-23**, so Mon/Wed/Sat thereafter
(1,057 Wed / 1,056 Sat / 257 Mon in the retained slice, as of the 2026-07-22 snapshot).
This does not affect delta mechanics, but it does mean "the previous three draws" (F4)
spans about 7 calendar days before 2021-08-23 and about 5 after.

**New draws arrive by manual entry, three times a week**, via a test GUI, in the CSV's
own format — draw order, not sorted. This makes `validate.py` an input guard rather than
a periodic audit, and makes the append-only manifest concept load-bearing: a mistyped
past row would otherwise be indistinguishable from a correct one. What no code can catch
is a *plausible* typo (23 for 32 is a legal draw) — that risk is accepted, not solved.

---

## Decisions

**Output is plain JSON files, not a database.**
Originally considered LiteDB. LiteDB is a .NET library with no native Python writer,
which would have forced a Python→JSON→C# importer hop for a few thousand records. At
this size the intermediate store earns nothing: the pipeline writes `data/features.json`
and the React app reads it directly. Revisit only if record count grows by orders of
magnitude or the app needs server-side query.

**Two distinct codes, not one.**
`deltaCode` describes a single draw's own five deltas (intra-draw). `shuffleCode`
describes movement between two consecutive number sets — direction and magnitude
(inter-draw). These answer different questions and must not be conflated. A third,
`shuffleCodeDelta`, applies the shuffleCode encoding to the delta-to-delta differences,
so movement is observable in both number space and gap space.

**Bucket thresholds (S=1–3, M=4–9, L=10+) kept as originally specified, not
data-derived.** Checked against the observed distribution of all 11,850 deltas in the
archive: this split gives 29.9% / 39.0% / 31.0%. Exact terciles (1–4 / 5–9 / 10+) give
37.9 / 31.0 / 31.0 — marginally more balanced, not enough to justify losing round,
legible boundaries. Deltas are discrete and lumpy; no split is clean.

**Invariants and expectations are separated, after getting it wrong once.**
The first `validate.py` treated the Mon/Wed/Sat schedule and 2–4 day gaps as hard
invariants. They are not physics; they are operator policy. Texas added Monday draws
on 2021-08-23, and under that design **correct data would have halted ingestion**.

Now: invariants raise (six distinct balls, matrix range, unique dates, ascending order,
no shrinkage), expectations report `Finding`s (draw days, gap lengths, row floor).
`strict=True` escalates findings for CI. Rows following a gap discontinuity carry
`unusual_gap` so inter-draw features across one can be excluded rather than trusted.

The general lesson: **an assertion is a claim that the world cannot change.** Most
things about a lottery operator's behaviour are not that. Encoding habit as law
produces a pipeline that breaks precisely when something interesting happens.

---

## Golden values — hand-verified

Draw **2026-07-22**, the reference case for all feature tests:

```
drawOrder        [14, 33, 54, 53, 44, 35]
numbers          [14, 33, 35, 44, 53, 54]
deltas           [19, 2, 9, 9, 1]
deltaSum         40                          (= 54 − 14 ✓)
deltaDiffPrev    [12, 0, 3, -5, -9]          (vs 2026-07-20 deltas [7, 2, 6, 14, 10])
deltaSumAvg3     40.33                       (34, 48, 39 → 121/3)
numDiff          [2, 14, 14, 17, 12, 3]      (vs sorted [12,19,21,27,41,51])
deltaCode.exact       19-02-09-09-01
deltaCode.bucket      LSMMS
deltaCode.shape       01-02-09-09-19
shuffleCode.exact       U02.U14.U14.U17.U12.U03
shuffleCode.direction   UUUUUU
shuffleCode.magnitude   62
shuffleCodeDelta.exact       U12.S00.U03.D05.D09
shuffleCodeDelta.direction   USUDD
shuffleCodeDelta.magnitude   29
```

| Date | sorted numbers | deltas | deltaSum |
|------|----------------|--------|----------|
| 2026-07-15 | 3, 13, 16, 27, 32, 37 | 10, 3, 11, 5, 5 | 34 |
| 2026-07-18 | 2, 25, 27, 32, 40, 50 | 23, 2, 5, 8, 10 | 48 |
| 2026-07-20 | 12, 19, 21, 27, 41, 51 | 7, 2, 6, 14, 10 | 39 |
| 2026-07-22 | 14, 33, 35, 44, 53, 54 | 19, 2, 9, 9, 1 | 40 |

Boundary case — **2006-04-26**, first retained draw: `[6, 8, 14, 23, 32, 52]`,
deltas `[2, 6, 9, 9, 20]`, deltaSum 46, deltaCode.exact `02-06-09-09-20`,
deltaCode.bucket `SMMML`. `deltaDiffPrev`, `shuffleCode`, `prevDrawId`, `deltaSumAvg3`
must all be `null`. The pipeline must **not** reach back to 2006-04-22 for a predecessor
— that draw is in the bonus-ball era.

First four draws, showing the null cascade at the boundary:

| date | deltas | deltaSum | deltaDiffPrev | deltaSumAvg3 |
|------|--------|----------|---------------|--------------|
| 2006-04-26 | 2, 6, 9, 9, 20 | 46 | null | null |
| 2006-04-29 | 2, 3, 18, 3, 13 | 39 | 0, −3, 9, −6, −7 | null |
| 2006-05-03 | 12, 7, 13, 3, 2 | 37 | 10, 4, −5, 0, −11 | null |
| 2006-05-06 | 7, 1, 7, 14, 1 | 30 | −5, −6, −6, 11, −1 | 40.67 |

---

## Verification notes carried from the original build

F1–F4 were cross-checked against an independent pure-Python reimplementation (raw
`csv`, no pandas, no shared code) across all 2,370 draws: **zero mismatches** on deltas,
sums, diffs, and the rolling mean. Agreement between two implementations from the same
spec is weaker evidence than agreement with reality, but it rules out pandas alignment
and off-by-one errors, which are the likely failure modes for this kind of code.

Two implementation traps worth re-checking after the rebuild:

- **F4 must be `shift(1)` then `rolling(3)`, never `rolling(3)` alone.** The latter
  includes the current draw, silently leaking the present into a feature meant to
  summarise the past.
- **Cutoff nulls (F3/F4) are structural, not special-cased.** `shift(1)` cannot reach
  past row 0, and row 0 is 2006-04-26 because ingestion already dropped everything
  earlier — the pipeline cannot reach into the bonus-ball era for a predecessor.
- **Codes must round-trip.** `deltaCode.exact` and `shuffleCode.exact` are records, not
  summaries; decoding must reproduce the exact input across the whole archive, not a
  sample.

**Status at time of relocation:** `encode.py` and the F5/F6 wiring in `features.py` had
been run once against the real archive and every value matched the golden table above.
The test files (`test_encode.py`, and the F5/F6 additions to `test_features.py`) were
written but never executed before the drive became unreadable. **Re-verify all of Phase
2 and Phase 3 from a full `pytest` run in this new repo before trusting anything above
as re-confirmed** — nothing here should be taken on faith twice.

---

## Analysis findings

*(none yet — Phase 6)*

When adding entries here, always state the random-chance baseline alongside the observed
value. A count without a baseline is not a finding. The bonus-ball entry above is the
model: 34 observed against 35.3 predicted is what made the conclusion solid.

---

## Dead ends

**Inferring matrix eras from max-ball-per-month: insufficient.**
The first pass at era detection took the highest ball seen in each month and inferred
pool size. It produced a clean, plausible, and **wrong** table — it labelled 2003–2006 as
"6/44" and missed the bonus ball entirely, because a bonus-ball format has exactly the
same max-ball signature as a smaller matrix. Max-ball tells you the pool ceiling; it
tells you nothing about whether the columns come from one pool or two. Distinctness
assertions are what distinguish them.

**Working directly on a D: drive without an independent backup: cost the git history.**
The original repo lived only on a drive that later reported as corrupted and unreadable.
`chkdsk` did not bring it back within the working session. The lesson isn't "don't use
D: drives" — it's that a single local copy, however version-controlled, is not resilient
to the underlying disk failing. Push to the GitHub remote early and often once one is
connected, so the remote — not the working copy — is the durable source of truth.

**Correction, 2026-08-06: the git history was not actually lost.** The rebuilt repo had
no `origin` configured, so this went unnoticed until Phase 5. `origin/master` on
`github.com/dcwinchester78/LottoMajik` still had the pre-crash commits through
`12601dd` (`docs(p5): brief the React phase`) — identical hashes to the reconstructed
local history up to that point, confirmed with
`git merge-base --is-ancestor origin/master master`. The rebuilt local repo turned out
to be a superset (same history plus the commits made after the crash), so it fast-forwarded
cleanly. Moral: check for a configured remote — and fetch it — before concluding history
is gone. The remote had been doing its job; the working copy just wasn't pointed at it.

---

## Phase 5 — React app decisions, 2026-08-06

**No charting library.** All five views (`web/src/components/`) are hand-rolled SVG —
`chartUtils.js` holds a binning helper, a nearest-point bisect for hover, and a
tooltip-position helper; each chart component builds its own `<path>`/`<rect>` markup
against a fixed `viewBox`. At five simple views over one JSON file, `recharts` or `d3`
would be a dependency to justify, not a time-saver. Revisit only if a future view needs
something this approach genuinely can't do cleanly (e.g. true pan/zoom over the full
archive).

**Every displayed count carries a visible baseline, not just a number in a tooltip.**
`CodeFrequency` renders `uniformBaselinePerCode` as a dashed mark inside each bar's
track (CSS `--baseline` token), and `DeltaDistribution`'s histograms compute their own
naive per-bin floor (`total observations ÷ bin count`) the same way. Both are captioned
explicitly as a naive floor, not a hypothesis test — matching the color-formula
guidance that only status colors and validated palettes get to look authoritative.

**`flags.hasPrev === false` and null `deltaSumAvg3` are rendered as prose, never as
`0`/`—`/`NaN`.** Verified directly against `features.json`, not assumed from the
schema: exactly one record has `hasPrev === false` (2006-04-26), and `deltaSumAvg3` is
null for exactly the first three retained draws (non-null starting at record 4,
`40.67`). `DrawDetail` branches on `flags.hasPrev` to show an explanatory note instead
of the "vs. previous draw" / shuffleCode blocks; `DeltaSumTimeline`'s average line
simply doesn't draw through the null stretch rather than interpolating or zeroing it.

**No GitHub Actions/CI wired up yet.** Verification this phase was `npm run build`
(catches compile errors) plus direct `node -e` checks against the real
`features.json` for the null-handling edge cases — not a browser render. No browser
automation tool was available this session, so the actual pixels were never
screenshotted by the agent; the user was asked to eyeball `localhost:5173` directly
instead. If that didn't happen, treat the views as build-verified but not visually
verified.
