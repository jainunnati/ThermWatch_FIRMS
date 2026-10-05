// Data-integrity tests: the packaged real data, the context layer and the V7 event mapping.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs'; import zlib from 'node:zlib'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
import { mapPointToEvent, normalizeFacility, linkFacilities } from '../src/services/normalize.js';
import { deriveAlerts } from '../src/services/alertsService.js';
import { eventMatchesTime } from '../src/utils/time.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const J = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));
const D = J('public/data/thermwatch_historical.json');
const C = J('public/data/thermwatch_context.json');
const L = J('public/data/thermwatch_live.json');
const detailed = new Map(D.sources.map((s) => [s.source_id, s]));
const facs = C.facilities.map(normalizeFacility); const byName = linkFacilities(facs);
const events = D.map_points.map((p, i) => mapPointToEvent(p, i + 1, { source: detailed.get(p.source_id) || null, enrichment: C.point_enrichment[p.source_id], facByName: byName, contract: D }));

test('headline real counts are present', () => {
  const s = D.system_stats;
  assert.equal(s.valid_observations, 2298169); assert.equal(s.physical_sources, 1056161); assert.equal(s.events, 1277339);
  assert.equal(s.pihs_candidates, 220); assert.equal(s.alerts_high, 726); assert.equal(s.alerts_medium, 342);
  assert.equal(D.data_timestamp.slice(0, 10), '2026-10-01'); assert.equal(D.data_window, '2026-01-01..2026-10-01');
  assert.equal(D.ml_status.state, 'READY_NOT_TRAINED'); assert.equal(D.ml_status.eligible_labels, 0);
});

test('map layer = top 3000 real sources, ranked, with valid coordinates; all 300 full records inside it', () => {
  assert.equal(D.map_points.length, 3000);
  assert.ok(D.map_points.every((p) => /^SRC-[0-9a-f]{10}$/.test(p.source_id) && Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180 && !(p.lat === 0 && p.lon === 0)));
  assert.equal(new Set(D.map_points.map((p) => p.source_id)).size, 3000);
  const ids = new Set(D.map_points.map((p) => p.source_id));
  assert.ok(D.sources.every((s) => ids.has(s.source_id)));
  assert.equal(D.map_points.filter((p) => p.tier === 'HIGH').length, 726);
  assert.equal(D.map_points.filter((p) => p.pihs).length, 220);
});

test('context layer is copied from the real registry indexes (no invented values)', () => {
  assert.equal(C.registry_sources, 1056161); assert.equal(C.contract_run_id, D.pipeline_run_id);
  assert.equal(C.facilities.length, 449); assert.equal(Object.keys(C.point_enrichment).length, 3000);
  const reg = new Map(zlib.gunzipSync(fs.readFileSync(path.join(ROOT, 'data-pipeline/intel_v1/live_indexes/registry_index.csv.gz'))).toString()
    .split('\n').slice(1).filter(Boolean).map((l) => l.split(',')).filter((r) => C.point_enrichment[r[0]]).map((r) => [r[0], Number(r[3])]));
  for (const [sid, e] of Object.entries(C.point_enrichment)) assert.equal(e.n_obs, reg.get(sid), sid);
  const pihs = fs.readFileSync(path.join(ROOT, 'data-pipeline/intel_v1/live_indexes/pihs_index.csv'), 'utf8').trim().split('\n').slice(1).map((l) => l.split(','));
  for (const [sid, , , score, ad] of pihs) { assert.equal(C.point_enrichment[sid].pihs_score, Number(score)); assert.equal(C.point_enrichment[sid].active_days, Number(ad)); }
  // detailed records agree with registry n_obs
  for (const s of D.sources) assert.equal(C.point_enrichment[s.source_id].n_obs, s.activity.detections, s.source_id);
});

