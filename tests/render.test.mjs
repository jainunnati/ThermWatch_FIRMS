// Render tests: the REAL React components, server-rendered with the REAL contract.
// Needs esbuild (a dependency of vite) and react/react-dom. Run: npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const esbuild = require(process.env.ESBUILD_PATH || 'esbuild');
const D = JSON.parse(fs.readFileSync(path.join(ROOT, 'public/data/thermwatch_historical.json'), 'utf8'));

const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'tw-render-')), 'bundle.cjs');
const entry = `
  import React from 'react'; import { renderToStaticMarkup } from 'react-dom/server';
  import { buildInvestigation } from ${JSON.stringify(path.join(ROOT, 'src/intel/investigationModel.js'))};
  import { InvestigationContent } from ${JSON.stringify(path.join(ROOT, 'src/components/intel/InvestigationView.jsx'))};
  import PrintReport from ${JSON.stringify(path.join(ROOT, 'src/components/investigation/PrintReport.jsx'))};
  import PointInvestigation from ${JSON.stringify(path.join(ROOT, 'src/components/investigation/PointInvestigation.jsx'))};
  import InvestigationHeader from ${JSON.stringify(path.join(ROOT, 'src/components/investigation/InvestigationHeader.jsx'))};
  import { mapPointToEvent } from ${JSON.stringify(path.join(ROOT, 'src/services/normalize.js'))};
  const ev = (s, c) => { const i = c.map_points.findIndex((p) => p.source_id === s.source_id); return mapPointToEvent(c.map_points[i], i + 1, { source: s, contract: c }); };
  export const report = (s, c) => renderToStaticMarkup(React.createElement(PrintReport, { event: ev(s, c), inv: buildInvestigation(s, c, null), contract: c, generatedAt: '2026-10-04T12:00:00Z' }));
  export const screen = (s, c) => renderToStaticMarkup(React.createElement(InvestigationContent, { inv: buildInvestigation(s, c, null), open: new Set(['id','obs','persist','events','thermal','spatial','facility','coverage','alert','ml','limits']), onToggle() {} }));
  export const header = (s, c) => renderToStaticMarkup(React.createElement(InvestigationHeader, { event: ev(s, c) }));
  export const point = (p, rank, enrichment, c) => { const e = mapPointToEvent(p, rank, { enrichment, contract: c });
    return { screen: renderToStaticMarkup(React.createElement(PointInvestigation, { event: e, contract: c, printMode: true })),
             report: renderToStaticMarkup(React.createElement(PrintReport, { event: e, inv: null, contract: c, generatedAt: '2026-10-04T12:00:00Z' })) }; };
`;
await esbuild.build({ stdin: { contents: entry, resolveDir: ROOT, loader: 'jsx' }, bundle: true, platform: 'node', format: 'cjs', outfile: out, loader: { '.js': 'jsx', '.jsx': 'jsx' }, external: ['react', 'react-dom', 'react-dom/server'], logLevel: 'error' });
const R = require(out);
const text = (h) => h.replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, ' ');
const PIHS = D.sources.find((s) => s.intelligence.pihs_flag); const ORD = D.sources.find((s) => !s.intelligence.pihs_flag);

test('print report prints the real source values (PIHS candidate and ordinary source)', () => {
  for (const s of [PIHS, ORD]) {
    const t = text(R.report(s, D));
    for (const v of [s.source_id, s.identity.first_seen.slice(0, 16).replace('T', ' '), String(s.activity.detections), s.events[0].event_id, s.events.at(-1).event_id, D.pipeline_run_id,
      s.activity.frp_max.toFixed(2), `${s.intelligence.pihs_score} / 8`, s.intelligence.alert_priority_score.toFixed(4)]) assert.ok(t.includes(v), `missing ${v}`);
    if (s.spatial.nearest_facility) assert.ok(t.includes(s.spatial.nearest_facility));
    for (const h of ['ThermWatch · SIH26162', 'Generated', 'Historical (validated) data to 2026-10-01', 'Source identity', 'Observations', 'Persistence & Activity', 'Event investigation', 'Thermal behaviour', 'Spatial behaviour', 'Coverage', 'Alert Priority', 'Machine learning', 'Limitations & caveats']) assert.ok(t.includes(h), h);
    assert.ok(s.events.every((e) => t.includes(e.event_id)), 'print has every event');
  }
});

