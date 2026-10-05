# ThermWatch Data Pipeline

Real NASA FIRMS VIIRS detections -> the JSON contract consumed by the V7 React UI (`public/data/thermwatch_historical.json`, `thermwatch_live.json`).

- `thermwatch_core/`: ingest, validation, physical deduplication, source/event formation, coverage, facility context, baselines.
- `intel_v1/`: PIHS rules + Alert Priority (`intel_core.py`), contract builders (`build_contract_v2.py`, `live_update.py`), tests.
- `ml_v1/`: ML feature / label-readiness / grouped-validation framework. **No production classifier is trained** (status `READY_NOT_TRAINED`, 0 eligible labels).
- `m1/`: label-research and attribution-MVP tooling (heuristic attribution only; not calibrated probabilities).

Rebuild all frontend artifacts from existing validated outputs with `../run_pipeline.sh`.

A NASA FIRMS key is only needed for the optional live workflow: copy `.env.example` to `.env` and set `FIRMS_MAP_KEY`
(in GitHub Actions it is read from `secrets.FIRMS_MAP_KEY`). Never commit `.env`.

The former mock backend / sample-data scripts that lived here were removed in V11.
