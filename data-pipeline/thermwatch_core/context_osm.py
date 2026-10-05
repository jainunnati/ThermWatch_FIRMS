"""OSM context features (Track A). CONTEXT ONLY - never a label, never a facility attribution decision.

Pipeline: tile plan -> cached, rate-limited Overpass fetch (injectable transport) -> parsed context elements ->
per-point features. Spatial association decisions stay in `facility.py`; this module only describes surroundings.

Design rules
* Fixed tile grid (TILE_DEG) so the number of Overpass calls is bounded by the number of distinct tiles, not points.
* Cache file per (tile, query hash): `osm_<query_hash>_<tile>.json` holding the raw Overpass response plus provenance
  (endpoint, query text, query hash, osm3s timestamp, fetch UTC). Re-runs are offline once cached.
* A point whose tile (or any neighbour tile needed for the largest radius) is not cached gets status MISSING_NOT_FETCHED
  and NULL features - never zero counts. A fetched tile with no matching elements gives real zeros (status OK).
* Distances: haversine to the element's point (node) or Overpass `center` (way/relation). Polygon geometry is NOT
  used, so distances to large sites are distances to their centre - documented limitation.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

TILE_DEG = 0.25
RADII_M = (1000, 5000)
QUERY_VERSION = "osm-context-q1"
# category -> list of (key, value-or-None) OSM tag selectors. Categories are context vocabularies, not classes.
CATEGORIES = {
    "industrial_landuse": [("landuse", "industrial")],
    "works": [("man_made", "works")],
    "power_plant": [("power", "plant"), ("power", "generator")],
    "chimney_or_flare": [("man_made", "chimney"), ("man_made", "flare")],
    "mine_or_quarry": [("landuse", "quarry"), ("industrial", "mine"), ("man_made", "mineshaft")],
    "oil_gas": [("industrial", "refinery"), ("industrial", "oil"), ("man_made", "petroleum_well"),
                ("man_made", "storage_tank"), ("pipeline", "substation")],
    "steel_metal": [("industrial", "steelmaker"), ("industrial", "metal_works"), ("product", "steel")],
    "landfill": [("landuse", "landfill")],
    "residential": [("landuse", "residential")],
    "farmland": [("landuse", "farmland")],
    "forest": [("landuse", "forest"), ("natural", "wood")],
}
FEATURE_STATUS_OK, FEATURE_STATUS_MISSING = "OK", "MISSING_NOT_FETCHED"


def tile_of(lat: float, lon: float) -> str:
    i, j = math.floor(lat / TILE_DEG), math.floor(lon / TILE_DEG)
    return f"{i:+05d}_{j:+05d}"


def tile_bbox(tile: str):
    i, j = (int(x) for x in tile.split("_"))
    return i * TILE_DEG, j * TILE_DEG, (i + 1) * TILE_DEG, (j + 1) * TILE_DEG   # south, west, north, east


def tiles_needed(lat: float, lon: float, radius_m: float = max(RADII_M)) -> list[str]:
    """Tiles that must be cached to compute features up to `radius_m` around the point."""
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    out = set()
    for la in (lat - dlat, lat, lat + dlat):
        for lo in (lon - dlon, lon, lon + dlon):
            out.add(tile_of(la, lo))
    return sorted(out)


def build_query(tile: str, timeout_s: int = 90) -> str:
    s, w, n, e = tile_bbox(tile)
    bb = f"({s:.4f},{w:.4f},{n:.4f},{e:.4f})"
    parts = []
    for selectors in CATEGORIES.values():
        for k, v in selectors:
            f = f'["{k}"="{v}"]' if v else f'["{k}"]'
            parts.append(f"nwr{f}{bb};")
    return f"[out:json][timeout:{timeout_s}];(" + "".join(parts) + ");out center tags;"


def query_hash(q: str) -> str:
    return hashlib.sha256((QUERY_VERSION + "\n" + q).encode()).hexdigest()[:16]


@dataclass
class OSMCache:
    root: Path

    def path(self, tile: str) -> Path:
        return Path(self.root) / f"osm_{query_hash(build_query(tile))}_{tile}.json"

    def has(self, tile: str) -> bool:
        return self.path(tile).exists()

    def load(self, tile: str) -> dict:
        return json.loads(self.path(tile).read_text())

    def store(self, tile: str, response: dict, endpoint: str) -> Path:
        q = build_query(tile)
        rec = {"provenance": {"tile": tile, "endpoint": endpoint, "query_version": QUERY_VERSION, "query": q,
                              "query_hash": query_hash(q),
                              "osm_base_timestamp": (response.get("osm3s") or {}).get("timestamp_osm_base"),
                              "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
               "response": response}
        p = self.path(tile); p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(rec, sort_keys=True)); tmp.replace(p)
        return p


def fetch_tiles(tiles, cache: OSMCache, transport: Callable[[str, str], dict], endpoint: str,
                min_interval_s: float = 2.0, max_calls: Optional[int] = None, sleep=time.sleep, log=print) -> dict:
    """Fetch uncached tiles only, sequentially, at most one call per `min_interval_s`. `transport(endpoint, query)`
    returns parsed JSON or raises. Failures are recorded, never cached, and leave the tile MISSING."""
    done, failed, skipped, calls = [], {}, [], 0
    for t in sorted(set(tiles)):
        if cache.has(t):
            skipped.append(t); continue
        if max_calls is not None and calls >= max_calls:
            failed[t] = "MAX_CALLS_REACHED"; continue
        if calls: sleep(min_interval_s)
        calls += 1
        try:
            resp = transport(endpoint, build_query(t))
            if not isinstance(resp, dict) or "elements" not in resp:
                raise ValueError("response has no 'elements'")
            cache.store(t, resp, endpoint); done.append(t)
        except Exception as ex:  # noqa: BLE001 - recorded, not swallowed
            failed[t] = f"{type(ex).__name__}: {ex}"; log(f"OSM tile {t} failed: {failed[t]}")
    return {"fetched": done, "already_cached": skipped, "failed": failed, "calls": calls}


def requests_transport(timeout_s: int = 120):
    """Real transport (requires network). Kept separate so tests never touch the network."""
    import requests

    def _t(endpoint, query):
        r = requests.post(endpoint, data={"data": query}, timeout=timeout_s,
                          headers={"User-Agent": "ThermWatch-SIH26162-research (context features)"})
        r.raise_for_status()
        return r.json()
    return _t


def _hav_m(a, b, c, d):
    r = math.radians
    x = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 12_742_000 * math.asin(math.sqrt(min(1.0, x)))


def _categories(tags: dict) -> list[str]:
    return [c for c, sel in CATEGORIES.items() if any(tags.get(k) == v if v else k in tags for k, v in sel)]


def parse_elements(response: dict) -> list[dict]:
    out = []
    for e in response.get("elements", []):
        if "lat" in e and "lon" in e: la, lo = e["lat"], e["lon"]
        elif "center" in e: la, lo = e["center"]["lat"], e["center"]["lon"]
        else: continue
        tags = e.get("tags") or {}
        cats = _categories(tags)
        if cats:
            out.append({"osm_ref": f"{e['type']}/{e['id']}", "lat": float(la), "lon": float(lo), "categories": cats,
                        "name": tags.get("name"), "operator": tags.get("operator"),
                        "type_tag": next((f"{k}={tags[k]}" for k in ("industrial", "power", "man_made", "landuse",
                                                                       "product", "natural") if k in tags), None)})
    return out


def point_features(lat: float, lon: float, cache: OSMCache) -> dict:
    need = tiles_needed(lat, lon)
    base = {"osm_status": FEATURE_STATUS_MISSING, "osm_tiles": ";".join(need), "osm_query_version": QUERY_VERSION,
            "osm_base_timestamp": None}
    for c in CATEGORIES:
        base[f"osm_nearest_{c}_m"] = None
        for r in RADII_M: base[f"osm_count_{c}_{r}m"] = None
    base.update(osm_nearest_any_ref=None, osm_nearest_any_type=None, osm_nearest_any_name=None, osm_nearest_any_m=None)
    if not all(cache.has(t) for t in need):
        return base
    elems, seen, stamps = [], set(), set()
    for t in need:
        rec = cache.load(t); stamps.add(rec["provenance"].get("osm_base_timestamp"))
        for el in parse_elements(rec["response"]):
            if el["osm_ref"] not in seen:
                seen.add(el["osm_ref"]); elems.append(el)
    base["osm_status"] = FEATURE_STATUS_OK
    base["osm_base_timestamp"] = ";".join(sorted(s for s in stamps if s)) or None
    dists = [(_hav_m(lat, lon, e["lat"], e["lon"]), e) for e in elems]
    maxr = max(RADII_M)
    for c in CATEGORIES:
        dc = sorted(d for d, e in dists if c in e["categories"])
        # nearest is only defined within the guaranteed-coverage radius; beyond it, NULL (unknown), not "far"
        base[f"osm_nearest_{c}_m"] = round(dc[0], 1) if dc and dc[0] <= maxr else None
        for r in RADII_M:
            base[f"osm_count_{c}_{r}m"] = sum(1 for d in dc if d <= r)
    ctx = [(d, e) for d, e in dists if d <= maxr and not set(e["categories"]) <= {"residential", "farmland", "forest"}]
    if ctx:
        d, e = min(ctx, key=lambda x: (x[0], x[1]["osm_ref"]))
        base.update(osm_nearest_any_ref=e["osm_ref"], osm_nearest_any_type=e["type_tag"], osm_nearest_any_name=e["name"],
                    osm_nearest_any_m=round(d, 1))
    return base
