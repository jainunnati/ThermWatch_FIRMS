import React from 'react';
import { useApp } from '../../context/AppContext.jsx';
import { CLASSIFICATIONS, CLASSIFICATION_ORDER } from '../../config/classification.js';
import { SEVERITY_ORDER, SEVERITIES } from '../../config/severity.js';
import { SeveritySwatch } from '../ui/Swatches.jsx';
import { fmtUtc } from '../../utils/format.js';

export default function MapLegend() {
  const { visibleEvents, timeMatched, events, time, load, store, selectedEventId, latestAcquisitionMs } = useApp();
  const untimed = events.filter((e) => !e.observations.length).length;
  const selectedHidden = selectedEventId && !visibleEvents.some((e) => e.id === selectedEventId);

  return (
    <div className="legend" aria-label="Map legend and status">
      <div className="legend__row">
        <span className="legend__head">Colour = source</span>
        {CLASSIFICATION_ORDER.map((k) => (
          <span key={k} className="legend__item"><span className="swatch" style={{ background: CLASSIFICATIONS[k].color }} />{CLASSIFICATIONS[k].label}</span>
        ))}
        <span className="legend__sep" aria-hidden="true" />
        <span className="legend__head">Size / pulse = severity</span>
        {SEVERITY_ORDER.map((k) => (
          <span key={k} className="legend__item"><SeveritySwatch severity={k} />{SEVERITIES[k].label}</span>
        ))}
      </div>
      <div className="legend__row legend__status">
        <span className={`status-pill status-pill--${time.mode}`}>{time.mode === 'live' ? 'Current' : 'Historical'}</span>
        <span className="status-pill status-pill--api" title={store ? `Validated historical FIRMS data ${store.contract.data_window} · ${store.liveStatus.text}` : ''}>Real data</span>
        {load.status === 'loading' && <span>Loading data…</span>}
        {load.status === 'ready' && (
          <span>
            <b>{visibleEvents.length}</b> of {timeMatched.length} sources in time range shown · {events.length} loaded
          </span>
        )}
        {latestAcquisitionMs && <span>Latest acquisition {fmtUtc(new Date(latestAcquisitionMs).toISOString())}</span>}
        {selectedHidden && <span className="legend__warn">Selected event is outside the current filters (shown pinned).</span>}
        {untimed > 0 && (time.mode === 'historical' || time.liveWindowHours != null) && <span className="legend__warn">{untimed.toLocaleString()} ranked sources have no packaged timestamps; shown only under “All available”.</span>}
        {load.skippedInvalid > 0 && <span className="legend__warn">{load.skippedInvalid} record(s) skipped: invalid coordinates.</span>}
      </div>
    </div>
  );
}
