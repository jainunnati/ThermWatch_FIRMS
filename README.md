# ThermWatch — SIH26162 (V11 FINAL)

Satellite thermal-event intelligence for industrial sites: **V7 user interface + V11 real data + V11 detailed investigation/report.**

## Run

```bash
npm install
cp .env.example .env      # add VITE_GOOGLE_MAPS_API_KEY for the map tiles
npm run dev               # http://localhost:5173
npm run build             # production build → dist/
```

Without a Google Maps key the map shows an explicit "key missing" state; Alerts, Activity, Facilities, Help, Investigation and the A4 report all still work on the real data.

## Live FIRMS feed (optional)

The browser never sees the FIRMS key. The Python pipeline reads `FIRMS_MAP_KEY` (from the environment, `data-pipeline/.env`, or the GitHub Actions secret of the same name) and publishes `public/data/thermwatch_live.json`, which the app reads.

```bash
cp data-pipeline/.env.example data-pipeline/.env        # put your NASA FIRMS MAP_KEY on the FIRMS_MAP_KEY= line
pip install -r data-pipeline/requirements.txt
python3 data-pipeline/intel_v1/live_update.py --indexes data-pipeline/intel_v1/live_indexes --out public/data/thermwatch_live.json
```

It queries the last day of VIIRS NRT (NOAA-20, NOAA-21, S-NPP) over India (`68,6,97.5,37.5`). If the key is missing or rejected it publishes `LIVE_FEED_UNAVAILABLE` and the app keeps showing the validated historical data, labelled as historical. The Google Maps key (`VITE_GOOGLE_MAPS_API_KEY` in the root `.env`) and the FIRMS key are different keys.

## Data (all real, all in `public/data/`)

| File | Content |
|---|---|
| `thermwatch_historical.json` | Validated V11 contract v2 (2026-01-01 → 2026-10-01): 2,298,169 valid FIRMS observations → 1,056,161 sources → 1,277,339 events; top-3,000 sources by Alert Priority; full event-level records for the top 300; coverage ledger; ML status. Byte-identical to V11 (SHA-256 pinned in `tests/fixtures`). |
| `thermwatch_context.json` | 449 documented facilities (GEM registry) + registry observation counts and PIHS values for the 3,000 ranked sources (`data-pipeline/intel_v1/build_frontend_context.py`). |
| `thermwatch_live.json` | Live artifact. Currently `LIVE_FEED_UNAVAILABLE` (no FIRMS key) — shown honestly in the UI. |

No mock, demo or synthetic dataset exists in the project, and there is no silent fallback: if a data file fails to load, the UI shows an error.

## What the UI shows

- **Map** (V7): opens on the **alert points** only: 1,068 real sources with Alert Priority HIGH (726) or MEDIUM (342). Layers → Low adds the other ranked sources (top 3,000 in total); Layers → Facilities / OSM adds the 449 registry facilities. The full 1,056,161-source registry stays in the pipeline and is never drawn as raw points.
- **Time control** (V7): Historical mode filters on real event timestamps (top-300 full records); sources without packaged timestamps are shown only under "All available".
- **Search** (V7): source IDs, facility names/places (e.g. Hazira) and types (e.g. steel). Choosing a facility pins it and its ranked sources within 5 km.
- **Alerts** (V7 drawer): the 726 real HIGH-tier sources in rank order.
- **Investigation** (V7 right drawer): V11's 11-step investigation for the top-300 sources (identity, observations, persistence & PIHS rule check, every event, thermal, spatial, facility & attribution, coverage, Alert Priority breakdown, ML, limitations). Other ranked sources show only their real registry/PIHS fields and say what is not packaged.
- **Print investigation**: A4 report from the same real record.

Honesty rules: ML is `READY_NOT_TRAINED` (no probabilities, no accuracy); attribution is heuristic, not probability; cause is always "Not confirmed"; unknown coverage is never "no fire".

## Tests

```bash
npm test                                              # model, data integrity, render (needs esbuild + react)
npm run test:browser                                  # Playwright acceptance against a running dev server
npm run test:layout                                   # layout must match the original V7 baseline
python3 data-pipeline/intel_v1/test_live_wiring.py    # FIRMS key name, all-India live area, no key leakage
python3 data-pipeline/intel_v1/test_investigation_v1.py
```

See `AUDIT_REPORT_V11_FINAL.md` for results and environment limitations.
