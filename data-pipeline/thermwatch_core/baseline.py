"""Eligibility-aware robust baseline: Median + MAD + Robust Z, per source, per sensor, per season.

History unit = per-source DAILY record (UTC date x sensor), aggregated with `daily_aggregator`.
Why daily and not per-event: a persistent source forms one long event, so per-event history would
collapse to a single value. (Spec leaves the FRP_today aggregation open; this is the documented choice.)

Eligibility rules (each excluded record is counted by reason - see `excluded_counts`):
  SAME_OR_LATER_DAY    record date >= evaluated date  -> an event never enters its own baseline and
                       future data never leaks into a replayed assessment (replay-safe, no wall-clock)
  DIFFERENT_SENSOR     sensor-stratified baseline (FRP distributions are not pooled across instruments)
  DIFFERENT_SEASON     season stratum (default IMD seasons; 'all' disables)
  REVIEWED_ANOMALOUS   ids supplied by an investigator review; the day still counts as a detection day
  FRP_MISSING          no FRP on that day
  EXTERNALLY_EXCLUDED  ids supplied by caller

Outcomes: OK | INSUFFICIENT_HISTORY | DEGENERATE_BASELINE | TARGET_FRP_MISSING.
With INSUFFICIENT_HISTORY no median/MAD/z is reported - a baseline is never invented.
All defaults marked CALIBRATION-OPEN are prototype settings, not validated constants.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .stats import empirical_percentile, mad, median, robust_score


def imd_season(month: int) -> str:
    """India Meteorological Department conventional seasons."""
    if month in (1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "pre-monsoon"
    if month in (6, 7, 8, 9):
        return "monsoon"
    return "post-monsoon"


@dataclass(frozen=True)
class BaselineParams:
    min_history: int = 10                 # spec prototype rule; CALIBRATION-OPEN
    stratum: str = "imd_season"           # 'imd_season' | 'all'
    stratify_sensor: bool = True
    mad_fallback: str = "meanad"          # 'meanad' | 'none'
    daily_aggregator: str = "max"         # 'max' | 'mean' | 'median'   (CALIBRATION-OPEN)
    reviewed_anomalous_ids: frozenset = frozenset()
    excluded_ids: frozenset = frozenset()
    min_normalization_reference: int = 10  # CALIBRATION-OPEN: LOO deviations needed for [0,1] map


def _agg(vals, how):
    if how == "max":
        return max(vals)
    if how == "mean":
        return sum(vals) / len(vals)
    if how == "median":
        return median(vals)
    raise ValueError(f"unknown aggregator {how}")


@dataclass
class DailyRecord:
    date: object
    sensor_key: str
    season: str
    frp: Optional[float]
    observation_ids: list


def build_daily_records(observations, params: BaselineParams):
    groups = defaultdict(list)
    for o in observations:
        groups[(o.utc_date, o.sensor_key if params.stratify_sensor else "ALL")].append(o)
    recs = []
    for (d, sk), obs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        vals = [o.frp_mw for o in obs if o.frp_mw is not None]
        season = imd_season(d.month) if params.stratum == "imd_season" else "all"
        recs.append(DailyRecord(d, sk, season, _agg(vals, params.daily_aggregator) if vals else None,
                                [o.observation_id for o in obs]))
    return recs


def compute_baseline(source_observations: Sequence, target_observations: Sequence,
                     params: BaselineParams = BaselineParams()) -> dict:
    """Compare the target observations (current event-day) with the source's own eligible history."""
    target = [o for o in target_observations]
    if not target:
        return {"status": "NO_TARGET", "reason": "no target observations"}
    t_date = min(o.utc_date for o in target)
    sensors = Counter(o.sensor_key for o in target)
    t_sensor = sensors.most_common(1)[0][0] if params.stratify_sensor else "ALL"
    t_season = imd_season(t_date.month) if params.stratum == "imd_season" else "all"
    t_vals = [o.frp_mw for o in target if o.frp_mw is not None]
    result = {
        "target_date": t_date.isoformat(), "sensor_key": t_sensor, "stratum": t_season,
        "aggregator": params.daily_aggregator, "sensor_mix_in_target": dict(sensors),
        "params": {"min_history": params.min_history, "mad_fallback": params.mad_fallback,
                   "stratum": params.stratum, "stratify_sensor": params.stratify_sensor,
                   "status": "CALIBRATION-OPEN"},
    }
    ledger = Counter()
    eligible = []
    for r in build_daily_records(source_observations, params):
        if r.date >= t_date:
            ledger["SAME_OR_LATER_DAY"] += 1; continue
        if params.stratify_sensor and r.sensor_key != t_sensor:
            ledger["DIFFERENT_SENSOR"] += 1; continue
        if r.season != t_season:
            ledger["DIFFERENT_SEASON"] += 1; continue
        if any(i in params.reviewed_anomalous_ids for i in r.observation_ids):
            ledger["REVIEWED_ANOMALOUS"] += 1; continue
        if any(i in params.excluded_ids for i in r.observation_ids):
            ledger["EXTERNALLY_EXCLUDED"] += 1; continue
        if r.frp is None:
            ledger["FRP_MISSING"] += 1; continue
        eligible.append(r)
    result["excluded_counts"] = dict(ledger)
    result["n_eligible"] = len(eligible)
    if eligible:
        result["history_first_date"] = eligible[0].date.isoformat()
        result["history_last_date"] = eligible[-1].date.isoformat()

    if not t_vals:
        result.update(status="TARGET_FRP_MISSING", reason="evaluated observations carry no FRP")
        return result
    x = _agg(t_vals, params.daily_aggregator)
    result["target_value_mw"] = x
    if len(eligible) < params.min_history:
        result.update(status="INSUFFICIENT_HISTORY",
                      reason=f"{len(eligible)} eligible daily records < min_history {params.min_history}")
        return result

    ref = [r.frp for r in eligible]
    z, method, status = robust_score(x, ref, params.mad_fallback)
    result.update(median_mw=median(ref), mad_mw=mad(ref))
    if status != "OK":
        result.update(status="DEGENERATE_BASELINE", robust_z=None, method=None,
                      reason="MAD is zero and no valid fallback spread (all eligible history identical)")
        return result
    result.update(status="OK", robust_z=z, method=method)

    # [0,1] evidence via empirical percentile of leave-one-out deviations (no hand-picked ranges).
    loo = []
    for i in range(len(ref)):
        others = ref[:i] + ref[i + 1:]
        if len(others) >= 3:
            zi, _, si = robust_score(ref[i], others, params.mad_fallback)
            if si == "OK":
                loo.append(max(0.0, zi))
    if len(loo) >= params.min_normalization_reference:
        result["t_anom"] = empirical_percentile(max(0.0, z), loo)
        result["t_anom_basis"] = f"empirical percentile of {len(loo)} leave-one-out positive deviations"
    else:
        result["t_anom"] = None
        result["t_anom_basis"] = "NORMALIZATION_REFERENCE_INSUFFICIENT"
    return result
