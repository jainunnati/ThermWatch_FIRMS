"""ThermWatch M1 source-level context feature table (Track A). No labels, no ML.

  plan   : list OSM tiles / WorldCover tiles needed for the selected sources (+ URLs). No network.
  fetch  : fetch missing OSM tiles (rate-limited, cached) and WorldCover tiles (requires network).
  build  : registry-native features + OSM + WorldCover -> feature CSV + schema + manifest (offline, cache-only).

Source selection: --sources FILE (one source_id per line) or --sample N (deterministic: lowest sha256(source_id)).
source_id is copied verbatim from the Step D registry; nothing in Step C/D is modified.
"""
import argparse, csv, gzip, hashlib, json, math, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thermwatch_core import context_osm as osm          # noqa: E402
from thermwatch_core import context_worldcover as wc    # noqa: E402

SCHEMA_VERSION = "m1-context-features-v1"
REGISTRY_COLS = ["source_id", "registry_id", "centroid_lat", "centroid_lon", "bbox_lat_min", "bbox_lat_max", "bbox_lon_min",
                 "bbox_lon_max", "first_seen_utc", "last_seen_utc", "n_obs", "n_events", "grade_composition", "n_obs_sp", "n_obs_nrt"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def select_sources(registry, ids=None, sample=None):
    rows = []
    with gzip.open(registry, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if ids is not None:
                if r["source_id"] in ids: rows.append({k: r[k] for k in REGISTRY_COLS})
            else:
                rows.append(({k: r[k] for k in REGISTRY_COLS}, hashlib.sha256(r["source_id"].encode()).hexdigest()))
                if len(rows) > 4 * sample: rows = sorted(rows, key=lambda x: x[1])[:sample]
    if ids is None: rows = [r for r, _ in sorted(rows, key=lambda x: x[1])[:sample]]
    if ids is not None and len(rows) != len(ids):
        missing = sorted(set(ids) - {r["source_id"] for r in rows})
        raise SystemExit(f"{len(missing)} source_ids not in registry, e.g. {missing[:3]}")
    return sorted(rows, key=lambda r: r["source_id"])


def registry_features(r):
    la, lo = float(r["centroid_lat"]), float(r["centroid_lon"])
    f0 = datetime.fromisoformat(r["first_seen_utc"]); f1 = datetime.fromisoformat(r["last_seen_utc"])
    dy = (float(r["bbox_lat_max"]) - float(r["bbox_lat_min"])) * 111_320
    dx = (float(r["bbox_lon_max"]) - float(r["bbox_lon_min"])) * 111_320 * math.cos(math.radians(la))
    n, ne = int(r["n_obs"]), int(r["n_events"])
    return {"source_id": r["source_id"], "registry_id": r["registry_id"], "centroid_lat": la, "centroid_lon": lo,
            "first_seen_utc": r["first_seen_utc"], "last_seen_utc": r["last_seen_utc"],
            "reg_span_days": round((f1 - f0).total_seconds() / 86400, 3), "reg_n_obs": n, "reg_n_events": ne,
            "reg_obs_per_event": round(n / ne, 4) if ne else None, "reg_bbox_diag_m": round(math.hypot(dx, dy), 1),
            "reg_grade_composition": r["grade_composition"], "reg_n_obs_sp": int(r["n_obs_sp"]), "reg_n_obs_nrt": int(r["n_obs_nrt"])}


def schema():
    cols = {}
    def add(name, dtype, source, null, leak):
        cols[name] = {"dtype": dtype, "source": source, "null_means": null, "leakage_class": leak}
    add("source_id", "str", "Step D registry", "never null", "IDENTIFIER (never a feature)")
    add("registry_id", "str", "Step D registry", "never null", "IDENTIFIER (never a feature)")
    add("centroid_lat", "float", "Step D registry", "never null", "SPATIAL_KEY (use only via grouped split; not a raw feature)")
    add("centroid_lon", "float", "Step D registry", "never null", "SPATIAL_KEY (use only via grouped split; not a raw feature)")
    for c in ("first_seen_utc", "last_seen_utc"):
        add(c, "iso8601", "Step D registry", "never null", "FULL_WINDOW (not prediction-time safe)")
    for c, d in (("reg_span_days", "float"), ("reg_n_obs", "int"), ("reg_n_events", "int"), ("reg_obs_per_event", "float"),
                 ("reg_bbox_diag_m", "float"), ("reg_n_obs_sp", "int"), ("reg_n_obs_nrt", "int")):
        add(c, d, "derived from Step D registry", "never null", "FULL_WINDOW aggregate: needs an as-of variant before ML")
    add("reg_grade_composition", "str", "Step D registry", "never null", "PROVENANCE (data grade, not a feature)")
    for k in osm.point_features(0.0, 0.0, osm.OSMCache(Path("/nonexistent"))):
        d = "int" if "_count_" in k else "float" if k.endswith("_m") else "str"
        add(k, d, f"OpenStreetMap via Overpass ({osm.QUERY_VERSION})",
            "osm_status!=OK -> not fetched (UNKNOWN, not zero); nearest_*_m null with status OK -> none within 5 km",
            "STATIC_CONTEXT (OSM snapshot; record osm_base_timestamp; context, never a label)")
    for k in wc.point_features(0.0, 0.0, "/nonexistent"):
        d = "float" if k.startswith("wc_frac") or k.endswith("_frac_500m") else "int" if k in ("wc_class_at_point", "wc_n_pixels_500m") else "str"
        add(k, d, wc.PRODUCT, "wc_status!=OK -> tile not fetched / partial (UNKNOWN); class null -> nodata pixel",
            "STATIC_CONTEXT (2021 land cover vs 2026 detections; context, never a label)")
    return {"schema_version": SCHEMA_VERSION, "grain": "SOURCE", "columns": cols, "column_order": list(cols),
            "rules": ["No column is a label.", "Missing context is UNKNOWN, never negative.",
                      "FULL_WINDOW columns must be replaced by as-of variants before training.",
                      "Join key: source_id (unchanged from Step D registry)."]}


def cmd_plan(rows, out):
    otiles, wtiles = set(), set()
    for r in rows:
        la, lo = float(r["centroid_lat"]), float(r["centroid_lon"])
        otiles.update(osm.tiles_needed(la, lo))
        wtiles.add(wc.tile_name(la, lo))
    plan = {"n_sources": len(rows), "osm_tiles": sorted(otiles), "n_osm_tiles": len(otiles),
            "osm_min_interval_s": 2.0, "worldcover_tiles": [{"tile": t, "url": wc.tile_url(t)} for t in sorted(wtiles)],
            "n_worldcover_tiles": len(wtiles)}
    (out / "fetch_plan.json").write_text(json.dumps(plan, indent=1) + "\n")
    print(f"plan: {len(rows)} sources -> {len(otiles)} OSM tiles, {len(wtiles)} WorldCover tiles")


def cmd_fetch(rows, out, osm_cache, wc_cache, endpoint, max_calls, only=None):
    plan = json.loads((out / "fetch_plan.json").read_text())
    res = {"skipped": "only=worldcover"} if only == "worldcover" else \
        osm.fetch_tiles(plan["osm_tiles"], osm.OSMCache(osm_cache), osm.requests_transport(), endpoint, max_calls=max_calls)
    import requests
    wres = {}
    for t in ([] if only == "osm" else plan["worldcover_tiles"]):
        p = wc.tile_path(wc_cache, t["tile"])
        if p.exists(): wres[t["tile"]] = "cached"; continue
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(t["url"], stream=True, timeout=600) as r:
                r.raise_for_status(); tmp = p.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for ch in r.iter_content(1 << 20): f.write(ch)
                tmp.replace(p)
            wres[t["tile"]] = "fetched"
        except Exception as ex:  # noqa: BLE001
            wres[t["tile"]] = f"FAILED {type(ex).__name__}: {ex}"
    name = f"fetch_result_{only or 'all'}.json"
    (out / name).write_text(json.dumps({"osm": res, "worldcover": wres}, indent=1) + "\n")
    print(json.dumps({"osm_fetched": len(res.get("fetched", [])), "osm_failed": len(res.get("failed", {})),
                      "worldcover": wres}))


def cmd_build(rows, out, osm_cache, wc_cache, registry):
    cache = osm.OSMCache(osm_cache); feats = []
    for r in rows:
        f = registry_features(r)
        f.update(osm.point_features(f["centroid_lat"], f["centroid_lon"], cache))
        f.update(wc.point_features(f["centroid_lat"], f["centroid_lon"], wc_cache))
        feats.append(f)
    sch = schema(); cols = list(sch["columns"])
    assert all(set(f) == set(cols) for f in feats), "feature/schema column drift"
    with open(out / "source_context_features.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n"); w.writeheader()
        for f in feats: w.writerow({k: ("" if f[k] is None else f[k]) for k in cols})   # schema defines column order
    (out / "source_context_features.schema.json").write_text(json.dumps(sch, indent=1, sort_keys=True) + "\n")
    caches = sorted(Path(osm_cache).glob("osm_*.json")) + sorted(Path(wc_cache).glob("*.tif"))
    used_o = {t for f in feats for t in (f["osm_tiles"] or "").split(";") if t}
    used_w = {t for f in feats for t in (f["wc_tiles"] or "").split(";") if t}
    man = {"schema_version": SCHEMA_VERSION, "n_sources": len(feats),
           "inputs": {"registry_sha256": sha(registry)},
           "context_cache_files_sha256": {p.name: sha(p) for p in caches
                                          if any(t in p.name for t in used_o | used_w)},
           "osm_status_counts": _count(feats, "osm_status"), "wc_status_counts": _count(feats, "wc_status"),
           "output_sha256": {"source_context_features.csv": sha(out / "source_context_features.csv"),
                             "source_context_features.schema.json": sha(out / "source_context_features.schema.json")}}
    (out / "feature_manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: man[k] for k in ("n_sources", "osm_status_counts", "wc_status_counts")}))


def _count(rows, k):
    c = {}
    for r in rows: c[r[k]] = c.get(r[k], 0) + 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["plan", "fetch", "build"])
    ap.add_argument("--registry", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--sources"); ap.add_argument("--sample", type=int)
    ap.add_argument("--osm-cache", default="context_cache/osm"); ap.add_argument("--wc-cache", default="context_cache/worldcover")
    ap.add_argument("--overpass", default="https://overpass-api.de/api/interpreter"); ap.add_argument("--max-osm-calls", type=int)
    ap.add_argument("--only", choices=["osm", "worldcover"])
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    ids = set(Path(a.sources).read_text().split()) if a.sources else None
    if ids is None and not a.sample: raise SystemExit("--sources or --sample required")
    rows = select_sources(a.registry, ids, a.sample)
    if a.command == "plan": cmd_plan(rows, out)
    elif a.command == "fetch": cmd_fetch(rows, out, a.osm_cache, a.wc_cache, a.overpass, a.max_osm_calls, a.only)
    else: cmd_build(rows, out, a.osm_cache, a.wc_cache, a.registry)


if __name__ == "__main__":
    main()
