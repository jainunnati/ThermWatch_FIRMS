"""Mode-tagged adapters: HISTORICAL / NRT (FIRMS CSV) and DEMO (supplied JSON).

No network access here. Real FIRMS files are obtained elsewhere (map-key API or archive request)
and handed to these adapters, which only (a) read, (b) fingerprint the file, (c) tag the mode.
A file is only as 'HISTORICAL' or 'NRT' as the person loading it attests; the adapter cannot
prove authenticity, so the sha256 + product string are recorded for audit.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schema import DataMode

OPTIONAL_COLUMNS = ("satellite", "instrument", "frp", "confidence", "daynight",
                    "scan", "track", "version")
BRIGHTNESS_COLUMNS = ("bright_ti4", "bright_ti5", "brightness", "bright_t31")


@dataclass
class RawBatch:
    mode: DataMode
    product: Optional[str]
    rows: list                     # list[(row_number, dict)]
    columns: list
    source_file: Optional[str]
    sha256: Optional[str]
    ingested_utc: datetime
    malformed: list                # list[(row_number, detail)] rows csv could not shape


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_firms_csv(path, mode: DataMode, product: Optional[str] = None,
                   ingested_utc: Optional[datetime] = None) -> RawBatch:
    """Read a FIRMS CSV export (VIIRS or MODIS layout). mode must be HISTORICAL or NRT."""
    if mode not in (DataMode.HISTORICAL, DataMode.NRT):
        raise ValueError("load_firms_csv is for real FIRMS files: mode must be HISTORICAL or NRT")
    path = Path(path)
    rows, malformed = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = [c.strip().lower() for c in (reader.fieldnames or [])]
        reader.fieldnames = columns
        for i, row in enumerate(reader, start=1):
            if None in row:                       # more cells than header
                malformed.append((i, "extra cells beyond header"))
                continue
            if any(v is None for v in row.values()):  # fewer cells than header
                malformed.append((i, "fewer cells than header"))
                continue
            rows.append((i, {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}))
    return RawBatch(mode, product, rows, columns, str(path), _sha256(path),
                    ingested_utc or datetime.now(timezone.utc), malformed)



def load_thermwatch_csv(path, mode: DataMode, product: Optional[str] = None,
                        ingested_utc: Optional[datetime] = None) -> RawBatch:
    """Load ThermWatch-clean CSV exports that use one ISO timestamp column.

    Expected columns:
      latitude, longitude, timestamp, brightness_k, frp_mw, confidence_score,
      satellite, instrument, day_night, source_sensor

    This adapter is deliberately a thin schema translation layer: it does not
    filter geography, invent missing values, deduplicate, or assign labels.
    Validation remains the responsibility of normalize_and_validate().
    """
    if mode not in (DataMode.HISTORICAL, DataMode.NRT):
        raise ValueError("load_thermwatch_csv is for real FIRMS-derived files: mode must be HISTORICAL or NRT")
    path = Path(path)
    rows, malformed = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = [c.strip().lower() for c in (reader.fieldnames or [])]
        reader.fieldnames = columns
        required = {"latitude", "longitude", "timestamp"}
        missing = sorted(required - set(columns))
        if missing:
            raise ValueError(f"ThermWatch CSV missing required columns: {missing}")
        for i, row in enumerate(reader, start=2):
            if None in row:
                malformed.append((i, "extra cells beyond header"))
                continue
            if any(v is None for v in row.values()):
                malformed.append((i, "fewer cells than header"))
                continue
            raw_ts = (row.get("timestamp") or "").strip()
            if not raw_ts:
                malformed.append((i, "timestamp empty"))
                continue
            # Accept the clean export's ISO-like UTC timestamp and translate
            # only the representation expected by the canonical validator.
            ts = raw_ts.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(ts)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                parsed = parsed.astimezone(timezone.utc)
                acq_date = parsed.strftime("%Y-%m-%d")
                acq_time = parsed.strftime("%H%M")
            except ValueError:
                malformed.append((i, f"unparseable timestamp: {raw_ts!r}"))
                continue
            rows.append((i, {
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "acq_date": acq_date,
                "acq_time": acq_time,
                "brightness": row.get("brightness_k"),
                "frp": row.get("frp_mw"),
                "confidence": row.get("confidence_score"),
                "satellite": row.get("satellite") or None,
                "instrument": row.get("instrument") or None,
                "daynight": row.get("day_night") or None,
                "source_sensor": row.get("source_sensor") or None,
            }))
    return RawBatch(mode, product, rows, columns, str(path), _sha256(path),
                    ingested_utc or datetime.now(timezone.utc), malformed)

def load_rows(rows, mode: DataMode, product: Optional[str] = "IN_MEMORY",
              ingested_utc: Optional[datetime] = None, source_file: Optional[str] = None) -> RawBatch:
    """In-memory batch (tests / fixtures)."""
    cols = sorted({k for r in rows for k in r})
    return RawBatch(mode, product, list(enumerate(rows, start=1)), cols, source_file, None,
                    ingested_utc or datetime.now(timezone.utc), [])
