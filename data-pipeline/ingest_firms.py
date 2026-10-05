"""
INGEST: NASA FIRMS
---------------------------------------------------------------------------
Talks to the real FIRMS Area API:

    https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{BBOX}/{DAY_RANGE}/{DATE}

- DAY_RANGE is capped at 10 by the API itself, so a multi-year historical
  pull is done as a sequence of small requests, one per 10-day window.
- Recent/near-real-time data uses the NRT source and doesn't need a DATE
  (defaults to "most recent N days").
- Every response is cached to disk under data-pipeline/raw/ so re-running
  the pipeline doesn't re-download data you already have, and so you can
  inspect exactly what NASA returned.

If FIRMS_MAP_KEY is not set, this module raises a clear error rather than
silently producing fake data.
---------------------------------------------------------------------------
"""

import csv
import io
import time
from datetime import date, timedelta

import requests

import config


class FirmsAuthError(RuntimeError):
    pass


def _require_key():
    if not config.FIRMS_MAP_KEY:
        raise FirmsAuthError(
            "FIRMS_MAP_KEY is not set. Get a free key at "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/ and put it in "
            "data-pipeline/.env (copy from .env.example)."
        )


def _cache_path(source, start_date, day_range):
    fname = f"{source}_{start_date}_{day_range}d.csv"
    return config.RAW_DIR / fname


def fetch_window(source: str, start_date: date, day_range: int, use_cache: bool = True, bbox: str = None):
    """
    Fetch one FIRMS area/csv window and return it as a list of dict rows.
    `start_date=None` means "most recent day_range days" (used for NRT).
    """
    _require_key()

    bbox = bbox or config.REGION_BBOX
    cache_path = _cache_path(source, start_date or "latest", day_range) if bbox == config.REGION_BBOX else None
    if use_cache and cache_path is not None and cache_path.exists():
        text = cache_path.read_text(encoding="utf-8")
    else:
        url = f"{config.FIRMS_BASE_URL}/{config.FIRMS_MAP_KEY}/{source}/{bbox}/{day_range}"
        if start_date is not None:
            url += f"/{start_date.isoformat()}"

        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        text = resp.text

        # FIRMS returns HTTP 200 with a plain-text error body on bad
        # MAP_KEY / bad params, so check for that explicitly.
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        if "Invalid" in first_line or "error" in first_line.lower():
            raise FirmsAuthError(f"FIRMS API returned an error: {first_line}")

        if cache_path is not None:
            cache_path.write_text(text, encoding="utf-8")
        time.sleep(config.FIRMS_REQUEST_DELAY_SECONDS)

    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def fetch_recent(days: int = None):
    """Near-real-time tail: last N days, single request (NRT source)."""
    days = days or config.RECENT_DAYS
    days = min(days, config.FIRMS_MAX_DAY_RANGE)
    return fetch_window(config.FIRMS_SOURCE_RECENT, start_date=None, day_range=days)


def fetch_historical(years: float = None):
    """
    Historical pull covering `years` back from today, chunked into
    <=10-day windows (the API's own limit) using the standard-processing
    (SP) source. Returns the combined rows from every window.
    """
    years = years or config.HISTORICAL_YEARS
    total_days = int(years * 365)
    chunk = config.FIRMS_MAX_DAY_RANGE

    today = date.today()
    all_rows = []
    windows = list(range(0, total_days, chunk))

    print(f"[ingest_firms] Historical pull: {years} years = {total_days} days "
          f"in {len(windows)} chunks of {chunk} days each (region={config.REGION_NAME})")

    for i, offset in enumerate(windows):
        # FIRMS window semantics: [DATE .. DATE + DAY_RANGE - 1], counting
        # forward, so we walk backwards from today in `chunk`-day steps.
        start_date = today - timedelta(days=offset + chunk - 1)
        day_range = chunk if offset + chunk <= total_days else total_days - offset
        try:
            rows = fetch_window(config.FIRMS_SOURCE_HISTORICAL, start_date, day_range)
            all_rows.extend(rows)
        except FirmsAuthError:
            raise
        except requests.RequestException as e:
            print(f"[ingest_firms] WARNING: window starting {start_date} failed ({e}), skipping")
        if (i + 1) % 10 == 0:
            print(f"[ingest_firms]   ...{i + 1}/{len(windows)} windows fetched")

    print(f"[ingest_firms] Historical pull complete: {len(all_rows)} raw rows")
    return all_rows
