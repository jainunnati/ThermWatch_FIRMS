import React from 'react';
import { Step, KV, Note, Tile, Tiles } from '../intel/parts.jsx';
import { COPY, pct } from '../../intel/investigationModel.js';

export const POINT_SECTIONS = ['id', 'obs', 'persist', 'context', 'ml', 'limits'];

/**
 * Investigation for a real ranked source whose full event-level record is not
 * packaged in this build (contract cap: top-300 full records of the top-3,000
 * ranked map layer). Shows only the real fields that exist; nothing is estimated.
 */
export default function PointInvestigation({ event, contract, open, onToggle, printMode = false }) {
  const p = event.real.point; const en = event.real.enrichment || {};
  const S = (id, n, title, status, summary, children) => <Step key={id} id={`inv-${id}`} n={n} title={title} status={status} summary={summary} open={open?.has(id)} onToggle={() => onToggle?.(id)} printMode={printMode}>{children}</Step>;
  const ml = contract.ml_status; const st = contract.system_stats;
  return (
    <div className="steps">
      {S('id', 1, 'Source identity', 'complete', 'A real persistent spatial source from the ThermWatch source registry.', (
        <KV rows={[
          ['Source ID', <span className="mono">{p.source_id}</span>],
          ['Alert queue rank', `#${event.rank} of ${st.sources_monitored.toLocaleString()} monitored sources (by Alert Priority)`],
          ['Latitude / longitude', <span className="mono">{event.latitude.toFixed(5)}, {event.longitude.toFixed(5)}</span>],
          ['Alert Priority tier', `${p.tier} (alert-priority-v1; HIGH ≥ 0.60 · MEDIUM ≥ 0.40)`],
          ['Data window', `${contract.data_window} · run ${contract.pipeline_run_id} · ${contract.pipeline_status}`],
        ]} />
      ))}
      {S('obs', 2, 'Observations', en.n_obs != null ? 'complete' : 'partial', 'Observation count from the real source registry (deduplicated FIRMS observations associated to this source).', (
        <Tiles><Tile v={en.n_obs != null ? en.n_obs.toLocaleString() : 'n/a'} t="Registry observations" hint="registry_index.csv.gz" /></Tiles>
      ))}
      {S('persist', 3, 'Persistence & Activity', p.pihs ? 'complete' : 'partial', 'PIHS (pihs-v1) is a transparent rule-based persistence detector, not ground truth.', (<>
        <div className={`inv-callout ${p.pihs ? 'inv-callout--pihs' : ''}`}>
          <div><div className="inv-callout__k">PIHS detector (pihs-v1)</div><div className="inv-callout__v">{p.pihs ? 'PIHS CANDIDATE' : 'NOT A PIHS CANDIDATE'}</div></div>
          {en.pihs_score != null && <div><div className="inv-callout__k">PIHS score</div><div className="inv-callout__v">{en.pihs_score} / 8</div></div>}
        </div>
        {p.pihs && <Tiles><Tile v={en.active_days ?? 'n/a'} t="Active days" /><Tile v={pct(en.night_frac, 1)} t="Night share" /></Tiles>}
        <Note>{COPY.persistenceNote}</Note>
      </>))}
      {S('context', 4, 'Events, thermal, facility, coverage', 'partial', null, (<>
        <Note tone="warn">The event-level record (events, FRP/TI4 statistics, facility distance, heuristic attribution, per-window coverage and Alert Priority component breakdown) is packaged only for the top 300 sources in this build. It is not shown rather than estimated.</Note>
        <KV rows={[['Run-wide coverage statement', contract.coverage_status], ['Coverage rule', COPY.coverageRule]]} />
      </>))}
      {S('ml', 5, 'Machine learning', 'context', null, (
        <KV rows={[['Status', `${ml.state} — ${ml.message}`], ['Gate', ml.blocked_because], ['Fallback', `${ml.fallback} (heuristic, not a classifier)`]]} />
      ))}
      {S('limits', 6, 'Limitations & caveats', 'info', null, (
        <ul className="inv-list">
          <li>{COPY.alertNote}</li>
          <li>PIHS is a transparent rule-based detector, not ground truth. A satellite detection is not a confirmed fire.</li>
          <li>{COPY.coverageRule}</li>
          <li>Cause: {COPY.cause}.</li>
          <li>No incident found does not mean no incident occurred.</li>
        </ul>
      ))}
    </div>
  );
}
