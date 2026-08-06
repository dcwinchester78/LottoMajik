# Texas Lottery Delta Pattern Analysis

## What this project is

A data-analysis pipeline over the historical Lotto Texas draw archive. The subject of
study is **the physical shuffling behavior of the ball machine** — how the drawn set of
six numbers moves, spreads, and re-spreads from draw to draw. Deltas and their encodings
are the instruments we use to observe that motion.

## What this project is NOT

**This project does not predict lottery numbers.** No model, script, notebook, report,
or UI in this repo may output a suggested, likely, favored, "due", or ranked set of
numbers to play. Lottery draws are independent events; any pattern found here is
descriptive of past mechanical behavior, not predictive of future outcomes.

Permitted: frequency analysis, distribution analysis, clustering of historical draws,
recurrence statistics, visualizations of past behavior, hypothesis testing against a
uniform-random null.

Not permitted: number recommendations, "hot/cold" pick lists, expected-value or
strategy advice, any framing that implies a future draw is knowable.

If a task appears to cross this line, the agent stops and asks. See `CLAUDE.md`.

---

## Data source and scope

`lottotexas.csv` — 3,773 rows, 1992-11-14 through 2026-07-22, no header row.

**Only draws from 2006-04-26 onward are analyzed: 2,370 draws.** Everything earlier is
filtered out at ingestion. See "Scope" below for why. The source CSV is never modified —
the cutoff is applied in `ingest.py` as a constant.

```
Lotto Texas,7,22,2026,14,33,54,53,44,35
   game    , M, D, YYYY, n1, n2, n3, n4, n5, n6
```

Columns: game name, month, day, year, then six ball numbers.

**Critical:** the six numbers are stored in **draw order**, not sorted. Only 106 of 3,773
rows happen to be ascending — roughly what chance predicts. Every delta computation must
sort ascending first. Draw order is itself a physical artifact and is preserved in the
output as `drawOrder`.

### Scope: 2006-04-26 onward, 6/54 only

The game's format changed several times before 2006, and one of those changes makes the
older data structurally incompatible rather than merely different:

| Period | Format | Status |
|--------|--------|--------|
| 1992-11-14 → 2000-07-15 | 6/50 | excluded |
| 2000-07-19 → 2003-04-30 | 6/54 | excluded |
| 2003-05-03 → 2006-04-22 | **5/44 + bonus ball** | excluded — not six main balls |
| **2006-04-26 → present** | **6/54** | **analyzed (2,370 draws)** |

The 2003–2006 period is not a 6/44 game. It drew five main balls from 44 plus a bonus
ball from a **second, independent pool of 44**, so its sixth column is not a member of
the same spatial draw and cannot participate in a delta. Confirmed against the archive
(the sixth column duplicates a main ball in 34 of 311 draws, matching the 5/44 collision
rate of 11.4% almost exactly) and against the Texas Lottery record.

Excluding everything before 2006-04-26 removes both matrix changes and the bonus-ball
format in one cut, leaving a single uninterrupted 6/54 regime. The pipeline therefore
carries **no era machinery at all** — one matrix, one ball pool, every draw comparable to
every other.

**Draw cadence:** Wed/Sat from 2006-04-26; Monday draws added 2021-08-23, so the schedule
is Mon/Wed/Sat thereafter. This affects the elapsed time spanned by "the previous three
draws" (F4) but not the mechanics. Gaps between consecutive draws are 2, 3, or 4 days —
never more, so the archive has no missing draws.

**New draws arrive by manual entry, three times a week**, through a test GUI, in the same
format the CSV stores (draw order, not sorted). See "Invariants vs. expectations" in
`CLAUDE.md` for how the pipeline stays correct as the archive grows and the schedule
potentially changes again.

---

## Features

Let the six numbers of draw *t*, sorted ascending, be `n₁ < n₂ < … < n₆`.

### F0 — date
The draw date, plus derived `year`, `month`, `day`, `dayOfWeek`.

### F1 — deltas
```
deltas[i] = n[i+1] − n[i]     for i = 0..4      → 5 values
```
Five gaps between six sorted numbers. **Positional and never re-sorted.** The order of
the deltas is meaningful — it records where in the number space the spread occurred.
Sorting them would erase exactly the information we are looking for.

Example (2026-07-22): sorted `[14, 33, 35, 44, 53, 54]` → deltas `[19, 2, 9, 9, 1]`

### F2 — deltaSum
```
deltaSum = Σ deltas = n₆ − n₁
```
The total spread of the draw. Example: `40`.

