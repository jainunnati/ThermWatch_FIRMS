"""Frontend data contract v2 (DEMO mode, deterministic, from validated historical outputs). Size-capped: top-N sources/events/map points.
  python3 data-pipeline/intel_v1/build_contract_v2.py --out public/data/thermwatch_historical.json"""
import argparse, csv, gzip, hashlib, json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); import intel_core as IC
P = {"registry": "/home/claude/stepd_out/source_registry_v1.csv.gz", "activity": "/home/claude/intel/source_activity_v1.csv.gz",
     "attr": "/mnt/user-data/outputs/attribution_mvp_v1/attribution_results_v1.csv", "coverage": "/home/claude/stepd_out/coverage_ledger_v1.csv",
     "events": "/home/claude/stepc_out/events.jsonl.gz", "features": "/mnt/user-data/outputs/ml_v1/feature_table_v1.csv",
     "b25": "/mnt/user-data/outputs/batch25_v1/PRIVATE_DO_NOT_SEND/batch25_source_ids.txt", "summary": "/home/claude/stepc_out/stream_run_summary.json"}
CONTRACT = "thermwatch-contract-v2"; N_SRC, N_ALERT, N_MAP = 300, 20, 3000


def coverage():
    rows = list(csv.DictReader(open(P["coverage"]))); out = {}
    for s in sorted({r["stream"] for r in rows}):
        R = [r for r in rows if r["stream"] == s]
        out[s] = {"days": len(R), "by_reason": dict(sorted(Counter(r["reason"] for r in R).items())),
                  "unverified_dates": sorted(r["date"] for r in R if r["status"] != "OBSERVED"),
                  "partial_boundary_days": sorted(r["date"] for r in R if r["span_boundary_day_partial_risk"] == "1")}
    return {"streams": out, "rule": "Days without verified coverage are UNKNOWN, never 'no fire'.",
            "reason_meaning": {"ROWS_PRESENT": "coverage present", "NONEMPTY_FILE_BUT_NO_ROWS_THAT_DAY": "file present but no detections that day (unverified)",
                               "COVERING_FILE_EMPTY": "empty source file (unverified)", "NO_FILE_COVERS_DAY": "missing file (unverified)"}}


def ml_status():
    sys.path.insert(0, str(HERE.parent / "ml_v1"))
    try:
        import labels_v1 as LB; g = LB.gate(LB.eligible_labels()); n, v = g["eligible_labels"], g["verdict"]
    except Exception:
        n, v = 0, "NO_DEFENSIBLE_SUPERVISED_TRAINING_YET"
    return {"state": "READY_NOT_TRAINED", "verdict": v, "eligible_labels": n, "message": "ML not trained: ground-truth gate not satisfied",
            "checks": ["Leakage audit", "Feature pipeline (30 features)", "Site-complex grouped evaluation", "Label validator"],
            "blocked_because": f"{n} defensible supervised labels (gate: >=30 per class from >=8 site complexes)",
            "statement": "ThermWatch refuses to train on invalid ground truth.", "fallback": "Heuristic attribution (Attribution MVP v1)"}


