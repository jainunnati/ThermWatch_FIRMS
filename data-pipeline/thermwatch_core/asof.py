"""As-of, gap-aware source features (Step 6D). No future leakage, no gap-as-zero.

Everything is computed at a prediction time `as_of_utc` from observations with timestamp <= as_of_utc ONLY.
The coverage ledger is itself rebuilt from the as-of-visible stream, so neither the stream span nor the gap
status of a day can depend on data that arrives later. Only COMPLETE UTC days before the as-of day enter the
window; the (partial) as-of day is reported separately.

Detection-day fraction uses covered days as its denominator; unverified days are reported, never counted as
"no fire". This is still NOT ONRR (swath/cloud opportunity is unavailable) and is not persistence evidence.
FRP statistics use only the as-of-visible observations; FRP == 0 is retained as a value and counted.
"""
from __future__ import annotations

from datetime import timedelta

from .coverage import build_coverage_ledger, stream_key
from .stats import median


def asof_filter(observations, as_of_utc):
    """Return (visible, n_hidden_future). Only `visible` may feed features."""
    vis = [o for o in observations if o.timestamp_utc <= as_of_utc]
    return vis, len(observations) - len(vis)


def asof_source_features(source_observations, stream_observations, as_of_utc, *, lookback_days: int = 30,
                         min_obs_per_day: int = 1) -> dict:
    src, _ = asof_filter(source_observations, as_of_utc)
    stream, _ = asof_filter(stream_observations, as_of_utc)
    ledger = build_coverage_ledger(stream, min_obs_per_day)
    as_of_day = as_of_utc.date()
    d1, d0 = as_of_day - timedelta(days=1), as_of_day - timedelta(days=lookback_days)
    streams = sorted({stream_key(o) for o in src}) or None
    win = ledger.window_status(d0, d1, streams if streams else None)
    det_days = {o.utc_date for o in src}
    covered = win["covered_days"]
    det_in_cov = [d for d in covered if d in det_days]
    det_outside_cov = [d for d in det_days if d0 <= d <= d1 and d not in set(covered)]
    frps = [o.frp_mw for o in src if o.frp_mw is not None]
    last = max((o.timestamp_utc for o in src), default=None)
    return {
        "as_of_utc": as_of_utc.isoformat(),
        "window": {"from": d0.isoformat(), "to": d1.isoformat(), "complete_days_only": True, "lookback_days": lookback_days},
        "n_observations_asof": len(src),
        "last_observation_utc": last.isoformat() if last else None,
        "hours_since_last_observation": round((as_of_utc - last).total_seconds() / 3600.0, 3) if last else None,
        "n_obs_on_as_of_day": sum(1 for o in src if o.utc_date == as_of_day),
        "n_days_in_window": win["n_days"],
        "n_days_covered": len(covered),
        "n_days_coverage_unverified": len(win["unverified_days"]),
        "n_detection_days_in_covered_days": len(det_in_cov),
        "n_detection_days_on_unverified_days": len(det_outside_cov),
        "detection_day_fraction_of_covered": (len(det_in_cov) / len(covered)) if covered else None,
        "fraction_status": ("NOT_COMPUTED_NO_COVERED_DAYS" if not covered else
                            "COMPUTED_OVER_COVERED_DAYS_ONLY; NOT_ONRR; unverified days excluded, not zero"),
        "coverage_basis": "ANY_SATELLITE_STREAM_OF_THIS_SOURCE; stream-day coverage is not swath/cloud opportunity",
        "covered_days_by_stream": win["covered_days_by_stream"],
        "window_starts_before_stream_span": bool(streams) and any(
            ledger.spans.get(s) and d0 < ledger.spans[s][0] for s in streams),
        "frp": {"n": len(frps), "median_mw": median(frps) if frps else None, "max_mw": max(frps) if frps else None,
                "n_frp_zero": sum(1 for o in src if o.frp_zero), "n_frp_missing": sum(1 for o in src if o.frp_mw is None)},
    }
