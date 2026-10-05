// ---------------------------------------------------------------------------
// REAL STORE — the only data source of the application.
//
//   /data/thermwatch_historical.json  real v2 contract (build_contract_v2.py):
//        2,298,169 valid FIRMS observations → 1,056,161 sources → 1,277,339 events,
//        top-3,000 sources by Alert Priority (map_points), top-300 with full
//        event-level records (sources), coverage ledger, ML status.
//   /data/thermwatch_context.json     real facility registry + registry/PIHS
//        enrichment for the 3,000 ranked sources (build_frontend_context.py).
//   /data/thermwatch_live.json        live artifact, or explicit LIVE_FEED_UNAVAILABLE.
//
// There is NO fallback dataset. If a file cannot be loaded the UI shows an
// error/unavailable state. Nothing here estimates or invents values: records
// are mapped onto the V7 event model, field by field, from the contract.
// ---------------------------------------------------------------------------
import { getStatic } from './http.js';
import { mapPointToEvent, normalizeFacility, linkFacilities } from './normalize.js';
import { liveState } from '../components/intel/liveState.js';

let cache = null;

export function loadRealStore() {
  if (cache) return cache;
  cache = (async () => {
    const [contract, context, liveRes] = await Promise.all([
      getStatic('/data/thermwatch_historical.json'),
      getStatic('/data/thermwatch_context.json'),
      getStatic('/data/thermwatch_live.json').then((v) => ({ v, err: null }), (err) => ({ v: null, err })),
    ]);
    if (!contract?.map_points || !Array.isArray(contract.sources)) throw new Error('thermwatch_historical.json is not a v2 ThermWatch contract.');
    const detailed = new Map(contract.sources.map((s) => [s.source_id, s]));
    const alertCards = new Map((contract.alerts || []).map((a) => [a.source_id, a]));
    const facilities = (context?.facilities || []).map(normalizeFacility).filter(Boolean);
    const enrich = context?.point_enrichment || {};
    const facByName = linkFacilities(facilities);
    let skipped = 0;
    const events = [];
    contract.map_points.forEach((p, i) => {
      const e = mapPointToEvent(p, i + 1, { source: detailed.get(p.source_id) || null, enrichment: enrich[p.source_id] || null, facByName, contract });
      if (e) events.push(e); else skipped += 1;
    });
    attachNearbySources(facilities, events);
    const live = liveRes.v;
    const ls = liveState(live);
    const warnings = [];
    if (ls.cls !== 'on') warnings.push(`${ls.cls === 'stale' ? 'Live FIRMS feed stale' : `Live FIRMS feed unavailable${live?.pipeline_status_detail ? ` (${live.pipeline_status_detail})` : ''}`} — showing validated historical data to ${String(contract.data_timestamp).slice(0, 10)}.`);
    return { contract, context, live, liveStatus: ls, detailed, alertCards, events, facilities, warnings, skippedInvalid: skipped };
  })().catch((err) => { cache = null; throw err; });
  return cache;
}

// Same 5 km radius the pipeline uses for facility context. Real coordinates only; this is
// proximity context for the investigator, not attribution and not cause.
export const NEARBY_KM = 5;
const hav = (a, b, c, d) => { const r = Math.PI / 180; const x = Math.sin(((c - a) * r) / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(((d - b) * r) / 2) ** 2; return 12742.0176 * Math.asin(Math.sqrt(x)); };
export function attachNearbySources(facilities, events) {
  const grid = new Map(); const cell = (la, lo) => `${Math.floor(la * 10)}:${Math.floor(lo * 10)}`;
  for (const e of events) { const k = cell(e.latitude, e.longitude); if (!grid.has(k)) grid.set(k, []); grid.get(k).push(e); }
  for (const f of facilities) {
    const near = [];
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) {
      for (const e of grid.get(`${Math.floor(f.latitude * 10) + i}:${Math.floor(f.longitude * 10) + j}`) || []) {
        const km = hav(f.latitude, f.longitude, e.latitude, e.longitude);
        if (km <= NEARBY_KM) near.push({ id: e.id, km, rank: e.rank });
      }
    }
    f.nearbySources = near.sort((a, b) => a.rank - b.rank);
  }
}

/** Test hook. */
export function _resetRealStore() { cache = null; }
