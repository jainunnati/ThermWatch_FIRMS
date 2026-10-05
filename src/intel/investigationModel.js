// ThermWatch investigation model (plain JS: unit-testable in Node, no React).
//
// Everything here is read from, or arithmetically derived from, the real v2 contract
// (public/data/thermwatch_historical.json, built by data-pipeline/intel_v1/build_contract_v2.py).
// NOTHING is estimated, simulated or trained. In particular this module does NOT compute:
//   baseline / MAD / normalised anomaly / thermal-anomaly score / fusion score / class probabilities.
// None of these exist in the real pipeline output, so none is shown.
//
// Rule constants below mirror data-pipeline/intel_v1/intel_core.py (pihs-v1, alert-priority-v1).
// tests/investigation.test.mjs + test_investigation_v1.py fail if they drift from that file.

export const PIHS_RULES = [
  { code: 'PERSISTENT_ACTIVITY', points: 3, field: 'active_days', op: '>=', threshold: 20, unit: 'active days', required: true, text: 'Thermal detections on at least 20 separate days' },
  { code: 'MULTI_DAY_ACTIVITY', points: 1, field: 'active_days', op: '>=', threshold: 5, unit: 'active days', required: false, text: 'Thermal detections on at least 5 separate days' },
  { code: 'NIGHT_DOMINANT', points: 2, field: 'night_share', op: '>=', threshold: 0.6, unit: 'night share', required: true, text: 'At least 60% of detections at night (and ≥ 3 detections)' },
  { code: 'REPEATED_EVENTS', points: 1, field: 'events', op: '>=', threshold: 3, unit: 'events', required: false, text: 'At least 3 separate thermal events' },
  { code: 'SPATIALLY_COMPACT', points: 1, field: 'extent_m', op: '<=', threshold: 750, unit: 'm extent', required: true, text: 'Detections within 750 m (≈ 2 VIIRS pixels) (and ≥ 3 detections)' },
];
export const ALERT_WEIGHTS = { pihs: 0.35, recency: 0.25, intensity_jump: 0.15, persistence: 0.15, facility_context: 0.10 };
export const ALERT_TIER_RULE = 'HIGH ≥ 0.60 · MEDIUM ≥ 0.40 · otherwise LOW';
export const COMPONENT_TEXT = {
  pihs: 'PIHS score ÷ 8',
  recency: 'Detections in last 30 days of the record ÷ 5 (capped at 1)',
  intensity_jump: '(FRP max ÷ FRP mean − 1) ÷ 4, within 0–1, only when ≥ 3 detections',
  persistence: 'Active days ÷ 60 (capped at 1)',
  facility_context: 'Top attribution weight ÷ 100, only for steel/metal, thermal power or LNG/gas categories',
};

export const COPY = {
  persistenceNote: 'Repeated thermal activity over multiple observation days increases investigation priority. Persistence is a detector / triage signal, not proof of industrial activity.',
  eventNote: "An event is a spatially and temporally associated group of satellite observations under ThermWatch's event-formation rules. It does not imply continuous thermal activity between satellite overpasses.",
  facilityNote: 'Facility proximity is contextual evidence, not proof of cause.',
  attributionNote: 'Attribution weights are heuristic relative weights, not calibrated probabilities.',
  coverageRule: 'Unknown coverage is not interpreted as no fire.',
  alertNote: 'Alert Priority is a triage ranking, not a probability of fire or industrial cause.',
  mlWhy: 'The available silver-label experiment was rejected after leakage/confounding diagnostics. ThermWatch therefore does not report fabricated classifier probabilities. The ML feature pipeline and grouped-validation framework remain ready for independently validated labels.',
  thermalNote: 'Thermal values are summary statistics over satellite overpasses. No historical baseline, anomaly score or fusion score exists in the real pipeline output, so none is shown.',
  cause: 'Not confirmed',
};