test('print/screen contain required honesty wording and no mock data', () => {
  for (const s of [PIHS, ORD]) for (const html of [R.report(s, D), R.screen(s, D)]) {
    const t = text(html);
    for (const w of ['Cause: Not confirmed', 'NOT TRAINED', 'Unknown coverage is not interpreted as no fire', 'heuristic relative weights, not calibrated probabilities', 'contextual evidence, not proof of cause',
      'not a probability of fire or industrial cause', 'does not imply continuous thermal activity between satellite overpasses', 'Repeated thermal activity over multiple observation days increases investigation priority',
      'silver-label experiment was rejected after leakage/confounding diagnostics']) assert.ok(t.includes(w), w);
    assert.doesNotMatch(t, /Lanjigarh|SYN-|synthetic/i); assert.doesNotMatch(t, /\bF1\b|accuracy\s*[:=]?\s*\d|\d\s*%\s*accura/i);
    assert.doesNotMatch(t, /\d+(\.\d+)?\s?% probability/i);
  }
});

test('all 300 real sources render a full investigation and report without error', () => {
  for (const s of D.sources) { const h = R.report(s, D); assert.ok(h.includes(s.source_id) && h.includes('Persistence &amp; Activity')); }
});

test('PIHS vs ordinary sources are presented differently and truthfully', () => {
  assert.ok(text(R.screen(PIHS, D)).includes('PIHS CANDIDATE') && !text(R.screen(PIHS, D)).includes('NOT A PIHS CANDIDATE'));
  const o = text(R.screen(ORD, D)); assert.ok(o.includes('NOT A PIHS CANDIDATE') && o.includes('Not flagged because'));
});

test('V7 investigation header shows real identity and honest labels', () => {
  const t = text(R.header(PIHS, D));
  for (const v of [PIHS.source_id, 'Alert Priority rank #1', 'PIHS candidate', 'Cause: Not confirmed', 'Not assessed', PIHS.spatial.nearest_facility]) assert.ok(t.includes(v), v);
});

test('ranked sources without a packaged full record get a truthful, non-estimated investigation + report', () => {
  const ctx = JSON.parse(fs.readFileSync(path.join(ROOT, 'public/data/thermwatch_context.json'), 'utf8'));
  const ids = new Set(D.sources.map((s) => s.source_id));
  const idx = D.map_points.findIndex((p) => !ids.has(p.source_id) && p.pihs);
  const p = D.map_points[idx]; const en = ctx.point_enrichment[p.source_id];
  const r = R.point(p, idx + 1, en, D);
  for (const h of [r.screen, r.report]) {
    const t = text(h);
    for (const v of [p.source_id, `#${idx + 1}`, String(en.n_obs), `${en.pihs_score} / 8`, 'PIHS CANDIDATE', 'packaged only for the top 300', 'READY_NOT_TRAINED', 'Not confirmed']) assert.ok(t.includes(v), v);
    assert.doesNotMatch(t, /Lanjigarh|SYN-|synthetic|FIRE_/i);
  }
});

test('unknown-coverage days appear in the report for a source overlapping S-NPP gaps', () => {
  const s = D.sources.find((x) => /S-NPP has \d+ unverified/.test(x.uncertainty.coverage_status));
  const t = text(R.report(s, D)); assert.ok(t.includes('unknown-coverage dates') || t.includes('unverified days')); assert.ok(t.includes('Unknown coverage is not interpreted as no fire'));
});
