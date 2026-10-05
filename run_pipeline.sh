#!/usr/bin/env bash
# ThermWatch: rebuild all frontend data artifacts from existing validated outputs (no re-ingestion of the 2.3M rows).
# Needs the intermediate pipeline outputs listed in data-pipeline/intel_v1/build_contract_v2.py (P = {...}).
set -euo pipefail
cd "$(dirname "$0")"
ACT=${ACT:-/home/claude/intel/source_activity_v1.csv.gz}
[ -f "$ACT" ] || python3 data-pipeline/intel_v1/source_activity_v1.py "$ACT"
python3 data-pipeline/intel_v1/build_contract_v2.py --out public/data/thermwatch_historical.json
python3 data-pipeline/intel_v1/build_frontend_context.py --contract public/data/thermwatch_historical.json --indexes data-pipeline/intel_v1/live_indexes --out public/data/thermwatch_context.json
python3 data-pipeline/intel_v1/live_update.py --indexes data-pipeline/intel_v1/live_indexes --out public/data/thermwatch_live.json   # LIVE or LIVE_FEED_UNAVAILABLE
echo "Done. npm install && npm run dev"
