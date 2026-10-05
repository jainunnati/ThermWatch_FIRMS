// Node tests for the real-data investigation model. Run: npm test   (node --test tests/)
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as M from '../src/intel/investigationModel.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const contractPath = path.join(ROOT, 'public/data/thermwatch_historical.json');
const D = JSON.parse(fs.readFileSync(contractPath, 'utf8'));
const inv = (s) => M.buildInvestigation(s, D, D.alerts.find((a) => a.source_id === s.source_id) || null);
const PIHS = D.sources.find((s) => s.intelligence.pihs_flag);
const ORD = D.sources.find((s) => !s.intelligence.pihs_flag);

test('every embedded source builds a real investigation (no synthetic ids)', () => {
  assert.equal(D.sources.length, 300);
  for (const s of D.sources) {
    assert.match(s.source_id, /^SRC-[0-9a-f]{10}$/); assert.doesNotMatch(s.source_id, /SYN/);
    const i = inv(s); assert.equal(i.source_id, s.source_id);
    assert.ok(i.events.rows.every((e) => /^EVT-[0-9a-f]{10}-\d{3}$/.test(e.event_id)));
  }
  assert.ok(D.alerts.every((a) => /^SRC-/.test(a.source_id)) && D.map_points.every((p) => /^SRC-/.test(p.source_id)));
});

test('investigation values are the real contract values (persistence/PIHS sourced from pipeline)', () => {
  for (const s of [PIHS, ORD]) {
    const i = inv(s);
    assert.equal(i.observations.detections, s.activity.detections); assert.equal(i.observations.activeDays, s.activity.active_days); assert.equal(i.observations.events, s.activity.events);
    assert.equal(i.persistence.score, s.intelligence.pihs_score); assert.equal(i.persistence.flag, s.intelligence.pihs_flag); assert.deepEqual(i.persistence.reasons, s.intelligence.pihs_reasons);
    assert.equal(i.alert.stored, s.intelligence.alert_priority_score); assert.equal(i.alert.tier, s.intelligence.alert_tier);
    assert.equal(i.thermal.frpMax, s.activity.frp_max); assert.equal(i.thermal.nightShare, s.activity.night_share);
    assert.equal(i.identity.lat, s.identity.lat); assert.equal(i.identity.first_seen, s.identity.first_seen);
    assert.equal(i.events.count, s.events.length);
  }
  assert.equal(PIHS.intelligence.pihs_flag, true); assert.equal(ORD.intelligence.pihs_flag, false);
});

test('pipeline self-consistency holds for all 300 sources (rules recompute, score reconciles, events sum to detections)', () => {
  for (const s of D.sources) {
    const i = inv(s);
    assert.ok(i.persistence.matchesPipeline, `PIHS recompute mismatch ${s.source_id}`);
    assert.ok(i.alert.reconciles, `alert score mismatch ${s.source_id}`);
    assert.ok(i.events.reconcilesWithDetections, `event obs mismatch ${s.source_id}`);
  }
});

test('rule constants mirror data-pipeline/intel_v1/intel_core.py (no drift)', () => {
  const py = fs.readFileSync(path.join(ROOT, 'data-pipeline/intel_v1/intel_core.py'), 'utf8');
  const points = JSON.parse(/^POINTS = (\{.*\})$/m.exec(py)[1]);
  const w = JSON.parse(/W = (\{[^}]*\})/.exec(py)[1].replace(/: \./g, ': 0.'));
  for (const r of M.PIHS_RULES) assert.equal(r.points, points[r.code], r.code);
  assert.deepEqual(M.ALERT_WEIGHTS, w);
  for (const re of [/ad >= 20/, /ad >= 5/, /nf >= 0\.6/, /ev >= 3/, /ext <= 750/]) assert.match(py, re);
  const t = Object.fromEntries(M.PIHS_RULES.map((r) => [r.code, r.threshold]));
  assert.deepEqual([t.PERSISTENT_ACTIVITY, t.MULTI_DAY_ACTIVITY, t.NIGHT_DOMINANT, t.REPEATED_EVENTS, t.SPATIALLY_COMPACT], [20, 5, 0.6, 3, 750]);
});

