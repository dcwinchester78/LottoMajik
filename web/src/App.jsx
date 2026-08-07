import { useState } from "react";
import { DataProvider, useLotteryData } from "./lib/DataContext.jsx";
import DrawTable from "./components/DrawTable.jsx";
import DeltaDistribution from "./components/DeltaDistribution.jsx";
import DeltaSumTimeline from "./components/DeltaSumTimeline.jsx";
import CodeFrequency from "./components/CodeFrequency.jsx";
import DrawDetail from "./components/DrawDetail.jsx";
import "./App.css";

const TABS = [
  { id: "table", label: "Draw table" },
  { id: "distribution", label: "Delta distribution" },
  { id: "timeline", label: "Delta sum over time" },
  { id: "codes", label: "Code frequency" },
  { id: "detail", label: "Single draw" },
];

function AppShell() {
  const data = useLotteryData();
  const [tab, setTab] = useState("table");
  // The draw a user picked from the table (or elsewhere) to inspect in the
  // "Single draw" view. Lives here, above the tabs, so any view can send the
  // reader to a specific draw's detail.
  const [selectedDrawId, setSelectedDrawId] = useState(null);

  function goToDraw(drawId) {
    setSelectedDrawId(drawId);
    setTab("detail");
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Lotto Texas — Delta Pattern Analysis</h1>
        <p className="subtitle">
          A descriptive record of how the drawn ball set has spread and moved,
          draw to draw, since the 6/54 format began on 2006-04-26. This is a
          study of past mechanical behavior, not a predictor: lottery draws
          are independent events, and nothing here ranks, favors, or suggests
          numbers for a future draw.
        </p>
      </header>

      <nav className="app-nav">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={t.id === tab ? "active" : ""}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="app-main">
        {data.status === "loading" && (
          <p className="state-message">Loading the draw archive…</p>
        )}
        {data.status === "error" && (
          <p className="state-message error">
            Could not load the draw archive: {String(data.error?.message ?? data.error)}
          </p>
        )}
        {data.status === "ready" && (
          <>
            {tab === "table" && (
              <DrawTable records={data.records} onSelectDraw={goToDraw} />
            )}
            {tab === "distribution" && <DeltaDistribution records={data.records} />}
            {tab === "timeline" && <DeltaSumTimeline records={data.records} />}
            {tab === "codes" && (
              <CodeFrequency summary={data.summary} onSelectBucket={() => {}} />
            )}
            {tab === "detail" && (
              <DrawDetail
                records={data.records}
                selectedDrawId={selectedDrawId}
                onSelectDraw={setSelectedDrawId}
              />
            )}
          </>
        )}
      </main>

      <footer className="app-footer">
        {data.status === "ready" && (
          <>
            <span>
              {data.summary.drawCount.toLocaleString()} draws ·{" "}
              {data.summary.dateRange.first} → {data.summary.dateRange.last}
            </span>
            <span>
              Config fingerprint: <code>{data.summary.configFingerprint}</code>
            </span>
          </>
        )}
        <span>
          All frequency counts are shown against a uniform-random baseline. That
          baseline is a naive floor for interpretation, not a hypothesis test —
          see the notes on each chart.
        </span>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <DataProvider>
      <AppShell />
    </DataProvider>
  );
}
