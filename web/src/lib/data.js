// Fetches the pipeline's output straight from web/public/data/ (written by
// `python -m src.emit --web`, see ../../src/emit.py). No transformation here
// beyond parsing JSON -- the contract is PROJECT.md's record shape, and the
// pipeline is the only place that shape gets decided.

const BASE = "/data";

async function fetchJson(name) {
  const res = await fetch(`${BASE}/${name}`);
  if (!res.ok) {
    throw new Error(`Failed to load /data/${name}: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Sanity-check the fetched data against itself. This is a UI-side smoke
 * check, not a re-run of the pipeline's validation (see src/validate.py) --
 * it exists to catch a stale/partial copy in web/public/data/, not to judge
 * the archive. Mismatches are reported, never thrown: a rendering bug in the
 * count is not a reason to blank the whole app.
 */
function checkConsistency(records, summary) {
  const problems = [];

  if (records.length !== summary.drawCount) {
    problems.push(
      `features.json has ${records.length} records but summary.json ` +
        `reports drawCount ${summary.drawCount} -- these may be out of sync.`,
    );
  }

  // Exactly one record should have no predecessor (the first retained draw,
  // 2006-04-26). Never assumed to be records[0] -- checked by the flag.
  const noPrev = records.filter((r) => r.flags.hasPrev === false);
  if (noPrev.length !== 1) {
    problems.push(
      `Expected exactly one record with flags.hasPrev === false, found ` +
        `${noPrev.length}.`,
    );
  }

  return problems;
}

export async function loadLotteryData() {
  const [records, summary, schema] = await Promise.all([
    fetchJson("features.json"),
    fetchJson("summary.json"),
    fetchJson("schema.json"),
  ]);

  const problems = checkConsistency(records, summary);
  if (problems.length) {
    // eslint-disable-next-line no-console
    console.warn("[data consistency]", problems.join(" "));
  }

  return { records, summary, schema, consistencyProblems: problems };
}
