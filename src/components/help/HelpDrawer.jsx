import React from 'react';
import Drawer from '../ui/Drawer.jsx';
import { useApp } from '../../context/AppContext.jsx';
import { CLASSIFICATIONS, CLASSIFICATION_ORDER } from '../../config/classification.js';
import { SEVERITIES, SEVERITY_ORDER } from '../../config/severity.js';
import { SeveritySwatch } from '../ui/Swatches.jsx';

function Topic({ title, children }) {
  return (
    <section className="help-topic">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

export default function HelpDrawer() {
  const { section, setSection, viewOnMap, openInvestigation, store, alerts } = useApp();
  const c = store?.contract;
  const st = c?.system_stats;
  const top = alerts[0];

  return (
    <Drawer open={section === 'help'} onClose={() => setSection(null)} title="Help">
      <div className="help">
        <Topic title="ThermWatch">
          <p>ThermWatch turns intermittent NASA FIRMS satellite thermal observations into persistent sources, events and explainable investigation priorities. It prioritises what to investigate. It does not confirm fires, accidents or causes.</p>
          <p className="help-flow">FIRMS observations → validation &amp; dedup → persistent sources → events → PIHS persistence → facility context → heuristic attribution → coverage → Alert Priority → investigation → report</p>
          {top && (
            <button type="button" className="btn btn--primary" onClick={() => { viewOnMap(top.eventId); openInvestigation(top.eventId); setSection(null); }}>
              Open the top-ranked real alert ({top.eventId})
            </button>
          )}
        </Topic>

        <Topic title="Real data in this build">
          {st ? (
            <ul className="legend-list">
              <li><b>{st.valid_observations.toLocaleString()}</b> valid FIRMS observations ({st.firms_observations.toLocaleString()} ingested)</li>
              <li><b>{st.physical_sources.toLocaleString()}</b> real sources · <b>{st.events.toLocaleString()}</b> real events</li>
              <li><b>{st.pihs_candidates}</b> PIHS candidates · <b>{st.alerts_high}</b> HIGH / <b>{st.alerts_medium}</b> MEDIUM Alert Priority</li>
              <li>Window {c.data_window} · status {c.pipeline_status} · run <span className="mono">{c.pipeline_run_id}</span></li>
              <li>Map: top {c.map_points.length.toLocaleString()} sources by Alert Priority; full event-level records for the top {c.sources.length}.</li>
              <li>Live feed: {store.liveStatus.text.replace(/^[○◐●]\s*/, '')}</li>
              <li>ML: <b>{c.ml_status.state}</b> — {c.ml_status.message}</li>
            </ul>
          ) : <p className="muted">Loading real data…</p>}
        </Topic>

        <Topic title="FIRMS">
          <p>NASA FIRMS lists satellite thermal detections (here VIIRS 375 m on S-NPP, NOAA-20 and NOAA-21) with acquisition time, location, FRP and brightness temperature. Polar-orbiting sensors pass over a location a few times a day, so FIRMS is discrete, intermittent observation — not continuous monitoring. A detection is not a ground-confirmed fire.</p>
        </Topic>

        <Topic title="Sources and events">
          <p>A <b>source</b> (SRC-…) is a set of physically deduplicated observations associated to one location. An <b>event</b> (EVT-…) is a spatially and temporally associated group of a source's observations. An event's span is the gap between satellite snapshots; it does not imply continuous burning.</p>
        </Topic>

        <Topic title="PIHS (persistence)">
          <p>pihs-v1 is a transparent rule-based detector: ≥ 20 active days (required), ≥ 60% night detections (required), detections within 750 m (required), plus multi-day and repeated-event points; score out of 8. It is a triage signal, not ground truth, and not proof of industrial activity.</p>
        </Topic>

        <Topic title="Facility context and attribution">
          <p>Facility points are Global Energy Monitor registry context. Attribution weights are a proximity-driven heuristic (Attribution MVP v1), <b>not calibrated probabilities</b>. Cause is always reported as <b>Not confirmed</b>.</p>
        </Topic>

        <Topic title="Coverage">
          <p>NOAA-20/NOAA-21 coverage is complete for the window; S-NPP has explicitly unverified days. Unknown coverage is never interpreted as “no fire”.</p>
        </Topic>

        <Topic title="Alert Priority">
          <p>alert-priority-v1 = 0.35 PIHS + 0.25 recency + 0.15 intensity jump + 0.15 persistence + 0.10 facility context. HIGH ≥ 0.60, MEDIUM ≥ 0.40. It is a ranking for investigators, not a probability of fire or industrial cause.</p>
        </Topic>

        <Topic title="Machine learning">
          <p>The supervised classifier is <b>{c?.ml_status.state || 'READY_NOT_TRAINED'}</b>: the ground-truth gate ({c?.ml_status.blocked_because || '0 defensible labels'}) is not satisfied, so no classifier probabilities or accuracy figures are shown.</p>
        </Topic>

        <Topic title="What the map shows">
          <p>By default the map shows <b>alert points</b> only: the real sources with Alert Priority HIGH or MEDIUM. These are the locations ThermWatch considers worth investigating. In <b>Layers</b>, turn on <b>Low</b> to add the other ranked monitored sources, and <b>Facilities / OSM</b> to add the documented facility registry.</p>
          <p>The map holds the top {c ? c.map_points.length.toLocaleString() : '3,000'} sources by Alert Priority. The full registry of {st ? st.physical_sources.toLocaleString() : '1,056,161'} sources stays in the pipeline (<code>data-pipeline/intel_v1/live_indexes/registry_index.csv.gz</code>) and is not drawn as raw points. A FIRMS observation is not an alert; Alert Priority is a triage ranking, not model confidence.</p>
          <p>Search accepts source IDs (e.g. <span className="mono">SRC-f10396fc99</span>), facility names and places (e.g. Hazira), and facility types (e.g. steel, coal). Choosing a facility pins it and its ranked sources within 5 km.</p>
        </Topic>

        <Topic title="Marker colour">
          <ul className="legend-list">
            {CLASSIFICATION_ORDER.map((k) => (
              <li key={k}><span className="swatch" style={{ background: CLASSIFICATIONS[k].color }} />{CLASSIFICATIONS[k].label}</li>
            ))}
          </ul>
          <p>Colour shows the heuristic facility-attribution context only (steel/metal, thermal power or LNG/gas within 5 km → Industrial). The real pipeline does not classify agricultural or natural fires, so those categories stay empty; everything else is Unknown / Other. Colour never changes with priority.</p>
        </Topic>

        <Topic title="Size and pulse">
          <ul className="legend-list">
            {SEVERITY_ORDER.map((k) => (
              <li key={k}><SeveritySwatch severity={k} /><b>{SEVERITIES[k].label}</b> — {SEVERITIES[k].description}</li>
            ))}
          </ul>
          <p>Size and pulse follow the real Alert Priority tier. Dimmed markers are outside the current time filter and never pulse.</p>
        </Topic>

        <Topic title="Time control">
          <p>Use <b>Historical</b> in the time control to pick a UTC range (e.g. one month); only sources with a real event observation inside the range are drawn. Filters use real event acquisition timestamps (UTC), packaged for the top-300 full records. Ranked sources without packaged timestamps appear only under “All available” — no time is ever invented. An empty range means nothing was recorded, not that nothing happened. The map only moves when you use View on map or search.</p>
        </Topic>

        <Topic title="Investigation report">
          <p>Open any source and use <b>Print investigation</b> for an A4 report generated from the same real record shown on screen: identity, observations, persistence &amp; PIHS rule check, every event, thermal statistics, spatial behaviour, facility context &amp; attribution, coverage, Alert Priority breakdown, ML status and limitations.</p>
        </Topic>
      </div>
    </Drawer>
  );
}
