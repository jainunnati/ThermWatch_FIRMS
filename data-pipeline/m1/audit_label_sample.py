"""Independent audit of a label-sample draw. Recomputes strata, populations and inclusion probabilities from the
registry, re-runs the sampler from the recorded seed, and checks sampler inputs. Exit 1 on failure.

  python3 m1/audit_label_sample.py --registry REG --exclude EXCL --draw-dir DIR
"""
import argparse, csv, gzip, json, re, subprocess, sys, tempfile
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_label_candidates import tier, cell   # noqa: E402  (same stratum definitions)

HERE = Path(__file__).resolve().parent

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--registry", required=True); ap.add_argument("--exclude", required=True)
    ap.add_argument("--draw-dir", required=True); a = ap.parse_args(); D = Path(a.draw_dir)
    draw = list(csv.DictReader(open(D / "PRIVATE_label_sample_draw.csv"))); man = json.loads((D / "label_sample_manifest.json").read_text())
    excl = set(Path(a.exclude).read_text().split()); chk = []
    def ck(n, ok, d=""): chk.append({"check": n, "ok": bool(ok), "detail": d})
    ids = [r["source_id"] for r in draw]
    ck("unique source_ids", len(ids) == len(set(ids)), f"{len(ids)} rows / {len(set(ids))} unique")
    ck("no overlap with the 185 pilot sources (original + linked ids)", not (set(ids) & excl), f"overlap={len(set(ids) & excl)}; exclude list={len(excl)}")
    want = set(ids); found = {}; pop = Counter()
    with gzip.open(a.registry, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["source_id"] in excl: continue
            s = (tier(r), cell(r)); pop[s] += 1
            if r["source_id"] in want: found[r["source_id"]] = (s, r["registry_id"])
    ck("all drawn ids exist in registry with matching registry_id",
       len(found) == len(ids) and all(found[r["source_id"]][1] == r["registry_id"] for r in draw))
    ck("recorded strata == recomputed strata", all(found[r["source_id"]][0] == (r["stratum_tier"], r["stratum_cell"]) for r in draw))
    ck("recorded stratum_population == recomputed", all(int(r["stratum_population"]) == pop[(r["stratum_tier"], r["stratum_cell"])] for r in draw))
    drawn = Counter((r["stratum_tier"], r["stratum_cell"]) for r in draw)
    ck("inclusion_prob == drawn/population per stratum",
       all(abs(float(r["inclusion_prob"]) - drawn[(r["stratum_tier"], r["stratum_cell"])] / pop[(r["stratum_tier"], r["stratum_cell"])]) < 1e-7 for r in draw))
    by_tier = Counter(r["stratum_tier"] for r in draw)
    ck("tier counts == requested allocation (or full stratum when smaller)",
       all(by_tier[t] == min(n, sum(v for (tt, _), v in pop.items() if tt == t)) for t, n in man["per_tier"].items()), dict(by_tier))
    with tempfile.TemporaryDirectory() as tmp:
        per = ",".join(f"{k}={v}" for k, v in man["per_tier"].items())
        subprocess.run([sys.executable, str(HERE / "sample_label_candidates.py"), "--registry", a.registry, "--exclude", a.exclude,
                        "--out", tmp, "--seed", man["seed"], "--per-tier", per], check=True, capture_output=True)
        ck("byte-identical re-draw from recorded seed", (Path(tmp) / "PRIVATE_label_sample_draw.csv").read_bytes() ==
           (D / "PRIVATE_label_sample_draw.csv").read_bytes(), man["seed"])
    src = (HERE / "sample_label_candidates.py").read_text()
    import ast
    doc = ast.get_docstring(ast.parse(src), clean=False) or ""
    code = "\n".join(l.split("#")[0] for l in src.replace(doc, "").splitlines())   # drop module docstring + comments
    scan = code.replace("PRIVATE_label_sample_draw.csv", "").replace("label_sample_manifest.json", "").replace(
        "thermwatch-label-sample-v1", "")                     # the tool's own output names / default seed
    forbidden = [w for w in ("candidate_group", "candidate_subgroup", "candidate_reason", "sampling_weight", "crosswalk",
                             "annotation_key", "label", "adjudicat", "AI_ASSISTED", "status") if re.search(w, scan, re.I)]
    ck("sampler code reads no labels/crosswalk/candidate metadata (registry + exclude list only)", not forbidden, f"hits={forbidden}")
    reg_cols = set(re.findall(r'\br\[["\'](\w+)["\']\]', code)) - {"stratum_tier", "stratum_cell"}   # r[...] = registry row; stratum_* are outputs
    ck("registry columns used for strata are label-free", reg_cols <= {"source_id", "registry_id", "n_events", "first_seen_utc",
                                                                         "last_seen_utc", "centroid_lat", "centroid_lon"}, sorted(reg_cols))
    rep = {"n_drawn": len(draw), "tier_counts": dict(by_tier), "n_strata_drawn": len(drawn), "n_region_cells": len({c for _, c in drawn}),
           "inclusion_prob_range": [min(float(r["inclusion_prob"]) for r in draw), max(float(r["inclusion_prob"]) for r in draw)],
           "frame_population_by_tier": man["frame_population_by_tier"], "checks": chk, "passed": all(c["ok"] for c in chk),
           "note": "The exclude list is derived from the private annotation key solely to EXCLUDE the 185 pilot sources; no "
                   "crosswalk status, label or candidate attribute is used to select or stratify."}
    (D / "label_sample_audit.json").write_text(json.dumps(rep, indent=1) + "\n")
    for c in chk: print(("PASS " if c["ok"] else "FAIL ") + c["check"], "" if c["ok"] else c["detail"])
    print(json.dumps({k: rep[k] for k in ("n_drawn", "tier_counts", "n_strata_drawn", "n_region_cells", "inclusion_prob_range")}))
    sys.exit(0 if rep["passed"] else 1)

if __name__ == "__main__":
    main()
