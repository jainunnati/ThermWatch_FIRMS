"""Stateful, deterministic source/event formation (replaces 2-decimal grid clustering).

Two identities, because one is not enough:
  SOURCE  = a spatially stable thermal location (incremental single-linkage with an extent cap).
  EVENT   = a temporal episode of a source: observations separated by <= W hours.

A flare observed every day for a year is ONE source and (with W=36 h) possibly one very long
event; a field burn seen twice in two days is a short event on its own source. Downstream baselines
therefore compare at source-day granularity (see baseline.py), not per long event.

Parameters (ALL calibration-open; defaults follow the frozen worked example and are NOT validated):
  source_radius_m   375    ~ one VIIRS I-band pixel. May split a source seen off-nadir (pixels grow);
                           see pixel_aware option and the sensitivity experiment.
  event_window_hours 36    the 'W' of the spec (prototype value; final value must come from evaluation).
  max_source_extent_m 2000 cap on distance from the source centroid to stop chaining along a line of fires.

Determinism: observations are processed in (timestamp, physical_key, observation_id) order, so results do not
depend on input row order. Source ids derive from the PHYSICAL KEY of the earliest observation (mode-free, so the
same physical source keeps its id whether it arrived as HISTORICAL or NRT). Adding EARLIER history can still
change them (documented limitation). Id collisions are detected and resolved deterministically (longer hash) and
reported in diagnostics['source_id_collisions']; duplicate observation ids are refused (never silently merged).

As-of safety (Step 6D): when as_of_utc is given, observations AFTER it are excluded from formation (counted in
diagnostics['n_excluded_after_as_of']), so a replay at time t cannot see the future.

Ambiguity is recorded, never silently resolved: an observation within radius of >1 source is assigned
to the nearest and logged in diagnostics['ambiguous_assignments']; sources are never auto-merged.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .geo import bbox, haversine_m, mean_centroid
from .schema import ModeMixingError, Observation


@dataclass(frozen=True)
class EventParams:
    source_radius_m: float = 375.0
    event_window_hours: float = 36.0
    max_source_extent_m: float = 2000.0
    pixel_aware: bool = False        # widen pair radius to pixel_factor * max(scan, track)
    pixel_factor: float = 1.0
    allow_mixed_modes: bool = False


@dataclass
class Source:
    source_id: str
    observation_ids: list
    centroid: tuple
    bbox: dict
    extent_m: float
    first_utc: datetime
    last_utc: datetime
    event_ids: list
    anchor_physical_key: str = ""    # physical key of the earliest observation; the source id is derived from it


@dataclass
class Event:
    event_id: str
    source_id: str
    observation_ids: list
    start_utc: datetime
    end_utc: datetime
    centroid: tuple
    bbox: dict
    state: str                       # 'active' | 'archived' (relative to as_of, never wall-clock)
    sensors: dict


@dataclass
class EventFormationResult:
    params: EventParams
    as_of_utc: datetime
    observations: dict               # observation_id -> Observation
    sources: dict                    # source_id -> Source
    events: dict                     # event_id -> Event
    assignment: dict                 # observation_id -> (source_id, event_id)
    diagnostics: dict

    def observations_of_source(self, source_id):
        return [self.observations[i] for i in self.sources[source_id].observation_ids]

    def observations_of_event(self, event_id):
        return [self.observations[i] for i in self.events[event_id].observation_ids]


def _short(s: str, n: int = 10) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:n]


def _new_source_id(anchor_key: str, taken, collisions: list) -> str:
    """Deterministic id from the anchor physical key; widen the hash on collision (never overwrite a source)."""
    n = 10
    sid = "SRC-" + _short(anchor_key, n)
    while sid in taken:
        collisions.append({"anchor_physical_key": anchor_key, "colliding_id": sid, "hash_chars": n})
        n += 4
        if n > 40:
            raise RuntimeError(f"cannot find a collision-free source id for {anchor_key}")
        sid = "SRC-" + _short(anchor_key, n)
    return sid


def form_events(observations, params: EventParams = EventParams(), as_of_utc: Optional[datetime] = None) -> EventFormationResult:
    observations = list(observations)
    modes = {o.data_mode for o in observations}
    if len(modes) > 1 and not params.allow_mixed_modes:
        raise ModeMixingError(f"Event formation refuses mixed data modes: {sorted(m.value for m in modes)}")
    ids = Counter(o.observation_id for o in observations)
    dup_ids = sorted(i for i, c in ids.items() if c > 1)
    if dup_ids:
        raise ValueError(f"duplicate observation_id(s) refused (dedup first, see identity.dedup_cross_source): {dup_ids[:5]}")
    n_after_as_of = 0
    if as_of_utc is not None:
        kept = [o for o in observations if o.timestamp_utc <= as_of_utc]
        n_after_as_of, observations = len(observations) - len(kept), kept
    obs_sorted = sorted(observations, key=lambda o: (o.timestamp_utc, o.physical_key, o.observation_id))
    n_dup_phys = len(obs_sorted) - len({o.physical_key for o in obs_sorted})
    if as_of_utc is None and obs_sorted:
        as_of_utc = obs_sorted[-1].timestamp_utc
    collisions = []

    max_px = max((max(o.scan_km or 0, o.track_km or 0) * 1000 for o in obs_sorted), default=0.0)
    search_r = params.source_radius_m
    if params.pixel_aware:
        search_r = max(search_r, params.pixel_factor * max_px)
    cell = 0.01  # degrees (~1.1 km) spatial hash

    index = defaultdict(list)            # (i, j) -> [(Observation, source_id)]
    src = {}                             # source_id -> state dict
    assignment, ambiguous = {}, []
    extent_rejections = 0

    def cell_of(lat, lon):
        return (math.floor(lat / cell), math.floor(lon / cell))

    for o in obs_sorted:
        ci, cj = cell_of(o.latitude, o.longitude)
        kl = int(math.ceil(search_r / (cell * 111_000.0))) + 1
        kn = int(math.ceil(search_r / (cell * 111_000.0 * max(0.05, math.cos(math.radians(o.latitude)))))) + 1
        cands = {}
        for di in range(-kl, kl + 1):
            for dj in range(-kn, kn + 1):
                for m, sid in index.get((ci + di, cj + dj), ()):
                    d = haversine_m(o.latitude, o.longitude, m.latitude, m.longitude)
                    r_pair = params.source_radius_m
                    if params.pixel_aware:
                        px = max(o.scan_km or 0, o.track_km or 0, m.scan_km or 0, m.track_km or 0) * 1000
                        r_pair = max(r_pair, params.pixel_factor * px)
                    if d <= r_pair and d < cands.get(sid, float("inf")):
                        cands[sid] = d
        valid = {}
        for sid, d in cands.items():
            s = src[sid]
            cen = (s["lat_sum"] / len(s["obs"]), s["lon_sum"] / len(s["obs"]))
            if haversine_m(o.latitude, o.longitude, cen[0], cen[1]) <= params.max_source_extent_m:
                valid[sid] = d
            else:
                extent_rejections += 1
        if valid:
            sid = min(valid, key=lambda k: (valid[k], k))
            if len(valid) > 1:
                ambiguous.append({"observation_id": o.observation_id,
                                  "candidates": {k: round(v, 1) for k, v in sorted(valid.items())},
                                  "assigned": sid})
        else:
            sid = _new_source_id(o.physical_key, src, collisions)
            src[sid] = {"obs": [], "lat_sum": 0.0, "lon_sum": 0.0, "episodes": [], "anchor": o.physical_key}
        s = src[sid]
        gap_h = None
        if s["obs"]:
            gap_h = (o.timestamp_utc - s["obs"][-1].timestamp_utc).total_seconds() / 3600.0
        if not s["episodes"] or gap_h > params.event_window_hours:
            s["episodes"].append([])
        s["episodes"][-1].append(o)
        s["obs"].append(o)
        s["lat_sum"] += o.latitude
        s["lon_sum"] += o.longitude
        index[(ci, cj)].append((o, sid))
        assignment[o.observation_id] = (sid, f"EVT-{sid[4:]}-{len(s['episodes']):03d}")

    sources, events = {}, {}
    for sid, s in src.items():
        pts = [(x.latitude, x.longitude) for x in s["obs"]]
        cen = mean_centroid(pts)
        eids = []
        for k, ep in enumerate(s["episodes"], start=1):
            eid = f"EVT-{sid[4:]}-{k:03d}"
            epts = [(x.latitude, x.longitude) for x in ep]
            end = ep[-1].timestamp_utc
            state = "active" if (as_of_utc - end).total_seconds() / 3600.0 <= params.event_window_hours else "archived"
            events[eid] = Event(eid, sid, [x.observation_id for x in ep], ep[0].timestamp_utc, end,
                                mean_centroid(epts), bbox(epts), state,
                                dict(Counter(x.sensor_label or "UNKNOWN" for x in ep)))
            eids.append(eid)
        sources[sid] = Source(sid, [x.observation_id for x in s["obs"]], cen, bbox(pts),
                              max(haversine_m(p[0], p[1], cen[0], cen[1]) for p in pts),
                              s["obs"][0].timestamp_utc, s["obs"][-1].timestamp_utc, eids, s["anchor"])

    n_src = len(sources)
    diagnostics = {
        "n_observations": len(obs_sorted), "n_sources": n_src, "n_events": len(events),
        "singleton_source_fraction": (sum(1 for s in sources.values() if len(s.observation_ids) == 1) / n_src) if n_src else None,
        "events_per_source_max": max((len(s.event_ids) for s in sources.values()), default=0),
        "ambiguous_assignments": ambiguous, "n_ambiguous_assignments": len(ambiguous),
        "extent_cap_rejections": extent_rejections,
        "search_radius_m": search_r, "pixel_aware": params.pixel_aware,
        "source_id_collisions": collisions, "n_source_id_collisions": len(collisions),
        "n_duplicate_physical_keys": n_dup_phys,
        "n_excluded_after_as_of": n_after_as_of,
    }
    return EventFormationResult(params, as_of_utc, {o.observation_id: o for o in obs_sorted},
                                sources, events, assignment, diagnostics)
