import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext.jsx';
import { useGoogleMaps } from '../../hooks/useGoogleMaps.js';
import { createMarkerOverlay, markerSpec } from './markerOverlay.js';
import { INDIA_VIEW, FOCUS_ZOOM } from '../../config/app.js';
import { SEVERITY_RANK } from '../../config/severity.js';
import { fmtUtc } from '../../utils/format.js';
import { latestAcquisition } from '../../utils/time.js';

const LEFT_DRAWER_PX = 380;
const RIGHT_DRAWER_PX = 480;

const ROADMAP_STYLES = [
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
];

function eventTitle(e, extra = '') {
  const t = latestAcquisition(e);
  const sev = e.severity ? `Alert Priority ${e.severity.toUpperCase()} #${e.rank}` : 'priority not supplied';
  return `${e.id} · ${sev}${e.persistentSource ? ' · PIHS candidate' : ''} · ${e.classification.label} · ${t ? `last seen ${fmtUtc(new Date(t).toISOString())}` : 'acquisition time not packaged'}${extra}`;
}

function MapUnavailable({ error }) {
  let title = 'Map unavailable';
  let body = error;
  if (error === 'missing-key') {
    title = 'Google Maps API key missing';
    body = 'Add VITE_GOOGLE_MAPS_API_KEY to .env and restart the dev server. Alerts, Facilities and Investigation still work without the map.';
  } else if (error === 'auth') {
    title = 'Google Maps rejected the API key';
    body = 'Check that the key is valid, the Maps JavaScript API is enabled, and this origin is an allowed referrer. Alerts, Facilities and Investigation still work.';
  }
  return (
    <div className="map-fallback" role="alert">
      <div className="map-fallback__card">
        <p className="map-fallback__title">{title}</p>
        <p className="map-fallback__body">{body}</p>
      </div>
    </div>
  );
}

