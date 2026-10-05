"""ThermWatch Attribution MVP v1 - Phase 1 HEURISTIC, proximity-driven attribution. NOT a model, NOT probabilities, NOT labels.
Method (methodology_version below; nothing is learned or tuned on labels):
  candidates : GEM operating exact-coordinate sites within R_MAX=5 km (STEEL->STEEL_METAL, COAL->THERMAL_POWER, OILGAS->LNG_GAS)
  weight     : w(d) = 1 / (d_km + EPS)^2, EPS = 0.1 km; category weight = sum over its candidates
  background : OTHER_UNKNOWN always gets w(BG_KM) with BG_KM = 2.0 km ("something else nearby" never vanishes)
  context    : AGRICULTURE / WILDFIRE only if cached OSM context (status OK) has farmland / forest within 1 km -> weight w(1.0)
  modifiers  : facility categories only, bounded: x1.2 if active_days>=20 and night_frac>=0.8; x0.8 if a single detection
  output     : weights normalised to integer percent summing to 100 (largest remainder)
  confidence : UNKNOWN if no facility within R_MAX; MEDIUM only if ALL of: top facility <=0.5 km, no other facility category within
               2 km, persistence modifier applied, OSM context OK with a matching facility tag within 1 km; otherwise LOW. HIGH never.
Statements produced are FACT (distances, counts) or HEURISTIC (ranking). The MVP never states a confirmed cause."""
import math

METHODOLOGY_VERSION = "attribution-mvp-v1 (w=1/(d+0.1)^2; bg@2km; mods x1.2/x0.8; no HIGH)"
EPS, R_MAX, BG_KM = 0.1, 5.0, 2.0
KIND2CAT = {"STEEL": "STEEL_METAL", "COAL": "THERMAL_POWER", "OILGAS": "LNG_GAS"}
OSM_TAG = {"STEEL_METAL": "osm_count_steel_metal_1000m", "THERMAL_POWER": "osm_count_power_plant_1000m", "LNG_GAS": "osm_count_oil_gas_1000m"}
DISCLAIMER = "Attribution weights are heuristic and proximity-driven. They are not calibrated probabilities or confirmed causes."


def haversine_km(a, b, c, d):
    r = math.radians; x = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, x)))


def w(d): return 1.0 / (d + EPS) ** 2


def pct(weights):
    t = sum(weights.values()); x = {k: v / t * 100 for k, v in weights.items()}; b = {k: math.floor(v) for k, v in x.items()}
    for k in sorted(x, key=lambda k: (-(x[k] - b[k]), k))[:100 - sum(b.values())]: b[k] += 1
    return b


def attribute(src, facilities, osm=None):
    """src: {source_id, lat, lon, active_days, night_frac, observation_count}; facilities: [(kind, id, name, lat, lon)] (pre-filtered nearby)."""
    cand = sorted(((haversine_km(src["lat"], src["lon"], f[3], f[4]), f) for f in facilities), key=lambda x: (x[0], str(x[1][1])))
    cand = [(d, f) for d, f in cand if d <= R_MAX]
    base = {"source_id": src["source_id"], "source_lat": round(src["lat"], 5), "source_lon": round(src["lon"], 5), "methodology_version": METHODOLOGY_VERSION,
            "active_days": src["active_days"], "night_frac": round(src["night_frac"], 3), "observation_count": src["observation_count"]}
    if not cand:
        return {**base, "confidence": "UNKNOWN", "weights": {}, "ranked": [], "nearest": None, "facts": ["No documented facility within 5 km."],
                "why": "Insufficient nearby context; no attribution is made.", "modifier": "none"}
    W = {}
    for d, f in cand: W[KIND2CAT[f[0]]] = W.get(KIND2CAT[f[0]], 0.0) + w(d)
    persistent = src["active_days"] >= 20 and src["night_frac"] >= 0.8; single = src["observation_count"] == 1
    mod = 1.2 if persistent else (0.8 if single else 1.0)
    W = {k: v * mod for k, v in W.items()}
    osm_ok = bool(osm) and osm.get("osm_status") == "OK"
    if osm_ok and (osm.get("osm_count_farmland_1000m") or 0) > 0: W["AGRICULTURE"] = w(1.0)
    if osm_ok and (osm.get("osm_count_forest_1000m") or 0) > 0: W["WILDFIRE"] = w(1.0)
    W["OTHER_UNKNOWN"] = w(BG_KM)
    P = pct(W); ranked = sorted(P.items(), key=lambda kv: (-kv[1], kv[0]))
    top = ranked[0][0]; near = cand[0]
    near_by = {}
    for d, f in cand: near_by.setdefault(KIND2CAT[f[0]], (d, f))
    other_fac_2km = [c for c, (d, _) in near_by.items() if c != KIND2CAT[near[1][0]] and d <= 2.0]
    medium = (top in near_by and near_by[top][0] <= 0.5 and not other_fac_2km and persistent and osm_ok and (osm.get(OSM_TAG[top]) or 0) > 0)
    facts = [f"Nearest {KIND2CAT[f[0]].replace('_', ' ').lower()} facility ({f[2]}): {d:.2f} km" for c, (d, f) in sorted(near_by.items(), key=lambda kv: kv[1][0])]
    facts += [f"Persistent source: {'YES' if src['active_days'] >= 20 else 'NO'}", f"Active days: {src['active_days']}", f"Detections: {src['observation_count']}",
              f"Night detections: {round(src['night_frac'] * 100)}%"]
    if not osm_ok: facts.append("Land-use context (OSM/WorldCover): not available for this location")
    why = (f"Heuristic: {top.replace('_', ' ').title()} receives the highest weight because " +
           (f"the nearest documented facility of that type is {near_by[top][0]:.2f} km away; distance is the strongest signal." if top in near_by else
            "no facility is close enough to outweigh the background.") +
           (" Sustained night-time activity modestly raises facility weights." if persistent else " A single detection modestly lowers facility weights." if single else ""))
    return {**base, "confidence": "MEDIUM" if medium else "LOW", "weights": P, "ranked": ranked, "facts": facts, "why": why,
            "modifier": "persistent x1.2" if persistent else ("single x0.8" if single else "none"),
            "nearest": {"name": near[1][2], "type": KIND2CAT[near[1][0]], "id": str(near[1][1]), "distance_km": round(near[0], 3)}}
