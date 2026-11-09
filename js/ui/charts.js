// Small hand-drawn SVG charts (no libraries).
const W = 300;
const H = 110;
const PAD = { l: 30, r: 4, t: 6, b: 14 };

function frame(maxY, xLabelLeft, xLabelRight, yFmt = (v) => v) {
  const y0 = H - PAD.b;
  return `<line class="axis" x1="${PAD.l}" y1="${y0}" x2="${W - PAD.r}" y2="${y0}"/>
    <line class="axis" x1="${PAD.l}" y1="${PAD.t}" x2="${W - PAD.r}" y2="${PAD.t}" stroke-dasharray="2 3"/>
    <text class="lbl" x="${PAD.l - 3}" y="${PAD.t + 3}" text-anchor="end">${yFmt(maxY)}</text>
    <text class="lbl" x="${PAD.l - 3}" y="${y0}" text-anchor="end">0</text>
    <text class="lbl" x="${PAD.l}" y="${H - 2}">${xLabelLeft}</text>
    <text class="lbl" x="${W - PAD.r}" y="${H - 2}" text-anchor="end">${xLabelRight}</text>`;
}

const sx = (i, n) => PAD.l + ((W - PAD.l - PAD.r) * (i + 0.5)) / n;
const sy = (v, max) => H - PAD.b - ((H - PAD.t - PAD.b) * v) / max;

export function renderBreachChart(el, metrics, windowSize = 120) {
  const data = metrics.slice(-windowSize);
  if (!data.length) {
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${frame(1, '', '')}</svg>`;
    return;
  }
  const n = data.length;
  const max = Math.max(1, ...data.map((d) => Math.max(d.breaches, d.weaknesses)));
  const bw = Math.max(1, (W - PAD.l - PAD.r) / n - 1);
  const bars = data
    .map((d, i) => (d.breaches ? `<rect class="bar" x="${sx(i, n) - bw / 2}" y="${sy(d.breaches, max)}" width="${bw}" height="${sy(0, max) - sy(d.breaches, max)}"/>` : ''))
    .join('');
  const line = data.map((d, i) => `${sx(i, n)},${sy(d.weaknesses, max)}`).join(' ');
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">
    ${frame(max, `R${data[0].round}`, `R${data.at(-1).round}`)}
    ${bars}<polyline class="line-grey" points="${line}"/></svg>`;
}

export function renderAccuracyChart(el, metrics, rolling = 10) {
  const outcomes = [];
  for (const m of metrics) {
    for (let i = 0; i < m.fixAttempts; i++) outcomes.push(i < m.fixSuccesses ? 1 : 0);
  }
  if (!outcomes.length) {
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${frame(100, '', '', (v) => `${v}%`)}</svg>`;
    return;
  }
  const pts = outcomes.map((_, i) => {
    const win = outcomes.slice(Math.max(0, i - rolling + 1), i + 1);
    return (100 * win.reduce((a, b) => a + b, 0)) / win.length;
  });
  const n = pts.length;
  const line = pts.map((v, i) => `${sx(i, n)},${sy(v, 100)}`).join(' ');
  const area = `${sx(0, n)},${sy(0, 100)} ${line} ${sx(n - 1, n)},${sy(0, 100)}`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">
    ${frame(100, 'fix #1', `fix #${n}`, (v) => `${v}%`)}
    <polygon class="area-blue" points="${area}"/><polyline class="line-blue" points="${line}"/></svg>`;
}