### F3 — deltaDiffPrev
```
deltaDiffPrev[i] = deltas[i] − prevDeltas[i]    for i = 0..4      → 5 signed values
```
Positional, signed. How each gap changed from the previous drawing. `null` only for the
first retained draw (2006-04-26). Example (vs 2026-07-20): `[12, 0, 3, −5, −9]`.

### F4 — deltaSumAvg3
```
deltaSumAvg3 = mean(deltaSum[t−1], deltaSum[t−2], deltaSum[t−3])
```
Excludes the current draw. `null` for the first three draws. Example: `40.33`.

### F5 — deltaCode  (intra-draw)
A code describing **the five deltas of this draw alone**. Nothing to do with the previous
draw. Its purpose is to group draws whose internal spread pattern matches.

| Field | Definition | Example |
|-------|------------|---------|
| `exact` | zero-padded deltas, positional | `19-02-09-09-01` |
| `bucket` | per-delta size class, positional — S=1–3, M=4–9, L=10+ | `LSMMS` |
| `shape` | deltas sorted ascending, as a multiset key | `01-02-09-09-19` |

Bucket thresholds were checked against the observed distribution of all 11,850 deltas
in the archive: S/M/L as specified splits 29.9% / 39.0% / 31.0%. Exact terciles would
give 37.9 / 31.0 / 31.0 — marginally more balanced, not enough to justify losing round
boundaries. Deltas are discrete and lumpy, so no split is clean.

`exact` and `bucket` preserve position and are the primary keys. `shape` is an
**additional** grouping key for the question "same set of gaps, different arrangement?"
— it is never substituted for the positional codes.

### F6 — shuffleCode  (inter-draw)
A code describing **the movement between two consecutive number sets** — direction and
magnitude, position by position, over the six sorted numbers.

```
numDiff[i] = n[i](t) − n[i](t−1)     for i = 0..5      → 6 signed values
```

| Field | Definition | Example |
|-------|------------|---------|
| `exact` | direction + distance per position; U=up, D=down, S=same | `U02.U14.U14.U17.U12.U03` |
| `direction` | sign pattern only | `UUUUUU` |
| `magnitude` | Σ \|numDiff\| — total travel | `62` |

`null` only for the first retained draw — the scope is a single 6/54 regime, so every
other draw has a directly comparable predecessor.

A parallel `shuffleCodeDelta` is emitted over F3 (the five delta-to-delta differences)
using the same encoding, so movement can be examined in number space and in gap space.

---

## Output

The pipeline writes plain JSON to `data/` — no database. The React app reads these files
directly.

```
data/
  features.json     # array of draw records, ascending by date
  features.jsonl    # same records, one per line (streaming / diffing)
  schema.json       # JSON Schema for a record
  summary.json      # counts, eras, date range, code-frequency tables
```

### Record shape

```json
{
  "drawId": "2026-07-22",
  "date": "2026-07-22",
  "year": 2026, "month": 7, "day": 22, "dayOfWeek": "Wed",
  "drawOrder": [14, 33, 54, 53, 44, 35],
  "numbers":   [14, 33, 35, 44, 53, 54],
  "deltas":    [19, 2, 9, 9, 1],
  "deltaSum":  40,
  "deltaDiffPrev": [12, 0, 3, -5, -9],
  "deltaSumAvg3": 40.33,
  "deltaCode": {
    "exact":  "19-02-09-09-01",
    "bucket": "LSMMS",
    "shape":  "01-02-09-09-19"
  },
  "shuffleCode": {
    "exact":     "U02.U14.U14.U17.U12.U03",
    "direction": "UUUUUU",
    "magnitude": 62
  },
  "shuffleCodeDelta": {
    "exact":     "U12.S00.U03.D05.D09",
    "direction": "USUDD",
    "magnitude": 29
  },
  "prevDrawId": "2026-07-20",
  "prevGapDays": 2,
  "flags": { "hasPrev": true, "unusualGap": false }
}
```

Formatting rules: dates ISO-8601. Magnitudes zero-padded to 2 digits in codes. Floats
rounded to 2 decimals. Records sorted ascending by date. Field order stable across runs
so `git diff` on `data/` stays readable.

---

## Repo layout

```
/
├── PROJECT.md              this file — the spec
├── CLAUDE.md               agent operating instructions
├── MEMORY.md               accumulated findings
├── lottotexas.csv          source data
├── src/
│   ├── config.py           pipeline parameters + fingerprint
│   ├── ingest.py           CSV → validated DataFrame (applies the 2006 cutoff)
│   ├── validate.py         invariant checks (raise) + expectation checks (report)
│   ├── manifest.py         append-only integrity across repeated ingestions
│   ├── append.py           validated write path for manually-entered draws
│   ├── features.py         F1–F6 computation
│   ├── encode.py           deltaCode / shuffleCode encoders
│   └── emit.py             DataFrame → data/*.json
├── tests/
│   ├── test_ingest.py
│   ├── test_features.py
│   ├── test_encode.py
│   └── test_emit.py
├── data/                   generated output (committed)
├── web/                    React app (Phase 5) — reads data/features.json
└── notebooks/              exploratory analysis
```

