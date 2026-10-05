"""Normalization + validation with a traceable exclusion ledger.

Two kinds of problems are kept distinct:
  * FATAL (observation excluded, row recorded in the ledger with reason + excerpt):
      MALFORMED_ROW, MISSING_COORDINATES, INVALID_COORDINATES, MISSING_DATE,
      UNPARSEABLE_TIMESTAMP, TIMESTAMP_IN_FUTURE, TIMESTAMP_BEFORE_MISSION, DUPLICATE_EXACT
  * FIELD-LEVEL (observation kept, offending field set to None, flag recorded):
      FRP_INVALID, FRP_NEGATIVE, FRP_SUSPICIOUS (kept as is), BRIGHTNESS_INVALID,
      BRIGHTNESS_OUT_OF_RANGE, CONFIDENCE_INVALID, CONFIDENCE_SEMANTICS_MISMATCH (value not valid for the
      sensor, e.g. numeric 55 on VIIRS), CONFIDENCE_SEMANTICS_UNKNOWN (numeric without a known sensor),
      DAYNIGHT_INVALID, SENSOR_UNKNOWN
  * INFORMATIONAL (observation and value kept unchanged): FRP_ZERO (frp == 0.0 is preserved as a real
      value, flagged, and never converted to missing), FRP_SUSPICIOUS

Invariant (tested): n_input == n_valid + n_excluded.
Large exclusion fractions raise a warning (status REVIEW_EXCLUSIONS) instead of passing silently.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .ingest import BRIGHTNESS_COLUMNS, OPTIONAL_COLUMNS, RawBatch
from .schema import Observation, make_observation_id, parse_confidence_ex


@dataclass(frozen=True)
class ValidationParams:
    max_future_skew_hours: float = 1.0               # clock-skew tolerance vs reference time
    earliest_valid_utc: datetime = datetime(2000, 1, 1, tzinfo=timezone.utc)  # before any FIRMS sensor
    frp_suspicious_mw: float = 5000.0                # flag only (CALIBRATION-OPEN sanity bound)
    brightness_range_k: tuple = (150.0, 550.0)       # outside => field nulled + flagged (sanity bound)
    max_exclusion_fraction: float = 0.02             # above => REVIEW_EXCLUSIONS warning
    reference_time_utc: Optional[datetime] = None    # defaults to batch.ingested_utc


@dataclass
class Exclusion:
    row_number: int
    reason: str
    detail: str
    source_file: Optional[str]
    excerpt: dict


@dataclass
class ValidationReport:
    observations: list
    exclusions: list
    flags: list                   # list[(observation_id, flag, detail)]
    stats: dict
    warnings: list = field(default_factory=list)

    def ledger(self):
        return [vars(e) for e in self.exclusions]


class _Bad:  # sentinel: value present but not parseable
    pass


BAD = _Bad()


def _num(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return BAD
    return x if x == x and x not in (float("inf"), float("-inf")) else BAD


def _excerpt(row):
    return {k: row.get(k) for k in ("latitude", "longitude", "acq_date", "acq_time", "satellite") if k in row}


def _infer_instrument(row):
    ins = (row.get("instrument") or "").strip().upper() or None
    if ins:
        return ins
    if "bright_ti4" in row:
        return "VIIRS"
    if "bright_t31" in row or ("brightness" in row and "bright_ti4" not in row and row.get("satellite") in ("Terra", "Aqua")):
        return "MODIS"
    return None


def normalize_and_validate(batch: RawBatch, params: ValidationParams = ValidationParams()) -> ValidationReport:
    ref = params.reference_time_utc or batch.ingested_utc
    observations, exclusions, flags, seen = [], [], [], {}
    n_input = len(batch.rows) + len(batch.malformed)

    for rn, detail in batch.malformed:
        exclusions.append(Exclusion(rn, "MALFORMED_ROW", detail, batch.source_file, {}))

    for rn, row in batch.rows:
        def exclude(reason, detail):
            exclusions.append(Exclusion(rn, reason, detail, batch.source_file, _excerpt(row)))

        lat, lon = _num(row.get("latitude")), _num(row.get("longitude"))
        if lat is None or lon is None:
            exclude("MISSING_COORDINATES", "latitude/longitude empty"); continue
        if lat is BAD or lon is BAD or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            exclude("INVALID_COORDINATES", f"lat={row.get('latitude')!r} lon={row.get('longitude')!r}"); continue
        acq_date = (row.get("acq_date") or "").strip() if isinstance(row.get("acq_date"), str) else row.get("acq_date")
        if not acq_date:
            exclude("MISSING_DATE", "acq_date empty"); continue
        acq_time = str(row.get("acq_time") if row.get("acq_time") not in (None, "") else "0000").strip().zfill(4)
        try:
            ts = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            exclude("UNPARSEABLE_TIMESTAMP", f"acq_date={acq_date!r} acq_time={acq_time!r}"); continue
        if (ts - ref).total_seconds() > params.max_future_skew_hours * 3600:
            exclude("TIMESTAMP_IN_FUTURE", f"{ts.isoformat()} > reference {ref.isoformat()}"); continue
        if ts < params.earliest_valid_utc:
            exclude("TIMESTAMP_BEFORE_MISSION", ts.isoformat()); continue

        satellite = (row.get("satellite") or None) if isinstance(row.get("satellite"), (str, type(None))) else str(row.get("satellite"))
        instrument = _infer_instrument(row)
        oid = make_observation_id(batch.mode, instrument, satellite, acq_date, acq_time, lat, lon)
        if oid in seen:
            exclude("DUPLICATE_EXACT", f"identical to row {seen[oid]}"); continue
        seen[oid] = rn

        local_flags = []
        frp = _num(row.get("frp"))
        if frp is BAD:
            frp = None; local_flags.append(("FRP_INVALID", repr(row.get("frp"))))
        elif frp is not None and frp < 0:
            local_flags.append(("FRP_NEGATIVE", str(frp))); frp = None
        elif frp is not None and frp == 0:
            local_flags.append(("FRP_ZERO", "source FRP is exactly 0.0; value preserved (not missing)"))
        elif frp is not None and frp > params.frp_suspicious_mw:
            local_flags.append(("FRP_SUSPICIOUS", f"{frp} MW > {params.frp_suspicious_mw}"))

        def brightness(col):
            v = _num(row.get(col))
            if v is BAD:
                local_flags.append(("BRIGHTNESS_INVALID", f"{col}={row.get(col)!r}")); return None
            if v is not None and not params.brightness_range_k[0] <= v <= params.brightness_range_k[1]:
                local_flags.append(("BRIGHTNESS_OUT_OF_RANGE", f"{col}={v}")); return None
            return v

        primary = brightness("bright_ti4") if "bright_ti4" in row else brightness("brightness")
        secondary = brightness("bright_ti5") if "bright_ti5" in row else (brightness("bright_t31") if "bright_t31" in row else None)

        cp = parse_confidence_ex(row.get("confidence"), instrument)
        cclass, cpct, csem = cp.confidence_class, cp.confidence_pct, cp.semantics
        if cp.status == "invalid":
            local_flags.append(("CONFIDENCE_INVALID", repr(row.get("confidence"))))
        elif cp.status == "semantics_mismatch":
            local_flags.append(("CONFIDENCE_SEMANTICS_MISMATCH", f"{row.get('confidence')!r} is not a valid {instrument} confidence; left unclassified"))
        elif cp.status == "semantics_unknown":
            local_flags.append(("CONFIDENCE_SEMANTICS_UNKNOWN", f"numeric {row.get('confidence')!r} with no known instrument; left unclassified"))

        dn = (row.get("daynight") or "").strip().upper() or None
        if dn not in (None, "D", "N"):
            local_flags.append(("DAYNIGHT_INVALID", repr(row.get("daynight")))); dn = None
        if instrument is None:
            local_flags.append(("SENSOR_UNKNOWN", "instrument not given and not inferable"))

        scan, track = _num(row.get("scan")), _num(row.get("track"))
        scan = None if scan is BAD else scan
        track = None if track is BAD else track

        obs = Observation(
            observation_id=oid, latitude=lat, longitude=lon, timestamp_utc=ts,
            acq_date=acq_date, acq_time=acq_time, data_mode=batch.mode,
            satellite=satellite, instrument=instrument, frp_mw=frp,
            brightness_k=primary, brightness_k_secondary=secondary,
            confidence_raw=(str(row.get("confidence")).strip() if row.get("confidence") not in (None, "") else None),
            confidence_class=cclass, confidence_pct=cpct, day_night=dn,
            scan_km=scan, track_km=track,
            version_raw=(row.get("version") or None) if isinstance(row.get("version"), (str, type(None))) else str(row.get("version")),
            source_product=batch.product, source_file=batch.source_file, row_number=rn,
            ingested_utc=batch.ingested_utc,
            confidence_semantics=csem, frp_zero=(frp is not None and frp == 0),
        )
        observations.append(obs)
        flags.extend((oid, f, d) for f, d in local_flags)

    n_valid, n_excl = len(observations), len(exclusions)
    assert n_input == n_valid + n_excl, "validation accounting broken"
    frac = (n_excl / n_input) if n_input else 0.0
    warnings = []
    status = "OK"
    if n_input == 0:
        status, warnings = "EMPTY", ["No input rows."]
    elif frac > params.max_exclusion_fraction:
        status = "REVIEW_EXCLUSIONS"
        warnings.append(f"{n_excl}/{n_input} rows excluded ({frac:.1%}) exceeds {params.max_exclusion_fraction:.0%}; inspect the ledger before trusting results.")
    present = set(batch.columns)
    stats = {
        "status": status, "data_mode": batch.mode.value, "product": batch.product,
        "source_file": batch.source_file, "file_sha256": batch.sha256,
        "n_input": n_input, "n_valid": n_valid, "n_excluded": n_excl, "exclusion_fraction": round(frac, 6),
        "frp_zero_count": sum(1 for o in observations if o.frp_zero),
        "confidence_semantics": dict(Counter(o.confidence_semantics or "NONE" for o in observations)),
        "exclusions_by_reason": dict(Counter(e.reason for e in exclusions)),
        "flags_by_reason": dict(Counter(f for _, f, _ in flags)),
        "by_instrument": dict(Counter(o.instrument or "UNKNOWN" for o in observations)),
        "by_satellite": dict(Counter(o.satellite or "UNKNOWN" for o in observations)),
        "time_min_utc": min((o.timestamp_utc for o in observations), default=None) and min(o.timestamp_utc for o in observations).isoformat(),
        "time_max_utc": max((o.timestamp_utc for o in observations), default=None) and max(o.timestamp_utc for o in observations).isoformat(),
        "optional_columns_absent": [c for c in OPTIONAL_COLUMNS if c not in present],
        "brightness_columns_present": [c for c in BRIGHTNESS_COLUMNS if c in present],
        "reference_time_utc": ref.isoformat(),
    }
    return ValidationReport(observations, exclusions, flags, stats, warnings)
