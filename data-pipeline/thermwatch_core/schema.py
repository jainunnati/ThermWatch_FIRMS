"""Canonical normalized FIRMS observation schema + provenance vocabulary.

Design rules
------------
* Every field except identity/position/time is OPTIONAL. VIIRS and MODIS exports differ;
  absent values are stored as None, never defaulted, never imputed.
* The raw confidence string is always preserved. A categorical VIIRS confidence (l/n/h) is
  NOT converted to a fake probability; it is mapped to an ordinal class only.
* Every observation carries a data_mode. DEMO / TEST_FIXTURE data can never be confused with
  HISTORICAL / NRT real FIRMS data (see ModeMixingError and merge_observation_sets).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import NamedTuple, Optional

PIPELINE_VERSION = "thermwatch-core-0.1.0"
SCHEMA_VERSION = "observation-schema-1"
TEST_FIXTURE_BANNER = "SOFTWARE TEST FIXTURE - NOT SCIENTIFIC GROUND TRUTH"


class DataMode(str, Enum):
    DEMO = "DEMO"                  # supplied project demo data; provenance unknown
    HISTORICAL = "HISTORICAL"      # archived FIRMS download (replay)
    NRT = "NRT"                    # FIRMS near-real-time product (latest available)
    TEST_FIXTURE = "TEST_FIXTURE"  # synthetic software-test data

    @property
    def is_real_firms(self) -> bool:
        return self in (DataMode.HISTORICAL, DataMode.NRT)


class ModeMixingError(ValueError):
    """Raised when real FIRMS data would be silently combined with demo/test data."""


# Ordinal confidence classes. Semantics are SENSOR-SPECIFIC (Step 6D):
#   VIIRS : categorical l/n/h (low/nominal/high). Never a percentage. Cleaned exports encode l/n/h as
#           30/70/95 (verified against 2,394 clean<->raw joined observations; see Step 6D audit).
#   MODIS : native integer 0-100 percentage; class bands below are an ASSUMPTION taken from the FIRMS
#           MODIS documentation and must be re-verified against the product guide you downloaded.
CONFIDENCE_CLASSES = ("low", "nominal", "high")
_CATEGORICAL = {"l": "low", "low": "low", "n": "nominal", "nominal": "nominal", "h": "high", "high": "high"}
VIIRS_LNH_TO_SCORE = {"l": 30, "n": 70, "h": 95}          # encoding used by the clean exports
_VIIRS_SCORE_TO_CLASS = {30.0: "low", 70.0: "nominal", 95.0: "high"}


def confidence_class_from_pct(pct: float) -> str:
    """MODIS-only bands: low 0-29, nominal 30-79, high 80-100 (ASSUMPTION; verify against product docs)."""
    if pct < 30:
        return "low"
    if pct < 80:
        return "nominal"
    return "high"


class ConfidenceParse(NamedTuple):
    confidence_class: Optional[str]
    confidence_pct: Optional[float]     # only for MODIS native percentages; None for categorical VIIRS
    status: str                         # ok | missing | invalid | semantics_mismatch | semantics_unknown
    semantics: Optional[str]            # which interpretation was applied (None when none could be)


def parse_confidence_ex(raw, instrument: Optional[str] = None) -> ConfidenceParse:
    """Sensor-specific confidence parsing. A numeric value is never interpreted under the wrong sensor's
    semantics: unknown-instrument numerics and unexpected values are left UNCLASSIFIED and flagged."""
    if raw is None or str(raw).strip() == "":
        return ConfidenceParse(None, None, "missing", None)
    s = str(raw).strip().lower()
    ins = (instrument or "").strip().upper() or None
    if s in _CATEGORICAL:
        if ins == "MODIS":
            return ConfidenceParse(None, None, "semantics_mismatch", "MODIS_UNEXPECTED_CATEGORICAL")
        return ConfidenceParse(_CATEGORICAL[s], None, "ok",
                               "VIIRS_CATEGORICAL_LNH" if ins == "VIIRS" else "CATEGORICAL_LNH_INSTRUMENT_UNSPECIFIED")
    try:
        p = float(s)
    except ValueError:
        return ConfidenceParse(None, None, "invalid", None)
    if not 0 <= p <= 100 or p != p:
        return ConfidenceParse(None, None, "invalid", None)
    if ins == "VIIRS":
        if p in _VIIRS_SCORE_TO_CLASS:
            return ConfidenceParse(_VIIRS_SCORE_TO_CLASS[p], None, "ok", "VIIRS_CATEGORICAL_ENCODED_30_70_95")
        return ConfidenceParse(None, None, "semantics_mismatch", "VIIRS_UNEXPECTED_NUMERIC")
    if ins == "MODIS":
        return ConfidenceParse(confidence_class_from_pct(p), p, "ok", "MODIS_NATIVE_PCT")
    return ConfidenceParse(None, None, "semantics_unknown", None)


def parse_confidence(raw, instrument: Optional[str] = None):
    """Backward-compatible 3-tuple (confidence_class, confidence_pct, status); see parse_confidence_ex."""
    c = parse_confidence_ex(raw, instrument)
    return c.confidence_class, c.confidence_pct, c.status


@dataclass(frozen=True)
class Observation:
    observation_id: str
    latitude: float
    longitude: float
    timestamp_utc: datetime            # source acquisition time, UTC, tz-aware
    acq_date: str                      # as supplied, YYYY-MM-DD
    acq_time: str                      # as supplied, HHMM (zero-padded)
    data_mode: DataMode
    satellite: Optional[str] = None    # e.g. 'N', '1', 'Terra', 'N20'
    instrument: Optional[str] = None   # 'VIIRS' | 'MODIS' | None
    frp_mw: Optional[float] = None
    brightness_k: Optional[float] = None            # VIIRS bright_ti4 / MODIS brightness
    brightness_k_secondary: Optional[float] = None  # VIIRS bright_ti5 / MODIS bright_t31
    confidence_raw: Optional[str] = None
    confidence_class: Optional[str] = None
    confidence_pct: Optional[float] = None
    day_night: Optional[str] = None    # 'D' | 'N'
    scan_km: Optional[float] = None
    track_km: Optional[float] = None
    version_raw: Optional[str] = None  # FIRMS 'version' column, e.g. '2.0NRT'
    source_product: Optional[str] = None   # e.g. VIIRS_SNPP_SP (supplied by adapter, not in CSV)
    source_file: Optional[str] = None
    row_number: Optional[int] = None
    ingested_utc: Optional[datetime] = None
    confidence_semantics: Optional[str] = None   # Step 6D: which sensor-specific interpretation was applied
    frp_zero: bool = False                       # Step 6D: source FRP was exactly 0 (value preserved, not missing)

    @property
    def physical_key(self) -> str:
        """Mode-free identity of the physical observation (see make_physical_key)."""
        return make_physical_key(self.instrument, self.satellite, self.timestamp_utc, self.latitude, self.longitude)

    @property
    def sensor_key(self) -> str:
        """Key used to stratify baselines (never pool incomparable FRP distributions)."""
        return self.instrument or "UNKNOWN_INSTRUMENT"

    @property
    def sensor_label(self) -> Optional[str]:
        s = " ".join(x for x in (self.instrument, self.satellite) if x)
        return s or None

    @property
    def utc_date(self):
        return self.timestamp_utc.date()

    def to_dict(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "timestamp_utc": self.timestamp_utc.isoformat().replace("+00:00", "Z"),
            "lat": self.latitude, "lon": self.longitude,
            "frp_mw": self.frp_mw, "bright_ti4_k": self.brightness_k,
            "confidence": self.confidence_raw,
            "sensor": self.sensor_label, "day_night": self.day_night,
            "data_mode": self.data_mode.value,
        }


def make_observation_id(mode: DataMode, instrument, satellite, acq_date, acq_time, lat, lon) -> str:
    """Deterministic, mode-prefixed id. Same satellite/instrument/time/pixel => same id (=> exact duplicate)."""
    return f"{mode.value}:{instrument or 'NA'}:{satellite or 'NA'}:{acq_date}:{acq_time}:{lat:.5f}:{lon:.5f}"


# Satellite spellings seen across FIRMS products / exports -> one canonical token (small, explicit table).
SATELLITE_ALIASES = {"NOAA-21": "N21", "NOAA21": "N21", "NOAA-20": "N20", "NOAA20": "N20",
                     "SUOMI-NPP": "N", "SNPP": "N", "NPP": "N"}


def canonical_satellite(satellite):
    if satellite is None or str(satellite).strip() == "":
        return None
    t = str(satellite).strip()
    return SATELLITE_ALIASES.get(t.upper(), t)


def _coord5(x: float) -> str:
    t = f"{x:.5f}"
    return "0.00000" if t == "-0.00000" else t


def make_physical_key(instrument, satellite, timestamp_utc: datetime, lat: float, lon: float) -> str:
    """Cross-source physical-observation identity. Deliberately EXCLUDES data_mode, file, row and every
    attribute value (FRP, confidence...) so the same detection delivered by two files/products collides on
    purpose. Resolution: acquisition minute (UTC) and 1e-5 deg (~1.1 m). Two real pixels of one satellite
    cannot share a minute and a 1e-5 deg position, so a key match IS the same physical observation."""
    return (f"PHYS|{(instrument or 'NA').upper()}|{canonical_satellite(satellite) or 'NA'}|"
            f"{timestamp_utc.strftime('%Y%m%dT%H%M')}|{_coord5(lat)}|{_coord5(lon)}")


def merge_observation_sets(*sets, allow_mixed: bool = False):
    """Concatenate observation lists, refusing to mix real FIRMS data with DEMO/TEST_FIXTURE data."""
    merged = [o for s in sets for o in s]
    modes = {o.data_mode for o in merged}
    if not allow_mixed and len(modes) > 1:
        raise ModeMixingError(f"Refusing to mix data modes: {sorted(m.value for m in modes)}")
    return merged
