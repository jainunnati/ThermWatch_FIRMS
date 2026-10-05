"""ThermWatch ml_v1 - deterministic source-level feature table (prediction-time information only).
  python3 ml_v1/build_features_v1.py --ids IDS.txt --out feature_table_v1.csv
Reads (read-only): Step D registry + membership, raw FIRMS CSVs, LABEL_FACTORY_V1 GEM distance features, OSM context cache.
Every column is declared in MANIFEST; only allowed_for_ml=YES columns are model features (see FEATURES)."""
import argparse, csv, gzip, math, statistics as S, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / "m1"))
from make_label_packet import extract, evidence          # recovered, regression-checked definitions; Step C identity
from thermwatch_core import context_osm as osm

REG = "/home/claude/stepd_out/source_registry_v1.csv.gz"; MEMB = "/home/claude/stepd_out/registry_membership_v1.tsv.gz"
RAW = "/home/claude/w/data_jan_oct_final"; GEMF = "/mnt/user-data/outputs/label_factory_v1/gem_distance_features_v1.csv"
OSM_CACHES = ["/tmp/osmz/OSM/pilot87_context_run_kit/data-pipeline/context_cache/osm"]
FEATURE_VERSION = "ml_v1-features-1"
# name: (group, definition, source, prediction_time_available, allowed, reason_if_excluded, leakage_risk)
MANIFEST = {
 "source_id": ("id", "registry source identifier", "Step D", "YES", "NO", "identifier; hash of anchor key, no predictive meaning; join key only", "LOW (excluded)"),
 "centroid_lat": ("spatial", "source centroid latitude", "Step D", "YES", "NO", "raw location acts as a site/region proxy; used only for grouping", "HIGH if used"),
 "centroid_lon": ("spatial", "source centroid longitude", "Step D", "YES", "NO", "as centroid_lat", "HIGH if used"),
 "first_seen_utc": ("temporal", "first detection time", "Step D", "YES", "NO", "absolute date encodes data period/stream, not source type", "MEDIUM"),
 "last_seen_utc": ("temporal", "last detection time", "Step D", "YES", "NO", "as first_seen_utc", "MEDIUM"),
 "grade_composition": ("provenance", "SP/NRT mix", "Step D", "YES", "NO", "data-processing provenance, not physics", "MEDIUM"),
 "detection_count": ("thermal", "number of member detections", "registry/raw", "YES", "YES", "", "LOW"),
 "active_days": ("thermal", "distinct UTC dates with a detection", "raw", "YES", "YES", "", "LOW"),
 "event_count": ("thermal", "registry events of the source", "Step D", "YES", "YES", "", "LOW"),
 "duration_days": ("thermal", "last - first detection, days", "raw", "YES", "YES", "", "LOW"),
 "detections_per_active_day": ("thermal", "detection_count / active_days", "derived", "YES", "YES", "", "LOW"),
 "max_gap_d": ("thermal", "max gap between consecutive detections (days); empty if 1 detection", "raw", "YES", "YES", "", "LOW"),
 "median_gap_d": ("thermal", "median gap between consecutive detections (days)", "raw", "YES", "YES", "", "LOW"),
 "span_frac": ("thermal", "active_days / (ceil(duration)+1)", "raw", "YES", "YES", "", "LOW"),
 "modal_month_frac": ("thermal", "share of detections in the most frequent month (temporal concentration)", "raw", "YES", "YES", "", "LOW"),
 "frp_mean": ("thermal", "mean FRP (MW)", "raw", "YES", "YES", "", "LOW"),
 "frp_median": ("thermal", "median FRP (MW)", "raw", "YES", "YES", "", "LOW"),
 "frp_max": ("thermal", "max FRP (MW)", "raw", "YES", "YES", "", "LOW"),
 "frp_cv": ("thermal", "FRP coefficient of variation (std/mean); 0 if 1 detection", "raw", "YES", "YES", "", "LOW"),
 "ti4_median": ("thermal", "median bright_ti4 (K)", "raw", "YES", "YES", "", "LOW"),
 "ti4_max": ("thermal", "max bright_ti4 (K)", "raw", "YES", "YES", "", "LOW"),
 "ti4_sat_frac": ("thermal", "share with bright_ti4 >= 367 K", "raw", "YES", "YES", "", "LOW"),
 "night_frac": ("thermal", "share of night detections", "raw", "YES", "YES", "", "LOW"),
 "conf_high_frac": ("thermal", "share with confidence = h", "raw", "YES", "YES", "", "LOW"),
 "spatial_extent_m": ("spatial", "max distance from centroid to a member (m)", "raw", "YES", "YES", "", "LOW"),
 "dist_nearest_steel_km": ("context", "GEM steel site distance (<=5 km, else empty)", "GEM trackers", "YES", "YES", "", "MEDIUM: GEM distances also generated the candidate frame; allowed as FEATURE (never as label); report ablation"),
 "dist_nearest_power_km": ("context", "GEM coal plant distance", "GEM trackers", "YES", "YES", "", "MEDIUM (see above)"),
 "dist_nearest_oilgas_km": ("context", "GEM oil/gas field distance", "GEM trackers", "YES", "YES", "", "MEDIUM (see above)"),
 "dist_nearest_any_km": ("context", "nearest GEM site of any type", "GEM trackers", "YES", "YES", "", "MEDIUM (see above)"),
 "candidate_count_5km": ("context", "GEM sites within 5 km", "GEM trackers", "YES", "YES", "", "MEDIUM (see above)"),
 "candidate_type_count_5km": ("context", "distinct GEM site types within 5 km", "GEM trackers", "YES", "YES", "", "MEDIUM (see above)"),
 "competing_facility_count_2km": ("context", "GEM sites within 2 km minus one", "GEM trackers", "YES", "YES", "", "MEDIUM (see above)"),
 "osm_status": ("context", "OK / MISSING_NOT_FETCHED", "OSM cache", "YES", "NO", "missingness indicator only; coverage is a fetch artefact (pilot87 tiles)", "HIGH (coverage bias)"),
 "osm_count_industrial_landuse_1000m": ("context", "OSM industrial landuse within 1 km (empty if not fetched)", "OSM", "YES", "YES", "", "LOW (empty=unknown)"),
 "osm_count_power_plant_1000m": ("context", "OSM power plants within 1 km", "OSM", "YES", "YES", "", "LOW"),
 "osm_count_farmland_1000m": ("context", "OSM farmland within 1 km", "OSM", "YES", "YES", "", "LOW"),
 "osm_count_forest_1000m": ("context", "OSM forest within 1 km", "OSM", "YES", "YES", "", "LOW"),
 "wc_status": ("context", "WorldCover status", "WorldCover", "YES", "NO", "not downloaded (always MISSING)", "n/a"),
}
FEATURES = [k for k, v in MANIFEST.items() if v[4] == "YES"]
COLUMNS = list(MANIFEST)


