"""
NORMALIZE
---------------------------------------------------------------------------
Turns raw FIRMS CSV rows (VIIRS column layout) into one consistent internal
event shape, validates coordinates/timestamps, and removes duplicates.

VIIRS FIRMS columns we rely on (see FIRMS attribute docs):
  latitude, longitude, acq_date, acq_time, satellite, instrument,
  confidence (n/l/h or 0-100), frp (Fire Radiative Power, MW),
  bright_ti4 (brightness temperature, K), daynight
---------------------------------------------------------------------------
"""

from datetime import datetime, timezone

CONFIDENCE_MAP = {"l": 0.3, "n": 0.6, "h": 0.9}  # VIIRS categorical -> numeric fallback


def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_confidence(raw):
    if raw is None or raw == "":
        return None
    raw = str(raw).strip().lower()
    if raw in CONFIDENCE_MAP:
        return CONFIDENCE_MAP[raw]
    numeric = _to_float(raw)
    if numeric is not None:
        # FIRMS sometimes reports confidence as 0-100
        return numeric / 100 if numeric > 1 else numeric
    return None


def _parse_timestamp(acq_date, acq_time):
    """acq_date='2026-01-05', acq_time='0130' (HHMM, UTC) -> ISO 8601 UTC."""
    if not acq_date:
        return None
    acq_time = (acq_time or "0000").strip().zfill(4)
    try:
        dt = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def _valid_coords(lat, lon):
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def normalize_rows(raw_rows, source_label):
    """
    raw_rows: list[dict] straight from csv.DictReader on a FIRMS response.
    Returns a list of normalized detection dicts (not yet deduplicated
    across multiple ingest calls - see deduplicate()).
    """
    normalized = []
    dropped = 0

    for row in raw_rows:
        lat = _to_float(row.get("latitude"))
        lon = _to_float(row.get("longitude"))
        timestamp = _parse_timestamp(row.get("acq_date"), row.get("acq_time"))

        if not _valid_coords(lat, lon) or timestamp is None:
            dropped += 1
            continue

        frp = _to_float(row.get("frp"))
        brightness = _to_float(row.get("bright_ti4") or row.get("brightness"))
        confidence = _parse_confidence(row.get("confidence"))

        detection_id = f"{row.get('satellite', 'SAT')}-{row.get('acq_date')}-{row.get('acq_time')}-{lat:.4f}-{lon:.4f}"

        normalized.append({
            "detectionId": detection_id,
            "latitude": lat,
            "longitude": lon,
            "timestamp": timestamp,
            "source": source_label,
            "satellite": row.get("satellite"),
            "instrument": row.get("instrument"),
            "frp": frp,
            "brightness": brightness,
            "confidence": confidence,
            "dayNight": row.get("daynight"),
        })

    if dropped:
        print(f"[normalize] Dropped {dropped} rows with invalid coordinates/timestamp ({source_label})")

    return normalized


def deduplicate(detections):
    """
    FIRMS can report the same physical hotspot more than once across
    overlapping satellite passes / overlapping historical windows. We treat
    two detections as the same event if they share a satellite and fall
    within a small rounded lat/lon cell and the same acquisition minute.
    """
    seen = set()
    unique = []
    for d in detections:
        key = (
            d["satellite"],
            round(d["latitude"], 3),
            round(d["longitude"], 3),
            d["timestamp"][:16],  # minute resolution
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)

    removed = len(detections) - len(unique)
    if removed:
        print(f"[normalize] Removed {removed} duplicate detections")
    return unique
