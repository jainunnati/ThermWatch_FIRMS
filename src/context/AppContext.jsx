import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { listEvents } from '../services/eventsService.js';
import { listFacilities } from '../services/facilitiesService.js';
import { listAlerts } from '../services/alertsService.js';
import { listActivity } from '../services/activityService.js';
import { loadRealStore } from '../services/realStore.js';
import { defaultFilters, eventMatchesFilters } from '../utils/filters.js';
import { eventMatchesTime, latestAcquisition } from '../utils/time.js';
import { SEVERITY_RANK } from '../config/severity.js';

const AppContext = createContext(null);
const PRIORITY_RANK = { high: 3, medium: 2, low: 1 };

const EMPTY = { events: [], facilities: [], alerts: [], activity: [] };

export function AppProvider({ children }) {
  // ---- data ----------------------------------------------------------------
  // Single real data source (no mode switch, no fallback dataset).
  const dataMode = 'real';
  const [store, setStore] = useState(null);
  const [data, setData] = useState(EMPTY);
  const [load, setLoad] = useState({ status: 'loading', error: null, warnings: [], skippedInvalid: 0, updatedAt: null });
  const [reloadNonce, setReloadNonce] = useState(0);
  const [acknowledged, setAcknowledged] = useState(() => new Set());
  const [sessionActivity, setSessionActivity] = useState([]);

  // ---- ui ------------------------------------------------------------------
  const [section, setSection] = useState(null); // 'alerts' | 'activity' | 'facilities' | 'help' | null
  const [baseMap, setBaseMap] = useState('roadmap');
  const [filters, setFilters] = useState(defaultFilters);
  const [time, setTime] = useState({ mode: 'live', liveWindowHours: null, fromUtc: '', toUtc: '' });
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [investigationOpen, setInvestigationOpen] = useState(false);
  const [focusRequest, setFocusRequest] = useState(null);
  const [selectedFacilityId, setSelectedFacilityId] = useState(null);
  const [now, setNow] = useState(() => Date.now());

  // ---- loading & polling ----------------------------------------------------
  const inFlight = useRef(null);

  const fetchAll = useCallback(async ({ background = false } = {}) => {
    inFlight.current?.abort();
    const ctrl = new AbortController();
    inFlight.current = ctrl;
    if (!background) setLoad((l) => ({ ...l, status: 'loading', error: null }));
    try {
      const [ev, facilities, activity, st] = await Promise.all([listEvents(), listFacilities(), listActivity(), loadRealStore()]);
      const alerts = await listAlerts(ev.events);
      if (ctrl.signal.aborted) return;
      setStore(st);
      setData({ events: ev.events, facilities, alerts, activity });
      setLoad({ status: 'ready', error: null, warnings: ev.warnings, skippedInvalid: ev.skippedInvalid, updatedAt: new Date().toISOString() });
      setNow(Date.now());
    } catch (err) {
      if (ctrl.signal.aborted) return;
      // Background poll failures keep the last good data and surface the error.
      setLoad((l) => ({ ...l, status: background ? l.status : 'error', error: err.message || String(err) }));
      if (!background) setData(EMPTY);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    return () => inFlight.current?.abort();
  }, [reloadNonce, fetchAll]);

  // Keep relative live windows honest without re-fetching: refresh "now" each minute.
  useEffect(() => {
    if (time.mode !== 'live' || time.liveWindowHours == null) return undefined;
    const id = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(id);
  }, [time.mode, time.liveWindowHours]);

  const retry = useCallback(() => setReloadNonce((n) => n + 1), []);

  // ---- derived -------------------------------------------------------------
  const eventsById = useMemo(() => new Map(data.events.map((e) => [e.id, e])), [data.events]);

  const timeMatched = useMemo(() => data.events.filter((e) => eventMatchesTime(e, time, now)), [data.events, time, now]);
  const visibleEvents = useMemo(() => timeMatched.filter((e) => eventMatchesFilters(e, filters)), [timeMatched, filters]);
  const historicalEvents = useMemo(() => {
    if (!filters.historical.events) return [];
    const inTime = new Set(timeMatched.map((e) => e.id));
    return data.events.filter((e) => !inTime.has(e.id) && eventMatchesFilters(e, filters));
  }, [data.events, timeMatched, filters]);

  const latestAcquisitionMs = useMemo(() => {
    let max = null;
    for (const e of data.events) {
      const t = latestAcquisition(e);
      if (t !== null && (max === null || t > max)) max = t;
    }
    return max;
  }, [data.events]);

  const alerts = useMemo(
    () =>
      data.alerts
        .map((a) => ({ ...a, state: acknowledged.has(a.id) ? 'acknowledged' : a.state, event: eventsById.get(a.eventId) || null }))
        // Investigation queue order: new first, then priority tier, then real Alert Priority rank.
        .sort((a, b) =>
          (a.state === 'new' ? 0 : 1) - (b.state === 'new' ? 0 : 1) ||
          (PRIORITY_RANK[b.event?.priority] || 0) - (PRIORITY_RANK[a.event?.priority] || 0) ||
          (SEVERITY_RANK[b.event?.severity] || 0) - (SEVERITY_RANK[a.event?.severity] || 0) ||
          (a.rank ?? 1e9) - (b.rank ?? 1e9)),
    [data.alerts, acknowledged, eventsById]
  );
  const newAlertCount = useMemo(() => alerts.filter((a) => a.state === 'new').length, [alerts]);

  const activity = useMemo(() => {
    const merged = [...sessionActivity, ...data.activity];
    const seen = new Set();
    return merged.filter((a) => !seen.has(a.eventId) && seen.add(a.eventId));
  }, [sessionActivity, data.activity]);

  // ---- actions -------------------------------------------------------------
  const recordActivity = useCallback((eventId) => {
    setSessionActivity((prev) => [{ id: `ACT-${eventId}`, eventId, atUtc: new Date().toISOString() }, ...prev.filter((a) => a.eventId !== eventId)].slice(0, 100));
  }, []);

  /** Open the investigation panel. Deliberately does NOT move the map. */
  const openInvestigation = useCallback((eventId) => {
    if (!eventId) return;
    setSelectedEventId(eventId);
    setInvestigationOpen(true);
    recordActivity(eventId);
  }, [recordActivity]);

  /** The only event action that pans/zooms: explicit "View on Map". */
  const viewOnMap = useCallback((eventId) => {
    const e = eventsById.get(eventId);
    if (!e) return;
    setSelectedEventId(eventId);
    setFocusRequest({ lat: e.latitude, lng: e.longitude, eventId, highlight: true, nonce: Date.now() });
  }, [eventsById]);

  const focusLocation = useCallback((lat, lng, zoom) => {
    setFocusRequest({ lat, lng, zoom, highlight: false, nonce: Date.now() });
  }, []);

  const closeInvestigation = useCallback(() => setInvestigationOpen(false), []);
  const clearFocusRequest = useCallback(() => setFocusRequest(null), []);

  const acknowledgeAlert = useCallback((alertId) => {
    setAcknowledged((prev) => new Set(prev).add(alertId));
  }, []);

  const openFacility = useCallback((facilityId) => {
    setSelectedFacilityId(facilityId);
    setSection('facilities');
  }, []);

  const toggleSection = useCallback((key) => setSection((s) => (s === key ? null : key)), []);

  const value = {
    dataMode, retry, load, store,
    events: data.events, eventsById, facilities: data.facilities,
    timeMatched, visibleEvents, historicalEvents, latestAcquisitionMs,
    alerts, newAlertCount, acknowledgeAlert,
    activity,
    section, setSection, toggleSection,
    baseMap, setBaseMap,
    filters, setFilters,
    time, setTime,
    selectedEventId, investigationOpen, openInvestigation, closeInvestigation, viewOnMap,
    focusRequest, clearFocusRequest, focusLocation,
    selectedFacilityId, setSelectedFacilityId, openFacility,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside <AppProvider>');
  return ctx;
}