export default function MapView() {
  const {
    visibleEvents, historicalEvents, eventsById, facilities, filters, baseMap,
    selectedEventId, openInvestigation, openFacility, selectedFacilityId,
    focusRequest, clearFocusRequest, section, investigationOpen,
  } = useApp();
  const { status, maps, error } = useGoogleMaps();

  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const overlayRef = useRef(null);
  const shapesRef = useRef([]);
  const handlersRef = useRef({});
  const [mapReady, setMapReady] = useState(false);

  handlersRef.current = { openInvestigation, openFacility };

  // Maps API became unusable (e.g. key rejected after the script loaded).
  const usable = status === 'ready' && !!maps;
  useEffect(() => {
    if (!usable) setMapReady(false);
  }, [usable]);

  // Create the map once.
  useEffect(() => {
    if (status !== 'ready' || !maps || mapRef.current || !containerRef.current) return undefined;
    const map = new maps.Map(containerRef.current, {
      center: INDIA_VIEW.center,
      zoom: INDIA_VIEW.zoom,
      disableDefaultUI: true,
      zoomControl: true,
      zoomControlOptions: maps.ControlPosition ? { position: maps.ControlPosition.RIGHT_BOTTOM } : undefined,
      clickableIcons: false,
      gestureHandling: 'greedy',
      mapTypeId: 'roadmap',
      styles: ROADMAP_STYLES,
    });
    const Overlay = createMarkerOverlay(maps);
    const overlay = new Overlay((kind, id) => {
      if (kind === 'facility') handlersRef.current.openFacility(id);
      else handlersRef.current.openInvestigation(id);
    });
    overlay.setMap(map);
    mapRef.current = map;
    overlayRef.current = overlay;
    setMapReady(true);
    return () => {
      overlay.setMap(null);
      shapesRef.current.forEach((s) => s.setMap(null));
      shapesRef.current = [];
      if (maps.event?.clearInstanceListeners) maps.event.clearInstanceListeners(map);
      mapRef.current = null;
      overlayRef.current = null;
      setMapReady(false);
    };
  }, [status, maps]);

  // Standard / Satellite.
  useEffect(() => {
    if (!mapReady || !mapRef.current) return;
    const isSat = baseMap === 'satellite';
    mapRef.current.setOptions({ mapTypeId: isSat ? 'hybrid' : 'roadmap', styles: isSat ? [] : ROADMAP_STYLES });
  }, [baseMap, mapReady]);

  // Marker items (events + facilities). Selected event is always drawn.
  const items = useMemo(() => {
    const out = [];
    const drawn = new Set();
    for (const e of historicalEvents) {
      drawn.add(e.id);
      out.push({ key: `e:${e.id}`, kind: 'event', id: e.id, lat: e.latitude, lng: e.longitude, title: eventTitle(e, ' · outside time filter'), spec: markerSpec(e, { historical: true, selected: e.id === selectedEventId }), z: e.id === selectedEventId ? 900 : 10 });
    }
    for (const e of visibleEvents) {
      drawn.add(e.id);
      out.push({ key: `e:${e.id}`, kind: 'event', id: e.id, lat: e.latitude, lng: e.longitude, title: eventTitle(e), spec: markerSpec(e, { selected: e.id === selectedEventId }), z: e.id === selectedEventId ? 1000 : 100 + (SEVERITY_RANK[e.severity] || 1) * 10 });
    }
    // Search/facility-selected context: the selected facility's real ranked sources within 5 km
    // are pinned even when their layer or time filter would hide them.
    const selFac = selectedFacilityId ? facilities.find((f) => f.id === selectedFacilityId) : null;
    for (const n of selFac?.nearbySources || []) {
      const e = eventsById.get(n.id);
      if (!e || drawn.has(e.id)) continue;
      drawn.add(e.id);
      out.push({ key: `e:${e.id}`, kind: 'event', id: e.id, lat: e.latitude, lng: e.longitude, title: eventTitle(e, ` · within 5 km of ${selFac.name}`), spec: markerSpec(e, { selected: e.id === selectedEventId }), z: 600 });
    }
    if (selectedEventId && !drawn.has(selectedEventId)) {
      const e = eventsById.get(selectedEventId);
      if (e) out.push({ key: `e:${e.id}`, kind: 'event', id: e.id, lat: e.latitude, lng: e.longitude, title: eventTitle(e, ' · selected (outside current filters)'), spec: markerSpec(e, { selected: true }), z: 1000 });
    }
    if (filters.context.facilities || selFac) {
      for (const f of filters.context.facilities ? facilities : [selFac]) {
        out.push({ key: `f:${f.id}`, kind: 'facility', id: f.id, lat: f.latitude, lng: f.longitude, title: `Facility · ${f.name} · ${f.type}`, z: 50 });
      }
    }
    return out;
  }, [visibleEvents, historicalEvents, eventsById, selectedEventId, selectedFacilityId, facilities, filters.context.facilities]);

  useEffect(() => {
    if (mapReady && overlayRef.current) overlayRef.current.setItems(items);
  }, [items, mapReady]);

  // Facility polygons (context) and historical footprints.
  useEffect(() => {
    if (!mapReady || !maps || !mapRef.current) return undefined;
    const shapes = [];
    for (const f of facilities) {
      if (filters.context.facilities && f.polygon?.length >= 3) {
        shapes.push(new maps.Polygon({
          map: mapRef.current,
          paths: f.polygon.map(([lat, lng]) => ({ lat, lng })),
          strokeColor: '#334155', strokeOpacity: 0.9, strokeWeight: 1.5,
          fillColor: '#334155', fillOpacity: 0.06, clickable: false,
        }));
      }
      const fp = f.historicalProfile?.footprint;
      if (filters.historical.facilityActivity && fp?.centroid && Number.isFinite(fp.median_spread_m)) {
        shapes.push(new maps.Circle({
          map: mapRef.current,
          center: { lat: fp.centroid[0], lng: fp.centroid[1] },
          radius: fp.median_spread_m,
          strokeColor: '#7C3AED', strokeOpacity: 0.9, strokeWeight: 1.5,
          fillColor: '#7C3AED', fillOpacity: 0.08, clickable: false,
        }));
      }
    }
    shapesRef.current = shapes;
    return () => {
      shapes.forEach((s) => s.setMap(null));
      shapesRef.current = [];
    };
  }, [mapReady, maps, facilities, filters.context.facilities, filters.historical.facilityActivity]);

  // Explicit focus requests only (View on Map, search, facility "Show on map").
  useEffect(() => {
    if (!mapReady || !focusRequest || !mapRef.current) return;
    const map = mapRef.current;
    map.panTo({ lat: focusRequest.lat, lng: focusRequest.lng });
    map.setZoom(focusRequest.zoom || FOCUS_ZOOM);
    const left = section ? LEFT_DRAWER_PX : 0;
    const right = investigationOpen ? RIGHT_DRAWER_PX : 0;
    if (left || right) map.panBy((right - left) / 2, 0);
    if (focusRequest.highlight && focusRequest.eventId) {
      // Wait one frame so the selected marker element exists.
      requestAnimationFrame(() => overlayRef.current?.highlight(`e:${focusRequest.eventId}`));
    }
    clearFocusRequest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequest, mapReady]);

  if (status === 'error') return <MapUnavailable error={error} />;

  return (
    <div className="map-canvas-wrap">
      <div ref={containerRef} className="map-canvas" aria-label="Thermal event map" />
      {status === 'loading' && <div className="map-loading">Loading map…</div>}
    </div>
  );
}
