// ---------------------------------------------------------------------------
// NORMALIZATION — real ThermWatch contract records → the V7 frontend Event model.
//
// One V7 "event" on the map = one real ThermWatch persistent SOURCE (SRC-…),
// ranked by Alert Priority (alert-priority-v1). Its real member events
// (EVT-…) appear inside the investigation.
//
// Mapping (no computation of new science):
//   severity / priority  ← alert_tier (HIGH / MEDIUM / LOW)      triage ranking, not probability
//   persistentSource     ← pihs_flag (pihs-v1 rule detector)
//   classification       ← nearest-facility attribution category (heuristic context) when the
//                          full record is packaged; otherwise "Unknown / Other"
//   behaviour            ← 'not_assessed' (the real pipeline has no baseline/anomaly fusion)
//   acquisition times    ← real event first/last observation timestamps (top-300 records only)
// ---------------------------------------------------------------------------
import { classificationOf } from '../config/classification.js';
import { industrialTypeKey } from '../config/industrialTypes.js';
import { DATA_KINDS } from '../config/provenance.js';
import { isValidLatLng } from '../utils/geo.js';

const num = (v) => (v === null || v === undefined || v === '' ? null : Number.isFinite(Number(v)) ? Number(v) : null);
const iso = (v) => { if (!v) return null; const t = new Date(v); return Number.isFinite(t.getTime()) ? t.toISOString() : null; };
const coordName = (lat, lng) => `${Math.abs(lat).toFixed(3)}° ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lng).toFixed(3)}° ${lng >= 0 ? 'E' : 'W'}`;
const TIER = { HIGH: 'high', MEDIUM: 'medium', LOW: 'low' };
const CAT_TYPE = { STEEL_METAL: 'steel', THERMAL_POWER: 'thermal_power', LNG_GAS: 'lng_gas' };
export const pretty = (k) => String(k ?? '').replace(/_/g, ' ').toLowerCase();

export function linkFacilities(facilities) {
  const m = new Map();
  for (const f of facilities) m.set(f.name.trim().toLowerCase(), f);
  return m;
}

export function mapPointToEvent(p, rank, { source = null, enrichment = null, facByName = new Map(), contract = null } = {}) {
  const lat = num(source?.identity?.lat ?? p?.lat);
  const lng = num(source?.identity?.lon ?? p?.lon);
  if (!p?.source_id || !isValidLatLng(lat, lng)) return null;
  const tier = TIER[String(p.tier || source?.intelligence?.alert_tier || '').toUpperCase()] || null;
  const sp = source?.spatial || null;
  const cat = sp?.facility_category || null;
  const indType = CAT_TYPE[cat] || null;
  const classKey = indType ? 'industrial' : 'unknown';
  const attr = source ? Object.entries(source.intelligence.attribution || {}).sort((a, b) => b[1] - a[1]) : [];
  const fac = sp?.nearest_facility ? facByName.get(sp.nearest_facility.trim().toLowerCase()) || null : null;
  const observations = (source?.events || []).flatMap((ev) => {
    const out = [{ id: `${ev.event_id}:first`, timestampUtc: iso(ev.first), eventId: ev.event_id }];
    if (ev.last && ev.last !== ev.first) out.push({ id: `${ev.event_id}:last`, timestampUtc: iso(ev.last), eventId: ev.event_id });
    return out;
  });
  const a = source?.activity;
  const kind = source ? 'real_detailed' : 'real_ranked';
  return {
    id: p.source_id,
    rank,
    latitude: lat,
    longitude: lng,
    locationName: sp?.nearest_facility ? `Near ${sp.nearest_facility}` : coordName(lat, lng),
    startUtc: iso(source?.identity?.first_seen),
    endUtc: iso(source?.identity?.last_seen),
    sourceRecordIds: (source?.events || []).map((ev) => ev.event_id),
    observations,
    frpSummary: a ? { n: num(a.detections), max: num(a.frp_max), mean: num(a.frp_mean), min: null } : null,
    sensor: 'VIIRS 375 m (S-NPP / NOAA-20 / NOAA-21)',
    classification: {
      key: classKey,
      label: classificationOf(classKey).label,
      sourceLabel: attr.length ? `Heuristic attribution: ${attr.map(([k, v]) => `${pretty(k)} ${v}%`).join(', ')}` : source ? 'No documented facility within 5 km — attribution unknown' : 'Attribution not packaged for this ranked source',
      mlNote: 'ML classifier READY_NOT_TRAINED — no class probabilities exist.',
      industrialType: indType,
      industrialSubclassLabel: cat ? pretty(cat) : null,
      g4: null,
      gateNote: null,
    },
    severity: tier,
    severitySource: tier ? `Alert Priority tier ${p.tier} (alert-priority-v1, rank #${rank})` : 'Not supplied',
    facility: sp?.nearest_facility ? { id: fac?.id || null, name: sp.nearest_facility, type: cat, distanceKm: num(sp.facility_distance_km), attribution: null } : null,
    behaviour: 'not_assessed',
    priority: tier,
    alertState: null,
    persistentSource: p.pihs === true,
    real: {
      source,
      point: p,
      enrichment,
      alertScore: num(source?.intelligence?.alert_priority_score),
      runId: contract?.pipeline_run_id || null,
    },
    provenance: {
      kind,
      label: DATA_KINDS[kind].label,
      dataSource: `thermwatch_historical.json · run ${contract?.pipeline_run_id || '—'} · ${contract?.data_window || ''}`,
      mode: 'HISTORICAL_VALIDATED',
      profileVersion: null,
    },
  };
}

export function normalizeFacility(f) {
  const lat = num(f?.latitude);
  const lng = num(f?.longitude);
  if (!f?.id || !isValidLatLng(lat, lng)) return null;
  return {
    id: String(f.id),
    name: f.name || String(f.id),
    type: f.type || 'Other Industrial',
    typeKey: industrialTypeKey(f.type) || 'other',
    typeDetail: f.kind ? `registry kind ${f.kind}` : null,
    latitude: lat,
    longitude: lng,
    locationLabel: null,
    polygon: null,
    provenance: f.provenance || { point: 'Facility registry point', polygon: null },
    historicalProfile: null,
  };
}

export function dedupeById(list) {
  const seen = new Set();
  return (list || []).filter((x) => x && !seen.has(x.id) && seen.add(x.id));
}
