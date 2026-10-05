"""Adjudicator review (third person) for the pilot.  Never edits MS/HM rows; never creates labels by agreement.
  build : python3 m1/adjudicate_v1.py build LEDGER_A1A2 OUT_DIR
  import: python3 m1/adjudicate_v1.py import ADJ.json LEDGER_IN LEDGER_OUT
The validator (evidence_research_v1.validate_final_label) remains the only authority on final labels."""
import csv, gzip, html, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_research_v1 as ER
SR = "/mnt/user-data/outputs/simple_review_v1/simple_review_content.json"
PKT = "/mnt/user-data/outputs/evidence_research_v1/pilot10_packet.csv"
REG = "/home/claude/stepd_out/source_registry_v1.csv.gz"
QFLAG = {"MS": "Quality flag: all 10 answers given in 41 seconds total; 9 YES answers contradict the conclusion shown on screen."}
AI_PREFIX = ("AI", "CHATGPT", "CLAUDE", "GPT", "LLM")


def gather(ledger):
    L = list(csv.DictReader(open(ledger))); C = {c["source_id"]: c for c in json.load(open(SR))}
    P = {r["source_id"]: r for r in csv.DictReader(open(PKT))}; times = {}
    with gzip.open(REG, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["source_id"] in P: times[r["source_id"]] = (r["first_seen_utc"], r["last_seen_utc"])
    out = []
    for sid, p in sorted(P.items(), key=lambda x: x[1]["pilot_id"]):
        c = C[sid]; ann = {}
        for role in ("ANNOTATOR_1", "ANNOTATOR_2"):
            r = next(r for r in L if r["source_id"] == sid and r["role"] == role)
            shown = r["evidence_url_or_reference"].replace("shown:", "").split(";") if r["evidence_url_or_reference"] else []
            ann[role] = {"who": r["reviewer_id"], "decision": r["reviewer_status"].replace("DECIDED_", ""), "shown": shown,
                         "flag": QFLAG.get(r["reviewer_id"], "")}
        ev = {e["item"]: e for e in c["evidence"]}
        out.append({"id": c["id"], "source_id": sid, "cls": c["cls"], "proposed_label": p["proposed_label"], "facility": c["facility"], "hs": c["hs"], "km": c["km"],
                    "first_seen": times[sid][0], "last_seen": times[sid][1], "conclusion": c["conclusion"], "risks": c["risks"],
                    "evidence": [ev[i] for i in dict.fromkeys(ann["ANNOTATOR_1"]["shown"] + ann["ANNOTATOR_2"]["shown"]) if i in ev],
                    "ms": ann["ANNOTATOR_1"], "hm": ann["ANNOTATOR_2"],
                    "agreement": ("YES/YES" if ann["ANNOTATOR_1"]["decision"] == ann["ANNOTATOR_2"]["decision"] == "YES" else
                                  "UNSURE/UNSURE" if ann["ANNOTATOR_1"]["decision"] == ann["ANNOTATOR_2"]["decision"] == "UNSURE" else "DISAGREEMENT")})
    return out


def build(ledger, out):
    D = gather(ledger); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    taken = sorted({d["ms"]["who"] for d in D} | {d["hm"]["who"] for d in D})
    page = open(Path(__file__).with_name("adjudicate_template.html")).read().replace("__DATA__", json.dumps(D, ensure_ascii=False)).replace("__TAKEN__", json.dumps(taken))
    (out / "adjudicator_review.html").write_text(page); json.dump(D, open(out / "adjudicator_review_content.json", "w"), indent=1, ensure_ascii=False)
    return D


def import_adjudication(path, ledger_in, ledger_out):
    d = json.load(open(path)); who = d["adjudicator"].strip()
    rows = list(csv.DictReader(open(ledger_in)))
    taken = {r["reviewer_id"].strip().lower() for r in rows if r["role"] in ("ANNOTATOR_1", "ANNOTATOR_2") and r["reviewer_id"]}
    if not who or who.upper().startswith(AI_PREFIX): raise SystemExit("adjudicator must be a human")
    if who.lower() in taken: raise SystemExit("adjudicator must be a third person (not an annotator)")
    if d.get("adjudicator_role") != "ADJUDICATOR": raise SystemExit("file is not an adjudication export")
    n = 0
    for x in d["decisions"]:
        if x["adjudicator_decision"] not in ("YES", "UNSURE_UNKNOWN"): raise SystemExit("decision must be YES or UNSURE_UNKNOWN")
        if not x["adjudicator_reason"].strip(): raise SystemExit(f"{x['candidate_id']}: reason required")
        for r in rows:
            if r["source_id"] == x["source_id"] and r["role"] == "ADJUDICATOR" and not r["reviewer_id"]:
                r.update(record_kind="ADJUDICATION", reviewer_id=who, reviewer_status="ADJUDICATED", adjudication_status="ADJUDICATED",
                         final_label=x["proposed_label"] if x["adjudicator_decision"] == "YES" else "UNKNOWN",
                         conflict_status="RESOLVED" if x["agreement"] == "DISAGREEMENT" else "NONE",
                         evidence_summary="Adjudicator reason: " + x["adjudicator_reason"].strip(), evidence_date=x["timestamp"][:10],
                         counter_evidence_searched="checklist: " + json.dumps(x["checklist"], sort_keys=True))
                n += 1
    with open(ledger_out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ER.LEDGER_COLUMNS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    return n


if __name__ == "__main__":
    if sys.argv[1] == "build": print(len(build(sys.argv[2], sys.argv[3])), "candidates")
    else: print(import_adjudication(*sys.argv[2:5]), "ADJUDICATOR rows recorded")
