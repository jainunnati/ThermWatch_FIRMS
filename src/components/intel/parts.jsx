import React from 'react';

// Presentational parts for the real-data investigation (adapted from the earlier investigation parts;
// no provenance-label dependency).
export const STEP_STATUS = {
  complete: { label: 'Complete', tone: 'ok' },
  partial: { label: 'Partial', tone: 'warn' },
  context: { label: 'Context only', tone: 'muted' },
  info: { label: 'Reference', tone: 'muted' },
};

export function Step({ n, id, title, status = 'complete', summary, children, open, onToggle, printMode, major }) {
  const s = STEP_STATUS[status] || STEP_STATUS.complete;
  const expanded = printMode || open;
  return (
    <section id={id} className={`step step--${s.tone} ${expanded ? 'is-open' : ''}${major ? ' step--major' : ''}`} aria-labelledby={`${id}-title`}>
      <div className="step__rail" aria-hidden="true"><span className="step__num">{n}</span></div>
      <div className="step__main">
        {printMode ? (
          <header className="step__head"><h3 id={`${id}-title`} className="step__title">{title}</h3><span className={`step__status step__status--${s.tone}`}>{s.label}</span></header>
        ) : (
          <button type="button" className="step__head" aria-expanded={expanded} onClick={onToggle}>
            <h3 id={`${id}-title`} className="step__title">{title}</h3><span className={`step__status step__status--${s.tone}`}>{s.label}</span>
            <svg className="step__chev" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          </button>
        )}
        {summary && <p className="step__summary">{summary}</p>}
        {expanded && <div className="step__body">{children}</div>}
      </div>
    </section>
  );
}

export function KV({ rows }) {
  return (
    <dl className="kv">
      {rows.filter(Boolean).map(([k, v]) => (<React.Fragment key={k}><dt>{k}</dt><dd>{v}</dd></React.Fragment>))}
    </dl>
  );
}

export function Table({ columns, rows, caption }) {
  if (!rows?.length) return null;
  return (
    <div className="table-wrap">
      <table className="table">
        {caption && <caption>{caption}</caption>}
        <thead><tr>{columns.map((c) => <th key={c.key} scope="col" className={c.num ? 'num' : ''}>{c.label}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={r.__key ?? i}>{columns.map((c) => <td key={c.key} className={c.num ? 'num' : ''}>{c.render ? c.render(r) : r[c.key] ?? '—'}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

export function Note({ children, tone = 'info' }) { return <p className={`note note--${tone}`}>{children}</p>; }
export function Sub({ title, children }) { return <div className="sub"><h4 className="sub__title">{title}</h4>{children}</div>; }
export function Tile({ v, t, hint, tone }) {
  return <div className={`inv-tile${tone ? ` inv-tile--${tone}` : ''}`}><div className="inv-tile__v">{v}</div><div className="inv-tile__t">{t}</div>{hint && <div className="inv-tile__h">{hint}</div>}</div>;
}
export function Tiles({ children }) { return <div className="inv-tiles">{children}</div>; }
