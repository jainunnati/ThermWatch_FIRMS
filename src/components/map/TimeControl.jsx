import React, { useEffect, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext.jsx';
import { LIVE_WINDOWS } from '../../config/app.js';
import { historicalRangeError, toUtcInput } from '../../utils/time.js';
import { fmtUtc } from '../../utils/format.js';

export default function TimeControl() {
  const { time, setTime, latestAcquisitionMs } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const err = historicalRangeError(time);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const setMode = (mode) => {
    if (mode === 'historical' && !time.fromUtc && !time.toUtc && latestAcquisitionMs) {
      // Start from the last 7 days of available acquisitions, not from "now".
      setTime((t) => ({ ...t, mode, fromUtc: toUtcInput(latestAcquisitionMs - 7 * 86400000), toUtc: toUtcInput(latestAcquisitionMs + 60000) }));
    } else {
      setTime((t) => ({ ...t, mode }));
    }
  };

  const quick = (days) => {
    const end = latestAcquisitionMs ?? Date.now();
    setTime((t) => ({ ...t, mode: 'historical', fromUtc: toUtcInput(end - days * 86400000), toUtc: toUtcInput(end + 60000) }));
  };

  const summary =
    time.mode === 'live'
      ? LIVE_WINDOWS.find((w) => w.value === time.liveWindowHours)?.label || 'All available'
      : `${time.fromUtc ? time.fromUtc.replace('T', ' ') : '…'} → ${time.toUtc ? time.toUtc.replace('T', ' ') : '…'} UTC`;

  return (
    <div className="time-control" ref={ref}>
      <button type="button" className={`map-btn time-btn time-btn--${time.mode} ${open ? 'is-active' : ''}`} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className={`mode-dot mode-dot--${time.mode}`} aria-hidden="true" />
        <span className="time-btn__mode">{time.mode === 'live' ? 'Current' : 'Historical'}</span>
        <span className="time-btn__summary">{summary}</span>
      </button>

      {open && (
        <div className="time-panel" role="dialog" aria-label="Date and time filter">
          <div className="segmented segmented--block" role="radiogroup" aria-label="Time mode">
            <button type="button" role="radio" aria-checked={time.mode === 'live'} className={time.mode === 'live' ? 'is-on' : ''} onClick={() => setMode('live')}>Current</button>
            <button type="button" role="radio" aria-checked={time.mode === 'historical'} className={time.mode === 'historical' ? 'is-on' : ''} onClick={() => setMode('historical')}>Historical</button>
          </div>

          {time.mode === 'live' ? (
            <>
              <label className="field">
                <span className="field__label">Show acquisitions from</span>
                <select value={time.liveWindowHours ?? 'all'} onChange={(e) => setTime((t) => ({ ...t, liveWindowHours: e.target.value === 'all' ? null : Number(e.target.value) }))}>
                  {LIVE_WINDOWS.map((w) => (
                    <option key={w.label} value={w.value ?? 'all'}>{w.label}</option>
                  ))}
                </select>
              </label>
              <p className="panel-note">Relative to now. Latest acquisition in data: <b>{latestAcquisitionMs ? fmtUtc(new Date(latestAcquisitionMs).toISOString()) : 'none'}</b>.</p>
            </>
          ) : (
            <>
              <div className="field-pair">
                <label className="field">
                  <span className="field__label">From (UTC)</span>
                  <input type="datetime-local" value={time.fromUtc} onChange={(e) => setTime((t) => ({ ...t, fromUtc: e.target.value }))} />
                </label>
                <label className="field">
                  <span className="field__label">To (UTC)</span>
                  <input type="datetime-local" value={time.toUtc} onChange={(e) => setTime((t) => ({ ...t, toUtc: e.target.value }))} />
                </label>
              </div>
              {err && <p className="field-error" role="alert">{err}</p>}
              <div className="chip-row">
                <button type="button" className="chip" onClick={() => quick(1)}>Last day of data</button>
                <button type="button" className="chip" onClick={() => quick(7)}>7 days</button>
                <button type="button" className="chip" onClick={() => quick(30)}>30 days</button>
                <button type="button" className="chip" onClick={() => setTime((t) => ({ ...t, fromUtc: '', toUtc: '' }))}>Clear</button>
              </div>
              <p className="panel-note">Filters on recorded acquisition timestamps only. A range with no records means no observation was recorded, not zero activity. Background refresh is paused in historical mode.</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
