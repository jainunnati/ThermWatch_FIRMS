"""Gap-aware coverage ledger (Step 6D): UNCOVERED IS NOT ZERO.

We only know a satellite stream delivered data on a UTC day if rows from it exist for that day. A day with no
rows inside a stream's span is NOT evidence of "no fire": it may be an outage, a processing gap or a download
gap. The ledger therefore has exactly two evidence-based day states per stream:

  OBSERVED              >= min_obs_per_day rows from this stream on that UTC day
  NO_ROWS_UNVERIFIED    inside the stream span (first..last observed day) but no rows: coverage UNKNOWN
  (anything outside the span is OUTSIDE_STREAM_SPAN: also unknown)

Stream = canonical (instrument, satellite). Boundary days of a stream span are flagged because the first/last
day is usually only partly delivered. This ledger says nothing about whether a specific location was inside a
swath (that is observation opportunity / ONRR, still unavailable).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .schema import canonical_satellite

OBSERVED = "OBSERVED"
NO_ROWS_UNVERIFIED = "NO_ROWS_UNVERIFIED"
OUTSIDE_STREAM_SPAN = "OUTSIDE_STREAM_SPAN"


def stream_key(o) -> str:
    return f"{(o.instrument or 'NA').upper()}:{canonical_satellite(o.satellite) or 'NA'}"


@dataclass
class CoverageLedger:
    min_obs_per_day: int
    counts: dict        # stream -> {date: n_obs}
    spans: dict         # stream -> (first_date, last_date)
    boundary: dict      # stream -> {date: (first_ts_iso, last_ts_iso)} for first/last day only

    def status(self, stream: str, d: date) -> str:
        sp = self.spans.get(stream)
        if sp is None or d < sp[0] or d > sp[1]:
            return OUTSIDE_STREAM_SPAN
        return OBSERVED if self.counts[stream].get(d, 0) >= self.min_obs_per_day else NO_ROWS_UNVERIFIED

    def streams(self):
        return sorted(self.spans)

    def window_status(self, d0: date, d1: date, streams=None) -> dict:
        """Day-level coverage for [d0, d1] inclusive. A day is 'covered' if ANY selected stream is OBSERVED."""
        sel = list(streams) if streams is not None else self.streams()
        covered, unverified, per = [], [], {s: 0 for s in sel}
        d = d0
        while d <= d1:
            st = [self.status(s, d) for s in sel]
            for s, x in zip(sel, st):
                per[s] += (x == OBSERVED)
            (covered if OBSERVED in st else unverified).append(d)
            d += timedelta(days=1)
        return {"n_days": (d1 - d0).days + 1, "covered_days": covered, "unverified_days": unverified,
                "covered_days_by_stream": per}

    def gap_intervals(self, stream: str) -> list:
        """Maximal runs of NO_ROWS_UNVERIFIED days inside the stream span."""
        sp = self.spans.get(stream)
        if sp is None:
            return []
        out, start, d = [], None, sp[0]
        while d <= sp[1]:
            gap = self.status(stream, d) == NO_ROWS_UNVERIFIED
            if gap and start is None:
                start = d
            if not gap and start is not None:
                out.append((start, d - timedelta(days=1))); start = None
            d += timedelta(days=1)
        if start is not None:
            out.append((start, sp[1]))
        return out

    def summary(self) -> dict:
        res = {}
        for s in self.streams():
            a, b = self.spans[s]
            gaps = self.gap_intervals(s)
            n_span = (b - a).days + 1
            n_gap = sum((y - x).days + 1 for x, y in gaps)
            res[s] = {"first_day": a.isoformat(), "last_day": b.isoformat(), "span_days": n_span,
                      "observed_days": n_span - n_gap, "no_rows_unverified_days": n_gap,
                      "gap_intervals": [{"from": x.isoformat(), "to": y.isoformat(), "days": (y - x).days + 1} for x, y in gaps],
                      "boundary_days_partial_risk": {k.isoformat(): v for k, v in self.boundary[s].items()},
                      "note": "no-rows days are coverage-UNKNOWN, never zero fire activity"}
        return res


def build_coverage_ledger(observations, min_obs_per_day: int = 1) -> CoverageLedger:
    counts = defaultdict(lambda: defaultdict(int))
    tsr = defaultdict(lambda: defaultdict(lambda: [None, None]))
    for o in observations:
        k, d = stream_key(o), o.utc_date
        counts[k][d] += 1
        r = tsr[k][d]
        r[0] = o.timestamp_utc if r[0] is None or o.timestamp_utc < r[0] else r[0]
        r[1] = o.timestamp_utc if r[1] is None or o.timestamp_utc > r[1] else r[1]
    spans, boundary = {}, {}
    for k, c in counts.items():
        a, b = min(c), max(c)
        spans[k] = (a, b)
        boundary[k] = {d: (tsr[k][d][0].isoformat(), tsr[k][d][1].isoformat()) for d in sorted({a, b})}
    return CoverageLedger(min_obs_per_day, {k: dict(v) for k, v in counts.items()}, spans, boundary)