export const num = (v) => {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const day = (iso) => (iso ? String(iso).slice(0, 10) : null);
const ms = (iso) => Date.parse(iso);
export const spanDays = (a, b) => (Number.isFinite(ms(a)) && Number.isFinite(ms(b)) ? (ms(b) - ms(a)) / 864e5 : null);

export function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371008.8; const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad; const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

const SAT_LABEL = { 'VIIRS N': 'Suomi NPP', 'VIIRS N20': 'NOAA-20', 'VIIRS N21': 'NOAA-21' };
export const satLabel = (k) => SAT_LABEL[k] || k;
const STREAM_LABEL = { 'VIIRS:N': 'S-NPP (VIIRS:N)', 'VIIRS:N20': 'NOAA-20 (VIIRS:N20)', 'VIIRS:N21': 'NOAA-21 (VIIRS:N21)' };

/** Rule table: real values vs the documented pihs-v1 thresholds. */
export function pihsRuleChecks(source) {
  const a = source.activity; const sp = source.spatial; const n = num(a.detections);
  const val = { active_days: num(a.active_days), night_share: num(a.night_share), events: num(a.events), extent_m: num(sp.extent_m) };
  return PIHS_RULES.map((r) => {
    const v = val[r.field];
    let met = v !== null && (r.op === '>=' ? v >= r.threshold : v <= r.threshold);
    if (r.code === 'NIGHT_DOMINANT' || r.code === 'SPATIALLY_COMPACT') met = met && n !== null && n >= 3;
    return { ...r, value: v, met };
  });
}

/** Recompute reasons/score from real values and compare with what the pipeline stored. */
export function pihsConsistency(source) {
  const checks = pihsRuleChecks(source);
  const reasons = checks.filter((c) => c.met).map((c) => c.code);
  const score = checks.filter((c) => c.met).reduce((s, c) => s + c.points, 0);
  const flag = ['PERSISTENT_ACTIVITY', 'NIGHT_DOMINANT', 'SPATIALLY_COMPACT'].every((c) => reasons.includes(c));
  const it = source.intelligence;
  const same = JSON.stringify([...reasons].sort()) === JSON.stringify([...(it.pihs_reasons || [])].sort()) && score === it.pihs_score && flag === it.pihs_flag;
  return { checks, recomputed: { reasons, score, flag }, matchesPipeline: same };
}

/** Alert Priority breakdown: stored components × documented weights; reconciles with stored score. */
export function alertBreakdown(source) {
  const it = source.intelligence; const comps = it.alert_components || {};
  const rows = Object.keys(ALERT_WEIGHTS).map((k) => {
    const c = num(comps[k]) ?? 0;
    return { key: k, component: c, weight: ALERT_WEIGHTS[k], contribution: c * ALERT_WEIGHTS[k], rule: COMPONENT_TEXT[k] };
  });
  const sum = rows.reduce((s, r) => s + r.contribution, 0);
  return { rows, sum, stored: it.alert_priority_score, reconciles: Math.abs(sum - it.alert_priority_score) < 0.0006, tier: it.alert_tier, reasons: it.alert_reason_codes || [], version: it.alert_version, tierRule: ALERT_TIER_RULE };
}

export function eventSummary(source) {
  const ev = source.events || [];
  const sorted = [...ev].sort((a, b) => (a.first < b.first ? -1 : 1));
  const [lat0, lon0] = [source.identity.lat, source.identity.lon];
  const rows = sorted.map((e, i) => {
    const dur = spanDays(e.first, e.last);
    const off = Array.isArray(e.centroid) ? haversineM(lat0, lon0, e.centroid[0], e.centroid[1]) : null;
    const gap = i > 0 ? spanDays(sorted[i - 1].last, e.first) : null;
    return { ...e, idx: i + 1, duration_days: dur, centroid_offset_m: off, gap_days_since_prev: gap, sat_list: (e.satellites || []).map(([k, c]) => ({ key: k, label: satLabel(k), count: c })) };
  });
  const totalObs = rows.reduce((s, r) => s + r.observations, 0);
  const sats = {};
  rows.forEach((r) => r.sat_list.forEach((s) => { sats[s.key] = (sats[s.key] || 0) + s.count; }));
  const offs = rows.map((r) => r.centroid_offset_m).filter((x) => x !== null);
  const durs = rows.map((r) => r.duration_days).filter((x) => x !== null);
  return {
    rows, count: rows.length, totalObs,
    reconcilesWithDetections: totalObs === num(source.activity.detections),
    activeCount: rows.filter((r) => r.status === 'active').length,
    satTotals: Object.entries(sats).map(([key, count]) => ({ key, label: satLabel(key), count })).sort((a, b) => b.count - a.count),
    maxObs: rows.reduce((m, r) => Math.max(m, r.observations), 0),
    longest: durs.length ? Math.max(...durs) : null,
    maxCentroidOffsetM: offs.length ? Math.max(...offs) : null,
    medianObs: rows.length ? [...rows].map((r) => r.observations).sort((a, b) => a - b)[Math.floor(rows.length / 2)] : null,
  };
}

/** Coverage inside this source's own first→last window, from the real coverage ledger. */
export function coverageForSource(source, coverage) {
  const a = day(source.identity.first_seen); const b = day(source.identity.last_seen);
  const streams = Object.entries(coverage.streams).map(([key, v]) => {
    const unv = v.unverified_dates.filter((d) => d >= a && d <= b);
    const partial = v.partial_boundary_days.filter((d) => d >= a && d <= b);
    return { key, label: STREAM_LABEL[key] || key, ledgerDays: v.days, unverifiedInWindow: unv, partialInWindow: partial, complete: unv.length === 0 };
  });
  const windowDays = Math.round(spanDays(`${a}T00:00:00Z`, `${b}T00:00:00Z`)) + 1;
  return { window: [a, b], windowDays, streams, rule: COPY.coverageRule, ledgerRule: coverage.rule, reasonMeaning: coverage.reason_meaning,
    anyUnverified: streams.some((s) => !s.complete) };
}

export function thermalSummary(source) {
  const a = source.activity; const it = source.intelligence; const c = it.alert_components || {};
  const fmax = num(a.frp_max); const fmean = num(a.frp_mean); const night = num(a.night_share);
  return {
    frpMax: fmax, frpMean: fmean, frpRatio: fmax !== null && fmean ? fmax / fmean : null,
    ti4Median: num(a.ti4_median), ti4Max: num(a.ti4_max),
    nightShare: night, dayShare: night === null ? null : 1 - night,
    recent30: num(a.recent_30d_detections),
    intensityJumpComponent: num(c.intensity_jump), recencyComponent: num(c.recency),
    intensityFlag: (it.alert_reason_codes || []).includes('INTENSITY_ABOVE_OWN_BASELINE'),
    hasBaseline: false, // no historical baseline is produced by the real pipeline output
  };
}

export function attributionSummary(source) {
  const it = source.intelligence; const sp = source.spatial;
  const entries = Object.entries(it.attribution || {}).sort((x, y) => y[1] - x[1]);
  return {
    entries, confidence: source.uncertainty.attribution_confidence, cause: COPY.cause,
    nearest: sp.nearest_facility ? { name: sp.nearest_facility, type: sp.facility_category, distanceKm: sp.facility_distance_km } : null,
    note: COPY.attributionNote, facilityNote: COPY.facilityNote,
  };
}

/** One call: everything the screen and the print report need, for one real source. */
export function buildInvestigation(source, contract, alertCard = null) {
  if (!source) return null;
  const a = source.activity; const id = source.identity;
  return {
    source_id: source.source_id, rank: source.rank,
    alertCard,
    sourceCoverageStatus: source.uncertainty.coverage_status,
    run: { monitored: contract.system_stats?.sources_monitored ?? null, id: contract.pipeline_run_id, mode: contract.mode, window: contract.data_window, timestamp: contract.data_timestamp, status: contract.pipeline_status, contract: contract.contract_version },
    identity: { ...id, durationDays: num(a.duration_days) ?? spanDays(id.first_seen, id.last_seen), durationDerived: num(a.duration_days) === null, extentM: source.spatial.extent_m, activeDayShare: spanDays(id.first_seen, id.last_seen) ? num(a.active_days) / (spanDays(id.first_seen, id.last_seen) + 1) : null },
    observations: { detections: num(a.detections), activeDays: num(a.active_days), events: num(a.events) },
    events: eventSummary(source),
    persistence: { ...pihsConsistency(source), flag: source.intelligence.pihs_flag, score: source.intelligence.pihs_score, reasons: source.intelligence.pihs_reasons, version: source.intelligence.pihs_version, note: COPY.persistenceNote },
    thermal: thermalSummary(source),
    facility: { ...attributionSummary(source).nearest, note: COPY.facilityNote, none: !source.spatial.nearest_facility },
    attribution: attributionSummary(source),
    coverage: coverageForSource(source, contract.coverage),
    alert: alertBreakdown(source),
    ml: { ...contract.ml_status, why: COPY.mlWhy },
    caveats: [
      COPY.persistenceNote, COPY.facilityNote, COPY.attributionNote, COPY.coverageRule, COPY.alertNote,
      'PIHS is a transparent rule-based detector, not ground truth. A satellite detection is not a confirmed fire.',
      'No incident found does not mean no incident occurred.',
    ],
  };
}

// Number formatting shared by screen + print.
export const f1 = (n, d = 1) => (n === null || n === undefined ? '—' : Number(n).toFixed(d));
export const pct = (n, d = 0) => (n === null || n === undefined ? '—' : `${(n * 100).toFixed(d)}%`);
export const utc = (iso) => (iso ? `${String(iso).slice(0, 16).replace('T', ' ')} UTC` : '—');
export const label = (k) => String(k).replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