test('attribution stays heuristic and cause stays unconfirmed', () => {
  for (const s of D.sources) {
    const i = inv(s);
    assert.equal(i.attribution.cause, 'Not confirmed'); assert.equal(s.uncertainty.cause, 'Not confirmed');
    assert.match(i.attribution.note, /heuristic relative weights, not calibrated probabilities/);
    assert.match(i.facility.note, /contextual evidence, not proof of cause/);
    assert.ok(i.attribution.entries.every(([, v]) => v >= 0 && v <= 100));
  }
  assert.ok(D.alerts.every((a) => a.cause === 'Not confirmed'));
  assert.doesNotMatch(JSON.stringify(inv(PIHS)).replace(/not calibrated probabilities/g, ''), /"probabilit/i);
});

test('ML stays untrained; no classifier probability or F1 anywhere in the model output', () => {
  const i = inv(PIHS);
  assert.equal(i.ml.state, 'READY_NOT_TRAINED'); assert.equal(i.ml.eligible_labels, 0); assert.match(i.ml.verdict, /NO_DEFENSIBLE/);
  assert.match(i.ml.why, /silver-label experiment was rejected after leakage\/confounding diagnostics/);
  assert.doesNotMatch(JSON.stringify(i), /\bF1\b|f1_score|accuracy|class_prob/i);
});

test('coverage uncertainty is visible and never turned into "no fire"', () => {
  let withGaps = 0;
  for (const s of D.sources) {
    const i = inv(s); const n = i.coverage.streams.find((x) => x.key === 'VIIRS:N').unverifiedInWindow.length;
    const m = /S-NPP has (\d+) unverified-coverage days/.exec(s.uncertainty.coverage_status);
    assert.equal(n, m ? Number(m[1]) : 0, `window coverage mismatch ${s.source_id}`);   // model == pipeline's own per-source count
    if (n) withGaps++;
    assert.equal(i.coverage.rule, 'Unknown coverage is not interpreted as no fire.');
    assert.equal(i.coverage.anyUnverified, n > 0);
    for (const st of i.coverage.streams) assert.ok(st.unverifiedInWindow.every((d) => d >= i.coverage.window[0] && d <= i.coverage.window[1]));
    assert.equal(i.coverage.streams.find((x) => x.key === 'VIIRS:N20').complete, true);
  }
  assert.ok(withGaps > 0, 'expected some sources to overlap S-NPP gaps');
  assert.equal(inv(PIHS).sourceCoverageStatus, PIHS.uncertainty.coverage_status);
});

test('no synthetic Lanjigarh baseline/MAD/fusion maths is recreated for real sources', () => {
  const i = inv(PIHS); assert.equal(i.thermal.hasBaseline, false);
  const keys = JSON.stringify(Object.keys(i.thermal).concat(Object.keys(i.persistence), Object.keys(i.alert)));
  assert.doesNotMatch(keys, /mad|anomaly|fusion|baseline_|zscore|onrr/i);
  const src = fs.readFileSync(path.join(ROOT, 'src/intel/investigationModel.js'), 'utf8').replace(/^\/\/.*$/gm, '');
  assert.doesNotMatch(src, /Math\.median|normalis|normaliz|fusionScore|madScore/i);
});

test('missing optional fields are shown as unavailable, not zero', () => {
  const s = D.sources.find((x) => x.activity.ti4_median === null); assert.ok(s, 'fixture: a source without TI4');
  const i = inv(s); assert.equal(i.thermal.ti4Median, null); assert.equal(i.thermal.ti4Max, null);
  assert.equal(M.f1(i.thermal.ti4Median), '—');
  assert.equal(i.identity.durationDerived, s.activity.duration_days === null);
});

test('historical contract remains deterministic and byte-identical to the validated V11 artifact', () => {
  // contract fields are pipeline output and are not edited: mode label 'DEMO' + run id prefix 'demo-' mean "deterministic historical build", status HISTORICAL_VALIDATED.
  assert.equal(D.generated_at, D.data_timestamp); assert.equal(D.pipeline_status, 'HISTORICAL_VALIDATED'); assert.match(D.pipeline_run_id, /^demo-[0-9a-f]{12}$/);
  const keyOf = (s) => [-s.intelligence.alert_priority_score, s.source_id];
  for (let k = 1; k < D.sources.length; k++) { const [a, b] = [keyOf(D.sources[k - 1]), keyOf(D.sources[k])]; assert.ok(a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]), `order @${k}`); }
  assert.deepEqual(D.sources.map((s) => s.rank), D.sources.map((_, i) => i + 1));
  assert.deepEqual(inv(PIHS), inv(PIHS));   // pure function
  const pinned = fs.readFileSync(path.join(ROOT, 'tests/fixtures/thermwatch_historical.sha256'), 'utf8').trim();
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(contractPath)).digest('hex'), pinned, 'public/data/thermwatch_historical.json changed; if you rebuilt it on purpose, update tests/fixtures/thermwatch_historical.sha256');
});

