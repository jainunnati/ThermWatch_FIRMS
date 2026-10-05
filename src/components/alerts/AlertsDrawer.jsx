import React, { useMemo, useState } from 'react';
import Drawer from '../ui/Drawer.jsx';
import Empty from '../ui/Empty.jsx';
import { ClassChip, SeverityChip } from '../ui/Chips.jsx';
import { useApp } from '../../context/AppContext.jsx';
import { fmtUtc, fmtCoord } from '../../utils/format.js';

const PAGE = 40;
const TABS = [
  { key: 'new', label: 'New' },
  { key: 'acknowledged', label: 'Acknowledged' },
  { key: 'all', label: 'All' },
];

function facilityLabel(e, facilitiesById) {
  if (!e?.facility) return e?.real?.source ? 'No documented facility within 5 km' : 'Not packaged for this ranked source';
  const f = e.facility.id ? facilitiesById.get(e.facility.id) : null;
  const d = Number.isFinite(e.facility.distanceKm) ? ` · ${e.facility.distanceKm.toFixed(2)} km (context, not cause)` : '';
  return `${f?.name || e.facility.name}${d}`;
}

function AlertItem({ alert, facilitiesById, onView, onInvestigate, onAck }) {
  const e = alert.event;
  return (
    <article className={`alert-item ${alert.state === 'new' ? 'is-new' : ''}`}>
      <header className="alert-item__head">
        <span className="alert-item__id">{alert.eventId}</span>
        <span className="alert-item__time">#{alert.rank}{alert.createdUtc ? ` · last seen ${fmtUtc(alert.createdUtc)}` : ''}</span>
      </header>
      {e ? (
        <>
          <div className="chip-row">
            <ClassChip classKey={e.classification.key} />
            <SeverityChip severity={e.severity} />
            {e.persistentSource && <span className="chip-tag chip-tag--pihs">PIHS candidate</span>}
          </div>
          <dl className="kv kv--tight">
            <dt>Facility</dt><dd>{facilityLabel(e, facilitiesById)}</dd>
            <dt>Location</dt><dd>{e.locationName}<br /><span className="mono">{fmtCoord(e.latitude, e.longitude)}</span></dd>
            <dt>Reason</dt><dd>{alert.reason || '—'}</dd>
            <dt>Cause</dt><dd>Not confirmed</dd>
            <dt>Status</dt><dd>{alert.state === 'new' ? 'New' : 'Acknowledged'}</dd>
          </dl>
        </>
      ) : (
        <p className="muted small">The event for this alert is not in the loaded data.</p>
      )}
      <div className="btn-row">
        <button type="button" className="btn" disabled={!e} onClick={() => onView(alert.eventId)}>View on map</button>
        <button type="button" className="btn btn--primary" disabled={!e} onClick={() => onInvestigate(alert.eventId)}>Investigate</button>
        {alert.state === 'new' && <button type="button" className="btn btn--ghost" onClick={() => onAck(alert.id)}>Acknowledge</button>}
      </div>
    </article>
  );
}

export default function AlertsDrawer() {
  const { section, setSection, alerts, facilities, viewOnMap, openInvestigation, acknowledgeAlert, load } = useApp();
  const [tab, setTab] = useState('new');
  const [limit, setLimit] = useState(PAGE);
  const facilitiesById = useMemo(() => new Map(facilities.map((f) => [f.id, f])), [facilities]);
  const list = useMemo(() => (tab === 'all' ? alerts : alerts.filter((a) => a.state === tab)), [alerts, tab]);

  return (
    <Drawer open={section === 'alerts'} onClose={() => setSection(null)} title="Alerts">
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? 'is-on' : ''} onClick={() => { setTab(t.key); setLimit(PAGE); }}>
            {t.label} <span className="tabs__count">{t.key === 'all' ? alerts.length : alerts.filter((a) => a.state === t.key).length}</span>
          </button>
        ))}
      </div>
      <p className="drawer-note">Alerts are the real sources with Alert Priority tier HIGH (alert-priority-v1: HIGH ≥ 0.60), one per source, in rank order. Alert Priority is a triage ranking, not a probability of fire or industrial cause. An alert is a prompt to investigate, not a confirmed incident.</p>
      {load.status === 'loading' && <Empty title="Loading alerts…" />}
      {load.status !== 'loading' && list.length === 0 && (
        <Empty title={tab === 'new' ? 'No new alerts' : 'Nothing here'}>
          {tab === 'new' ? 'New alerts appear here. The map never moves on its own — use View on map.' : null}
        </Empty>
      )}
      {list.slice(0, limit).map((a) => (
        <AlertItem key={a.id} alert={a} facilitiesById={facilitiesById} onView={viewOnMap} onInvestigate={openInvestigation} onAck={acknowledgeAlert} />
      ))}
      {list.length > limit && (
        <button type="button" className="text-btn text-btn--block" onClick={() => setLimit((l) => l + PAGE)}>Show more ({list.length - limit} remaining)</button>
      )}
    </Drawer>
  );
}