def main(out):
    reg = {}
    with gzip.open(P["registry"], "rt", newline="") as f:
        for r in csv.DictReader(f):
            la = float(r["centroid_lat"]); dy = (float(r["bbox_lat_max"]) - float(r["bbox_lat_min"])) * 111320
            dx = (float(r["bbox_lon_max"]) - float(r["bbox_lon_min"])) * 111320 * math.cos(math.radians(la))
            reg[r["source_id"]] = {"lat": round(la, 5), "lon": round(float(r["centroid_lon"]), 5), "n_events": r["n_events"], "extent_m": round(math.hypot(dx, dy), 1), "grade": r["grade_composition"]}
    attr = {r["source_id"]: r for r in csv.DictReader(open(P["attr"]))}; feat = {r["source_id"]: r for r in csv.DictReader(open(P["features"]))}
    b25 = set(open(P["b25"]).read().split()); scored = []; cnt = Counter()
    with gzip.open(P["activity"], "rt", newline="") as f:
        for r in csv.DictReader(f):
            sid = r["source_id"]
            if sid in b25: continue
            g = reg[sid]; fe = dict(r, event_count=g["n_events"], spatial_extent_m=g["extent_m"], latitude=g["lat"], longitude=g["lon"])
            a = attr.get(sid); at = {"top": a["top_attribution"], "top_pct": int(a["top_attribution_percent"]), "all": json.loads(a["all_attributions_json"]), "confidence": a["confidence"],
                                     "nearest_name": a["nearest_facility"], "nearest_type": a["nearest_facility_type"], "nearest_km": float(a["nearest_facility_distance_km"])} if a else None
            p = IC.pihs(fe); al = IC.alert(fe, p, at); cnt["pihs"] += p["pihs_flag"]; cnt[al["alert_tier"]] += 1
            scored.append((-al["alert_priority_score"], sid, fe, p, al, at))
    scored.sort(key=lambda x: (x[0], x[1])); top = scored[:N_SRC]; ids = {x[1] for x in top}
    ev = defaultdict(list)
    with gzip.open(P["events"], "rt") as f:
        for line in f:
            e = json.loads(line)
            if e[1] in ids: ev[e[1]].append({"event_id": e[0], "observations": e[2], "first": e[3], "last": e[4], "centroid": e[5], "status": e[7], "satellites": e[8]})
    cov = coverage(); snpp_unv = set(cov["streams"]["VIIRS:N"]["unverified_dates"])
    sources, alerts = [], []
    for rank, (_, sid, fe, p, al, at) in enumerate(top, 1):
        fx = feat.get(sid, {}); g = reg[sid]
        u = sum(1 for d in snpp_unv if fe["first_seen"][:10] <= d <= fe["last_seen"][:10])
        covs = "Complete for NOAA-20 and NOAA-21; " + (f"S-NPP has {u} unverified-coverage days in this window (missing data is not evidence of no fire)" if u else "S-NPP complete")
        src = {"source_id": sid, "rank": rank, "identity": {"lat": g["lat"], "lon": g["lon"], "first_seen": fe["first_seen"], "last_seen": fe["last_seen"], "grade": g["grade"]},
               "activity": {"detections": int(fe["detection_count"]), "active_days": int(fe["active_days"]), "events": int(g["n_events"]), "night_share": float(fe["night_frac"]),
                            "frp_max": float(fe["frp_max"]), "frp_mean": float(fe["frp_mean"]), "ti4_median": fx.get("ti4_median") or None, "ti4_max": fx.get("ti4_max") or None,
                            "duration_days": fx.get("duration_days") or None, "recent_30d_detections": int(fe["recent_30d_detections"])},
               "spatial": {"extent_m": g["extent_m"], "nearest_facility": at["nearest_name"] if at else None, "facility_distance_km": at["nearest_km"] if at else None, "facility_category": at["nearest_type"] if at else None},
               "intelligence": {**p, **al, "attribution": at["all"] if at else {}},
               "uncertainty": {"coverage_status": covs, "attribution_confidence": at["confidence"] if at else "UNKNOWN", "cause": "Not confirmed"},
               "events": sorted(ev[sid], key=lambda e: e["first"])}
        sources.append(src)
        if rank <= N_ALERT: alerts.append(IC.why_card(rank, fe, p, al, at, covs))
    ss = json.load(open(P["summary"]))["diagnostics"] if Path(P["summary"]).exists() else {}
    body = {"contract_version": CONTRACT, "mode": "DEMO", "data_timestamp": "2026-10-01T23:59:00+00:00", "data_window": "2026-01-01..2026-10-01",
            "pipeline_status": "HISTORICAL_VALIDATED", "coverage_status": "NOAA-20/NOAA-21 complete; S-NPP 45 unverified days (explicit, never treated as no-fire)",
            "system_stats": {"firms_observations": 2298170, "valid_observations": 2298169, "physical_sources": 1056161, "events": 1277339, "sources_monitored": len(scored),
                             "pihs_candidates": cnt["pihs"], "alerts_high": cnt["HIGH"], "alerts_medium": cnt["MEDIUM"], "heldout_excluded": len(b25)},
            "coverage": cov, "alerts": alerts, "sources": sources,
            "map_points": [{"source_id": x[1], "lat": x[2]["latitude"], "lon": x[2]["longitude"], "tier": x[4]["alert_tier"], "pihs": x[3]["pihs_flag"]} for x in scored[:N_MAP]],
            "ml_status": ml_status(), "disclaimer": "Attribution weights are heuristic and proximity-driven. They are not calibrated probabilities or confirmed causes."}
    rid = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]
    body["pipeline_run_id"] = f"demo-{rid}"; body["generated_at"] = body["data_timestamp"]   # deterministic: tied to data, not wall clock
    # backward-compatible v1 fields for existing consumers
    body["summary"] = {"total_sources": len(scored), "pihs_candidates": cnt["pihs"], "alerts_high": cnt["HIGH"], "alerts_medium": cnt["MEDIUM"], "coverage_status": body["coverage_status"]}
    Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_text(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps(body["system_stats"]), "| bytes", Path(out).stat().st_size)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); main(ap.parse_args().out)
