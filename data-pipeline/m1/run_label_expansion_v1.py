"""Run LABEL_EXPANSION_V1 (no network, no labels).  python3 m1/run_label_expansion_v1.py OUT_DIR"""
import ast, csv, gzip, inspect, json, sys
from collections import Counter, defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, "/home/claude/gem")
import label_expansion_v1 as LX
import register_match as RM
from thermwatch_core import context_osm as osm, context_worldcover as wc
REG = "/home/claude/stepd_out/source_registry_v1.csv.gz"; R72 = "/mnt/user-data/outputs/review72_evidence_v1/review72_evidence_packet.csv"
B25 = "/mnt/user-data/outputs/batch25_v1/PRIVATE_DO_NOT_SEND/batch25_source_ids.txt"
CACHES = ["/tmp/osmz/OSM/pilot87_context_run_kit/data-pipeline/context_cache/osm", "/home/claude/r72/context_cache/osm"]
PROHIBITED = ["active_days", "observation_count", "n_obs", "frp", "ti4", "night_frac", "max_gap_d", "median_gap_d", "n_events", "duration_days",
              "persistence", "prediction", "probability", "hypothesis", "stratum", "inclusion_prob", "candidate_group", "candidate_subgroup",
              "candidate_reason", "priority_group", "selection_reason"]


def main(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    r72 = list(csv.DictReader(open(R72))); r72_ids = {r["source_id"] for r in r72}; b25 = set(open(B25).read().split())
    sites = [s for s in RM.sites() if s["lat"] is not None and 5 <= s["lat"] <= 39 and 66 <= s["lon"] <= 99]
    LX.TrackedRow.accessed = set()
    with gzip.open(REG, "rt", newline="") as f:
        cands, sc = LX.generate((LX.TrackedRow(r) for r in csv.DictReader(f)), sites, b25 | r72_ids)
    accessed = sorted(LX.TrackedRow.accessed)
    cols = list(cands[0])
    with open(out / "label_expansion_candidates_v1.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(cands)
    with open(out / "label_expansion_research_priority_v1.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["evidence_priority", "source_id", "proposed_context_class", "candidate_decision", "site_complex_id", "first_in_site_complex", "registry_reference_url", "competing_facility_count_2km", "distance_km"])
        seen = set()
        for x in cands:
            w.writerow([x["evidence_priority"], x["source_id"], x["proposed_context_class"], x["candidate_decision"], x["site_complex_id"], int(x["site_complex_id"] not in seen),
                        int(x["registry_reference"].startswith("http")), x["competing_facility_count_2km"], x["distance_km"]]); seen.add(x["site_complex_id"])
    led = LX.ledger_rows(cands)
    with open(out / "label_expansion_evidence_ledger_v1.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(led[0]), lineterminator="\n"); w.writeheader(); w.writerows(led)
    # capacity: REVIEW72 (frozen) + expansion REVIEW, by examples and by site complex
    r72_sc = {r["source_id"]: sc[f"{r['gem_facility_type']}:{r['gem_facility_id']}"] for r in r72}
    cap = {}
    for cls in ("STEEL_METAL", "THERMAL_POWER", "LNG_GAS"):
        a = [r for r in r72 if r["candidate_class"] == cls]; b = [x for x in cands if x["candidate_decision"] == "REVIEW" and x["proposed_context_class"] == cls]
        sa = {r72_sc[r["source_id"]] for r in a}; sb = {x["site_complex_id"] for x in b}
        cap[cls] = {"review72_candidates": len(a), "review72_site_complexes": len(sa), "expansion_review_candidates": len(b),
                    "expansion_new_site_complexes": len(sb - sa), "total_candidates": len(a) + len(b), "total_site_complexes": len(sa | sb),
                    "additional_candidates_needed_for_30": max(0, 30 - len(a)), "additional_site_complexes_needed_for_8": max(0, 8 - len(sa)),
                    "candidate_capacity_reaches_30": len(a) + len(b) >= 30, "site_capacity_reaches_8": len(sa | sb) >= 8}
    unk = Counter(x["rejection_reason"].split(":")[1].strip() if ":" in x["rejection_reason"] else "" for x in cands if x["candidate_decision"] == "UNKNOWN")
    # context worklist (REVIEW72 + expansion REVIEW)
    tiles_o, tiles_w = defaultdict(set), defaultdict(set)
    pts = [(r["source_id"], float(r["source_lat"]), float(r["source_lon"])) for r in r72] + [(x["source_id"], x["source_lat"], x["source_lon"]) for x in cands if x["candidate_decision"] == "REVIEW"]
    for sid, la, lo in pts:
        for t in osm.tiles_needed(la, lo): tiles_o[t].add(sid)
        tiles_w[wc.tile_name(la, lo)].add(sid)
    cached = lambda t: any(osm.OSMCache(c).has(t) for c in CACHES)
    work = {"scope": "REVIEW72 + LABEL_EXPANSION_V1 REVIEW candidates", "not_executed": "network fetch deferred to a network-enabled machine",
            "osm": {"n_tiles": len(tiles_o), "n_cached": sum(cached(t) for t in tiles_o), "tiles": [{"tile": t, "cached": cached(t), "n_sources": len(tiles_o[t]), "source_ids": sorted(tiles_o[t])} for t in sorted(tiles_o)]},
            "worldcover": {"n_tiles": len(tiles_w), "n_cached": 0, "tiles": [{"tile": t, "url": wc.tile_url(t), "n_sources": len(tiles_w[t]), "source_ids": sorted(tiles_w[t])} for t in sorted(tiles_w)]}}
    (out / "label_expansion_context_worklist.json").write_text(json.dumps(work, indent=1) + "\n")
    # leakage audit: runtime field access + static scan of the generator's code
    src = inspect.getsource(LX); doc = ast.get_docstring(ast.parse(src)) or ""
    code = "\n".join(l.split("#")[0] for l in src.replace(doc, "").splitlines()).lower()
    fields = []
    for p in PROHIBITED:
        rt = p in accessed; st = p.lower() in code
        fields.append({"field": p, "accessed_at_runtime": rt, "referenced_in_generator_code": st, "ok": not (rt or st)})
    audit = {"generator_module": "m1/label_expansion_v1.py", "registry_fields_accessed_at_runtime": accessed,
             "allowed_registry_fields": sorted(LX.REG_FIELDS_ALLOWED), "only_allowed_fields_read": set(accessed) <= LX.REG_FIELDS_ALLOWED,
             "prohibited_fields": fields, "verdict": "PASS" if set(accessed) <= LX.REG_FIELDS_ALLOWED and all(f["ok"] for f in fields) else "FAIL",
             "other_inputs": ["GEM tracker sites (register_match.sites)", "REVIEW72 packet (source_id, coordinates, facility ids - for exclusion and complex mapping)", "Batch-25 id list (exclusion only)"]}
    (out / "label_expansion_leakage_audit.json").write_text(json.dumps(audit, indent=1) + "\n")
    summ = {"expansion_candidates": len(cands), "decisions": dict(Counter(x["candidate_decision"] for x in cands)),
            "review_by_class": dict(Counter(x["proposed_context_class"] for x in cands if x["candidate_decision"] == "REVIEW")),
            "unknown_conflicts": dict(unk), "capacity": cap, "context": {"osm_tiles": len(tiles_o), "osm_cached": work["osm"]["n_cached"], "worldcover_tiles": len(tiles_w)},
            "leakage_audit": audit["verdict"], "accepted": 0}
    (out / "label_expansion_summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "label_expansion_out")