def build(ids, out):
    ids = set(ids); reg = {}
    with gzip.open(REG, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["source_id"] in ids: reg[r["source_id"]] = r
    gem = {r["source_id"]: r for r in csv.DictReader(open(GEMF))}
    obs = extract(ids, MEMB, RAW); caches = [osm.OSMCache(c) for c in OSM_CACHES]; rows = []
    for sid in sorted(ids):
        R, o = reg[sid], obs[sid]; e = evidence(o); frp = [x["frp"] for x in o]; g = gem.get(sid, {})
        la, lo = float(R["centroid_lat"]), float(R["centroid_lon"])
        oc = next((c for c in caches if all(c.has(t) for t in osm.tiles_needed(la, lo))), None)
        of = osm.point_features(la, lo, oc) if oc else {"osm_status": osm.FEATURE_STATUS_MISSING}
        n = len(o); mean = sum(frp) / n; sd = (sum((v - mean) ** 2 for v in frp) / n) ** 0.5
        r = {"source_id": sid, "centroid_lat": round(la, 6), "centroid_lon": round(lo, 6), "first_seen_utc": R["first_seen_utc"], "last_seen_utc": R["last_seen_utc"],
             "grade_composition": R["grade_composition"], "detection_count": n, "active_days": e["active_days"], "event_count": int(R["n_events"]),
             "duration_days": round(e["duration_days"], 4), "detections_per_active_day": round(n / e["active_days"], 4),
             "max_gap_d": "" if e["max_gap_d"] is None else round(e["max_gap_d"], 4), "median_gap_d": "" if e["median_gap_d"] is None else round(e["median_gap_d"], 4),
             "span_frac": round(e["span_frac"], 4), "modal_month_frac": round(e["modal_month_frac"], 4), "frp_mean": round(mean, 4), "frp_median": round(e["frp_median"], 4),
             "frp_max": round(e["frp_max"], 4), "frp_cv": round(sd / mean, 4) if mean > 0 else 0.0, "ti4_median": round(e["ti4_median"], 3), "ti4_max": round(e["ti4_max"], 3),
             "ti4_sat_frac": round(e["ti4_sat_frac"], 4), "night_frac": round(e["night_frac"], 4), "conf_high_frac": round(e["conf_high_frac"], 4),
             "spatial_extent_m": round(e["spatial_extent_m"], 2),
             **{k: g.get(k, "") for k in ("dist_nearest_steel_km", "dist_nearest_power_km", "dist_nearest_oilgas_km", "dist_nearest_any_km", "candidate_count_5km",
                                          "candidate_type_count_5km", "competing_facility_count_2km")},
             "osm_status": of["osm_status"], **{k: ("" if of.get(k) is None else of.get(k)) for k in ("osm_count_industrial_landuse_1000m", "osm_count_power_plant_1000m",
                                                                                                         "osm_count_farmland_1000m", "osm_count_forest_1000m")},
             "wc_status": "MISSING_NOT_FETCHED"}
        assert list(r) == COLUMNS, "schema drift"
        rows.append(r)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ids", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
    print(len(build(Path(a.ids).read_text().split(), a.out)), "rows,", len(FEATURES), "ML features")
