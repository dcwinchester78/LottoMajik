import { useMemo, useState } from "react";
import "./components.css";

const PAGE_SIZE = 50;

export default function DrawTable({ records, onSelectDraw }) {
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [sortField, setSortField] = useState("date");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    return records.filter((r) => {
      if (fromDate && r.date < fromDate) return false;
      if (toDate && r.date > toDate) return false;
      return true;
    });
  }, [records, fromDate, toDate]);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sortField === "deltaSum") return (a.deltaSum - b.deltaSum) * dir;
      return a.date < b.date ? -dir : a.date > b.date ? dir : 0;
    });
  }, [filtered, sortField, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageRows = sorted.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function toggleSort(field) {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "date" ? "desc" : "desc");
    }
    setPage(1);
  }

  function updateFrom(v) {
    setFromDate(v);
    setPage(1);
  }

  function updateTo(v) {
    setToDate(v);
    setPage(1);
  }

  function clearFilter() {
    setFromDate("");
    setToDate("");
    setPage(1);
  }

  const arrow = (field) =>
    sortField === field ? (
      <span className="sort-arrow">{sortDir === "asc" ? "▲" : "▼"}</span>
    ) : null;

  return (
    <div className="card">
      <h2>Draw table</h2>
      <p className="card-note">
        Every retained draw, 2006-04-26 onward. Numbers are sorted ascending as
        drawn balls always are before deltas are computed; the five deltas are
        shown in their original position and are never reordered here.
      </p>

      <div className="filter-row">
        <label className="filter-field">
          From
          <input
            type="date"
            value={fromDate}
            max={toDate || undefined}
            onChange={(e) => updateFrom(e.target.value)}
          />
        </label>
        <label className="filter-field">
          To
          <input
            type="date"
            value={toDate}
            min={fromDate || undefined}
            onChange={(e) => updateTo(e.target.value)}
          />
        </label>
        {(fromDate || toDate) && (
          <button className="btn" onClick={clearFilter}>
            Clear
          </button>
        )}
        <span className="result-count">
          {sorted.length.toLocaleString()} of {records.length.toLocaleString()} draws
        </span>
      </div>

      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th className="sortable" onClick={() => toggleSort("date")}>
                Date {arrow("date")}
              </th>
              <th>Day</th>
              <th>Numbers</th>
              <th>Deltas (positional)</th>
              <th className="sortable" onClick={() => toggleSort("deltaSum")}>
                &Delta;Sum {arrow("deltaSum")}
              </th>
              <th>Code</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((r) => (
              <tr key={r.drawId} onClick={() => onSelectDraw(r.drawId)}>
                <td>{r.date}</td>
                <td>{r.dayOfWeek}</td>
                <td>
                  <span className="num-chips">
                    {r.numbers.map((n, i) => (
                      <span className="num-chip" key={i}>
                        {n}
                      </span>
                    ))}
                  </span>
                </td>
                <td>
                  <span className="delta-seq">{r.deltas.join(" · ")}</span>
                </td>
                <td className="tabular-nums">{r.deltaSum}</td>
                <td>
                  <span className="code-badge" title={r.deltaCode.exact}>
                    {r.deltaCode.bucket}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button className="btn" disabled={safePage <= 1} onClick={() => setPage(1)}>
          First
        </button>
        <button
          className="btn"
          disabled={safePage <= 1}
          onClick={() => setPage((p) => p - 1)}
        >
          Prev
        </button>
        <span>
          Page {safePage} of {pageCount}
        </span>
        <button
          className="btn"
          disabled={safePage >= pageCount}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
        </button>
        <button
          className="btn"
          disabled={safePage >= pageCount}
          onClick={() => setPage(pageCount)}
        >
          Last
        </button>
      </div>
    </div>
  );
}
