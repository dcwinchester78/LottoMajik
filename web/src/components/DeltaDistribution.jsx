import { useMemo, useRef, useState } from "react";
import { histogram, binLabel, relativeRect } from "./chartUtils.js";
import "./components.css";

const BIN_WIDTH = 2;
const GAP_LABELS = [
  "Gap 1  (n2 − n1)",
  "Gap 2  (n3 − n2)",
  "Gap 3  (n4 − n3)",
  "Gap 4  (n5 − n4)",
  "Gap 5  (n6 − n5)",
];

function roundedTopRectPath(x, y, w, h, r) {
  if (h <= 0) return "";
  const radius = Math.max(0, Math.min(r, w / 2, h));
  return `M${x},${y + h} L${x},${y + radius} Q${x},${y} ${x + radius},${y} L${
    x + w - radius
  },${y} Q${x + w},${y} ${x + w},${y + radius} L${x + w},${y + h} Z`;
}

function Bars({ bins, baseline, width = 560, height = 150, compact = false }) {
  const containerRef = useRef(null);
  const [hover, setHover] = useState(null);

  const padLeft = 6;
  const padRight = 6;
  const padTop = 8;
  const padBottom = compact ? 16 : 20;
  const innerWidth = width - padLeft - padRight;
  const innerHeight = height - padTop - padBottom;

  const n = bins.length;
  const band = innerWidth / n;
  const barWidth = Math.min(24, Math.max(1, band - 2));
  const yMax = Math.max(baseline, ...bins.map((b) => b.count), 1) * 1.15;

  const yFor = (v) => padTop + innerHeight - (v / yMax) * innerHeight;
  const baselineY = yFor(baseline);
  const labelStep = Math.ceil(n / (compact ? 6 : 12));

  function handleEnter(e, bin) {
    if (!containerRef.current) return;
    const pos = relativeRect(containerRef.current, e.currentTarget);
    setHover({ bin, ...pos });
  }

  return (
    <div className="chart-wrap" ref={containerRef}>
      <svg
        className="chart-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Histogram of observed delta values against a naive uniform baseline"
      >
        <line
          className="baseline-line"
          x1={padLeft}
          y1={baselineY}
          x2={width - padRight}
          y2={baselineY}
        />
        {bins.map((bin, i) => {
          const x = padLeft + i * band + (band - barWidth) / 2;
          const barHeight = (bin.count / yMax) * innerHeight;
          const y = padTop + innerHeight - barHeight;
          return (
            <g key={i}>
              <path
                d={roundedTopRectPath(x, y, barWidth, barHeight, 3)}
                fill="var(--series-blue)"
              />
              <rect
                className="hit-target"
                x={padLeft + i * band}
                y={padTop}
                width={band}
                height={innerHeight}
                onMouseEnter={(e) => handleEnter(e, bin)}
                onMouseLeave={() => setHover(null)}
                onFocus={(e) => handleEnter(e, bin)}
                onBlur={() => setHover(null)}
                tabIndex={0}
              />
              {i % labelStep === 0 && (
                <text
                  className="axis-label"
                  x={x + barWidth / 2}
                  y={height - padBottom + 12}
                  textAnchor="middle"
                >
                  {bin.start}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover && (
        <div
          className="chart-tooltip"
          style={{ left: hover.left, top: hover.top, transform: "translate(-50%, -100%)" }}
        >
          <div className="tt-row">
            <span className="tt-label">Delta {binLabel(hover.bin)}:</span>
            <span className="tt-value">{hover.bin.count}</span>
          </div>
          <div className="tt-row">
            <span className="tt-label">Naive floor:</span>
            <span className="tt-value">{baseline.toFixed(1)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DeltaDistribution({ records }) {
  const { pooledBins, pooledBaseline, perPosition } = useMemo(() => {
    const allDeltas = records.flatMap((r) => r.deltas);
    const pBins = histogram(allDeltas, BIN_WIDTH);
    const pBaseline = allDeltas.length / pBins.length;

    const perPos = [0, 1, 2, 3, 4].map((i) => {
      const values = records.map((r) => r.deltas[i]);
      const bins = histogram(values, BIN_WIDTH);
      const baseline = values.length / bins.length;
      return { bins, baseline };
    });

    return { pooledBins: pBins, pooledBaseline: pBaseline, perPosition: perPos };
  }, [records]);

  return (
    <div className="card">
      <h2>Delta distribution</h2>
      <p className="card-note">
        How large the gaps between consecutive sorted numbers have been,
        across all {records.length.toLocaleString()} draws. The five
        positions are kept separate below because a delta's position in the
        draw is part of what it records — collapsing them into one pooled
        count (top chart) discards that.
      </p>
      <div className="baseline-note">
        <span className="swatch" /> Dashed line is a naive uniform floor
        (total observations ÷ number of bins) — a crude reference, not a
        hypothesis test. It ignores that small and large deltas are not
        equally reachable from every position.
      </div>

      <h3 style={{ fontSize: 12.5, fontWeight: 600, margin: "4px 0 2px" }}>
        All deltas pooled ({records.length * 5} observations)
      </h3>
      <Bars bins={pooledBins} baseline={pooledBaseline} />

      <div className="small-multiples">
        {perPosition.map((p, i) => (
          <div className="small-multiple" key={i}>
            <h3>{GAP_LABELS[i]}</h3>
            <Bars bins={p.bins} baseline={p.baseline} width={260} height={130} compact />
          </div>
        ))}
      </div>
    </div>
  );
}
