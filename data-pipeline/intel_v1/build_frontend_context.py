"""Frontend context layer for the V7 map UI, built ONLY from real, already-validated ThermWatch artifacts.

  python3 data-pipeline/intel_v1/build_frontend_context.py \
      --contract public/data/thermwatch_historical.json \
      --indexes data-pipeline/intel_v1/live_indexes \
      --out public/data/thermwatch_context.json

Inputs (all real, all already in the repo):
  live_indexes/facilities_index.csv   documented facility registry (COAL / OILGAS / STEEL), 449 rows
  live_indexes/pihs_index.csv         the 220 real pihs-v1 candidates with score / active days / night fraction
  live_indexes/registry_index.csv.gz  all 1,056,161 real sources (id, centroid, n_obs)
  thermwatch_historical.json          v2 contract (map_points = top-3000 sources by Alert Priority)

Output: facilities[] + point_enrichment{source_id: {...}} for the 3,000 ranked map points.
Nothing is estimated: every value is copied from an input row. Missing values stay missing (null).
"""
import argparse, csv, gzip, json
from pathlib import Path

KIND = {"COAL": "Thermal Power", "OILGAS": "LNG / Gas", "STEEL": "Iron & Steel"}
KIND_SRC = {"COAL": "Global Energy Monitor coal plant tracker (registry point)",
            "OILGAS": "Global Energy Monitor oil & gas tracker (registry point)",
            "STEEL": "Global Energy Monitor steel plant tracker (registry point)"}


def main(contract, indexes, out):
    c = json.loads(Path(contract).read_text())
    idx = Path(indexes)
    pts = {p["source_id"] for p in c["map_points"]}
    fac = []
    for r in csv.DictReader(open(idx / "facilities_index.csv")):
        fac.append({"id": r["site_id"], "name": r["name"], "kind": r["kind"], "type": KIND.get(r["kind"], "Other Industrial"),
                    "latitude": float(r["lat"]), "longitude": float(r["lon"]),
                    "provenance": {"point": KIND_SRC.get(r["kind"], "Facility registry point"), "polygon": None,
                                   "source": "data-pipeline/intel_v1/live_indexes/facilities_index.csv"}})
    pihs = {r["source_id"]: {"pihs_score": int(r["pihs_score"]), "active_days": int(r["active_days"]), "night_frac": float(r["night_frac"])}
            for r in csv.DictReader(open(idx / "pihs_index.csv"))}
    enr = {}
    n_reg = 0
    with gzip.open(idx / "registry_index.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f):
            n_reg += 1
            if r["source_id"] in pts:
                enr[r["source_id"]] = {"n_obs": int(r["n_obs"]), "registry_lat": float(r["lat"]), "registry_lon": float(r["lon"])}
    for sid in pts:
        e = enr.setdefault(sid, {"n_obs": None})
        e.update(pihs.get(sid, {}))
    body = {"context_version": "thermwatch-context-v1", "contract_run_id": c["pipeline_run_id"], "data_window": c["data_window"],
            "registry_sources": n_reg, "pihs_index_rows": len(pihs), "map_points": len(pts),
            "facilities": fac, "point_enrichment": dict(sorted(enr.items())),
            "note": "Values copied from real ThermWatch indexes. n_obs = deduplicated FIRMS observations associated to the source in the source registry. "
                    "pihs_* only present for real pihs-v1 candidates. Facility points are registry context, not ground truth or attribution."}
    Path(out).write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"facilities={len(fac)} registry={n_reg} enriched={sum(1 for v in enr.values() if v.get('n_obs') is not None)}/{len(pts)} pihs_in_points={sum(1 for s in pts if s in pihs)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", default="public/data/thermwatch_historical.json")
    ap.add_argument("--indexes", default="data-pipeline/intel_v1/live_indexes")
    ap.add_argument("--out", default="public/data/thermwatch_context.json")
    a = ap.parse_args(); main(a.contract, a.indexes, a.out)
