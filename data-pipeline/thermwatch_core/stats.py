"""Plain robust statistics (no numpy needed; inputs are small histories)."""
from __future__ import annotations

import statistics
from typing import Optional, Sequence

MAD_TO_SIGMA_K = 0.6745            # spec: robust_z = 0.6745 * (x - median) / MAD
MEANAD_K = 1.253314                # Iglewicz & Hoaglin (1993) modified-z fallback when MAD == 0


def median(xs: Sequence[float]) -> float:
    return statistics.median(xs)


def mad(xs: Sequence[float], center: Optional[float] = None) -> float:
    """Raw (unscaled) median absolute deviation, exactly as in the spec."""
    c = median(xs) if center is None else center
    return statistics.median([abs(x - c) for x in xs])


def mean_abs_dev(xs: Sequence[float], center: float) -> float:
    return sum(abs(x - center) for x in xs) / len(xs)


def percentile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def distribution_summary(xs: Sequence[float]) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0, "min": None, "p10": None, "median": None, "mad": None, "p90": None, "max": None}
    m = median(xs)
    return {"n": len(xs), "min": min(xs), "p10": percentile(xs, 10), "median": m,
            "mad": mad(xs, m), "p90": percentile(xs, 90), "max": max(xs)}


def robust_score(x: float, reference: Sequence[float], mad_fallback: str = "meanad", eps: float = 1e-9):
    """Return (z, method, status).

    status: OK | DEGENERATE_BASELINE.  method: MAD | MEANAD_FALLBACK | None.
    Never divides by zero and never fabricates a huge score from a zero spread.
    """
    m = median(reference)
    d = mad(reference, m)
    if d > eps:
        return MAD_TO_SIGMA_K * (x - m) / d, "MAD", "OK"
    if mad_fallback == "meanad":
        ma = mean_abs_dev(reference, m)
        if ma > eps:
            return (x - m) / (MEANAD_K * ma), "MEANAD_FALLBACK", "OK"
    return None, None, "DEGENERATE_BASELINE"


def empirical_percentile(x: float, reference: Sequence[float]) -> float:
    """Fraction of reference values <= x (monotone map into [0,1])."""
    return sum(1 for r in reference if r <= x) / len(reference)
