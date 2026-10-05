import React, { useMemo, useState } from 'react';
import Drawer from '../ui/Drawer.jsx';
import Empty from '../ui/Empty.jsx';
import { useApp } from '../../context/AppContext.jsx';
import { classificationOf } from '../../config/classification.js';
import { fmtUtc, fmtRelative, fmtNum } from '../../utils/format.js';
import { latestAcquisition } from '../../utils/time.js';

const PAGE = 60;

function DetectionRow({ e, onOpen, onView }) {
  const t = latestAcquisition(e);
  return (
    <li className="feed-row">
      <span className="swatch" style={{ background: classificationOf(e.classification.key).color }} />
      <button type="button" className="feed-row__main" onClick={() => onOpen(e.id)}>
        <span className="feed-row__title">{e.locationName}</span>
        <span className="feed-row__sub">
          <span className="mono">{e.id}</span> · {e.classification.label} · FRP {fmtNum(e.frpSummary?.max, 1)} MW
        </span>
      </button>
      <span className="feed-row__time mono">{t ? fmtUtc(new Date(t).toISOString()).slice(11) : '—'}</span>
      <button type="button" className="icon-btn icon-btn--sm" title="View on map" aria-label={`View ${e.id} on map`} onClick={() => onView(e.id)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="2.4" fill="currentColor" /><circle cx="8" cy="8" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.3" /></svg>
      </button>
    </li>
  );
}

export default function ActivityDrawer() {
  const { section, setSection, timeMatched, activity, eventsById, openInvestigation, viewOnMap, time } = useApp();
  const [tab, setTab] = useState('detections');
  const [limit, setLimit] = useState(PAGE);

  const grouped = useMemo(() => {
    const sorted = [...timeMatched].sort((a, b) => (latestAcquisition(b) || 0) - (latestAcquisition(a) || 0)).slice(0, limit);
    const groups = [];
    for (const e of sorted) {
      const t = latestAcquisition(e);
      const day = t ? new Date(t).toISOString().slice(0, 10) : 'Unknown date';
      if (!groups.length || groups[groups.length - 1].day !== day) groups.push({ day, items: [] });
      groups[groups.length - 1].items.push(e);
    }
    return groups;
  }, [timeMatched, limit]);

  return (
    <Drawer open={section === 'activity'} onClose={() => setSection(null)} title="Activity">
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === 'detections'} className={tab === 'detections' ? 'is-on' : ''} onClick={() => setTab('detections')}>
          Detections <span className="tabs__count">{timeMatched.length}</span>
        </button>
        <button type="button" role="tab" aria-selected={tab === 'investigated'} className={tab === 'investigated' ? 'is-on' : ''} onClick={() => setTab('investigated')}>
          Investigated <span className="tabs__count">{activity.length}</span>
        </button>
      </div>

      {tab === 'detections' && (
        <>
          <p className="drawer-note">
            Events with acquisitions in the {time.mode === 'live' ? 'current' : 'historical'} time range, newest first, grouped by UTC day. Days without rows had no recorded acquisition — not zero activity.
          </p>
          {grouped.length === 0 && <Empty title="No acquisitions in this time range">Widen the range in the time control. Satellite observation is intermittent.</Empty>}
          {grouped.map((g) => (
            <div key={g.day} className="feed-group">
              <h3 className="feed-group__day">{g.day}</h3>
              <ul className="feed">
                {g.items.map((e) => <DetectionRow key={e.id} e={e} onOpen={openInvestigation} onView={viewOnMap} />)}
              </ul>
            </div>
          ))}
          {timeMatched.length > limit && (
            <button type="button" className="text-btn text-btn--block" onClick={() => setLimit((l) => l + PAGE)}>Show more ({timeMatched.length - limit} remaining)</button>
          )}
        </>
      )}

      {tab === 'investigated' && (
        <>
          {activity.length === 0 && <Empty title="No investigations yet">Events you open for investigation appear here for quick return.</Empty>}
          <ul className="feed">
            {activity.map((a) => {
              const e = eventsById.get(a.eventId);
              return (
                <li key={a.id} className="feed-row">
                  <span className="swatch" style={{ background: e ? classificationOf(e.classification.key).color : '#94A3B8' }} />
                  <button type="button" className="feed-row__main" onClick={() => openInvestigation(a.eventId)} disabled={!e}>
                    <span className="feed-row__title">{e?.locationName || a.eventId}</span>
                    <span className="feed-row__sub"><span className="mono">{a.eventId}</span>{a.atUtc ? ` · opened ${fmtRelative(a.atUtc)}` : ''}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Drawer>
  );
}
