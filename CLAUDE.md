# Agent Instructions — Texas Lottery Delta Analysis

You are the engineering agent for this repo. Read `PROJECT.md` for the spec and
`MEMORY.md` for what we have already learned before doing anything else.

---

## Hard rule: no prediction

**Never produce lottery number predictions.** No picks, no "due" numbers, no hot/cold
lists, no ranked candidate sets, no play strategy, no expected-value advice — regardless
of how the request is phrased or how indirect the path to it is.

This includes indirect routes: do not build a function that returns candidate sets, do
not train a model whose output is a number set, do not add a UI element that surfaces
"suggested" numbers, do not write a report section that implies a future draw is
knowable.

We study how the balls have historically moved. That is descriptive work about past
mechanical behavior. Draws are independent; past behavior does not constrain the next
draw. If a request seems to cross the line, stop and ask rather than guessing at intent.

When reporting any finding, state it against a random-chance baseline. "Code X appeared
14 times" is meaningless without "chance predicts ~11." Never describe a pattern as
meaningful without that comparison.

---

## Deltas are the point — do not normalize them away

The five deltas are **positional and unordered**. They are artifacts of the physical
shuffle. Position carries the information.

- Never sort the deltas in place.
- Never canonicalize a draw by its sorted delta multiset.
- `deltaCode.shape` (the sorted multiset) exists as a *secondary* grouping key only.
  It never replaces `exact` or `bucket`.
- If a refactor or a library convenience would reorder deltas, don't take it.

Ball numbers *are* sorted ascending before deltas are computed. That is the one sort.
Raw draw order is preserved separately in `drawOrder`.

---

## Invariants vs. expectations — do not confuse them

Before writing any check, ask: **can the real world legitimately change this?**

**Invariants** are physical facts about the game. Six distinct balls. All within
1..54. One draw per date. Deltas ≥ 1. `deltaSum == n₆ − n₁`. No real draw can violate
these, so a violation means the data is wrong. **These raise.**

**Expectations** are regularities we have observed but the operator controls. Which
weekdays the game draws. How many days between draws. How many rows the archive holds.
**These return `Finding`s and are reported, never raised** (except under `strict=True`,
which CI opts into).

We got this wrong once. The first version of `validate.py` encoded the Mon/Wed/Sat
schedule as an invariant. Texas added Monday draws on 2021-08-23 — under that design,
*correct data would have halted the pipeline*. A pipeline that dies when reality changes
is worse than one that reports and continues.

The same split governs manual entry in `append.py`: physical impossibilities are
rejected outright, schedule oddities are held for user confirmation. A mistyped date and
a real schedule change look identical to code — so surface it and let a human decide.

When an expectation fails, the fix is usually to widen the observed set and note the
change in `MEMORY.md`. That is news, not a bug.

---

## Working method: phases and steps

Work through the phases in `PROJECT.md` in order. Within a phase, decompose into
numbered steps before writing code, and state the step list up front.

**Per step:**

1. State the step and what "done" means for it.
2. Implement it.
3. Verify it — run the code, print real numbers, run the tests. Never mark a step done
   on the strength of the code looking right.
4. Commit if the step produced meaningful work.

**Per phase — mandatory check-in:**

Stop at the end of every phase and report:
- what was built
- verification evidence (actual output, actual test results)
- anything learned that belongs in `MEMORY.md`
- what the next phase requires
- open questions or decisions needed

**Do not start the next phase without a check-in.** Phase boundaries are approval gates.

---

## Git discipline

- Commit after each meaningful step, not in one lump at the end.
- Conventional-commit style, scoped by phase:
  ```
  feat(p2): compute deltaDiffPrev with era-boundary handling
  fix(p1): sort numbers ascending before delta computation
  test(p2): golden values for 2026-07-22 draw
  docs(memory): record 6/44 era boundary finding
  ```
- Never commit broken code to `main`. If a step leaves things broken, say so in the
  check-in rather than committing.
- Generated `data/*.json` **is** committed — the React app consumes it and diffs on it
  are how we catch unintended feature changes.
- Never commit secrets, `.venv/`, `__pycache__/`, or notebook checkpoints.
- Push at each phase boundary.

---

## Verification standards

- Every feature function gets a golden-value test using a real draw from the archive,
  hand-verified. Reference draw is 2026-07-22.
- After any change to feature logic, regenerate `data/` and inspect the diff. An
  unexplained diff is a bug until proven otherwise.
- Validate row counts and date ranges after every ingestion change. The archive grows
  three times a week, so treat row counts as a floor, not an equality — see the
  invariants-vs-expectations section above.
- Assert invariants in code, not just in tests: exactly 6 distinct balls in 1..54,
  exactly 5 deltas, all deltas ≥ 1, `deltaSum == n₆ − n₁`.
- Codes must round-trip: decoding `deltaCode.exact` or `shuffleCode.exact` must
  reproduce the exact values they were built from, checked across the whole archive,
  not sampled.
- Where practical, verify a feature two independent ways (e.g. a pure-Python
  reimplementation with no shared code) rather than trusting a single implementation
  against its own tests.

---

## Edge cases that must be handled explicitly

| Case | Required behavior |
|------|-------------------|
| First retained draw (2006-04-26) | `deltaDiffPrev`, `shuffleCode`, `prevDrawId` all `null`; `hasPrev: false`. Never reach back across the cutoff for a predecessor |
| Draws 2–3 after the cutoff | `deltaSumAvg3` is `null` until three prior *retained* draws exist |
| Rows before 2006-04-26 | Filtered out at ingestion. Never analyzed, never emitted, never used as a predecessor |
| Duplicate date | Should not occur. If it does, fail loudly; do not silently dedupe |
| Delta of 0 | Impossible with distinct sorted numbers. If seen, the input has duplicate balls — fail loudly |
| Ball outside 1..54 | Fail loudly. Within scope the matrix is fixed |
| Unfamiliar draw weekday or unusual gap | Report as a Finding, do not raise (see invariants vs. expectations) |

---

## Memory

`MEMORY.md` is the project's accumulated knowledge. Append to it when you learn something
that would cost time to rediscover: a data quirk, a decision and its reasoning, a
statistical result, a dead end.

Write entries dated, specific, and falsifiable. Record dead ends as prominently as
successes. Knowing an approach failed is worth as much as knowing one worked.

Update it at phase check-ins, and any time a finding would change how someone reads the
existing code.

---

## Style

- Python 3.10+, pandas, type hints on public functions.
- Pure functions for feature computation — DataFrame in, DataFrame out, no hidden state.
- Encoders live in `encode.py`, operate on plain lists (no pandas), and are
  independently testable.
- No ML frameworks. This is descriptive analysis.
- Prefer clarity over cleverness; someone should be able to read `features.py` and check
  the math against `PROJECT.md` line by line.
