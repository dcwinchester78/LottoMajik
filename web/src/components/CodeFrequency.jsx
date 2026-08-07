import "./components.css";

const GROUPS = [
  {
    key: "deltaCodeBucket",
    title: "Bucket codes — deltaCode.bucket",
    sub: "Size class per gap position (S=1–3, M=4–9, L=10+), positional.",
  },
  {
    key: "deltaCodeShape",
    title: "Shape codes — deltaCode.shape",
    sub: "Same five gaps, sorted — a secondary key for \"same spread, different arrangement,\" never a replacement for the positional codes.",
  },
  {
    key: "shuffleCodeDirection",
    title: "Shuffle direction — shuffleCode.direction",
    sub: "Up/down/same per sorted ball position vs. the previous draw. One fewer coded draw than the archive total: the first retained draw has no predecessor.",
  },
];

function FreqGroup({ def, data }) {
  if (!data) return null;
  const baseline = data.uniformBaselinePerCode;
  const maxScale = Math.max(baseline, ...data.top.map((t) => t.count)) * 1.08;

  return (
    <div className="freq-group">
      <h3>{def.title}</h3>
      <p className="freq-sub">{def.sub}</p>
      <div className="baseline-note">
        <span className="swatch" /> {data.distinctCodes.toLocaleString()} distinct
        codes across {data.totalCoded.toLocaleString()} coded draws — naive
        uniform floor ≈ {baseline.toFixed(2)} per code if every code were
        equally reachable. This is a crude reference, not a hypothesis test:
        it ignores that some codes are structurally far more reachable than
        others (see the note below the chart list).
      </div>

      <div className="freq-list" role="table" aria-label={`${def.title} frequency, most observed first`}>
        {data.top.map((t) => {
          const widthPct = Math.min(100, (t.count / maxScale) * 100);
          const baselinePct = Math.min(100, (baseline / maxScale) * 100);
          return (
            <div className="freq-row" key={t.code}>
              <span className="freq-code">{t.code}</span>
              <span className="freq-bar-track">
                <span className="freq-bar-fill" style={{ width: `${widthPct}%` }} />
                <span className="freq-baseline-mark" style={{ left: `${baselinePct}%` }} title="Naive uniform floor" />
              </span>
              <span className="freq-count">
                {t.count} <span style={{ color: "var(--text-muted)" }}>({t.vsUniform.toFixed(1)}×)</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function CodeFrequency({ summary }) {
  const freqs = summary.codeFrequencies;

  return (
    <div className="card">
      <h2>Code frequency</h2>
      <p className="card-note">
        How often each code has occurred historically, most observed first —
        every count shown against the dashed naive-uniform-floor baseline
        (solid bar vs. dashed mark). This describes what has already
        happened; draws are independent, so no code here is "due" and none
        is a forecast of the next draw.
      </p>
      <div className="chart-legend">
        <span className="legend-item">
          <span className="legend-swatch-line" style={{ background: "var(--series-blue)" }} />
          Observed count
        </span>
        <span className="legend-item">
          <span className="legend-swatch-dash" />
          Naive uniform floor
        </span>
      </div>

      {GROUPS.map((def) => (
        <FreqGroup key={def.key} def={def} data={freqs[def.key]} />
      ))}

      <p className="card-note" style={{ marginTop: 4 }}>
        Top 25 by count within each group, out of every distinct code
        observed. {" "}
        <code className="code-badge">shuffleCode.direction</code> in
        particular skews far above its uniform floor for structural reasons,
        not chance: if the previous draw sat low in the range, almost any
        successor moves every position up, so <code className="code-badge">UUUUUU</code>-style
        codes are mechanically easier to land on than a uniform-random model
        assumes. A model that accounts for that is future work (Phase 6),
        not something this table claims to already do.
      </p>
    </div>
  );
}
