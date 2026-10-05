"""Observation opportunity + ONRR. Opportunity data is NEVER invented.

ONRR(f, W) = D_detect / D_possible.  FIRMS detection files contain detections only, so D_possible
needs a separate coverage layer (e.g. predicted overpass geometry, optionally cloud-screened).
Without one, the status is OBSERVATION_OPPORTUNITY_UNKNOWN and no ONRR is reported; the persistence
conclusion must then carry reduced confidence. A missing detection is never read as 'inactive'.

`OpportunityTable.basis` states what the opportunity counts mean, e.g. 'geometric_overpass'
(swath coverage only; cloud state UNKNOWN) or 'clear_sky_screened'. `cloud_screened` drives caveats.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .stats import empirical_percentile, mad, median, robust_score


@dataclass
class OpportunityTable:
    """Per-location counts of valid observation opportunities per UTC day."""
    days: dict                       # date -> n_valid_opportunities (>=0)
    basis: str                       # 'geometric_overpass' | 'clear_sky_screened' | ...
    cloud_screened: bool = False
    provenance: str = ""


def compute_onrr(detect_days, opportunity: Optional[OpportunityTable], window_end: date, window_days: int = 30) -> dict:
    """window_days default 30 is CALIBRATION-OPEN (spec leaves W_ONRR unlocked)."""
    start = window_end - timedelta(days=window_days - 1)
    detect = {d for d in detect_days if start <= d <= window_end}
    out = {"window_start": start.isoformat(), "window_end": window_end.isoformat(), "window_days": window_days,
           "window_status": "CALIBRATION-OPEN", "D_detect": len(detect)}
    if opportunity is None:
        out.update(status="OBSERVATION_OPPORTUNITY_UNKNOWN", D_possible=None, onrr=None,
                   caveats=["No observation-opportunity layer supplied: absence of detections is NOT evidence of inactivity.",
                            "Persistence conclusions carry reduced confidence."])
        return out
    possible = {d for d, n in opportunity.days.items() if start <= d <= window_end and n >= 1}
    inconsistent = sorted(detect - possible)       # a detection proves the location was observable that day
    possible |= detect
    caveats = []
    if inconsistent:
        caveats.append(f"{len(inconsistent)} detection day(s) had no recorded opportunity; counted as possible (detection implies coverage).")
    if not opportunity.cloud_screened:
        caveats.append("Opportunity is not cloud-screened: cloud state UNKNOWN; ONRR may understate recurrence.")
    out.update(D_possible=len(possible), basis=opportunity.basis, cloud_screened=opportunity.cloud_screened,
               detect_without_opportunity_days=[d.isoformat() for d in inconsistent], caveats=caveats)
    if not possible:
        out.update(status="NO_VALID_OPPORTUNITIES", onrr=None)
    else:
        out.update(status="OK", onrr=len(detect) / len(possible))
    return out


def persistence_deviation(current_onrr: Optional[float], historical_onrrs, min_history: int = 10,
                          mad_fallback: str = "meanad") -> dict:
    """G12: positive robust deviation of current ONRR vs the source's own historical ONRR windows."""
    if current_onrr is None:
        return {"status": "OBSERVATION_OPPORTUNITY_UNKNOWN", "p_robust": None, "p_dev": None, "p_norm": None}
    hist = [h for h in historical_onrrs if h is not None]
    if len(hist) < min_history:
        return {"status": "INSUFFICIENT_HISTORY", "p_robust": None, "p_dev": None, "p_norm": None,
                "n_history": len(hist), "reason": f"{len(hist)} historical ONRR windows < {min_history}"}
    z, method, status = robust_score(current_onrr, hist, mad_fallback)
    if status != "OK":
        return {"status": "DEGENERATE_BASELINE", "p_robust": None, "p_dev": None, "p_norm": None, "n_history": len(hist)}
    loo = []
    for i in range(len(hist)):
        zi, _, si = robust_score(hist[i], hist[:i] + hist[i + 1:], mad_fallback)
        if si == "OK":
            loo.append(max(0.0, zi))
    p_dev = max(0.0, z)
    return {"status": "OK", "p_robust": z, "p_dev": p_dev, "method": method, "n_history": len(hist),
            "hist_median": median(hist), "hist_mad": mad(hist),
            "p_norm": empirical_percentile(p_dev, loo) if len(loo) >= min_history else None,
            "p_norm_basis": f"empirical percentile of {len(loo)} leave-one-out deviations"}
