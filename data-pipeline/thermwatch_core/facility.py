"""Facility association: "which facility, if any, is spatially associated with this thermal event?"

This module answers ONLY that question. It does NOT answer "is this an industrial fire?".
It assigns no industrial classification, no fire type, no risk/priority, no score and no
confidence percentage. Spatial association is not causation: an event near a facility may be
unrelated to it (a crop fire beside a plant), and a facility absent from the supplied dataset can
never be a candidate.

Three separate stages (no opaque combined function):

  A. generate_candidates   screening: which usable facilities are within the configured radius?
  B. compute_evidence      per candidate: only the quantities the supplied geometry supports.
  C. decide                ASSOCIATED | MULTIPLE_CANDIDATES | UNRESOLVED | INSUFFICIENT_EVIDENCE
                           (plus NOT_COMPUTED when no facility dataset is supplied at all).

`associate_point` / `associate_event` run A -> B -> C; `to_facility_attribution` renders the §14
`facility_attribution` object. Pass that object to `assessment.build_assessment(facility=...)`.

PARAMETERS (see FacilityParams) are CALIBRATION-OPEN and UNVALIDATED. The default 1000 m candidate
radius is a placeholder so the software runs; it was not derived from data and is deliberately NOT
the legacy 3 km. The separation margin is OFF by default (no invented threshold).

Evidence actually computed (units in the key names):
  distance_to_point_m     great-circle (haversine) distance, event point -> facility reference point
  point_in_polygon        only if a valid polygon was supplied; boundary counts as inside
  boundary_distance_m     only if a valid polygon was supplied; UNSIGNED distance to the polygon
                          boundary (also when inside), planar local approximation
  observations_inside_polygon / n_observations   only if a valid polygon AND observation points given
Evidence NOT computed here (kept null, never guessed): spatial_score, attribution_confidence,
distance_to_hist_centroid_m (needs facility-specific thermal history, a later step).

Decision rules (explicit, conservative):
  * no dataset (None/empty)                         -> NOT_COMPUTED
  * event point missing/invalid                     -> INSUFFICIENT_EVIDENCE
  * dataset supplied but no usable facility record  -> INSUFFICIENT_EVIDENCE
  * usable facilities but none within the radius    -> UNRESOLVED
  * exactly one candidate within the radius         -> ASSOCIATED (basis SOLE_CANDIDATE_WITHIN_RADIUS)
  * several candidates:
      - exactly one has the event inside its polygon AND every other candidate has polygon evidence
        (so its containment is known to be False)   -> ASSOCIATED (basis POLYGON_CONTAINMENT)
      - else, only if separation_margin_m is set and the nearest candidate is at least that much
        nearer than the runner-up                   -> ASSOCIATED (basis SEPARATION_MARGIN)
      - else                                        -> MULTIPLE_CANDIDATES (no facility selected)

Known limits (also returned in `limitations`): the 375 m VIIRS pixel footprint is not modelled; the
event point is the event centroid; point-only facilities are measured to their reference point while
polygon facilities are measured to their boundary, so point-only facilities are disadvantaged;
polygons are simple rings (no holes, no antimeridian handling); association is relative to the
supplied dataset, whose completeness is unknown; fixtures used in tests are not ground truth.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .geo import EARTH_RADIUS_M, haversine_m

NOT_COMPUTED = "NOT_COMPUTED"
ASSOCIATED = "ASSOCIATED"
MULTIPLE_CANDIDATES = "MULTIPLE_CANDIDATES"
UNRESOLVED = "UNRESOLVED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STATUSES = (ASSOCIATED, MULTIPLE_CANDIDATES, UNRESOLVED, INSUFFICIENT_EVIDENCE, NOT_COMPUTED)

PARAMS_LABEL = "CALIBRATION-OPEN, NOT VALIDATED (placeholder values; not derived from data)"
MODULE_VERSION = "facility-association-0.1.0"

LIMITATIONS = (
    "Spatial association only; it is not proof that the facility caused or is burning in the event.",
    "Association is relative to the supplied facility dataset; its completeness is unknown.",
    "Event position is the event centroid; the satellite pixel footprint (VIIRS ~375 m) is not modelled.",
    "Point-only facilities are measured to their reference point, polygon facilities to their boundary; "
    "point-only facilities are therefore disadvantaged.",
    "Candidate radius (and separation margin, if set) are calibration-open and unvalidated.",
    "No spatial score or attribution confidence is computed.",
)


@dataclass(frozen=True)
class FacilityParams:
    """All thresholds are explicit. None of them is validated."""
    candidate_radius_m: float = 1000.0              # placeholder; NOT the legacy 3 km
    separation_margin_m: Optional[float] = None     # None = distance may never break a tie

    def __post_init__(self):
        r = self.candidate_radius_m
        if isinstance(r, bool) or not isinstance(r, (int, float)) or not math.isfinite(r) or r <= 0:
            raise ValueError("candidate_radius_m must be a finite number > 0")
        m = self.separation_margin_m
        if m is not None and (isinstance(m, bool) or not isinstance(m, (int, float)) or not math.isfinite(m) or m <= 0):
            raise ValueError("separation_margin_m must be None or a finite number > 0")

    def to_dict(self) -> dict:
        return {"candidate_radius_m": float(self.candidate_radius_m),
                "separation_margin_m": (None if self.separation_margin_m is None else float(self.separation_margin_m)),
                "label": PARAMS_LABEL}


# ------------------------------------------------------------------ input parsing / validation
def _num(v):
    """float, None if absent/blank; ValueError if present but unusable (bool, non-numeric, non-finite)."""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, bool):
        raise ValueError("bool")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError("not numeric")
    if not math.isfinite(x):
        raise ValueError("not finite")
    return x


def validate_point(lat, lon):
    """Return (lat, lon, None) or (None, None, reason). Reasons: MISSING_COORDINATES | INVALID_COORDINATES."""
    try:
        la, lo = _num(lat), _num(lon)
    except ValueError:
        return None, None, "INVALID_COORDINATES"
    if la is None or lo is None:
        return None, None, "MISSING_COORDINATES"
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        return None, None, "INVALID_COORDINATES"
    return la, lo, None


@dataclass(frozen=True)
class Facility:
    id: str
    name: Optional[str]
    type: Optional[str]
    latitude: float
    longitude: float
    polygon: Optional[tuple]        # ring of (lat, lon), open (not repeated closing vertex); None = absent/invalid
    polygon_status: str             # ABSENT | VALID | INVALID
    bbox: tuple                     # (min_lat, max_lat, min_lon, max_lon) of polygon if valid else of the point

    def key(self):
        return (self.id, self.name, self.type, self.latitude, self.longitude, self.polygon)


@dataclass(frozen=True)
class FacilityDataset:
    n_supplied: int
    facilities: tuple               # usable, sorted by id (input-order independent)
    rejected: tuple                 # ({"id":..., "reasons":[...]}, ...) sorted deterministically
    notes: tuple                    # non-fatal data issues, e.g. FACILITY_TYPE_MISSING, POLYGON_INVALID

    @property
    def n_usable(self):
        return len(self.facilities)

    def summary(self) -> dict:
        return {"n_supplied": self.n_supplied, "n_usable": self.n_usable, "n_rejected": len(self.rejected),
                "rejected": [dict(r) for r in self.rejected], "notes": list(self.notes)}


def _parse_polygon(raw):
    """Return (ring_tuple|None, status). Ring is a list of [lat, lon]; closing vertex optional."""
    if raw is None or (isinstance(raw, (list, tuple)) and len(raw) == 0):
        return None, "ABSENT"
    try:
        pts = []
        for p in raw:
            la, lo, bad = validate_point(p[0], p[1])
            if bad or la is None:
                return None, "INVALID"
            pts.append((la, lo))
    except (TypeError, IndexError, KeyError):
        return None, "INVALID"
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(set(pts)) < 3:
        return None, "INVALID"
    # zero-area ring (all vertices collinear in a local plane) is not a polygon
    lat0, lon0 = pts[0]
    xy = [_project(la, lo, lat0, lon0) for la, lo in pts]
    area2 = sum(xy[i][0] * xy[(i + 1) % len(xy)][1] - xy[(i + 1) % len(xy)][0] * xy[i][1] for i in range(len(xy)))
    if abs(area2) < 1e-6:
        return None, "INVALID"
    return tuple(pts), "VALID"


def normalize_facilities(records) -> FacilityDataset:
    """Parse the facility shape {id, name, type, latitude|lat, longitude|lng|lon, polygon?}.

    Unusable records are rejected with reasons (never repaired, never defaulted). Duplicate ids with
    different content are all rejected (identity is ambiguous); exact duplicates collapse to one.
    A missing type or name does NOT make a facility unusable: the type simply stays null.
    Output is sorted, so it does not depend on input order.
    """
    records = list(records or [])
    parsed, rejected, notes = [], [], []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            rejected.append({"id": None, "reasons": ["NOT_AN_OBJECT"], "index": i}); continue
        fid = r.get("id")
        fid = None if fid is None or str(fid).strip() == "" else str(fid).strip()
        lat_raw = r["latitude"] if "latitude" in r else r.get("lat")
        lon_raw = r["longitude"] if "longitude" in r else (r["lng"] if "lng" in r else r.get("lon"))
        la, lo, bad = validate_point(lat_raw, lon_raw)
        reasons = []
        if fid is None:
            reasons.append("MISSING_ID")
        if bad:
            reasons.append("FACILITY_" + bad)
        if reasons:
            rejected.append({"id": fid, "reasons": reasons, **({"index": i} if fid is None else {})}); continue
        ring, pstat = _parse_polygon(r.get("polygon"))
        name = r.get("name")
        name = None if name is None or str(name).strip() == "" else str(name).strip()
        ftype = r.get("type")
        ftype = None if ftype is None or str(ftype).strip() == "" else str(ftype).strip()
        if ftype is None:
            notes.append({"id": fid, "note": "FACILITY_TYPE_MISSING"})
        if pstat == "INVALID":
            notes.append({"id": fid, "note": "POLYGON_INVALID_TREATED_AS_ABSENT"})
        bb = ((min(p[0] for p in ring), max(p[0] for p in ring), min(p[1] for p in ring), max(p[1] for p in ring))
              if ring else (la, la, lo, lo))
        parsed.append(Facility(fid, name, ftype, la, lo, ring, pstat, bb))

    by_id = {}
    for f in parsed:
        by_id.setdefault(f.id, []).append(f)
    usable = []
    for fid in sorted(by_id):
        group = by_id[fid]
        distinct = {f.key() for f in group}
        if len(distinct) == 1:
            usable.append(group[0])   # identical content, so any member is the same record
        else:
            rejected.append({"id": fid, "reasons": ["DUPLICATE_ID_CONFLICT"]})
    rejected.sort(key=lambda d: (str(d.get("id")), d.get("index", -1), ",".join(d["reasons"])))
    notes.sort(key=lambda d: (d["id"], d["note"]))
    return FacilityDataset(len(records), tuple(usable), tuple(rejected), tuple(notes))


# ------------------------------------------------------------------ geometry (local planar metres)
def _project(lat, lon, lat0, lon0):
    x = math.radians(lon - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def polygon_relation(lat, lon, ring):
    """(inside: bool, boundary_distance_m: float). Planar approximation centred on the point.
    A point on the boundary (distance ~0) counts as inside. Valid for extents of a few tens of km."""
    xy = [_project(a, b, lat, lon) for a, b in ring]       # event point is the origin
    n = len(xy)
    dmin = min(_seg_dist(0.0, 0.0, *xy[i], *xy[(i + 1) % n]) for i in range(n))
    inside = False
    for i in range(n):
        (x1, y1), (x2, y2) = xy[i], xy[(i + 1) % n]
        if (y1 > 0) != (y2 > 0):
            xc = x1 + (0 - y1) * (x2 - x1) / (y2 - y1)
            if xc > 0:
                inside = not inside
    if dmin <= 1e-6:
        inside = True
    return inside, dmin


# ------------------------------------------------------------------ stage A: candidate generation
@dataclass(frozen=True)
class Candidate:
    facility: Facility
    screening_distance_m: float     # 0 if inside valid polygon; else boundary (valid polygon) or point distance
    screening_basis: str            # "polygon" | "point"


def generate_candidates(lat, lon, dataset: FacilityDataset, params: FacilityParams = FacilityParams()):
    """Stage A. Facilities whose screening distance is <= candidate_radius_m, ordered by
    (screening distance, id). Independent of dataset input order. `lat`/`lon` must already be valid."""
    r = params.candidate_radius_m
    out = []
    for f in dataset.facilities:
        # cheap prefilter: great-circle distance >= north-south separation (1 m slack absorbs float round-off,
        # so a facility exactly at the radius is never wrongly skipped)
        gap = 0.0 if f.bbox[0] <= lat <= f.bbox[1] else min(abs(lat - f.bbox[0]), abs(lat - f.bbox[1]))
        if math.radians(gap) * EARTH_RADIUS_M > r + 1.0:
            continue
        if f.polygon:
            inside, bd = polygon_relation(lat, lon, f.polygon)
            d, basis = (0.0 if inside else bd), "polygon"
        else:
            d, basis = haversine_m(lat, lon, f.latitude, f.longitude), "point"
        if d <= r:
            out.append(Candidate(f, d, basis))
    out.sort(key=lambda c: (c.screening_distance_m, c.facility.id))
    return out


# ------------------------------------------------------------------ stage B: evidence
def compute_evidence(lat, lon, cand: Candidate, observation_points=None) -> dict:
    """Stage B. Only supported quantities; unavailable ones are None with an explicit status."""
    f = cand.facility
    ev = {
        "facility_id": f.id, "facility_name": f.name, "facility_type": f.type,
        "geometry_basis": cand.screening_basis,
        "distance_to_point_m": round(haversine_m(lat, lon, f.latitude, f.longitude), 1),
        "polygon_status": f.polygon_status,
        "point_in_polygon": None, "boundary_distance_m": None,
        "observations_inside_polygon": None, "n_observations": None,
        "candidate_distance_m": round(cand.screening_distance_m, 1),
        "notes": [],
    }
    if f.polygon:
        inside, bd = polygon_relation(lat, lon, f.polygon)
        ev["point_in_polygon"], ev["boundary_distance_m"] = inside, round(bd, 1)
        if observation_points:
            pts = sorted(observation_points)
            ev["n_observations"] = len(pts)
            ev["observations_inside_polygon"] = sum(1 for p in pts if polygon_relation(p[0], p[1], f.polygon)[0])
    else:
        ev["notes"].append("POLYGON_ABSENT: containment and boundary distance unavailable" if f.polygon_status == "ABSENT"
                           else "POLYGON_INVALID: containment and boundary distance unavailable")
    if f.type is None:
        ev["notes"].append("FACILITY_TYPE_MISSING")
    return ev


# ------------------------------------------------------------------ stage C: decision
@dataclass(frozen=True)
class AssociationDecision:
    status: str
    selected: Optional[dict]                 # chosen candidate's evidence (ASSOCIATED only)
    candidates: tuple                        # all candidate evidence dicts, deterministic order
    basis: Optional[str]
    reason_codes: tuple
    reason: str
    event_point: Optional[tuple]
    params: FacilityParams
    dataset_summary: Optional[dict]


def decide(evidences, params: FacilityParams, *, point_ok=True, point_issue=None, dataset: Optional[FacilityDataset] = None,
           event_point=None) -> AssociationDecision:
    """Stage C. `evidences` are stage-B dicts for every candidate, already ordered by candidate_distance_m, id."""
    ds = dataset.summary() if dataset is not None else None

    def out(status, codes, reason, selected=None, basis=None):
        return AssociationDecision(status, selected, tuple(evidences), basis, tuple(codes), reason, event_point, params, ds)

    if dataset is None or dataset.n_supplied == 0:
        return out(NOT_COMPUTED, ["FACILITY_DATASET_NOT_SUPPLIED"], "no facility dataset supplied; association not computed")
    if not point_ok:
        return out(INSUFFICIENT_EVIDENCE, [point_issue or "EVENT_COORDINATES_UNUSABLE"],
                   "event coordinates are missing or invalid; no spatial comparison is possible")
    if dataset.n_usable == 0:
        return out(INSUFFICIENT_EVIDENCE, ["NO_USABLE_FACILITY_RECORDS"],
                   f"{dataset.n_supplied} facility record(s) supplied but none usable (see dataset_summary.rejected)")
    if not evidences:
        return out(UNRESOLVED, ["NO_FACILITY_WITHIN_RADIUS"],
                   f"no usable facility within the configured candidate radius of {params.candidate_radius_m:g} m "
                   "(dataset completeness unknown)")
    if len(evidences) == 1:
        e = evidences[0]
        return out(ASSOCIATED, ["SOLE_CANDIDATE_WITHIN_RADIUS"],
                   f"{e['facility_id']} is the only usable facility within {params.candidate_radius_m:g} m "
                   "(spatial association only; not causation)", selected=e, basis="SOLE_CANDIDATE_WITHIN_RADIUS")
    inside = [e for e in evidences if e["point_in_polygon"] is True]
    unknown = [e for e in evidences if e["point_in_polygon"] is None]
    if len(inside) == 1 and not unknown:
        e = inside[0]
        return out(ASSOCIATED, ["POLYGON_CONTAINMENT_UNIQUE"],
                   f"event lies inside the polygon of {e['facility_id']} only; every other candidate has polygon "
                   "evidence placing the event outside (spatial association only; not causation)",
                   selected=e, basis="POLYGON_CONTAINMENT")
    m = params.separation_margin_m
    if m is not None:
        d0, d1 = evidences[0]["candidate_distance_m"], evidences[1]["candidate_distance_m"]
        if d1 - d0 >= m:
            e = evidences[0]
            return out(ASSOCIATED, ["SEPARATION_MARGIN_MET"],
                       f"{e['facility_id']} is at least {m:g} m nearer than the runner-up "
                       f"({d0:g} m vs {d1:g} m; basis {e['geometry_basis']}/{evidences[1]['geometry_basis']}); "
                       "distance-based, unvalidated margin", selected=e, basis="SEPARATION_MARGIN")
    return out(MULTIPLE_CANDIDATES, ["EVIDENCE_CANNOT_DISTINGUISH_CANDIDATES"],
               f"{len(evidences)} candidate facilities within {params.candidate_radius_m:g} m; the available "
               "evidence does not distinguish them, so none is selected")


# ------------------------------------------------------------------ orchestration
def associate_point(lat, lon, facilities, params: FacilityParams = FacilityParams(), *, observation_points=None):
    """Run A -> B -> C for one event position. `facilities` is a raw record list, a FacilityDataset, or None."""
    la, lo, issue = validate_point(lat, lon)
    ds = facilities if isinstance(facilities, FacilityDataset) else (normalize_facilities(facilities) if facilities is not None else None)
    if issue:
        return decide([], params, point_ok=False, point_issue="EVENT_" + issue, dataset=ds)
    if ds is None or ds.n_supplied == 0 or ds.n_usable == 0:
        return decide([], params, dataset=ds, event_point=(la, lo))
    cands = generate_candidates(la, lo, ds, params)
    evid = [compute_evidence(la, lo, c, observation_points) for c in cands]
    return decide(evid, params, dataset=ds, event_point=(la, lo))


def associate_event(result, event_id, facilities, params: FacilityParams = FacilityParams()):
    """Use the core event representation: event centroid is the event point; event observations feed
    the optional per-observation containment count."""
    ev = result.events[event_id]
    pts = [(o.latitude, o.longitude) for o in result.observations_of_event(event_id)]
    return associate_point(ev.centroid[0], ev.centroid[1], facilities, params, observation_points=pts)


# ------------------------------------------------------------------ §14 rendering
def to_facility_attribution(d: AssociationDecision) -> dict:
    """§14 `facility_attribution`. Existing frontend keys are preserved with their existing types
    (`alternative_candidates` = list of ID strings). New keys are additive and ignored by the frontend."""
    sel = d.selected
    ids = [e["facility_id"] for e in d.candidates]
    alts = [i for i in ids if not sel or i != sel["facility_id"]]
    ambiguity = (True if d.status == MULTIPLE_CANDIDATES
                 else False if d.status in (ASSOCIATED, UNRESOLVED) else None)
    return {
        "status": d.status,
        "candidate_facility_id": sel["facility_id"] if sel else None,
        "candidate_facility_type": sel["facility_type"] if sel else None,
        "point_in_polygon": sel["point_in_polygon"] if sel else None,
        "boundary_distance_m": sel["boundary_distance_m"] if sel else None,
        "distance_to_hist_centroid_m": None,
        "spatial_score": None,
        "attribution_confidence": None,
        "reason": d.reason,
        "alternative_candidates": alts,
        "ambiguity_flag": ambiguity,
        # additive fields
        "association_usable": d.status == ASSOCIATED,
        "association_basis": d.basis,
        "candidate_evidence": [dict(e) for e in d.candidates],
        "reason_codes": list(d.reason_codes),
        "evidence": {
            "event_point": ({"lat": d.event_point[0], "lon": d.event_point[1]} if d.event_point else None),
            "distance_unit": "m", "distance_to_hist_centroid_m_status": "NOT_COMPUTED: needs facility thermal history (later step)",
            "spatial_score_status": "NOT_COMPUTED: no justified weights", "attribution_confidence_status": "NOT_COMPUTED: no calibration",
        },
        "parameters": d.params.to_dict(),
        "facility_dataset": d.dataset_summary,
        "uncertainty": {"basis": "no confidence is computed; see limitations", "limitations": list(LIMITATIONS)},
        "label": f"D; {PARAMS_LABEL}; {MODULE_VERSION}",
    }


# ------------------------------------------------------------------ Step 6D: raw context vs decision output
# Fields produced by stage C / to_facility_attribution() are the OUTPUT of a heuristic decision (status,
# which facility was "selected", whether it is usable...). They must never be fed to a model as features:
# that would let a hand-written rule (and its unvalidated thresholds) leak into the learner. Raw geometry
# context below is computed WITHOUT calling decide().
DECISION_DERIVED_FIELDS = frozenset({
    "status", "candidate_facility_id", "candidate_facility_type", "association_usable", "association_basis",
    "reason", "reason_codes", "ambiguity_flag", "alternative_candidates", "candidate_evidence", "selected",
    "attribution_confidence", "spatial_score", "distance_to_hist_centroid_m", "basis",
})
RAW_CONTEXT_STATUS_NOT_COMPUTED = "NOT_COMPUTED"


def assert_no_decision_fields(feature_dict: dict) -> None:
    """Guard for any future feature table: raises if a decision-derived field is present."""
    leaked = sorted(DECISION_DERIVED_FIELDS & set(feature_dict))
    if leaked:
        raise ValueError(f"decision-derived facility fields must not be used as features: {leaked}")


def facility_raw_context(lat, lon, facilities, params: FacilityParams = FacilityParams()) -> dict:
    """Raw facility geometry/context around a point. No ASSOCIATED/UNRESOLVED status, no selected facility,
    no reason codes, no ambiguity flag. Missing dataset -> every value None (NOT zero facilities)."""
    base = {"facility_context_status": RAW_CONTEXT_STATUS_NOT_COMPUTED, "candidate_radius_m": params.candidate_radius_m,
            "n_facilities_within_radius": None, "nearest_screening_distance_m": None,
            "nearest_distance_to_point_m": None, "nearest_point_in_polygon": None,
            "nearest_boundary_distance_m": None, "nearest_polygon_status": None, "nearest_facility_type": None}
    la, lo, issue = validate_point(lat, lon)
    ds = facilities if isinstance(facilities, FacilityDataset) else (normalize_facilities(facilities) if facilities is not None else None)
    if issue:
        return {**base, "facility_context_status": "NOT_COMPUTED_EVENT_COORDINATES_UNUSABLE"}
    if ds is None or ds.n_supplied == 0:
        return {**base, "facility_context_status": "NOT_COMPUTED_NO_FACILITY_DATASET"}
    if ds.n_usable == 0:
        return {**base, "facility_context_status": "NOT_COMPUTED_NO_USABLE_FACILITY_RECORDS"}
    cands = generate_candidates(la, lo, ds, params)
    if not cands:
        return {**base, "facility_context_status": "COMPUTED_NONE_WITHIN_RADIUS_DATASET_COMPLETENESS_UNKNOWN",
                "n_facilities_within_radius": 0}
    ev = compute_evidence(la, lo, cands[0])
    return {**base, "facility_context_status": "COMPUTED", "n_facilities_within_radius": len(cands),
            "nearest_screening_distance_m": ev["candidate_distance_m"], "nearest_distance_to_point_m": ev["distance_to_point_m"],
            "nearest_point_in_polygon": ev["point_in_polygon"], "nearest_boundary_distance_m": ev["boundary_distance_m"],
            "nearest_polygon_status": ev["polygon_status"], "nearest_facility_type": ev["facility_type"]}
