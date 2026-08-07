// Small shared helpers for the hand-rolled SVG charts. No charting library --
// the app has five simple views, and a dependency-free chart keeps the
// contract (data in, pixels out) easy to check against PROJECT.md by eye.

/** Bucket a flat array of positive integers into fixed-width bins starting at 1. */
export function histogram(values, binWidth) {
  const max = values.length ? Math.max(...values) : 0;
  const binCount = Math.max(1, Math.ceil(max / binWidth));
  const bins = Array.from({ length: binCount }, (_, i) => ({
    start: i * binWidth + 1,
    end: (i + 1) * binWidth,
    count: 0,
  }));
  for (const v of values) {
    const idx = Math.min(binCount - 1, Math.floor((v - 1) / binWidth));
    bins[idx].count += 1;
  }
  return bins;
}

export function binLabel(bin) {
  return bin.start === bin.end ? `${bin.start}` : `${bin.start}–${bin.end}`;
}

/** Reads a hovered element's position relative to a container ref, for tooltip placement. */
export function relativeRect(containerEl, targetEl) {
  const c = containerEl.getBoundingClientRect();
  const t = targetEl.getBoundingClientRect();
  return {
    left: t.left - c.left + t.width / 2,
    top: t.top - c.top,
  };
}
