import React, { useEffect, useMemo, useRef, useState } from 'react';
import Drawer from '../ui/Drawer.jsx';
import Empty from '../ui/Empty.jsx';
import { BehaviourChip } from '../ui/Chips.jsx';
import { useApp } from '../../context/AppContext.jsx';
import { INDUSTRIAL_TYPES, INDUSTRIAL_TYPE_ORDER } from '../../config/industrialTypes.js';
import { fmtCoord, fmtUtc } from '../../utils/format.js';
import { latestAcquisition } from '../../utils/time.js';

function FacilityCard({ f, events, selected, onShow, onOpenEvent, cardRef }) {
  const latest = events.reduce((best, e) => {
    const t = latestAcquisition(e);
    return t !== null && (!best || t > best.t) ? { t, e } : best;
  }, null);
  const top = events[0] || null; // highest Alert Priority rank within 5 km
  const hp = f.historicalProfile;
  return (
    <article ref={cardRef} className={`facility ${selected ? 'is-selected' : ''}`}>
      <header>
        <h3 className="facility__name">{f.name}</h3>
        <p className="facility__type">{f.type}{f.typeDetail ? ` — ${f.typeDetail}` : ''}</p>
      </header>
      <dl className="kv kv--tight">
        <dt>Location</dt><dd>{f.locationLabel ? `${f.locationLabel} · ` : ''}<span className="mono">{fmtCoord(f.latitude, f.longitude)}</span></dd>
        <dt>Point source</dt><dd>{f.provenance?.point || '—'}</dd>
        {f.provenance?.polygon && (<><dt>Geometry</dt><dd>{f.provenance.polygon}</dd></>)}
        <dt>Ranked sources ≤ 5 km</dt><dd>{events.length ? <><span className="mono">{events.slice(0, 6).map((e) => `${e.id} (#${e.rank} ${String(e.priority).toUpperCase()})`).join(', ')}</span>{events.length > 6 ? ` +${events.length - 6} more` : ''}</> : 'None among the top-3,000 ranked sources'}</dd>
        <dt>Latest observation</dt><dd>{latest ? fmtUtc(new Date(latest.t).toISOString()) : 'No attributed observation'}</dd>
        <dt>Historical behaviour</dt>
        <dd>
          {hp ? (
            <>Profile <span className="mono">{hp.profile_version}</span> · stratum {hp.stratum} · {hp.eligible_detections} eligible detections · footprint {hp.footprint?.median_spread_m} m median spread <em>({hp.label})</em></>
          ) : (
            'No facility historical profile in the real pipeline output'
          )}
        </dd>
      </dl>
      {latest && <div className="facility__status"><span className="muted small">Latest event behaviour:</span> <BehaviourChip behaviour={latest.e.behaviour} /></div>}
      <div className="btn-row">
        <button type="button" className="btn" onClick={() => onShow(f)}>Show on map</button>
        {top && <button type="button" className="btn btn--primary" onClick={() => onOpenEvent(top.id)}>Investigate top nearby</button>}
      </div>
    </article>
  );
}

export default function FacilitiesDrawer() {
  const { section, setSection, facilities, events, focusLocation, openInvestigation, selectedFacilityId, setSelectedFacilityId } = useApp();
  const [q, setQ] = useState('');
  const [types, setTypes] = useState(() => new Set(INDUSTRIAL_TYPE_ORDER));
  const selectedRef = useRef(null);

  // Real ranked sources within 5 km of each facility (computed from real coordinates in realStore).
  const eventsById = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);
  const eventsByFacility = useMemo(() => new Map(facilities.map((f) => [f.id, (f.nearbySources || []).map((n) => eventsById.get(n.id)).filter(Boolean)])), [facilities, eventsById]);

  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return facilities.filter((f) => types.has(f.typeKey) && (!needle || `${f.name} ${f.type} ${f.locationLabel || ''}`.toLowerCase().includes(needle)));
  }, [facilities, q, types]);

  useEffect(() => {
    if (section === 'facilities' && selectedFacilityId) selectedRef.current?.scrollIntoView({ block: 'nearest' });
  }, [section, selectedFacilityId]);

  const toggleType = (k) => setTypes((prev) => {
    const next = new Set(prev);
    if (next.has(k)) next.delete(k); else next.add(k);
    return next;
  });

  return (
    <Drawer open={section === 'facilities'} onClose={() => setSection(null)} title="Facilities">
      <div className="drawer-tools">
        <input type="search" className="input" placeholder="Search facilities" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search facilities" />
        <div className="chip-row">
          {INDUSTRIAL_TYPE_ORDER.map((k) => (
            <button key={k} type="button" className={`chip ${types.has(k) ? 'is-on' : ''}`} aria-pressed={types.has(k)} onClick={() => toggleType(k)}>
              {INDUSTRIAL_TYPES[k].label}
            </button>
          ))}
        </div>
      </div>
      <p className="drawer-note">{facilities.length} documented facilities (Global Energy Monitor registry points: coal power, oil &amp; gas, steel). Facility proximity is contextual evidence, not ground truth and not proof of cause.</p>
      {list.length === 0 && <Empty title="No facilities match">Clear the search or re-enable facility types.</Empty>}
      {list.map((f) => (
        <FacilityCard
          key={f.id}
          f={f}
          events={eventsByFacility.get(f.id) || []}
          selected={f.id === selectedFacilityId}
          cardRef={f.id === selectedFacilityId ? selectedRef : undefined}
          onShow={(fac) => { setSelectedFacilityId(fac.id); focusLocation(fac.latitude, fac.longitude, 14); }}
          onOpenEvent={openInvestigation}
        />
      ))}
    </Drawer>
  );
}
