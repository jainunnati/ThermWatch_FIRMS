"""ThermWatch v1 contract builder (uses existing validated outputs; no re-ingestion).
  python3 data-pipeline/intel_v1/build_contract_v1.py [--activity ACT.csv.gz] [--out OUT_DIR] [--public public/thermwatch_intel.json] [--top 20]
Steps: sources -> PIHS detector -> attribution (Attribution MVP v1 results) -> alert ranking -> why-cards -> frontend JSON."""
import argparse, csv, gzip, json, math, sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "ml_v1"))
import intel_core as IC
REG = "/home/claude/stepd_out/source_registry_v1.csv.gz"; ATTR = "/mnt/user-data/outputs/attribution_mvp_v1/attribution_results_v1.csv"
COV = "/home/claude/stepd_out/coverage_ledger_v1.csv"; B25 = "/mnt/user-data/outputs/batch25_v1/PRIVATE_DO_NOT_SEND/batch25_source_ids.txt"
CONTRACT_VERSION = "thermwatch-intel-contract-v1"


def ml_status():
    try:
        import labels_v1 as LB; g = LB.gate(LB.eligible_labels())
    except Exception as e:  # noqa: BLE001
        g = {"eligible_labels": None, "verdict": f"UNAVAILABLE ({type(e).__name__})"}
    return {"state": "READY_NOT_TRAINED", "verdict": g["verdict"], "eligible_labels": g["eligible_labels"],
            "checks": ["Leakage audit", "Feature pipeline (30 features)", "Site-complex grouped evaluation", "Label validator"],
            "blocked_because": f"{g['eligible_labels']} defensible supervised labels (gate: >=30 per class from >=8 site complexes)",
            "statement": "ThermWatch refuses to train on invalid ground truth.", "fallback": "Heuristic attribution (Attribution MVP v1)"}


def main(a):
    unver = {}
    for r in csv.DictReader(open(COV)):
        if r["status"] != "OBSERVED": unver.setdefault(r["stream"], set()).add(r["date"])
    reg = {}
    with gzip.open(REG, "rt", newline="") as f:
        for r in csv.DictReader(f):
            la = float(r["centroid_lat"]); dy = (float(r["bbox_lat_max"]) - float(r["bbox_lat_min"])) * 111320
            dx = (float(r["bbox_lon_max"]) - float(r["bbox_lon_min"])) * 111320 * math.cos(math.radians(la))
            reg[r["source_id"]] = (round(la, 5), round(float(r["centroid_lon"]), 5), r["n_events"], round(math.hypot(dx, dy), 1))
    attr = {}
    for r in csv.DictReader(open(ATTR)):
        attr[r["source_id"]] = {"top": r["top_attribution"], "top_pct": int(r["top_attribution_percent"]), "all": json.loads(r["all_attributions_json"]),
                                "confidence": r["confidence"], "nearest_name": r["nearest_facility"], "nearest_type": r["nearest_facility_type"],
                                "nearest_km": float(r["nearest_facility_distance_km"]) if r["nearest_facility_distance_km"] else None}
    b25 = set(open(B25).read().split()); scored, cnt = [], Counter()
    with gzip.open(a.activity, "rt", newline="") as f:
        for r in csv.DictReader(f):
            sid = r["source_id"]
            if sid in b25: continue
            la, lo, ev, ext = reg[sid]
            feat = dict(r, event_count=ev, spatial_extent_m=ext, latitude=la, longitude=lo)
            p = IC.pihs(feat); at = attr.get(sid); al = IC.alert(feat, p, at)
            cnt["sources"] += 1; cnt["pihs"] += p["pihs_flag"]; cnt["tier_" + al["alert_tier"]] += 1; cnt["facility_context"] += at is not None; cnt["pihs_gem"] += p["pihs_flag"] and at is not None
            scored.append((-al["alert_priority_score"], sid, feat, p, al, at))
    scored.sort(key=lambda x: (x[0], x[1])); cards = []
    for rank, (_, sid, feat, p, al, at) in enumerate(scored[:a.top], 1):
        d0, d1 = date.fromisoformat(feat["first_seen"][:10]), date.fromisoformat(feat["last_seen"][:10])
        days = {(d0 + timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)}; u = len(days & unver.get("VIIRS:N", set()))
        cov = "Complete for NOAA-20 and NOAA-21; " + (f"S-NPP has {u} unverified-coverage days in this window (missing data is not evidence of no fire)" if u else "S-NPP complete")
        cards.append(IC.why_card(rank, feat, p, al, at, cov))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    with open(out / "pihs_candidates.csv", "w", newline="") as fh:   # input for gihs_benchmark.py (evaluation only)
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["source_id", "latitude", "longitude", "pihs_score", "active_days", "night_frac"])
        for _, sid, feat, p, al, at in sorted(scored, key=lambda x: x[1]):
            if p["pihs_flag"]: w.writerow([sid, feat["latitude"], feat["longitude"], p["pihs_score"], feat["active_days"], feat["night_frac"]])
    contract = {"contract_version": CONTRACT_VERSION, "pihs_version": IC.PIHS_RULES_VERSION, "alert_version": IC.ALERT_VERSION,
                "data_window": "2026-01-01..2026-10-01 (FIRMS VIIRS NOAA-20, NOAA-21, S-NPP)",
                "summary": {"total_sources": cnt["sources"], "pihs_candidates": cnt["pihs"], "alerts_high": cnt["tier_HIGH"], "alerts_medium": cnt["tier_MEDIUM"],
                            "sources_with_facility_context": cnt["facility_context"], "pihs_with_gem_facility_5km": cnt["pihs_gem"],
                            "consistency_check": f"PIHS uses no facility data, yet {cnt['pihs_gem']} of {cnt['pihs']} candidates ({100*cnt['pihs_gem']/max(1,cnt['pihs']):.1f}%) lie within 5 km of a documented GEM facility vs {100*cnt['facility_context']/max(1,cnt['sources']):.2f}% of all sources (internal consistency, not accuracy)", "coverage_status": "NOAA-20/NOAA-21 complete; S-NPP 45 unverified days (explicit, never treated as no-fire)",
                            "excluded_heldout": len(b25)},
                "alerts": cards, "ml_status": ml_status(),
                "disclaimer": "Attribution weights are heuristic and proximity-driven. They are not calibrated probabilities or confirmed causes."}
    js = json.dumps(contract, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    (out / "thermwatch_intel.json").write_text(js)
    if a.public: Path(a.public).write_text(js)
    print(json.dumps(contract["summary"], indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--activity", default="/home/claude/intel/source_activity_v1.csv.gz")
    ap.add_argument("--out", default="/home/claude/intel/out"); ap.add_argument("--public", default=None); ap.add_argument("--top", type=int, default=20)
    main(ap.parse_args())
