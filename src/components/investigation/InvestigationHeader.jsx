import React from 'react';
import { ClassChip, SeverityChip, BehaviourChip } from '../ui/Chips.jsx';
import { DATA_KINDS } from '../../config/provenance.js';
import { industrialTypeLabel } from '../../config/industrialTypes.js';
import { fmtCoord, fmtUtc } from '../../utils/format.js';

/** V7 investigation header (banner + identity + chips + at-a-glance), filled from the real source. */
export default function InvestigationHeader({ event, facility }) {
  const kind = DATA_KINDS[event.provenance.kind];
  const s = event.real?.source;
  const fac = facility?.name || event.facility?.name;
  return (
    <>
      {kind?.banner && (
        <div className={`banner banner--${event.provenance.kind}`} role="note">
          <strong>{kind.label}</strong>
          <span> {kind.banner} Cause: Not confirmed.</span>
        </div>
      )}
      <header className="inv__head">
        <p className="inv__id mono">{event.id}{event.rank ? ` · Alert Priority rank #${event.rank}` : ''}</p>
        <h2 className="inv__title">{event.locationName}</h2>
        <p className="inv__coords mono">{fmtCoord(event.latitude, event.longitude, 5)}</p>
        <div className="chip-row">
          <ClassChip classKey={event.classification.key} />
          <SeverityChip severity={event.severity} />
          <BehaviourChip behaviour={event.behaviour} />
          {event.persistentSource ? <span className="chip-tag chip-tag--pihs">PIHS candidate</span> : <span className="chip-tag chip-tag--muted">PIHS: no</span>}
          <span className="chip-tag chip-tag--muted">Cause: Not confirmed</span>
        </div>
        <dl className="glance">
          <div><dt>Attribution context</dt><dd>{event.classification.industrialType ? `${industrialTypeLabel(event.classification.industrialType)} (heuristic)` : 'Unknown / not attributed'}</dd></div>
          <div><dt>Nearest facility</dt><dd>{fac ? `${fac}${Number.isFinite(event.facility?.distanceKm) ? ` · ${event.facility.distanceKm.toFixed(2)} km` : ''}` : s ? 'None within 5 km' : 'Not packaged'}</dd></div>
          <div><dt>Alert Priority</dt><dd>{event.priority ? event.priority.toUpperCase() : '—'}{event.real?.alertScore != null ? ` · ${event.real.alertScore.toFixed(4)}` : ''}</dd></div>
          <div><dt>Last seen</dt><dd>{fmtUtc(event.endUtc)}</dd></div>
        </dl>
        <p className="inv__sep-note">Persistence (PIHS), facility context, heuristic attribution, coverage and Alert Priority are separate results with separate evidence. Alert Priority is a triage ranking, not a probability.</p>
      </header>
    </>
  );
}