test('V7 event mapping uses real ids, coordinates, tiers and PIHS flags', () => {
  assert.equal(events.filter(Boolean).length, 3000);
  for (const [i, e] of events.entries()) {
    const p = D.map_points[i];
    assert.equal(e.id, p.source_id); assert.equal(e.rank, i + 1);
    assert.equal(e.priority, p.tier.toLowerCase()); assert.equal(e.persistentSource, p.pihs);
    assert.equal(e.behaviour, 'not_assessed');
    assert.ok(Math.abs(e.latitude - p.lat) < 1e-9 && Math.abs(e.longitude - p.lon) < 1e-9);
    if (detailed.has(e.id)) {
      const s = detailed.get(e.id);
      assert.equal(e.provenance.kind, 'real_detailed'); assert.equal(e.endUtc, new Date(s.identity.last_seen).toISOString());
      assert.deepEqual(e.sourceRecordIds, s.events.map((x) => x.event_id));
      assert.ok(e.observations.every((o) => /^EVT-/.test(o.eventId)));
    } else { assert.equal(e.provenance.kind, 'real_ranked'); assert.equal(e.observations.length, 0); assert.equal(e.startUtc, null); }
    assert.equal(e.classification.key, ['STEEL_METAL', 'THERMAL_POWER', 'LNG_GAS'].includes(detailed.get(e.id)?.spatial.facility_category) ? 'industrial' : 'unknown');
  }
});

test('facility links resolve to real registry rows', () => {
  const linked = events.filter((e) => e.facility?.id);
  assert.ok(linked.length > 100);
  for (const e of linked) assert.equal(facs.find((f) => f.id === e.facility.id).name, e.facility.name);
});

test('alerts = the 726 real HIGH-tier sources in rank order, cause never claimed', () => {
  const a = deriveAlerts(events); assert.equal(a.length, 726);
  assert.deepEqual(a.map((x) => x.rank), [...a.map((x) => x.rank)].sort((x, y) => x - y));
  assert.equal(a[0].eventId, D.sources[0].source_id);
  assert.ok(a.every((x) => !/probab|confirmed cause/i.test(x.reason)));
});

test('time filter never invents times: untimed ranked sources only appear under "All available"', () => {
  const untimed = events.find((e) => !e.observations.length); const timed = events.find((e) => e.observations.length);
  assert.equal(eventMatchesTime(untimed, { mode: 'live', liveWindowHours: null }), true);
  assert.equal(eventMatchesTime(untimed, { mode: 'live', liveWindowHours: 24 * 30 }, Date.parse('2026-10-04T00:00:00Z')), false);
  assert.equal(eventMatchesTime(untimed, { mode: 'historical', fromUtc: '2026-01-01T00:00', toUtc: '2026-10-02T00:00' }), false);
  assert.equal(eventMatchesTime(timed, { mode: 'historical', fromUtc: '2026-01-01T00:00', toUtc: '2026-10-02T00:00' }), true);
});

test('live artifact is honest (unavailable, zero sources, no fabricated data)', () => {
  assert.equal(L.pipeline_status, 'LIVE_FEED_UNAVAILABLE'); assert.equal(L.live_sources.length, 0); assert.equal(L.system_stats.live_observations, 0);
});

