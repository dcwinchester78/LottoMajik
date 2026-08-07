import { useMemo, useRef, useState } from "react";
import { bisectNearest } from "./chartUtils.js";
import "./components.css";

const WIDTH = 700;
const HEIGHT = 260;
const PAD_LEFT = 40;
const PAD_RIGHT = 12;
const PAD_TOP = 12;
const PAD_BOTTOM = 26;

function niceFloor(v, step) {
  return Math.floor(v / step) * step;
}
function niceCeil(v, step) {
  return Math.ceil(v / step) * step;
}

export default function DeltaSumTimeline({ records }) {
  const containerRef = useRef(null);
  const [hoverIdx, setHoverIdx] = useState(null);

  const model = useMemo(() => {
    const times = records.map((r) => new Date(r.date).getTime());
    const sums = records.map((r) => r.deltaSum);
    const avg3 = records.map((r) => r.deltaSumAvg3);

    const tMin = times[0];
    const tMax = times[times.length - 1];
    const vMin = niceFloor(Math.min(...sums), 5);
    const vMax = niceCeil(Math.max(...sums), 5);

    const innerWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
    const innerHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;

    const xScale = (t) => PAD_LEFT + ((t - tMin) / (tMax - tMin)) * innerWidth;
    const yScale = (v) => PAD_TOP + innerHeight - ((v - vMin) / (vMax - vMin)) * innerHeight;

    let sumPath = "";
    sums.forEach((v, i) => {
      const cmd = i === 0 ? "M" : "L";
      sumPath += `${cmd}${xScale(times[i]).toFixed(1)},${yScale(v).toFixed(1)} `;
    });

    let avgPath = "";
    let drawing = false;
    avg3.forEach((v, i) => {
      if (v == null) {
        drawing = false;
        return;
      }
      avgPath += `${drawing ? "L" : "M"}${xScale(times[i]).toFixed(1)},${yScale(v).toFixed(1)} `;
      drawing = true;
    });

    const yearSpan = new Date(tMax).getFullYear() - new Date(tMin).getFullYear();
    const yearStep = Math.max(1, Math.ceil((yearSpan + 1) / 9));
    const xTicks = [];
    for (let y = new Date(tMin).getFullYear(); y <= new Date(tMax).getFullYear(); y += yearStep) {
      const t = new Date(`${y}-01-01`).getTime();
      if (t >= tMin && t <= tMax) xTicks.push({ t, label: String(y) });
    }

    const yTicks = [];
    for (let v = vMin; v <= vMax; v += 10) yTicks.push(v);

    return { times, sums, avg3, tMin, tMax, vMin, vMax, xScale, yScale, sumPath, avgPath, xTicks, yTicks, innerWidth, innerHeight };
  }, [records]);

  function handleMove(e) {
    const box = e.currentTarget.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width));
    const t = model.tMin + fraction * (model.tMax - model.tMin);
    setHoverIdx(bisectNearest(model.times, t));
  }

  const hovered = hoverIdx != null ? records[hoverIdx] : null;
  const hoverX = hoverIdx != null ? model.xScale(model.times[hoverIdx]) : null;

  return (
    <div className="card">
      <h2>&Delta;Sum over time</h2>
      <p className="card-note">
        Total spread of each draw (n6 − n1) across the archive, with a
        trailing 3-draw average overlaid. The average is computed from the
        three draws strictly before each point — it never includes the
        current draw, and is blank for the first three retained draws
        because no such window exists yet.
      </p>

      <div className="chart-wrap" ref={containerRef}>
        <svg
          className="chart-svg"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label="Line chart of deltaSum over time with 3-draw trailing average"
        >
          {model.yTicks.map((v) => (
            <g key={v}>
              <line
                className="gridline"
                x1={PAD_LEFT}
                x2={WIDTH - PAD_RIGHT}
                y1={model.yScale(v)}
                y2={model.yScale(v)}
              />
              <text className="axis-label" x={PAD_LEFT - 6} y={model.yScale(v) + 3} textAnchor="end">
                {v}
              </text>
            </g>
          ))}
          {model.xTicks.map((tk) => (
            <text
              key={tk.label}
              className="axis-label"
              x={model.xScale(tk.t)}
              y={HEIGHT - PAD_BOTTOM + 14}
              textAnchor="middle"
            >
              {tk.label}
            </text>
          ))}

          <path d={model.sumPath} fill="none" stroke="var(--series-blue)" strokeWidth="1.5" opacity="0.85" />
          <path d={model.avgPath} fill="none" stroke="var(--series-red)" strokeWidth="2" />

          {hoverX != null && (
            <>
              <line
                x1={hoverX}
                x2={hoverX}
                y1={PAD_TOP}
                y2={HEIGHT - PAD_BOTTOM}
                stroke="var(--text-muted)"
                strokeWidth="1"
              />
              <circle cx={hoverX} cy={model.yScale(hovered.deltaSum)} r="4" fill="var(--series-blue)" stroke="var(--surface-1)" strokeWidth="2" />
              {hovered.deltaSumAvg3 != null && (
                <circle cx={hoverX} cy={model.yScale(hovered.deltaSumAvg3)} r="4" fill="var(--series-red)" stroke="var(--surface-1)" strokeWidth="2" />
              )}
            </>
          )}

          <rect
            x={PAD_LEFT}
            y={PAD_TOP}
            width={model.innerWidth}
            height={model.innerHeight}
            fill="transparent"
            onMouseMove={handleMove}
            onMouseLeave={() => setHoverIdx(null)}
          />
        </svg>

        {hovered && (
          <div
            className="chart-tooltip"
            style={{
              left: Math.min(Math.max(hoverX, 70), WIDTH - 70),
              top: 4,
              transform: "translate(-50%, 0)",
            }}
          >
            <div style={{ marginBottom: 4, color: "var(--text-secondary)" }}>{hovered.date}</div>
            <div className="tt-row">
              <span className="tt-key" style={{ background: "var(--series-blue)" }} />
              <span className="tt-label">&Delta;Sum:</span>
              <span className="tt-value">{hovered.deltaSum}</span>
            </div>
            <div className="tt-row">
              <span className="tt-key" style={{ background: "var(--series-red)" }} />
              <span className="tt-label">3-draw avg:</span>
              <span className="tt-value">
                {hovered.deltaSumAvg3 != null
                  ? hovered.deltaSumAvg3.toFixed(2)
                  : "not yet available"}
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="chart-legend">
        <span className="legend-item">
          <span className="legend-swatch-line" style={{ background: "var(--series-blue)" }} />
          &Delta;Sum per draw
        </span>
        <span className="legend-item">
          <span className="legend-swatch-line" style={{ background: "var(--series-red)" }} />
          Trailing 3-draw average
        </span>
      </div>
    </div>
  );
}