**One repo, deliberately.** `data/features.json` is a contract between the pipeline and
the app. A change to feature logic and the UI change that depends on it belong in one
commit, reviewable as one diff. Split across two repos, version skew becomes possible —
the app expecting a field the JSON no longer emits — with no single commit showing when
it broke.

Stack: Python 3.10+, pandas, pytest. No ML frameworks — see non-goals.

---

## Phases

| Phase | Goal | Done when |
|-------|------|-----------|
| 0 | Repo scaffold, git, docs | Committed, pushed |
| 1 | Ingestion — parse, filter to 2006+, validate, sort | 2,370+ rows load clean, validation suite green |
| 2 | Features F1–F4 | Golden-value tests pass |
| 3 | Encoders F5–F6 | Codes round-trip, frequency tables sane |
| 4 | JSON emission + schema | `data/*.json` written and schema-validated |
| 5 | React app | App reads `features.json` end to end |
| 6 | Descriptive pattern analysis | Findings recorded in `MEMORY.md`, against a real null |

Phases 0–4 are complete. Phase 4 delivered the stated first goal: features into a store
the app can read.

---

# Phase 5 brief — the React app

Build in `web/`, Vite + React. This section exists so the session that builds it starts
with the contract rather than inferring it.

## The data contract

The app consumes `data/features.json`: an array of records, ascending by date, shaped
exactly as documented above and validated against `data/schema.json`. Treat the schema as
authoritative — it is generated from the same config as the data.

**Handle nulls as a first-class case, not an edge case.** The first retained draw
(2006-04-26) has no predecessor, so `deltaDiffPrev`, `deltaSumAvg3`, `shuffleCode`,
`shuffleCodeDelta`, `prevDrawId` and `prevGapDays` are all `null`. A record where
`flags.hasPrev` is `false` is not missing data — it is complete data about a draw that
begins the series. Rendering `0`, `—`, or `NaN` there would assert something false.
Currently exactly one record is in this state; do not hard-code that assumption.

`data/summary.json` carries `configFingerprint`. Surface it somewhere in the UI. Two
datasets built with different parameters are not comparable, and the fingerprint is the
only thing that makes that visible.

### Vite and the data path

Vite will not import from outside its project root, so `web/` cannot reach up into
`../data/`. Resolved by having `emit.py` write a second copy into `web/public/data/`
(`out_dir` is already a parameter) rather than by relaxing Vite's filesystem rules or
adding a build-time copy step. The app then fetches `/data/features.json` as a normal
static asset. Keep `data/` at the repo root as the canonical, committed output.

## What the first views should show

Descriptive views over history. In rough priority:

1. **Draw table** — date, numbers, deltas, deltaSum, deltaCode. Sortable, filterable by
   date range. The workhorse.
2. **Delta distribution** — histogram of all five delta positions, and per-position, so
   the positional structure is visible rather than collapsed.
3. **deltaSum over time** — line chart with `deltaSumAvg3` overlaid.
4. **Code frequency** — bucket codes and shuffle directions by count, **always displayed
   against the baseline** (see below).
5. **Single draw detail** — one draw with its deltas, its codes, and its movement from
   the previous draw.

## Two constraints specific to the UI

**No prediction, restated for the interface.** The hard rule in `CLAUDE.md` applies to
pixels as much as to functions. Do not build: a "suggested numbers" panel, a hot/cold
ball display, a "due" indicator, a number picker that highlights candidates, a countdown
framing the next draw as forecastable, or any control that produces a set of numbers.
Sorting a frequency table descending is fine; labelling the top row "most likely" is not.
The app describes what the machine has done, in the past tense.

**Never show a count without its baseline.** A frequency bar with no comparison implies
significance that has not been established. Every count in the UI needs its expected
value beside it, and the summary's `uniformBaselinePerCode` is a *crude floor*, not a
hypothesis test — a uniform null ignores that some codes are structurally far more
reachable than others. `shuffleCodeDirection` shows this vividly: `UUUUUU` appears ~32×
"uniform expectation", which is close to meaningless, because if the previous draw
skewed low then almost any successor moves every position up. Until Phase 6 supplies a
proper null, label these as raw counts and say plainly that the baseline is naive.

## Done when

The app loads `features.json`, renders the draw table and at least one chart over the
full archive, handles the null-predecessor record correctly, displays the config
fingerprint, and shows no view that implies a future draw is knowable.
