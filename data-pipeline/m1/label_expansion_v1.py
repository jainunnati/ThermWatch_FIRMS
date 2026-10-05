"""LABEL_EXPANSION_V1 - research-candidate expansion (NOT labels). Frozen inputs: LABEL_FACTORY_V1 + REVIEW72.
Rules (written before running):
  Pool       : registry sources with >= 1 operating exact-coordinate GEM site within 2 km; excluded: Batch-25, REVIEW72.
  Candidate  : decision REVIEW  if exactly one facility TYPE within 2 km (research queue for that context class)
               decision UNKNOWN if more than one facility type within 2 km (class-definition conflict, e.g. steel +
                                captive power) - listed, never forced to the nearest type
               decision REJECT  never generated here (2-5 km sources are already features-only in the factory)
               decision ACCEPT  never generated (requires independent evidence + adjudication)
  Registry columns read: source_id, centroid_lat, centroid_lon ONLY (enforced by TrackedRow in tests/audit).
  site_complex_id: connected components of ALL in-extent GEM sites within 5 km; id = 'SC-' + first 10 hex of
                   sha256(sorted member facility keys) -> independent of which sources are candidates.
  evidence_priority (research efficiency only): GEM reference URL present, fewer competing sites within 2 km, closer,
                   first candidate of each site complex before repeats. No FIRMS field is read anywhere."""
import csv, gzip, hashlib, json, math, sys
from collections import defaultdict, Counter
from pathlib import Path

REG_FIELDS_ALLOWED = {"source_id", "centroid_lat", "centroid_lon"}
KIND2CLS = {"STEEL": "STEEL_METAL", "COAL": "THERMAL_POWER", "OILGAS": "LNG_GAS"}
REGISTRY_NAME = {"STEEL": "GEM Global Iron and Steel Tracker Sep-2026 (V1)", "COAL": "GEM Global Coal Plant Tracker Jul-2026",
                 "OILGAS": "GEM Global Oil and Gas Extraction Tracker Mar-2026"}


class TrackedRow(dict):
    """dict that records every key read - used to prove which registry fields the generator touches."""
    accessed = set()
    def __getitem__(self, k): TrackedRow.accessed.add(k); return super().__getitem__(k)
    def get(self, k, d=None): TrackedRow.accessed.add(k); return super().get(k, d)


def km(a, b, c, d):
    r = math.radians; x = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, x)))


def site_complexes(sites, link_km=5.0):
    keys = [f"{s['kind']}:{s['site_id']}" for s in sites]; loc = {f"{s['kind']}:{s['site_id']}": (s["lat"], s["lon"]) for s in sites}
    parent = {k: k for k in keys}
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    grid = defaultdict(list)
    for k in keys: grid[(math.floor(loc[k][0] / 0.05), math.floor(loc[k][1] / 0.05))].append(k)
    for k in keys:
        gi, gj = math.floor(loc[k][0] / 0.05), math.floor(loc[k][1] / 0.05)
        for di in range(-2, 3):
            for dj in range(-2, 3):
                for o in grid.get((gi + di, gj + dj), []):
                    if o > k and km(*loc[k], *loc[o]) <= link_km: parent[find(k)] = find(o)
    comp = defaultdict(list)
    for k in keys: comp[find(k)].append(k)
    return {k: "SC-" + hashlib.sha256("|".join(sorted(m)).encode()).hexdigest()[:10] for m in comp.values() for k in m}


def decide(c2):
    """c2: candidates within 2 km [(kind, key, name, d, ref)], nearest first. Uses only facility types/distances."""
    types = {x[0] for x in c2}
    if len(types) > 1: return "UNKNOWN", f"class-definition conflict: {sorted(types)} within 2 km (e.g. captive/adjacent plants)"
    return "REVIEW", "single facility type within 2 km; needs independent non-GEM evidence"


def generate(registry_rows, sites, exclude):
    grid = defaultdict(list)
    for s in sites: grid[(math.floor(s["lat"] / 0.05), math.floor(s["lon"] / 0.05))].append(s)
    sc = site_complexes(sites); out = []; seen_ids = set()
    for r in registry_rows:
        sid = r["source_id"]
        if sid in exclude or sid in seen_ids: continue          # duplicate input rows never yield duplicate candidates
        seen_ids.add(sid)
        la, lo = float(r["centroid_lat"]), float(r["centroid_lon"]); gi, gj = math.floor(la / 0.05), math.floor(lo / 0.05)
        c = []
        for di in range(-1, 2):
            for dj in range(-1, 2):
                for s in grid.get((gi + di, gj + dj), []):
                    d = km(la, lo, s["lat"], s["lon"])
                    if d <= 2.0: c.append((s["kind"], f"{s['kind']}:{s['site_id']}", s["name"], round(d, 4), s["ref"] if isinstance(s["ref"], str) else "", s["lat"], s["lon"]))
        if not c: continue
        c = sorted(set(c), key=lambda x: (x[3], x[1])); dec, why = decide(c); n = c[0]
        out.append({"source_id": sid, "proposed_context_class": KIND2CLS[n[0]] if dec == "REVIEW" else "UNRESOLVED_MULTI_TYPE",
                    "facility_name": n[2], "facility_type": n[0], "facility_id": n[1], "facility_lat": round(n[5], 6), "facility_lon": round(n[6], 6),
                    "source_lat": round(la, 5), "source_lon": round(lo, 5), "distance_km": n[3],
                    "second_nearest_distance_km": c[1][3] if len(c) > 1 else "", "competing_facility_count_2km": len(c) - 1,
                    "site_complex_id": sc[n[1]], "registry_source": REGISTRY_NAME[n[0]], "registry_reference": n[4] or REGISTRY_NAME[n[0]],
                    "evidence_priority": "", "evidence_status": "NO_EVIDENCE", "candidate_decision": dec, "rejection_reason": "" if dec == "REVIEW" else why,
                    "notes": why if dec == "REVIEW" else "listed for research; never forced to the nearest type"})
    out.sort(key=lambda x: (0 if x["registry_reference"].startswith("http") else 1, x["competing_facility_count_2km"], x["distance_km"], x["source_id"]))
    seen, first, rest = set(), [], []
    for x in out:
        (rest if x["site_complex_id"] in seen else first).append(x); seen.add(x["site_complex_id"])
    for i, x in enumerate(first + rest, 1): x["evidence_priority"] = i
    return sorted(first + rest, key=lambda x: x["evidence_priority"]), sc


def ledger_rows(cands):
    return [{"source_id": x["source_id"], "proposed_label": x["proposed_context_class"], "label_tier": "UNRESOLVED", "label_confidence": "",
             "facility_type": x["facility_type"], "facility_reference": x["registry_reference"], "facility_distance_km": x["distance_km"],
             "evidence_type": "", "evidence_url_or_reference": "", "evidence_date": "", "evidence_summary": "",
             "counter_evidence": x["rejection_reason"], "competing_candidates": x["competing_facility_count_2km"],
             "reviewer_status": "NEEDS_RESEARCH", "adjudication_status": "NOT_STARTED"} for x in cands]
