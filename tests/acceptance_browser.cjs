// Browser acceptance test for the V7 UI on real V11 data. Requires playwright + Chromium.
//   BASE_URL=http://localhost:5173 CHROME=/path/to/chrome PLAYWRIGHT_PATH=/path/to/playwright node tests/acceptance_browser.cjs [outdir]
// MAPS_STUB=1 injects a minimal google.maps stub (no network) so marker creation from real data can be verified;
// the preview must then be built with VITE_GOOGLE_MAPS_API_KEY set to any non-empty value.
const fs = require('fs'); const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const BASE = process.env.BASE_URL || 'http://localhost:5173'; const OUT = process.argv[2] || '/tmp/acceptance'; const STUB = process.env.MAPS_STUB === '1';
fs.mkdirSync(OUT, { recursive: true });
const D = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/thermwatch_historical.json'), 'utf8'));
const C = JSON.parse(fs.readFileSync(path.join(__dirname, '../public/data/thermwatch_context.json'), 'utf8'));
const results = []; const ok = (n, c, x = '') => { results.push({ name: n, pass: !!c, extra: x }); console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${x ? '  — ' + x : ''}`); };
const MAPS_STUB_JS = `window.google = { maps: (() => {
  class LatLng { constructor(a, b) { this.a = a; this.b = b; } lat() { return this.a; } lng() { return this.b; } }
  class Map { constructor(el) { this.el = el; el.style.overflow = "hidden"; el.style.isolation = "isolate"; } setOptions() {} panTo(p) { window.__panTo = p; } setZoom(z) { window.__zoom = z; } panBy() {} }
  class OverlayView { setMap(m) { this.map = m; if (m) { this.onAdd(); this.draw(); } else this.onRemove(); }
    getPanes() { return { overlayMouseTarget: this.map.el }; } getProjection() { return { fromLatLngToDivPixel: (ll) => ({ x: (ll.lng() - 60) * 20, y: (35 - ll.lat()) * 20 }) }; } }
  class Shape { constructor() {} setMap() {} }
  return { Map, OverlayView, LatLng, Polygon: Shape, Circle: Shape, ControlPosition: { RIGHT_BOTTOM: 9 }, event: { clearInstanceListeners() {} } };
})() };`;
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  if (STUB) await page.addInitScript(MAPS_STUB_JS);
  const errors = []; page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  const body = () => page.evaluate(() => document.body.innerText);
  await page.goto(BASE, { waitUntil: 'networkidle' }); await page.waitForSelector('.legend__status');
  let t = await body();

  // UI structure (V7)
  const layout = await page.evaluate(() => ({ sidebar: !!document.querySelector('nav.sidebar'), topbar: !!document.querySelector('.topbar'), legend: !!document.querySelector('.legend'),
    nav: [...document.querySelectorAll('.nav-btn__label')].map((e) => e.textContent), alertBar: !!document.querySelector('.tw-ab, .tw-console'),
    rightPad: getComputedStyle(document.querySelector('.workspace')).paddingRight }));
  ok('V7 shell: sidebar + topbar + legend', layout.sidebar && layout.topbar && layout.legend);
  ok('V7 navigation intact (Map, Alerts, Activity, Facilities, Help)', ['Map', 'Alerts', 'Activity', 'Facilities', 'Help'].every((n) => layout.nav.includes(n)), layout.nav.join(','));
  ok('no permanent alert bar / no 320px right reservation', !layout.alertBar && layout.rightPad === '0px', `padding-right=${layout.rightPad}`);
  const nAlert = D.map_points.filter((x) => x.tier !== 'LOW').length;   // 726 HIGH + 342 MEDIUM
  ok('A. legend: default map shows only the alert points; all 3000 ranked sources still loaded', t.includes(`${nAlert} of 3000 sources in time range shown · 3000 loaded`), `${nAlert}`);
  ok('honest live-feed state shown (V7 data banner)', /Live FIRMS feed unavailable/.test(t));
  ok('no mock content on landing', !/Lanjigarh|SYN-|FIRE_|Demo data|Synthetic/i.test(t));
  if (STUB) {
    const cnt = () => page.evaluate(() => ({ ev: document.querySelectorAll('.tw-marker:not(.tw-marker--facility)').length, fac: document.querySelectorAll('.tw-marker--facility').length,
      ids: [...document.querySelectorAll('.tw-marker__dot')].map((b) => b.dataset.id), pulse: document.querySelectorAll('.tw-marker--pulse').length, halo: document.querySelectorAll('.tw-marker--halo').length }));
    let m = await cnt();
    ok('A. default map draws only alert points (726 HIGH + 342 MEDIUM), not thousands of sources', m.ev === nAlert && m.ev === 1068, `markers=${m.ev}`);
    ok('A. alert points use V7 marker language (726 pulse = HIGH, 342 halo = MEDIUM)', m.pulse === 726 && m.halo === 342, `pulse=${m.pulse} halo=${m.halo}`);
    ok('A. facilities are optional context (off by default)', m.fac === 0, `facilities=${m.fac}`);
    ok('A. marker ids are real SRC ids of HIGH/MEDIUM sources', m.ids.every((i) => /^SRC-[0-9a-f]{10}$/.test(i) && D.map_points.find((x) => x.source_id === i).tier !== 'LOW'));
    await page.screenshot({ path: `${OUT}/00_default_alert_points.png` });
    // B. existing Layers toggles reveal the broader source population + facilities without corrupting alerts
    await page.click('button:has-text("Layers")'); await page.waitForTimeout(200);
    await page.locator('.layers-panel .layer-row', { hasText: 'Low' }).locator('input').check();
    await page.locator('.layers-panel .layer-row', { hasText: 'Facilities' }).locator('input').check(); await page.waitForTimeout(300);
    m = await cnt();
    ok('B. Layers → Low reveals all 3,000 ranked sources; HIGH/MEDIUM alert markers unchanged', m.ev === 3000 && m.pulse === 726 && m.halo === 342, `markers=${m.ev} pulse=${m.pulse} halo=${m.halo}`);
    ok('B. Layers → Facilities reveals 449 real registry facilities', m.fac === 449, `facilities=${m.fac}`);
    await page.click('.layers-panel button:has-text("Reset filters")'); await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    ok('B. Reset returns to the alert-point default', (await cnt()).ev === 1068);
    // C. historical filtering with the existing V7 time control, real timestamps only
    const realIn = (a, b) => new Set(D.sources.filter((x) => x.events.some((ev) => (ev.first >= a && ev.first <= b) || (ev.last >= a && ev.last <= b))).map((x) => x.source_id));
    const openTime = async () => { if (!(await page.$('.time-panel'))) { await page.click('.time-btn'); await page.waitForSelector('.time-panel'); } };
    const setRange = async (from, to) => {
      await openTime(); await page.click('.time-panel [role=radio]:has-text("Historical")');
      const ins = page.locator('.time-panel input[type=datetime-local]'); await ins.nth(0).fill(from); await ins.nth(1).fill(to); await page.waitForTimeout(400);
    };
    await setRange('2026-01-01T00:00', '2026-01-31T23:59'); const jan = new Set((await cnt()).ids);
    await setRange('2026-09-01T00:00', '2026-09-30T23:59'); const sep = new Set((await cnt()).ids);
    const eq = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));
    const rj = realIn('2026-01-01T00:00', '2026-01-31T23:59:59'), rs = realIn('2026-09-01T00:00', '2026-09-30T23:59:59');
    const alertOnly = (set) => new Set([...set].filter((id) => D.map_points.find((x) => x.source_id === id).tier !== 'LOW'));
    ok('C. January range draws exactly the alert sources with a real event observation in January', eq(jan, alertOnly(rj)), `${jan.size} vs ${alertOnly(rj).size}`);
    ok('C. September range draws exactly the alert sources active in September', eq(sep, alertOnly(rs)), `${sep.size} vs ${alertOnly(rs).size}`);
    ok('C. different periods show different real activity', jan.size > 0 && sep.size > 0 && !eq(jan, sep));
    t = await body(); ok('C. untimed ranked sources are explained, not given invented dates', /no packaged timestamps/.test(t));
    await page.screenshot({ path: `${OUT}/00b_historical_september.png` });
    // back to Current / All available
    await openTime(); await page.click('.time-panel [role=radio]:has-text("Current")'); await page.waitForTimeout(150);
    await page.click('.time-btn'); await page.waitForTimeout(300);
    ok('C. returning to All available restores the 1068 alert points', (await cnt()).ev === 1068, `${(await cnt()).ev}`);
    // E. clicking an alert MARKER opens the V7 drawer with the V11 investigation
    await page.locator(`.tw-marker__dot[data-id="${D.sources[0].source_id}"]`).dispatchEvent('click'); await page.waitForTimeout(500);
    ok('E. clicking an alert marker opens the V7 investigation drawer with the full V11 record',
      (await page.getAttribute('[data-testid=real-investigation]', 'data-source-id').catch(() => null)) === D.sources[0].source_id && !!(await page.$('.drawer--right')));
    await page.click('.drawer--right .icon-btn'); await page.waitForTimeout(200);
  } else ok('map shows explicit key-missing state (no key in this run)', /Google Maps API key missing/.test(t));
  await page.screenshot({ path: `${OUT}/01_landing.png` });

  // Alerts → investigation (full record)
  await page.click('.nav-btn:has-text("Alerts")'); await page.waitForSelector('.alert-item');
  t = await body();
  ok('alerts: 726 real HIGH alerts, top = rank #1 real source', t.includes('All 726') || (await page.locator('.tabs__count').first().innerText()) === '726');
  ok('top alert is the rank-1 real source', (await page.locator('.alert-item__id').first().innerText()) === D.sources[0].source_id);
  await page.screenshot({ path: `${OUT}/02_alerts.png` });
  await page.locator('.alert-item').first().locator('text=Investigate').click(); await page.waitForSelector('[data-testid=real-investigation]');
  await page.click('text=Expand all steps'); await page.waitForTimeout(300);
  t = await body(); const s = D.sources[0];
  ok('investigation opens in V7 right drawer with full real record', (await page.getAttribute('[data-testid=real-investigation]', 'data-detail')) === 'full' && !!(await page.$('.drawer--right.drawer--wide')));
  for (const [n, v] of [['source id', s.source_id], ['first seen', s.identity.first_seen.slice(0, 16).replace('T', ' ')], ['detections', String(s.activity.detections)], ['first event', s.events[0].event_id],
    ['PIHS score', `${s.intelligence.pihs_score} / 8`], ['alert score', s.intelligence.alert_priority_score.toFixed(4)], ['nearest facility', s.spatial.nearest_facility], ['run id', D.pipeline_run_id]])
    ok(`investigation shows real ${n}`, t.includes(v), v);
  for (const w of ['Persistence & Activity', 'Event investigation', 'Coverage', 'Alert Priority', 'Machine learning', 'READY_NOT_TRAINED', 'Cause: Not confirmed', 'Unknown coverage is not interpreted as no fire']) ok(`investigation section/wording: ${w}`, t.includes(w));
  await page.screenshot({ path: `${OUT}/03_investigation.png` });

  // A4 report
  await page.emulateMedia({ media: 'print' });
  const rep = await page.evaluate(() => { const r = document.querySelector('#print-root [data-testid=print-report]'); return r ? { id: r.dataset.sourceId, text: r.innerText, vis: getComputedStyle(r).display !== 'none' } : null; });
  ok('print report rendered for the selected real source', rep && rep.id === s.source_id && rep.vis);
  ok('print report lists every real event', rep && s.events.every((e) => rep.text.includes(e.event_id)));
  ok('print report contains no mock incidents', rep && !/Lanjigarh|SYN-|FIRE_|synthetic/i.test(rep.text));
  await page.pdf({ path: `${OUT}/investigation_${s.source_id}_A4.pdf`, format: 'A4', printBackground: true });
  const pdfSize = fs.statSync(`${OUT}/investigation_${s.source_id}_A4.pdf`).size; ok('A4 PDF generated', pdfSize > 20000, `${pdfSize} bytes`);
  await page.emulateMedia({ media: 'screen' });

  // Ranked (non-full) source via search
  const ids = new Set(D.sources.map((x) => x.source_id)); const p = D.map_points.find((x) => !ids.has(x.source_id) && x.pihs);
  await page.fill('.search input', p.source_id); await page.waitForTimeout(250);
  await page.keyboard.press('Enter'); await page.waitForTimeout(500);
  const rid = await page.getAttribute('[data-testid=real-investigation]', 'data-source-id').catch(() => null);
  const rdet = await page.getAttribute('[data-testid=real-investigation]', 'data-detail').catch(() => null);
  await page.click('text=Expand all steps').catch(() => {}); await page.waitForTimeout(200);
  t = await body(); const en = C.point_enrichment[p.source_id];
  ok('search opens a real ranked (non-full) source investigation', rid === p.source_id && rdet === 'ranked', `${rid} ${rdet}`);
  ok('ranked investigation shows real registry n_obs + PIHS values', t.includes(en.n_obs.toLocaleString()) && t.includes(`${en.pihs_score} / 8`));
  ok('ranked investigation states missing detail instead of estimating it', t.includes('packaged only for the top 300'));
  await page.screenshot({ path: `${OUT}/05_ranked_source.png` });
  await page.fill('.search input', D.sources[0].source_id); await page.waitForTimeout(250);
  const first = await page.locator('.search__results li').first().innerText().catch(() => '');
  await page.keyboard.press('Enter'); await page.waitForTimeout(500);
  ok('D. search SRC-f10396fc99 → first result is that real source and opens its V11 investigation',
    first.includes(D.sources[0].source_id) && (await page.getAttribute('[data-testid=real-investigation]', 'data-source-id').catch(() => null)) === D.sources[0].source_id);
  await page.click('.drawer--right .icon-btn').catch(() => {});
  await page.fill('.search input', 'Hazira'); await page.waitForTimeout(250);
  const hz = await page.locator('.search__results').innerText().catch(() => '');
  ok('D. search "Hazira" returns real GEM facilities', /Hazira power station|ArcelorMittal Nippon Steel Hazira/.test(hz));
  await page.locator('.search__results li', { hasText: 'Hazira' }).first().click(); await page.waitForTimeout(500);
  const sel = C.facilities.find((f) => f.name === (hz.match(/(Hazira power station \([^)]+\)|ArcelorMittal Nippon Steel Hazira plant|Hazira power station)/) || [])[0]);
  ok('D. choosing a facility opens the Facilities drawer on that facility', (await page.locator('.facility.is-selected').count()) === 1);
  if (STUB) ok('D. the chosen facility is pinned on the map although the Facilities layer is off', (await page.locator('.tw-marker--facility').count()) === 1, `${await page.locator('.tw-marker--facility').count()}`);
  t = await body(); ok('D. facility card reports real ranked sources within 5 km', /Ranked sources ≤ 5 km/.test(t));
  await page.screenshot({ path: `${OUT}/06_search_hazira.png` });

  // Facilities
  await page.click('.nav-btn:has-text("Map")'); await page.click('.nav-btn:has-text("Facilities")'); await page.waitForSelector('.facility');
  ok('facilities drawer lists 449 real registry facilities', (await page.locator('.facility').count()) === 449);
  await page.screenshot({ path: `${OUT}/04_facilities.png` });
  await page.click('.nav-btn:has-text("Help")'); t = await body();
  const st = D.system_stats;
  for (const [n, v] of [['valid observations', '2,298,169'], ['sources', '1,056,161'], ['events', '1,277,339'], ['PIHS', '220'], ['HIGH', '726'], ['MEDIUM', '342'], ['ML', 'READY_NOT_TRAINED']])
    ok(`help exposes real figure: ${n} ${v}`, t.includes(v) && (n === 'ML' || [st.valid_observations, st.physical_sources, st.events, st.pihs_candidates, st.alerts_high, st.alerts_medium].map((x) => x.toLocaleString()).includes(v)));
  ok('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  await browser.close();
  fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
  const f = results.filter((r) => !r.pass).length; console.log(`\n${results.length - f}/${results.length} passed`); process.exit(f ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
