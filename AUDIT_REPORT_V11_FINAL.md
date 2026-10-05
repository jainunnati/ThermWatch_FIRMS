# ThermWatch SIH26162 — V11 FINAL audit report

Date: 2026-10-04. Rebuilt from the two supplied ZIPs: `ThermWatch-SIH26162-V7.zip` and `ThermWatch-SIH26162-V11-FINAL.zip`.

> **V7 is the frontend/layout source of truth.**
> **V11 is the real-data/intelligence/report source of truth.**
>
> The application root is V7's `src/main.jsx` → `AppProvider` → V7 `App.jsx` (Sidebar, MapView, topbar, legend, drawers). V11's `ThermWatchConsole`, `AlertBar`, tabbed console, 320 px reservation and standalone Intel page are **not** in the project (verified by grep and by tests).

## 0. This revision — map information hierarchy, historical filtering, search, FIRMS wiring

Scope was limited to marker filtering, search behaviour and FIRMS wiring. The V7 shell, layout, drawers, CSS and the V11 investigation/report are unchanged. `tests/visual_v7_layout.cjs` still reports **126/126 shell measurements identical to the original V7**.

| Area | Before | After | File(s) |
|---|---|---|---|
| Default map | All 3,000 ranked sources + 449 facilities drawn | **Alert points only: 1,068 = 726 HIGH + 342 MEDIUM**, in V7's existing marker style (HIGH pulse, MEDIUM halo) | `src/utils/filters.js` (default `severities.low=false`, `context.facilities=false`) |
| Ordinary sources | — | Still loaded (all 3,000). Revealed with V7's existing **Layers → Low** toggle; facilities with **Layers → Facilities / OSM**. Reset returns to alert points. The full 1,056,161-source registry remains in `data-pipeline/intel_v1/live_indexes/registry_index.csv.gz` and is never rendered as raw points. | `LayersPanel.jsx` (tooltip text only) |
| Time behaviour | Out-of-range sources drawn dimmed by default | Out-of-range sources not drawn by default (existing "Historical thermal events" toggle can re-enable dimmed display), so V7's Historical range changes what is visible. Filtering uses only real event first/last timestamps (top-300 records). Sources without packaged timestamps appear only under "All available", with a legend note; no dates invented. | `filters.js`, `MapLegend.jsx` (note now also shown in Historical mode) |
| Search | Substring over ids, location names, facilities; unordered | Exact source-ID match first; facilities by name, place, type and registry kind (e.g. "Hazira", "steel", "coal"); sources by nearest-facility name/attribution context, in Alert Priority rank order; unmatched → no results | `src/services/search.js` |
| Facility context | "Nearby" linked only by name, top-300 only | Each facility lists the real ranked sources **within 5 km** (haversine on real coordinates, same 5 km radius as the pipeline's facility context), ranked. Choosing a facility in search pins it and those sources on the map even when their layers are off. Labelled as context, never cause. | `realStore.js` (`attachNearbySources`), `FacilitiesDrawer.jsx`, `MapView.jsx` |
| Help | — | New "What the map shows" topic: alert points vs ranked sources vs full registry; Alert Priority ≠ model confidence; how to search and use Historical mode | `HelpDrawer.jsx` |
| FIRMS live area (**bug fix**) | `live_update.py` declared an all-India `BBOX` but `fetch_window` always used `config.REGION_BBOX` (South Gujarat dev box), so a valid key would only ever query South Gujarat | `fetch_window(..., bbox=None)` (default unchanged); `live_update.fetch_live` passes the all-India `BBOX`. Region-scoped cache is used only for the default region. | `data-pipeline/ingest_firms.py`, `data-pipeline/intel_v1/live_update.py` |
| FIRMS credential naming | Checked: `FIRMS_MAP_KEY` is used consistently by `config.py`, `ingest_firms.py`, `live_update.py`, `data-pipeline/.env.example` and the GitHub Actions secret. The frontend never reads it (it reads only `thermwatch_live.json`). | **Left unchanged** (correct). No key hard-coded; no `.env` committed. | — |

Live-vs-historical: when the key is missing or rejected, `live_update.py` publishes `LIVE_FEED_UNAVAILABLE` with zero live sources. The app shows "Live FIRMS feed unavailable … showing validated historical data to 2026-10-01" and labels data "Real data" (historical window 2026-01-01 → 2026-10-01). Historical data is never presented as a live feed.

Validated figures unchanged: 2,298,170 ingested / 2,298,169 valid observations; 1,056,161 sources; 1,277,339 events; 1,056,136 monitored; 220 PIHS; 726 HIGH; 342 MEDIUM. Contract SHA-256 unchanged (pinned test).

### Results of this revision (run on the unpacked final ZIP)

| Test | Result |
|---|---|
| A — default map draws 1,068 alert points (726 pulse, 342 halo), no facilities, only HIGH/MEDIUM real SRC ids | pass |
| B — Layers → Low shows all 3,000 with alert markers unchanged; Facilities shows 449; Reset restores 1,068 | pass |
| C — January / September ranges draw exactly the alert sources with a real event observation in that month (296 / 300); periods differ; untimed sources explained; All available restores 1,068 | pass |
| D — search `SRC-f10396fc99` → first result, opens V11 investigation; "Hazira" → real GEM facilities; choosing one opens its card, lists ranked sources ≤ 5 km, pins it on the map | pass |
| E — clicking an alert marker opens the V7 drawer with the full V11 investigation | pass |
| F — honesty wording (Cause: Not confirmed, READY_NOT_TRAINED, Alert Priority, no probabilities) | pass (render + acceptance suites) |
| G — mock scan | 0 obsolete mock artifacts (section 5) |
| H — secret scan | clean; no `.env` files |
| I — build | `npm install` **failed (registry 403)**; `npm run build` not run. Production build NOT verified (section 8). |
| FIRMS wiring (`test_live_wiring.py`) | 4/4: variable name consistent; live request uses all-India area for all 3 NRT sources; missing key → `LIVE_FEED_UNAVAILABLE`; rejected-key error does not echo the key |

## 1. Sources of truth

| Role | Source | How it was used |
|---|---|---|
| UI / layout / design | **V7** | The whole V7 `src/` tree was the starting point. Shell, sidebar navigation, topbar (search, time control, base-map switch, layers), map view and marker overlay, legend, left drawers (Alerts, Activity, Facilities, Help), right investigation drawer (480 px), typography and CSS were kept. |
| Real data / intelligence / reports | **V11** | V11's validated contract, live artifact, real indexes, investigation model, 11-step investigation content, charts, A4 report and data pipeline were carried over and connected to the V7 UI. |

Result: **V7 UI + V11 real data + V11 detailed investigator/report.** One application; no parallel console, no standalone page.

## 2. UI preservation (V7 → final)

Byte-identical to V7: `index.html`, `Sidebar.jsx`, `SearchBar.jsx`, `TimeControl.jsx`, `BaseMapSwitch.jsx`, `markerOverlay.js`, `ActivityDrawer.jsx`, `Drawer.jsx`, `Empty.jsx`, `ErrorBoundary.jsx`, `Swatches.jsx`, `useGoogleMaps.js`, `format.js`, `geo.js`, `behaviour.js`, `severity.js`, `industrialTypes.js`.

`app.css`: 5 lines differ, all badge colour classes (`status-pill--demo`, `chip-tag--synthetic`, `banner--synthetic*`, `banner--supplied` replaced by `chip-tag--pihs`, `banner--real_ranked`, `banner--real_detailed`). No layout, width or spacing rule changed.

Changed for behaviour/content only (layout untouched): LayersPanel (tooltips), filters.js (default layers), search.js (ranking/matching), AlertsDrawer, FacilitiesDrawer, HelpDrawer, MapLegend (data pill and count text; V7 wording kept), MapView (marker tooltip text), Chips (label wording), App (error banner text), InvestigationDrawer/PrintReport (now render the V11 investigation). `investigation.css` adds only tiles, callouts, tags and bars used inside the V7 drawer.

- No permanent right-side Alert Bar; no 320 px reservation (V11 `AlertBar.jsx`, `ThermWatchConsole.jsx` and their CSS were not carried over). The browser test asserts `.workspace` padding-right is 0 and no `.tw-ab`/`.tw-console` exists.
- Screenshots of V7 and the final build at 1400×900 were compared side by side: same layout.

## 2b. Visual acceptance against the original V7 (1400×900)

`tests/visual_v7_layout.cjs` starts both applications from their roots and walks 7 states:
1. landing
2. Alerts drawer
3. investigation opened from the top alert
4. Activity
5. Facilities
6. Help
7. Layers panel

In each state it measures position, size, font family, font size and background of 18 shell elements: app shell, sidebar, brand, sidebar nav/foot, workspace, topbar, search, topbar controls, legend, map canvas, left drawer, right drawer, drawer head/body, layers panel, nav button, tabs. The baseline `tests/fixtures/v7_layout_baseline.json` was recorded from the **original, unmodified V7 application** (built from `ThermWatch-SIH26162-V7.zip`).

**Result: 126/126 shell measurements identical to V7.**

- The first comparison found one deviation: the legend was 18–51 px taller because of longer status wording. It was fixed by restoring V7's legend wording ("Colour = source", "Size / pulse = severity", a single data pill, the V7 count sentence). The live-feed status remains in V7's data banner and in Help.
- Side-by-side screenshots for all 7 states are in `docs/v7_vs_final/`.
- A minimal `google.maps` stand-in is used in both runs (no key/network in the sandbox). It clips markers to the map like the real API.

## 3. Real data retained

| File | Content |
|---|---|
| `public/data/thermwatch_historical.json` | V11 contract v2, **byte-identical** to V11's `thermwatch_demo.json` (renamed only). SHA-256 `91bb3a8147a8675539f8a8ec700b9433fb3ee854a77aaf29d21ef8730287eb63` (original `91bb3a8147a8675539f8a8ec700b9433fb3ee854a77aaf29d21ef8730287eb63`). |
| `public/data/thermwatch_live.json` | V11 live artifact: `LIVE_FEED_UNAVAILABLE` (FIRMS credentials missing or rejected). |
| `public/data/thermwatch_context.json` | New, built by `data-pipeline/intel_v1/build_frontend_context.py` purely from V11's real indexes: 449 GEM registry facilities; registry `n_obs` for all 3,000 ranked sources (from the 1,056,161-row registry); pihs-v1 score/active days/night fraction for all 220 candidates. |

Contract figures: 2,298,169 valid FIRMS observations (2,298,170 ingested) → 1,056,161 sources → 1,277,339 events; 1,056,136 monitored (25 held out); 220 PIHS candidates; 726 HIGH / 342 MEDIUM Alert Priority; window 2026-01-01..2026-10-01; status `HISTORICAL_VALIDATED`.

How it appears in the V7 UI:
- **Map**: 3,000 markers = the top-3,000 real sources by Alert Priority, at real coordinates, with real `SRC-…` IDs. Size/pulse = real tier (726 pulse as HIGH). Colour = heuristic facility-attribution context (Industrial context for steel/metal, thermal power, LNG/gas within 5 km; otherwise Unknown/Other). 449 real facility markers.
- **Alerts**: the 726 real HIGH-tier sources in rank order; rank #1 = `SRC-f10396fc99`.
- **Facilities**: 449 real registry facilities, linked by name to nearby ranked sources.
- **Time control**: real event first/last timestamps (top-300). Ranked sources without packaged times appear only under "All available"; no time is invented.

Contract labels `mode: "DEMO"` and run id `demo-a6cc1be9870b` are untouched pipeline output (V11's term for the deterministic historical build). They are not mock data; the UI labels this data "Historical (validated)" and "Real FIRMS data".

## 4. Detailed investigator report retained

The V11 investigation model (`src/intel/investigationModel.js`) and full content (`InvestigationView.jsx`) are unchanged in substance and render inside the V7 investigation drawer under a V7-style header. For each of the top-300 sources, all 11 steps:

1. Identity
2. Observations
3. Persistence & Activity, with the PIHS rule check recomputed against pipeline values
4. Every event, with timeline and table
5. Thermal
6. Spatial
7. Facility context and heuristic attribution
8. Per-source coverage window with unknown-coverage dates
9. Alert Priority component breakdown, reconciled with the stored score
10. ML (`READY_NOT_TRAINED`)
11. Limitations, with "Cause: Not confirmed"

**Print investigation** produces an A4 report from the same content, all steps expanded and every event listed. Verified: `SRC-f10396fc99` exported to a 9-page A4 PDF in headless Chromium.

The other 2,700 ranked sources have no event-level record in the contract (V11 size cap: 300). Their investigation and report show only their real fields (rank, tier, coordinates, registry `n_obs`, PIHS values) and state that the remaining detail is not packaged. Nothing is estimated.

## 5. Mock / demo data removed (deleted from the filesystem)

From V7:
- `src/data/demo/lanjigarh.js` (Lanjigarh synthetic worked example)
- `src/data/demo/syntheticMarkers.js`
- `src/data/demo/facilities.js` (DEMO-FAC-*)
- `src/services/demoStore.js`
- `public/demo/fire_events.json`
- `backend/` (Express mock server incl. `backend/data/fire_events.json`)
- V7 `data-pipeline/` (incl. `sample_data.py`, `build_backend_data.py`; replaced by V11's pipeline)
- `InvestigationBody.jsx`, `ContextImagery.jsx`, investigation `parts.jsx`, all six synthetic-assessment charts
- Demo/API data-mode switch, "Use demo data" fallback

From V11:
- `public/thermwatch_demo.html` (standalone parallel page)
- `public/thermwatch_intel.json`
- `build_standalone.py`, `standalone_template.html`
- `ThermWatchConsole.jsx`, `AlertBar.jsx` and their tests
- `run_demo.sh` (→ `run_pipeline.sh`), `run_demo.py` (→ `build_contract_v1.py`)
- Superseded `AUDIT_REPORT_FINAL.md` and `PRODUCT_INTEGRATION_REPORT.md`

### Recursive scan

Patterns: `Lanjigarh`, `LANJIGARH`, `FIRE_`, `fire_events`, `legacy`, `google-map-shell`, `sample_data`, `demo`/`Demo`/`DEMO`, `SYN-`, `synthetic`, `mock`. File names: `*demo*`, `*mock*`, `*sample*`, `*fire_events*`, `*lanjigarh*`, `*legacy*`.

| Classification | Hits |
|---|---|
| 1. Legitimate real data | `Lanjigarh Refinery power station` (GEM coal plant, id L100000102479) in `live_indexes/facilities_index.csv` and `thermwatch_context.json`. Contract fields `mode:"DEMO"` / run id `demo-…` (pipeline output, byte-pinned). |
| 2. Test fixture | `ml_v1/test_ml_v1.py` `SYN-*` ids and `m1/validate_label_packet.py` "synthetic-test" rows (temporary software-test fixtures for the training gate). `test_intel_v1.py` synthetic feature dicts. `thermwatch_core/schema.py` `TEST_FIXTURE` mode. All assertions in `tests/*` and `test_investigation_v1.py` that *forbid* mock markers. |
| 3. Documentation / code guards | README sentences stating no mock data exists. `thermwatch_core` `DataMode.DEMO` guard that refuses to mix demo data with FIRMS data. "legacy 3 km" radius comments in `facility.py`. Comment in `intel/parts.jsx`. Filenames `m1/sample_label_candidates.py` and `m1/audit_label_sample.py` (statistical sampling of label candidates, not sample data). |
| 4. Obsolete mock data | **0** |

`google-map-shell`: 0 hits. The Google Maps component is V7's real map view, not a demo shell.

The tests enforce that the only "Lanjigarh" string is that one real facility row (`investigation.test.mjs`, `test_investigation_v1.py`).

## 6. Scientific honesty (unchanged from V11)

- ML is `READY_NOT_TRAINED` (0 defensible labels; gate ≥ 30 per class from ≥ 8 site complexes). No classifier probabilities or accuracy figures anywhere.
- Attribution is labelled heuristic relative weights, not probabilities.
- Cause is "Not confirmed" everywhere.
- Unknown coverage is never "no fire".
- The live feed is shown as unavailable; there is no silent fallback dataset. A failed data load shows an error banner.

## 7. Test results (run on the unpacked final ZIP)

| Suite | Result |
|---|---|
| `tests/investigation.test.mjs` (model, rule drift, honesty, mock isolation, contract hash) | 13/13 pass |
| `tests/data_integrity.test.mjs` (counts, map layer, context vs registry, V7 mapping, alerts, time filter, live honesty, secrets, default layers, historical ranges, search, 5 km proximity) | 13/13 pass |
| `tests/render.test.mjs` (server-rendered investigation + A4 report for all 300 sources, header, ranked-source report) | 7/7 pass |
| `tests/visual_v7_layout.cjs` — final vs original-V7 baseline | 126/126 identical |
| `tests/acceptance_browser.cjs` — no Maps key | 46/46 pass |
| `tests/acceptance_browser.cjs` — `MAPS_STUB=1` (Tests A–E incl. markers, layers, time, search) | 59/59 pass |
| `data-pipeline/intel_v1/test_investigation_v1.py` | 8/8 pass |
| `data-pipeline/intel_v1/test_live_wiring.py` | 4/4 pass |
| `data-pipeline/intel_v1/test_intel_v1.py` | 13 run, 12 pass, 1 skipped (needs an intermediate output not in the ZIPs) |
| `data-pipeline/m1/test_ingest_annotations.py` | 7/7 pass |
| `data-pipeline/intel_v1/test_product_v1.py` | 8/9 pass; 1 error (`test_association_new_source_and_dedup`). **Pre-existing**: the original V11 ZIP fails identically. |
| `data-pipeline/ml_v1/test_ml_v1.py` | 3/7 pass; 3 errors + 1 failure. **Pre-existing**: identical in the original V11; they read files from the original build machine (`/home/claude/ml_ids_6892.txt`, `/mnt/user-data/outputs/adjudication_pass1/…`) that are not in either ZIP. |
| Mock-data scan | 0 obsolete mock hits (section 5) |
| Secret scan (Google/AWS/GitHub/OpenAI key patterns, private keys, key-like assignments, 32-hex strings outside the contract) | clean; no `.env` committed |

`test_investigation_v1.py` had 3 tests that hard-coded V11's console-only architecture (e.g. "App must import ThermWatchConsole", "src/services must not exist"). They were rewritten to assert the new architecture (V7 shell on the real store only) and the real-facility Lanjigarh exception.

## 8. Build status and environment limitations

- `npm install`: **FAILED** — the npm registry returned `403 Forbidden` (sandbox has no package-registry access).
- `npm run build`: **NOT RUN SUCCESSFULLY** — `vite: not found` (consequence of the failed install). **The production Vite build has not been verified.**
- Substitute verification: `tests/build_preview.mjs` bundles `src/main.jsx` with esbuild (React 19 from the sandbox's global modules; the project declares React 18.3). This compiled with no errors, and all browser tests ran against it. This is an offline verification bundle, **not** the production build. Run `npm install && npm run build` on a networked machine before deployment.
- Google Maps tiles could not be tested (no API key, no network). With no key the V7 "key missing" state is shown and verified. Marker creation from real data was verified against a minimal `google.maps` stub.
- Live FIRMS feed: unavailable (no `FIRMS_MAP_KEY`). The UI shows this honestly.
- `run_pipeline.sh` / `build_contract_v2.py` need the intermediate pipeline outputs from the original build machine (not in either ZIP) to regenerate the contract. The packaged contract is the validated V11 artifact.
