import React from 'react';
import { satLabel } from '../../intel/investigationModel.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Event activity timeline: one bar per real event, x = first→last observation, height = observation count (linear).
 *  Lower strip marks S-NPP days with UNKNOWN coverage inside the source window. No interpolation between events. */
export function EventTimeline({ rows, window: win, unknownDays = [], unknownLabel = 'S-NPP unknown-coverage days' }) {
  const W = 720; const H = 210; const L = 38; const R = 8; const T = 10; const plotH = 130; const base = T + plotH;
  const t0 = Date.parse(`${win[0]}T00:00:00Z`); const t1 = Date.parse(`${win[1]}T23:59:59Z`); const span = Math.max(1, t1 - t0);
  const x = (iso) => L + ((Date.parse(iso) - t0) / span) * (W - L - R);
  const maxObs = Math.max(1, ...rows.map((r) => r.observations));
  const ticks = []; const d = new Date(t0); d.setUTCDate(1);
  for (let c = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1)); c.getTime() <= t1; c = new Date(Date.UTC(c.getUTCFullYear(), c.getUTCMonth() + 1, 1))) ticks.push(new Date(c));
  return (
    <figure className="chart-fig">
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Event timeline: ${rows.length} events, maximum ${maxObs} observations per event`}>
        <line className="chart-grid" x1={L} x2={W - R} y1={T} y2={T} /><line className="chart-grid" x1={L} x2={W - R} y1={T + plotH / 2} y2={T + plotH / 2} />
        <line className="chart-axis" x1={L} x2={W - R} y1={base} y2={base} /><line className="chart-axis" x1={L} x2={L} y1={T} y2={base} />
        <text className="chart-tick" x={L - 4} y={T + 4} textAnchor="end">{maxObs}</text>
        <text className="chart-tick" x={L - 4} y={T + plotH / 2 + 4} textAnchor="end">{Math.round(maxObs / 2)}</text>
        <text className="chart-tick" x={L - 4} y={base + 3} textAnchor="end">0</text>
        {rows.map((r) => { const x0 = x(r.first); const w = Math.max(2.2, x(r.last) - x0); const h = Math.max(2, (r.observations / maxObs) * plotH);
          return <rect key={r.event_id} className={r.status === 'active' ? 'chart-bar chart-bar--current' : 'chart-bar'} x={x0} y={base - h} width={w} height={h}><title>{`${r.event_id}: ${r.observations} observation${r.observations === 1 ? '' : 's'}, ${r.first.slice(0, 10)} → ${r.last.slice(0, 10)}`}</title></rect>; })}
        {ticks.map((c) => <g key={c.toISOString()}><line className="chart-axis" x1={x(c.toISOString())} x2={x(c.toISOString())} y1={base} y2={base + 4} /><text className="chart-tick" x={x(c.toISOString())} y={base + 15} textAnchor="middle">{MONTHS[c.getUTCMonth()]}</text></g>)}
        <text className="chart-label" x={L} y={base + 36}>{unknownLabel} ({unknownDays.length})</text>
        <line className="chart-grid" x1={L} x2={W - R} y1={base + 48} y2={base + 48} />
        {unknownDays.map((u) => <rect key={u} className="chart-unknown" x={x(`${u}T12:00:00Z`) - 1.2} y={base + 41} width={2.4} height={14}><title>{`${u}: unverified coverage (unknown, not 'no fire')`}</title></rect>)}
        {unknownDays.length === 0 && <text className="chart-tick" x={L} y={base + 66}>No unknown-coverage days in this source window.</text>}
      </svg>
      <figcaption className="chart-caption">Bars = events (x: first → last observation, height: observations, linear scale 0–{maxObs}). Bar width does not imply continuous activity. Red = event still flagged active at data cut-off.</figcaption>
    </figure>
  );
}

export function SplitBar({ parts, caption }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return (
    <div className="split-bar" role="img" aria-label={parts.map((p) => `${p.label} ${(p.value / total * 100).toFixed(1)}%`).join(', ')}>
      <div className="split-bar__track">{parts.map((p) => <i key={p.label} className={p.cls} style={{ width: `${(p.value / total) * 100}%` }} />)}</div>
      <div className="split-bar__legend">{parts.map((p) => <span key={p.label}><b className={p.cls} /> {p.label} {(p.value / total * 100).toFixed(1)}%</span>)}</div>
      {caption && <p className="chart-caption">{caption}</p>}
    </div>
  );
}

export function BarRows({ rows, max, fmt = (v) => v, suffix = '' }) {
  const m = max ?? Math.max(1e-9, ...rows.map((r) => r.value));
  return <div className="inv-bars">{rows.map((r) => <div key={r.label} className="tw-bar-row"><span>{r.label}</span><b>{fmt(r.value)}{suffix}</b><div className="tw-bar"><i style={{ width: `${Math.min(100, (r.value / m) * 100)}%` }} /></div></div>)}</div>;
}
export { satLabel };
