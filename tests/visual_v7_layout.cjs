// V7 layout acceptance: walks the app from its root through 7 states at 1400x900 and compares the
// position, size and typography of every shell element with the baseline measured on the ORIGINAL V7
// application (tests/fixtures/v7_layout_baseline.json). Any deviation fails.
//   BASE_URL=... CHROME=... PLAYWRIGHT_PATH=... node tests/visual_v7_layout.cjs [outdir]
//   RECORD=1 BASE_URL=<V7 app> ... node tests/visual_v7_layout.cjs   -> (re)records the baseline from V7
// A minimal google.maps stub is injected so the map canvas and markers render without a key/network.
const fs = require('fs'); const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const BASE = process.env.BASE_URL || 'http://localhost:5173'; const OUT = process.argv[2] || '/tmp/v7layout';
const FIX = path.join(__dirname, 'fixtures/v7_layout_baseline.json'); fs.mkdirSync(OUT, { recursive: true });
const STUB = `window.google={maps:(()=>{class LatLng{constructor(a,b){this.a=a;this.b=b}lat(){return this.a}lng(){return this.b}}
class Map{constructor(el){this.el=el;el.style.overflow="hidden";el.style.isolation="isolate"}setOptions(){}panTo(){}setZoom(){}panBy(){}}
class OverlayView{setMap(m){this.map=m;if(m){this.onAdd();this.draw()}else this.onRemove()}getPanes(){return{overlayMouseTarget:this.map.el}}
getProjection(){return{fromLatLngToDivPixel:(ll)=>({x:(ll.lng()-60)*28+100,y:(36-ll.lat())*28})}}}
class S{setMap(){}}return{Map,OverlayView,LatLng,Polygon:S,Circle:S,ControlPosition:{RIGHT_BOTTOM:9},event:{clearInstanceListeners(){}}}})()};`;
const SEL = ['.app-shell', 'nav.sidebar', '.brand', '.sidebar__nav', '.sidebar__foot', '.workspace', '.topbar', '.search', '.topbar__right', '.legend', '.map-canvas-wrap', '.drawer--left', '.drawer--right', '.drawer__head', '.drawer__body', '.layers-panel', '.nav-btn', '.tabs'];
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME, args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 1400, height: 900 } }); await p.addInitScript(STUB);
  await p.goto(BASE, { waitUntil: 'networkidle' }); await p.waitForTimeout(800);
  const geo = {};
  const shot = async (n) => {
    await p.screenshot({ path: `${OUT}/${n}.png` });
    geo[n] = await p.evaluate((sel) => Object.fromEntries(sel.map((s) => { const e = document.querySelector(s); if (!e) return [s, null]; const r = e.getBoundingClientRect(); const c = getComputedStyle(e);
      return [s, [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height), c.fontFamily.split(',')[0].replace(/"/g, ''), c.fontSize, c.backgroundColor]]; })), SEL);
  };
  await shot('1_landing');
  await p.click('.nav-btn:has-text("Alerts")'); await p.waitForTimeout(400); await shot('2_alerts');
  await p.locator('.alert-item').first().locator('text=Investigate').click(); await p.waitForTimeout(600); await shot('3_investigation');
  await p.click('.drawer--right .icon-btn'); await p.click('.nav-btn:has-text("Activity")'); await p.waitForTimeout(400); await shot('4_activity');
  await p.click('.nav-btn:has-text("Facilities")'); await p.waitForTimeout(400); await shot('5_facilities');
  await p.click('.nav-btn:has-text("Help")'); await p.waitForTimeout(400); await shot('6_help');
  await p.click('.nav-btn:has-text("Help")'); await p.click('button:has-text("Layers")'); await p.waitForTimeout(300); await shot('7_layers');
  await b.close();
  if (process.env.RECORD === '1') { fs.writeFileSync(FIX, JSON.stringify(geo, null, 1)); console.log(`baseline recorded from ${BASE}`); return; }
  const base = JSON.parse(fs.readFileSync(FIX, 'utf8')); let fail = 0, n = 0;
  for (const st of Object.keys(base)) for (const s of SEL) { n++; const x = JSON.stringify(base[st][s]), y = JSON.stringify(geo[st]?.[s]);
    if (x !== y) { fail++; console.log(`FAIL  ${st} ${s}\n      V7:    ${x}\n      final: ${y}`); } }
  console.log(`${n - fail}/${n} shell measurements identical to V7`); process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