test('no data file in public/ carries a key-like secret', () => {
  for (const f of fs.readdirSync(path.join(ROOT, 'public/data'))) assert.doesNotMatch(fs.readFileSync(path.join(ROOT, 'public/data', f), 'utf8'), /MAP_KEY=|api[_-]?key\s*[:=]\s*["'][A-Za-z0-9]{16,}/i, f);
});

// ---- Map information hierarchy, search and proximity (real data only) ----
import { defaultFilters, eventMatchesFilters } from '../src/utils/filters.js';
import { searchAll } from '../src/services/search.js';
import { attachNearbySources, NEARBY_KM } from '../src/services/realStore.js';

test('default map = alert points only (HIGH + MEDIUM), ordinary sources kept but hidden, facilities off', () => {
  const f = defaultFilters();
  const shown = events.filter((e) => eventMatchesFilters(e, f));
  assert.equal(shown.length, D.map_points.filter((p) => p.tier !== 'LOW').length);
  assert.equal(shown.length, 726 + 342);
  assert.ok(shown.every((e) => e.priority === 'high' || e.priority === 'medium'));
  assert.equal(f.context.facilities, false); assert.equal(f.historical.events, false);
  assert.equal(events.length, 3000);   // nothing deleted: LOW-tier sources still loaded
  const all = events.filter((e) => eventMatchesFilters(e, { ...f, severities: { ...f.severities, low: true } }));
  assert.equal(all.length, 3000);
});

test('historical filter uses only real event timestamps (January vs September differ, no invented times)', () => {
  const f = defaultFilters();
  const range = (a, b) => events.filter((e) => eventMatchesFilters(e, f) && eventMatchesTime(e, { mode: 'historical', fromUtc: a, toUtc: b })).map((e) => e.id);
  const jan = range('2026-01-01T00:00', '2026-01-31T23:59'); const sep = range('2026-09-01T00:00', '2026-09-30T23:59');
  const real = (a, b) => D.sources.filter((s) => s.events.some((ev) => (ev.first >= a && ev.first <= b) || (ev.last >= a && ev.last <= b))).map((s) => s.source_id);
  assert.deepEqual(new Set(jan), new Set(real('2026-01-01T00:00', '2026-01-31T23:59:59')));
  assert.deepEqual(new Set(sep), new Set(real('2026-09-01T00:00', '2026-09-30T23:59:59')));
  assert.ok(jan.length > 0 && sep.length > 0); assert.notDeepEqual(new Set(jan), new Set(sep));
  assert.ok([...jan, ...sep].every((id) => detailed.has(id)), 'only sources with packaged timestamps can match a range');
});

test('search: exact source id first; facility names/places/types; no fabricated hits', () => {
  attachNearbySources(facs, events);
  const r1 = searchAll('SRC-f10396fc99', { events, facilities: facs });
  assert.equal(r1[0].kind, 'event'); assert.equal(r1[0].id, 'SRC-f10396fc99');
  const r2 = searchAll('Hazira', { events, facilities: facs });
  assert.ok(r2.some((r) => r.kind === 'facility' && /Hazira/.test(r.label)));
  assert.ok(r2.every((r) => r.kind !== 'facility' || facs.some((f) => f.id === r.id)));
  const r3 = searchAll('steel', { events, facilities: facs });
  assert.ok(r3.some((r) => r.kind === 'facility') && r3.some((r) => r.kind === 'event'));
  const evs = r3.filter((r) => r.kind === 'event').map((r) => events.find((e) => e.id === r.id).rank);
  assert.deepEqual(evs, [...evs].sort((a, b) => a - b), 'sources in Alert Priority rank order');
  assert.deepEqual(searchAll('zzqx-no-such-place', { events, facilities: facs }), []);
});

test('facility proximity is real-coordinate distance ≤ 5 km, ranked, and never labelled as cause', () => {
  attachNearbySources(facs, events);
  const R = 6371.0088, rad = Math.PI / 180;
  const km = (a, b, c, d) => 2 * R * Math.asin(Math.sqrt(Math.sin(((c - a) * rad) / 2) ** 2 + Math.cos(a * rad) * Math.cos(c * rad) * Math.sin(((d - b) * rad) / 2) ** 2));
  let pairs = 0;
  for (const f of facs) {
    const brute = events.filter((e) => km(f.latitude, f.longitude, e.latitude, e.longitude) <= NEARBY_KM).map((e) => e.id).sort();
    assert.deepEqual(f.nearbySources.map((n) => n.id).sort(), brute, f.name);
    const ranks = f.nearbySources.map((n) => n.rank); assert.deepEqual(ranks, [...ranks].sort((a, b) => a - b));
    pairs += brute.length;
  }
  assert.ok(pairs > 0);
  const top = D.sources[0];   // rank-1 source sits 0.04 km from its nearest facility
  assert.ok(facs.find((f) => f.name === top.spatial.nearest_facility).nearbySources.some((n) => n.id === top.source_id));
});
