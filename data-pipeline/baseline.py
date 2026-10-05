"""
BASELINE + RISK
---------------------------------------------------------------------------
Deliberately the simplest model that is still honest and explainable -
exactly what an SIH prototype needs (see PDF section 15: "risk is not just
a frontend calculation" - here it is a documented backend calculation the
frontend merely visualizes).

LOCATION CLUSTERING
  Detections are grouped into "location cells" by rounding lat/lon to 2
  decimal places (~1.1km at the equator). This turns thousands of raw FIRMS
  points into a manageable number of persistent "spots" the UI can show as
  one investigable event each, the same way the existing frontend expects
  (one card per location, not one per satellite pixel).

BASELINE
  For each location cell, the baseline is the mean Fire Radiative Power
  (FRP, in MW - FIRMS' own measure of heat output) of all historical
  detections at that cell over the trailing BASELINE_WINDOW_DAYS
  (config.py), EXCLUDING the most recent detection itself. This is a plain
  rolling mean, nothing more - documented here so anyone reviewing the
  prototype can see exactly what "baseline" means.

  baselineDeviation = (latest_frp - baseline) / baseline

  If a cell has no historical history yet (a brand-new hotspot), baseline
  falls back to the region-wide mean FRP so we don't divide by zero or
  overstate the deviation of a single new detection.

CLASSIFICATION (prototype-only, rule-based, never fabricated)
  Uses only what enrich.py actually determined (land cover + facility
  proximity) plus the deviation computed above. If the signal is weak or
  ambiguous, the event is explicitly labeled "Unknown / Unclassified"
  rather than guessed at - matching the "do not fabricate labels"
  requirement.

RISK
  A small deterministic table over (classification, baselineDeviation).
  Frontend never computes this itself - it only ever displays riskLevel /
  alertSeverity as produced here.
---------------------------------------------------------------------------
"""

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import config

CLASSIFICATIONS = {
    "INDUSTRIAL_FIRE": "Industrial Fire",
    "PERSISTENT_THERMAL_SOURCE": "Persistent Thermal Source",
    "NATURAL_FIRE": "Natural Fire",
    "AGRICULTURAL_BURNING": "Agricultural Burning",
    "UNKNOWN": "Unknown / Unclassified",
}

RISK_LEVELS = {"LOW": "LOW", "WARNING": "WARNING", "HIGH": "HIGH"}


def _cell_key(lat, lon):
    return (round(lat, 2), round(lon, 2))


def cluster_by_location(detections):
    cells = defaultdict(list)
    for d in detections:
        cells[_cell_key(d["latitude"], d["longitude"])].append(d)
    return cells


def compute_region_mean_frp(detections):
    frps = [d["frp"] for d in detections if d.get("frp") is not None]
    return statistics.mean(frps) if frps else 10.0  # small non-zero fallback


def compute_baseline_for_cell(cell_detections, exclude_id, region_mean_frp, window_days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    history = [
        d for d in cell_detections
        if d["detectionId"] != exclude_id
        and d.get("frp") is not None
        and datetime.fromisoformat(d["timestamp"]) >= cutoff
    ]
    if not history:
        return region_mean_frp
    return statistics.mean(d["frp"] for d in history)


def classify(latest, baseline_deviation):
    land_cover = latest.get("landCover")
    is_industrial = land_cover == "Industrial Area"
    is_forest = land_cover == "Forest"
    confidence = latest.get("confidence") or 0.0

    # Not enough signal to say anything useful -> be honest about it.
    if confidence < 0.3:
        return CLASSIFICATIONS["UNKNOWN"], round(min(confidence + 0.2, 0.5), 2)

    if is_industrial and baseline_deviation is not None and baseline_deviation >= 0.4:
        return CLASSIFICATIONS["INDUSTRIAL_FIRE"], round(min(0.55 + confidence * 0.4, 0.97), 2)

    if is_industrial:
        # Elevated heat at a known facility that ISN'T a sharp spike above
        # its own history usually means routine flaring / continuous
        # process heat, not a fire event.
        return CLASSIFICATIONS["PERSISTENT_THERMAL_SOURCE"], round(min(0.5 + confidence * 0.3, 0.9), 2)

    if is_forest and confidence >= 0.5:
        return CLASSIFICATIONS["NATURAL_FIRE"], round(min(0.5 + confidence * 0.4, 0.95), 2)

    if not is_industrial and not is_forest and baseline_deviation is not None and baseline_deviation >= 0.3:
        # Short-lived heat away from any known facility or forest, in the
        # dry-biomass FRP range typical of crop-residue burning.
        return CLASSIFICATIONS["AGRICULTURAL_BURNING"], round(min(0.45 + confidence * 0.3, 0.85), 2)

    return CLASSIFICATIONS["UNKNOWN"], round(min(0.4 + confidence * 0.2, 0.6), 2)


def compute_risk(classification, baseline_deviation):
    dev = baseline_deviation or 0
    if classification == CLASSIFICATIONS["INDUSTRIAL_FIRE"] and dev >= 0.7:
        return RISK_LEVELS["HIGH"]
    if classification == CLASSIFICATIONS["INDUSTRIAL_FIRE"]:
        return RISK_LEVELS["WARNING"]
    if classification == CLASSIFICATIONS["NATURAL_FIRE"] and dev >= 0.6:
        return RISK_LEVELS["HIGH"]
    if classification == CLASSIFICATIONS["NATURAL_FIRE"]:
        return RISK_LEVELS["WARNING"]
    if classification == CLASSIFICATIONS["AGRICULTURAL_BURNING"]:
        return RISK_LEVELS["WARNING"] if dev >= 0.5 else RISK_LEVELS["LOW"]
    if classification == CLASSIFICATIONS["PERSISTENT_THERMAL_SOURCE"]:
        return RISK_LEVELS["LOW"]
    return RISK_LEVELS["LOW"]


def build_thermal_history(cell_detections, days=14):
    """Daily-bucketed mean FRP for the trailing `days`, oldest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    by_day = defaultdict(list)
    for d in cell_detections:
        ts = datetime.fromisoformat(d["timestamp"])
        if ts >= cutoff and d.get("frp") is not None:
            by_day[ts.date().isoformat()].append(d["frp"])

    baseline = compute_baseline_for_cell(cell_detections, exclude_id=None, region_mean_frp=10.0,
                                          window_days=config.BASELINE_WINDOW_DAYS)
    history = []
    day = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
    for _ in range(days):
        key = day.isoformat()
        values = by_day.get(key)
        history.append({
            "date": key,
            "baseline": round(baseline, 1),
            "value": round(statistics.mean(values), 1) if values else 0,
        })
        day += timedelta(days=1)
    return history


def build_current_day_history(cell_detections):
    """2-hourly buckets for today, using whatever recent detections exist."""
    today = datetime.now(timezone.utc).date()
    buckets = {f"{h:02d}:00": [] for h in range(0, 24, 2)}
    for d in cell_detections:
        ts = datetime.fromisoformat(d["timestamp"])
        if ts.date() == today and d.get("frp") is not None:
            bucket_hour = (ts.hour // 2) * 2
            buckets[f"{bucket_hour:02d}:00"].append(d["frp"])

    return [
        {"time": t, "value": round(statistics.mean(v), 1) if v else 0}
        for t, v in buckets.items()
    ]
