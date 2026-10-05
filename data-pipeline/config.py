"""
CONFIGURATION
---------------------------------------------------------------------------
Every tunable knob for the pipeline lives here. Change the region, the
historical window, or the FIRMS product from this one file - nothing else
needs to be touched.
---------------------------------------------------------------------------
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is a convenience only - if it's missing we just rely on
    # real environment variables (e.g. exported in the shell, or set in CI).
    pass

# ---------------------------------------------------------------------------
# NASA FIRMS
# ---------------------------------------------------------------------------
# Free key: https://firms.modaps.eosdis.nasa.gov/api/map_key/
# Never commit a real key - this is read from .env (see .env.example).
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "")

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# VIIRS 375m is the best fit for industrial-scale thermal anomalies (finer
# resolution than MODIS's 1km). NOAA-20/21 back up S-NPP for near-daily
# revisit. NRT = near-real-time (last ~2 months rolling); SP = standard
# (science-quality, longer-lag) processing, used for the historical pull.
FIRMS_SOURCE_RECENT = os.getenv("FIRMS_SOURCE_RECENT", "VIIRS_SNPP_NRT")
FIRMS_SOURCE_HISTORICAL = os.getenv("FIRMS_SOURCE_HISTORICAL", "VIIRS_SNPP_SP")

# The area API caps each request at 10 days of data, so historical pulls are
# always chunked into windows of this size regardless of HISTORICAL_YEARS.
FIRMS_MAX_DAY_RANGE = 10

# MAP_KEY is limited to 5000 transactions / 10-minute window (NASA docs).
# We stay well under that and add a small delay between requests to be
# polite to the shared service.
FIRMS_REQUEST_DELAY_SECONDS = 2

# ---------------------------------------------------------------------------
# GEOGRAPHIC SCOPE
# ---------------------------------------------------------------------------
# Default pipeline region: the South Gujarat petrochemical/industrial coastline
# (Dahej - Hazira - Ankleshwar - Surat belt). Small enough to keep the
# historical pull laptop-friendly; real enough to be a genuine, checkable region.
#
# FIRMS area coordinates are "west,south,east,north".
REGION_NAME = os.getenv("REGION_NAME", "South Gujarat Industrial Belt")
REGION_BBOX = os.getenv("REGION_BBOX", "68.5,20.5,73.5,23.5")  # covers Jamnagar -> Dahej -> Surat

# ---------------------------------------------------------------------------
# TIME WINDOW
# ---------------------------------------------------------------------------
HISTORICAL_YEARS = float(os.getenv("HISTORICAL_YEARS", "3"))
RECENT_DAYS = int(os.getenv("RECENT_DAYS", "10"))  # near-real-time tail, pulled with FIRMS_SOURCE_RECENT

# ---------------------------------------------------------------------------
# INDUSTRIAL FACILITY CONTEXT (OpenStreetMap via Overpass API)
# ---------------------------------------------------------------------------
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

# Any thermal detection within this distance of a known facility is treated
# as "industrial context". Chosen to comfortably cover large refinery /
# petrochemical complexes without swallowing an entire district.
INDUSTRIAL_PROXIMITY_KM = float(os.getenv("INDUSTRIAL_PROXIMITY_KM", "3.0"))

# ---------------------------------------------------------------------------
# BASELINE / RISK (see baseline.py for the full explanation)
# ---------------------------------------------------------------------------
BASELINE_WINDOW_DAYS = int(os.getenv("BASELINE_WINDOW_DAYS", "60"))

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent
RAW_DIR = PIPELINE_DIR / "raw"
PROCESSED_DIR = PIPELINE_DIR / "processed"

for d in (RAW_DIR, PROCESSED_DIR):
    d.mkdir(parents=True, exist_ok=True)
