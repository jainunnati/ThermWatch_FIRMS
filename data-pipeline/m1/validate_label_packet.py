"""Validate a v1.1 blind packet: blindness, v1.0 compatibility, registry consistency, intake compatibility.
Intake is exercised on SYNTHETIC fills in a temporary directory that is deleted afterwards; no label is kept.

  python3 m1/validate_label_packet.py --packet-dir DIR --frozen-packet V10.csv --registry REG --draw DRAW.csv --ingest INGEST.py
"""
import argparse, csv, gzip, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
for k in ("packet-dir", "frozen-packet", "registry", "draw", "ingest"): ap.add_argument("--" + k, required=True)
a = ap.parse_args(); D = Path(a.packet_dir)
P = D / "blind_annotation_label400.csv"; rows = list(csv.DictReader(open(P))); hdr = list(rows[0])
key = json.load(open(D / "PRIVATE_label400_annotation_key.json"))["records"]; kmap = {k["annotation_id"]: k for k in key}
v10 = next(csv.reader(open(a.frozen_packet))); v10_ids = {r["annotation_id"] for r in csv.DictReader(open(a.frozen_packet))}
draw = list(csv.DictReader(open(a.draw)))
chk = []
def ck(n, ok, d=""): chk.append({"check": n, "ok": bool(ok), "detail": str(d)})
ids = [r["annotation_id"] for r in rows]
ck("1. exactly 400 records", len(rows) == 400, len(rows))
ck("2. unique blind IDs; no collision with v1.0 pilot IDs", len(set(ids)) == 400 and not (set(ids) & v10_ids))
ck("3. records ordered by blind ID", ids == sorted(ids))
ann = [c for c in v10 if c.startswith(("annotator", "adjud"))]
ck("4. annotation/adjudication columns identical to frozen v1.0 (names and order)", [c for c in hdr if c.startswith(("annotator", "adjud"))] == ann)
ck("5. every frozen v1.0 evidence column present", all(c in hdr for c in v10), [c for c in v10 if c not in hdr])
ck("6. no label/annotation value pre-filled", all(r[c] == "" for r in rows for c in ann))
blob = P.read_text() + (D / "blind_annotation_label400.json").read_text()
draw_ids = {d["source_id"] for d in draw}
tokens = {"source/registry IDs": r"\b(SRC|REG)-[0-9a-f]", "pilot candidate IDs": r"CAND-\d", "crosswalk status": r"\b(LINKED|RELINK_REVIEW|UNRESOLVED)\b",
          "strata tiers": r"\b(EPISODIC|RECURRENT|PERSISTENT)\b", "strata cells": r"[+-]\d{2}_[+-]\d{3}", "sampling fields": r"inclusion_prob|stratum|order_hash|thermwatch-label-sample",
          "AI-assisted layer": r"AI_ASSIST|pattern_hypothesis|NO_INDEPENDENT_EVIDENCE|rule_applied", "model outputs": r"predict|probability|score"}
hits = {n: re.findall(p, blob)[:3] for n, p in tokens.items() if re.search(p, blob)}
ck("7. no hidden metadata (IDs, strata, weights, crosswalk, AI labels, model outputs) in packet", not hits, hits)
ck("8. unrecovered fields empty in every record", all(r[c] == "" for r in rows for c in ("xsat_pair_frac", "neigh_750m", "neigh_2km"))
   and all(r["unrecovered_fields"] == "xsat_pair_frac;neigh_750m;neigh_2km" for r in rows))
ck("9. private key covers exactly the 400 drawn sources", {k["source_id"] for k in key} == draw_ids and set(kmap) == set(ids))
reg = {}
with gzip.open(a.registry, "rt", newline="") as f:
    for r in csv.DictReader(f):
        if r["source_id"] in draw_ids: reg[r["source_id"]] = r
bad = []
for r in rows:
    g = reg[kmap[r["annotation_id"]]["source_id"]]; n = int(r["observation_count"])
    if not (n == int(g["n_obs"]) == int(r["n_obs_N20"]) + int(r["n_obs_SNPP"]) + int(r["n_obs_N21"]) == int(r["n_obs_sp"]) + int(r["n_obs_nrt"])
            and int(r["n_events"]) == int(g["n_events"]) and r["first_seen_utc"] == g["first_seen_utc"] and r["last_seen_utc"] == g["last_seen_utc"]
            and int(r["n_obs_sp"]) == int(g["n_obs_sp"]) and r["grade_composition"] == g["grade_composition"]
            and 1 <= int(r["active_days"]) <= n and 0 <= float(r["night_frac"]) <= 1 and float(r["spatial_extent_m"]) >= 0):
        bad.append(r["annotation_id"])
ck("10. evidence consistent with Step D registry (counts, dates, grades, ranges)", not bad, bad[:3])
tmp = Path(tempfile.mkdtemp(prefix="pkt_intake_"))
try:
    def fill(i, extra=None):
        out = []
        for r in rows:
            r = dict(r); p = f"annotator{i}_"
            r.update({p + "id": f"synthetic-test-{i}", p + "label": "UNSURE", p + "industrial_context": "UNKNOWN_INSUFFICIENT",
                      p + "timestamp_utc": "2000-01-01T00:00:00Z"}); out.append(r)
        if extra: extra(out)
        with open(tmp / f"a{i}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=hdr, lineterminator="\n"); w.writeheader(); w.writerows(out)
    run = lambda adj=None: subprocess.run([sys.executable, a.ingest, "--packet", str(P), "--a1", str(tmp / "a1.csv"), "--a2", str(tmp / "a2.csv"),
                                           "--out", str(tmp / "o")] + (["--adj", str(adj)] if adj else []), capture_output=True, text=True)
    fill(1); fill(2); p1 = run(); p2 = run(tmp / "o" / "adjudication_sheet.csv")
    st = json.loads((tmp / "o" / "intake_report.json").read_text())
    fill(1, lambda o: o[0].update(frp_max="999")); p3 = run()
    ck("11. frozen intake tool accepts the v1.1 packet end-to-end (synthetic fills, temp only)",
       p1.returncode == 0 and p2.returncode == 0 and st.get("status") == "FINAL_LABELS_WRITTEN", st.get("status"))
    ck("12. intake still rejects edited evidence on the v1.1 packet", p3.returncode == 1)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
ck("13. synthetic intake files deleted", not tmp.exists())
rep = {"packet": str(P), "n_records": len(rows), "n_columns": len(hdr), "new_columns_vs_v1.0": [c for c in hdr if c not in v10],
       "checks": chk, "passed": all(c["ok"] for c in chk)}
(D / "label400_packet_validation.json").write_text(json.dumps(rep, indent=1) + "\n")
for c in chk: print(("PASS " if c["ok"] else "FAIL ") + c["check"], "" if c["ok"] else c["detail"])
print("new columns:", rep["new_columns_vs_v1.0"])
sys.exit(0 if rep["passed"] else 1)
