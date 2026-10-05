"""Regression check: make_label_packet.evidence() must reproduce the frozen pilot packet values for the 87 LINKED
pilot sources (restricted to the pilot scope: SP NOAA-20 + S-NPP). Exit 1 on any mismatch.

  python3 m1/verify_recovered_definitions.py --members MEMBERS_JSON --key PRIVATE_annotation_key.json --pilot-csv PILOT.csv
"""
import argparse, csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_label_packet import evidence   # noqa: E402

TOL = {"duration_days": 0.0015, "max_gap_d": 0.0015, "median_gap_d": 0.0015, "spatial_extent_m": 0.0015,
       "frp_median": 0.006, "frp_max": 0.006, "ti4_median": 0.006, "ti4_max": 0.006, "ti4_sat_frac": 0.0006,
       "night_frac": 0.0006, "conf_high_frac": 0.0006, "span_frac": 0.0006, "modal_month_frac": 0.0006,
       "active_days": 0, "observation_count": 0}
ap = argparse.ArgumentParser()
for k in ("members", "key", "pilot-csv"): ap.add_argument("--" + k, required=True)
a = ap.parse_args()
M = json.load(open(a.members)); C = {r["candidate_id"]: r for r in csv.DictReader(open(a.pilot_csv))}
K = [k for k in json.load(open(a.key))["records"] if k["ml_feature_table_eligible"]]
res = {f: 0 for f in list(TOL) + ["sat_mix", "first_seen", "last_seen"]}
for k in K:
    c = C[k["candidate_id"]]; e = evidence([o for o in M[k["linked_source_id"]] if o["prod"] in ("VIIRS_NOAA20_SP", "VIIRS_SNPP_SP")])
    for f, t in TOL.items():
        res[f] += (e[f] is None and c[f] == "") or (e[f] is not None and c[f] != "" and abs(e[f] - float(c[f])) <= t)
    res["sat_mix"] += e["sat_mix"] == c["sat_mix"]
    res["first_seen"] += e["first"].isoformat(sep=" ") == c["first_seen"]
    res["last_seen"] += e["last"].isoformat(sep=" ") == c["last_seen"]
ok = all(v == len(K) for v in res.values())
print(json.dumps({"n_sources": len(K), "fields_reproduced": {f: f"{v}/{len(K)}" for f, v in res.items()}, "all_exact": ok}, indent=1))
sys.exit(0 if ok else 1)
