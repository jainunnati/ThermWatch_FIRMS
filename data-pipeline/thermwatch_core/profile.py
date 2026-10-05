"""Historical source profile (descriptive; does NOT assert persistence from record counts).

'naive_detection_day_fraction' = active days / inclusive span days. It is NOT ONRR: it ignores
observation opportunity, so it is labelled naive and never used as persistence evidence on its own.

recurrence_class thresholds are CALIBRATION-OPEN prototype settings (ProfileParams) - not scientific constants.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from .stats import distribution_summary, median, percentile


@dataclass(frozen=True)
class ProfileParams:
    min_active_days: int = 5      # CALIBRATION-OPEN
    min_span_days: int = 14       # CALIBRATION-OPEN
    transient_max_active_days: int = 2


def build_source_profile(source_id: str, observations: Sequence, params: ProfileParams = ProfileParams()) -> dict:
    obs = sorted(observations, key=lambda o: o.timestamp_utc)
    if not obs:
        return {"source_id": source_id, "n_observations": 0, "recurrence_class": "NO_OBSERVATIONS"}
    days = sorted({o.utc_date for o in obs})
    span_days = (days[-1] - days[0]).days + 1
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    n_active = len(days)
    if n_active <= params.transient_max_active_days and span_days <= params.transient_max_active_days + 1:
        rc = "TRANSIENT"
    elif n_active >= params.min_active_days and span_days >= params.min_span_days:
        rc = "RECURRENT_DETECTIONS"
    else:
        rc = "INSUFFICIENT_TIME_BASE"
    return {
        "source_id": source_id,
        "data_modes": sorted({o.data_mode.value for o in obs}),
        "n_observations": len(obs),
        "first_observation_utc": obs[0].timestamp_utc.isoformat(),
        "last_observation_utc": obs[-1].timestamp_utc.isoformat(),
        "distinct_active_days": n_active,
        "span_days_inclusive": span_days,
        "naive_detection_day_fraction": round(n_active / span_days, 6),
        "naive_fraction_note": "Ignores observation opportunity. NOT ONRR. Not persistence evidence by itself.",
        "gap_days": {"n": len(gaps), "median": median(gaps) if gaps else None,
                     "p90": percentile(gaps, 90) if gaps else None, "max": max(gaps) if gaps else None},
        "frp_mw": distribution_summary([o.frp_mw for o in obs]),
        "frp_missing": sum(1 for o in obs if o.frp_mw is None),
        "brightness_k": distribution_summary([o.brightness_k for o in obs]),
        "sensors": dict(Counter(o.sensor_label or "UNKNOWN" for o in obs)),
        "day_night": dict(Counter(o.day_night or "UNKNOWN" for o in obs)),
        "recurrence_class": rc,
        "recurrence_params": {"min_active_days": params.min_active_days, "min_span_days": params.min_span_days,
                              "status": "CALIBRATION-OPEN"},
    }