test('real counts come from the generated contract, not hardcoded', () => {
  const s = D.system_stats; assert.ok(s.firms_observations > 2e6 && s.physical_sources > 1e6 && s.events > 1.2e6);
  for (const f of ['src/components/help/HelpDrawer.jsx', 'src/components/map/MapLegend.jsx', 'src/services/realStore.js']) {
    assert.doesNotMatch(fs.readFileSync(path.join(ROOT, f), 'utf8'), /2298170|2298169|1056161|1277339/, f);
  }
});

test('judge-facing source tree has no mock data references and no legacy imports', () => {
  const bad = /SYN-EVT|SYN-OBS|SYN-MRK|LANJIGARH_ASSESSMENT|fire_events|FIRE_\d|DEMO-FAC|syntheticMarkers|demoStore/i;
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
  for (const f of [...walk(path.join(ROOT, 'src')), ...walk(path.join(ROOT, 'public')), path.join(ROOT, 'index.html')]) {
    if (!/\.(jsx?|json|html|css)$/.test(f)) continue;
    const t = fs.readFileSync(f, 'utf8'); assert.doesNotMatch(t, bad, f);
    if (/\.jsx?$/.test(f) || /\.css$/.test(f)) assert.doesNotMatch(t, /Lanjigarh/i, `${f} mentions Lanjigarh`);
    if (/\.jsx?$/.test(f)) assert.doesNotMatch(t, /legacy\//, `${f} imports legacy`);
  }
  // The only permitted 'Lanjigarh' string is the real Global Energy Monitor facility registry row in the context layer.
  const ctx = JSON.parse(fs.readFileSync(path.join(ROOT, 'public/data/thermwatch_context.json'), 'utf8'));
  const hits = ctx.facilities.filter((f) => /lanjigarh/i.test(f.name));
  assert.deepEqual(hits.map((f) => f.id), ['L100000102479']);
  assert.doesNotMatch(JSON.stringify({ ...ctx, facilities: ctx.facilities.filter((f) => f.id !== 'L100000102479') }), /lanjigarh/i);
  for (const p of ['src/data', 'public/demo', 'backend', 'src/services/demoStore.js', 'src/components/investigation/InvestigationBody.jsx', 'public/thermwatch_demo.html'])
    assert.ok(!fs.existsSync(path.join(ROOT, p)), `${p} must not exist`);
});

test('UI/model wording never frames probability as a claim', () => {
  const files = ['src/intel/investigationModel.js', 'src/components/intel/InvestigationView.jsx', 'src/components/investigation/PointInvestigation.jsx', 'src/components/investigation/InvestigationHeader.jsx', 'src/components/investigation/PrintReport.jsx', 'src/components/alerts/AlertsDrawer.jsx', 'src/components/help/HelpDrawer.jsx', 'src/services/normalize.js'];
  for (const f of files) for (const line of fs.readFileSync(path.join(ROOT, f), 'utf8').split('\n')) {
    if (/^\s*\/\//.test(line)) continue;   // comments are not user-visible
    if (/probabilit/i.test(line)) assert.match(line, /not|no |never|without|fabricated/i, `${f}: ${line.trim().slice(0, 100)}`);
    assert.doesNotMatch(line, /Alert (Priority )?confidence/i);
  }
});
