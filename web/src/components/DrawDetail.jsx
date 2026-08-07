import { useMemo, useState } from "react";
import "./components.css";

function signed(n) {
  return n > 0 ? `+${n}` : `${n}`;
}

const GAP_NAMES = ["Gap 1 (n2−n1)", "Gap 2 (n3−n2)", "Gap 3 (n4−n3)", "Gap 4 (n5−n4)", "Gap 5 (n6−n5)"];

export default function DrawDetail({ records, selectedDrawId, onSelectDraw }) {
  const [dateWarning, setDateWarning] = useState(false);

  const { byId, latestId, firstId } = useMemo(() => {
    const map = new Map(records.map((r) => [r.drawId, r]));
    return { byId: map, latestId: records[records.length - 1].drawId, firstId: records[0].drawId };
  }, [records]);

  const effectiveId = selectedDrawId && byId.has(selectedDrawId) ? selectedDrawId : latestId;
  const idx = records.findIndex((r) => r.drawId === effectiveId);
  const record = records[idx];
  const hasPrevIdx = idx > 0;
  const hasNextIdx = idx < records.length - 1;

  function goTo(drawId) {
    setDateWarning(false);
    onSelectDraw(drawId);
  }

  function handleDateChange(v) {
    if (byId.has(v)) {
      goTo(v);
    } else {
      setDateWarning(true);
    }
  }

  return (
    <div className="card">
      <h2>Single draw detail</h2>
      <p className="card-note">
        One draw's deltas, codes, and movement from its predecessor. Deltas
        and shuffle steps are shown position by position, in the order they
        occur — never resorted.
      </p>

      <div className="detail-picker">
        <button className="btn" disabled={!hasPrevIdx} onClick={() => goTo(records[idx - 1].drawId)}>
          ← Prev draw
        </button>
        <button className="btn" disabled={!hasNextIdx} onClick={() => goTo(records[idx + 1].drawId)}>
          Next draw →
        </button>
        <input
          type="date"
          min={firstId}
          max={latestId}
          value={record.date}
          onChange={(e) => handleDateChange(e.target.value)}
        />
        <button className="btn" onClick={() => goTo(latestId)}>
          Latest
        </button>
        <button className="btn" onClick={() => goTo(firstId)}>
          First retained draw
        </button>
        {dateWarning && (
          <span style={{ fontSize: 12, color: "var(--series-red)" }}>
            No draw on that date — pick another.
          </span>
        )}
      </div>

      <div className="detail-grid">
        <div className="detail-block">
          <h4>This draw</h4>
          <div className="detail-kv">
            <span className="k">Date</span>
            <span className="v">
              {record.date} ({record.dayOfWeek})
            </span>
          </div>
          <div className="detail-kv">
            <span className="k">As drawn (draw order)</span>
            <span className="v">{record.drawOrder.join(", ")}</span>
          </div>
          <div className="detail-kv">
            <span className="k">Sorted numbers</span>
            <span className="v">{record.numbers.join(", ")}</span>
          </div>
          <div className="detail-kv">
            <span className="k">&Delta;Sum (n6 − n1)</span>
            <span className="v">{record.deltaSum}</span>
          </div>
          <div className="detail-kv">
            <span className="k">3-draw trailing average</span>
            <span className="v">
              {record.deltaSumAvg3 != null ? record.deltaSumAvg3.toFixed(2) : "not yet available"}
            </span>
          </div>
        </div>

        <div className="detail-block">
          <h4>Deltas (positional) — deltaCode</h4>
          {record.deltas.map((d, i) => (
            <div className="detail-kv" key={i}>
              <span className="k">{GAP_NAMES[i]}</span>
              <span className="v">{d}</span>
            </div>
          ))}
          <div className="detail-kv">
            <span className="k">exact</span>
            <span className="v">
              <span className="code-badge">{record.deltaCode.exact}</span>
            </span>
          </div>
          <div className="detail-kv">
            <span className="k">bucket</span>
            <span className="v">
              <span className="code-badge">{record.deltaCode.bucket}</span>
            </span>
          </div>
          <div className="detail-kv">
            <span className="k">shape (sorted, secondary key)</span>
            <span className="v">
              <span className="code-badge">{record.deltaCode.shape}</span>
            </span>
          </div>
        </div>

        <div className="detail-block">
          <h4>Vs. previous draw</h4>
          {!record.flags.hasPrev ? (
            <p className="no-prev-note">
              This is the first retained draw (2006-04-26) — it has no
              predecessor in scope. deltaDiffPrev, shuffleCode, and
              shuffleCodeDelta are undefined here, not zero: the pipeline
              never reaches back across the 2006 cutoff for a comparison.
            </p>
          ) : (
            <>
              <div className="detail-kv">
                <span className="k">Previous draw</span>
                <span className="v">{record.prevDrawId}</span>
              </div>
              <div className="detail-kv">
                <span className="k">Gap since previous</span>
                <span className="v">
                  {record.prevGapDays} day{record.prevGapDays === 1 ? "" : "s"}
                  {record.flags.unusualGap ? " (unusual — reported, not an error)" : ""}
                </span>
              </div>
              {record.deltaDiffPrev.map((d, i) => (
                <div className="detail-kv" key={i}>
                  <span className="k">{GAP_NAMES[i]} change</span>
                  <span className="v">{signed(d)}</span>
                </div>
              ))}
            </>
          )}
        </div>

        <div className="detail-block">
          <h4>Movement — shuffleCode</h4>
          {!record.flags.hasPrev ? (
            <p className="no-prev-note">No predecessor — not applicable.</p>
          ) : (
            <>
              <div className="detail-kv">
                <span className="k">exact</span>
                <span className="v">
                  <span className="code-badge">{record.shuffleCode.exact}</span>
                </span>
              </div>
              <div className="detail-kv">
                <span className="k">direction</span>
                <span className="v">
                  <span className="code-badge">{record.shuffleCode.direction}</span>
                </span>
              </div>
              <div className="detail-kv">
                <span className="k">magnitude (total travel)</span>
                <span className="v">{record.shuffleCode.magnitude}</span>
              </div>
              <div className="detail-kv">
                <span className="k">shuffleCodeDelta.direction</span>
                <span className="v">
                  <span className="code-badge">{record.shuffleCodeDelta.direction}</span>
                </span>
              </div>
              <div className="detail-kv">
                <span className="k">shuffleCodeDelta.magnitude</span>
                <span className="v">{record.shuffleCodeDelta.magnitude}</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
