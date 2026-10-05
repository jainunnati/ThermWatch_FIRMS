import React from 'react';
import { InvestigationContent } from '../intel/InvestigationView.jsx';
import PointInvestigation from './PointInvestigation.jsx';
import { COPY, utc } from '../../intel/investigationModel.js';
import { fmtCoord } from '../../utils/format.js';

/**
 * Print-only A4 investigation report. Hidden on screen; shown by print.css while
 * the rest of the application is hidden. Reuses the on-screen investigation
 * content (every step expanded, every event listed) so it cannot drift.
 */
export default function PrintReport({ event, inv, contract, generatedAt = new Date().toISOString() }) {
  return (
    <article className="report" data-testid="print-report" data-source-id={event.id}>
      <header className="report__head">
        <div>
          <p className="report__brand">ThermWatch · SIH26162</p>
          <h1 className="report__title">Source investigation report</h1>
        </div>
        <dl className="report__meta">
          <div><dt>Source</dt><dd className="mono">{event.id}</dd></div>
          <div><dt>Generated</dt><dd>{utc(generatedAt)}</dd></div>
          <div><dt>Data status</dt><dd>Historical (validated) data to {String(contract.data_timestamp).slice(0, 10)} · run {contract.pipeline_run_id}</dd></div>
        </dl>
      </header>
      <p className="report__warning">
        VALIDATED HISTORICAL DATA — real FIRMS-derived ThermWatch source{event.rank ? ` (Alert Priority rank #${event.rank})` : ''} at {fmtCoord(event.latitude, event.longitude, 5)}, not a live incident finding. Cause: {COPY.cause}. Alert Priority is a triage ranking, not a probability.
        {!inv && ' Event-level detail is not packaged for this ranked source; only real registry/PIHS fields are reported.'}
      </p>
      {inv ? <InvestigationContent inv={inv} printMode /> : <PointInvestigation event={event} contract={contract} printMode />}
      <footer className="report__foot">
        ThermWatch is investigation-prioritisation decision support. A satellite detection is not a confirmed fire, persistence is not proof of industrial activity, attribution weights are heuristic, unknown coverage is not interpreted as no fire, and ML is {contract.ml_status.state}.
      </footer>
    </article>
  );
}
