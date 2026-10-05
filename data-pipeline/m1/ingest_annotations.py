"""ThermWatch CP2/CP3 intake: validate two independent annotation files against the frozen v1.0 packet, measure agreement,
emit an adjudication sheet for disagreements, and (when an adjudication file is supplied) the final label table.
Never creates a label: every final value is copied from an annotator (agreement) or the adjudicator (disagreement).

  python3 ingest_annotations.py --packet blind_annotation.csv --a1 annotator1.csv --a2 annotator2.csv --out DIR [--adj adjudication.csv]
"""
import argparse, csv, hashlib, json, sys
from collections import Counter
from pathlib import Path

PROTOCOL = "annotation-protocol-v1.0"
L1 = ["INDUSTRIAL_FIRE", "PERSISTENT_THERMAL_SOURCE/ROUTINE_PROCESS_HEAT", "WILDFIRE", "AGRICULTURAL_BURNING",
      "GAS_FLARE/INDUSTRIAL_FLARE", "OTHER_UNKNOWN", "UNSURE"]
L2 = ["LNG_GAS", "STEEL_METAL", "THERMAL_POWER", "REFINERY", "PETROCHEMICAL", "MINING", "OTHER_INDUSTRIAL",
      "NOT_INDUSTRIAL", "UNKNOWN_INSUFFICIENT"]
TIERS = ["HIGH", "MEDIUM", "LOW"]; RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
EVID = ["OFFICIAL_RECORD", "OPERATOR_OR_FIELD_CONFIRMATION", "DATED_HIGH_RES_IMAGERY", "UNDATED_OR_BASEMAP_IMAGERY",
        "PUBLIC_REPORT", "FIRMS_PATTERN_ONLY"]
ADJ_COLS = ["adjudicator_id", "adjudicated_label", "adjudicated_confidence_tier", "adjudicated_industrial_context",
            "adjudicated_industrial_context_confidence_tier", "adjudication_basis", "adjudication_notes", "adjudication_timestamp_utc"]


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return {r["annotation_id"]: r for r in csv.DictReader(open(p, newline="", encoding="utf-8"))}


def kappa(a, b):
    n = len(a)
    if n == 0: return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b); pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n / n
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def check_annotation(r, i, errs):
    p = f"annotator{i}_"; aid = r["annotation_id"]
    def e(m): errs.append(f"{aid} A{i}: {m}")
    if not r[p + "id"].strip(): e("missing annotator id")
    lab, tier = r[p + "label"], r[p + "confidence_tier"]
    if lab not in L1: e(f"label {lab!r} not in v1.0 classes")
    if (lab == "UNSURE") != (tier == ""): e("tier must be empty iff label is UNSURE")
    if tier and tier not in TIERS: e(f"bad tier {tier!r}")
    types = [t for t in r[p + "evidence_type"].split(";") if t]
    if any(t not in EVID for t in types): e(f"unknown evidence_type in {types}")
    non_firms = [t for t in types if t != "FIRMS_PATTERN_ONLY"]
    if tier in ("HIGH", "MEDIUM") and not non_firms: e("HIGH/MEDIUM requires a non-FIRMS evidence type")
    if non_firms and not (r[p + "evidence_url_or_ref"].strip() and r[p + "evidence_date"].strip()):
        e("non-FIRMS evidence needs evidence_url_or_ref and evidence_date")
    ctx, ctier = r[p + "industrial_context"], r[p + "industrial_context_confidence_tier"]
    if ctx not in L2: e(f"industrial_context {ctx!r} not in v1.0 values")
    if (ctx == "UNKNOWN_INSUFFICIENT") != (ctier == ""): e("context tier must be empty iff UNKNOWN_INSUFFICIENT")
    if ctier and ctier not in TIERS: e(f"bad context tier {ctier!r}")
    if ctier in ("HIGH", "MEDIUM") and not r[p + "industrial_context_evidence_ref"].strip():
        e("HIGH/MEDIUM context requires industrial_context_evidence_ref")
    if not r[p + "timestamp_utc"].strip(): e("missing timestamp_utc")


def main():
    ap = argparse.ArgumentParser()
    for k in ("packet", "a1", "a2", "out"): ap.add_argument("--" + k, required=True)
    ap.add_argument("--adj")
    a = ap.parse_args(); O = Path(a.out); O.mkdir(parents=True, exist_ok=True)
    P, A1, A2 = load(a.packet), load(a.a1), load(a.a2)
    errs = []
    cols = list(next(iter(P.values())).keys())
    evid_cols = [c for c in cols if not c.startswith(("annotator", "adjud"))]
    for name, F, i in (("a1", A1, 1), ("a2", A2, 2)):
        if set(F) != set(P): errs.append(f"{name}: annotation_id set differs from packet ({len(F)} vs {len(P)})")
        for aid, r in F.items():
            if aid not in P: continue
            if any(r.get(c) != P[aid][c] for c in evid_cols): errs.append(f"{aid} {name}: read-only evidence columns were edited")
            other = 2 if i == 1 else 1
            if any(r.get(c, "") for c in cols if c.startswith((f"annotator{other}_", "adjud"))):
                errs.append(f"{aid} {name}: fields of the other annotator or adjudicator are filled")
            check_annotation(r, i, errs)
    for aid in set(A1) & set(A2):
        if A1[aid]["annotator1_id"].strip() and A1[aid]["annotator1_id"] == A2[aid]["annotator2_id"]:
            errs.append(f"{aid}: annotator 1 and 2 have the same id (independence rule)")
    rep = {"protocol": PROTOCOL, "inputs_sha256": {k: sha(getattr(a, k)) for k in ("packet", "a1", "a2")},
           "n_packet": len(P), "validation_errors": errs[:200], "n_validation_errors": len(errs)}
    if errs:
        rep["status"] = "REJECTED_FIX_INPUTS"
        (O / "intake_report.json").write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
        print(f"REJECTED: {len(errs)} validation errors (see intake_report.json)"); sys.exit(1)

    ids = sorted(P)
    l1a = [A1[k]["annotator1_label"] for k in ids]; l1b = [A2[k]["annotator2_label"] for k in ids]
    l2a = [A1[k]["annotator1_industrial_context"] for k in ids]; l2b = [A2[k]["annotator2_industrial_context"] for k in ids]
    rep["agreement"] = {"level1_raw": round(sum(x == y for x, y in zip(l1a, l1b)) / len(ids), 4), "level1_cohen_kappa": kappa(l1a, l1b),
                        "level2_raw": round(sum(x == y for x, y in zip(l2a, l2b)) / len(ids), 4), "level2_cohen_kappa": kappa(l2a, l2b)}
    need = [k for k in ids if A1[k]["annotator1_label"] != A2[k]["annotator2_label"]
            or A1[k]["annotator1_industrial_context"] != A2[k]["annotator2_industrial_context"]]
    rep["n_needing_adjudication"] = len(need)
    sheet_cols = ["annotation_id"] + [c for c in cols if c.startswith(("annotator1_", "annotator2_"))] + evid_cols[1:] + ADJ_COLS
    with open(O / "adjudication_sheet.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sheet_cols, lineterminator="\n"); w.writeheader()
        for k in need:
            row = {**P[k], **{c: A1[k][c] for c in cols if c.startswith("annotator1_")}, **{c: A2[k][c] for c in cols if c.startswith("annotator2_")}}
            w.writerow({c: row.get(c, "") for c in sheet_cols})
    ADJ = load(a.adj) if a.adj else {}
    if a.adj:
        rep["inputs_sha256"]["adj"] = sha(a.adj)
        for k in need:
            r = ADJ.get(k)
            if r is None: errs.append(f"{k}: missing from adjudication file"); continue
            if r["adjudicator_id"].strip() in ("", A1[k]["annotator1_id"], A2[k]["annotator2_id"]):
                errs.append(f"{k}: adjudicator id empty or equal to an annotator")
            if r["adjudicated_label"] not in L1 or r["adjudicated_industrial_context"] not in L2: errs.append(f"{k}: bad adjudicated value")
            if (r["adjudicated_label"] == "UNSURE") != (r["adjudicated_confidence_tier"] == ""): errs.append(f"{k}: adjudicated tier rule")
            if (r["adjudicated_industrial_context"] == "UNKNOWN_INSUFFICIENT") != (r["adjudicated_industrial_context_confidence_tier"] == ""):
                errs.append(f"{k}: adjudicated context tier rule")
            if not r["adjudication_basis"].strip(): errs.append(f"{k}: adjudication_basis is mandatory")
        extra = sorted(set(ADJ) - set(need))
        if extra: errs.append(f"adjudication file has records that did not need adjudication: {extra[:5]}")
    final = []
    if a.adj and not errs:
        for k in ids:
            r1, r2 = A1[k], A2[k]
            if k in need:
                j = ADJ[k]
                lab, tier, ctx, ctier, basis = (j["adjudicated_label"], j["adjudicated_confidence_tier"],
                                                j["adjudicated_industrial_context"], j["adjudicated_industrial_context_confidence_tier"], "ADJUDICATED")
            else:
                lab, ctx, basis = r1["annotator1_label"], r1["annotator1_industrial_context"], "AGREEMENT"
                t = [x for x in (r1["annotator1_confidence_tier"], r2["annotator2_confidence_tier"]) if x]
                tier = min(t, key=RANK.get) if t else ""
                ct = [x for x in (r1["annotator1_industrial_context_confidence_tier"], r2["annotator2_industrial_context_confidence_tier"]) if x]
                ctier = min(ct, key=RANK.get) if ct else ""
            final.append({"annotation_id": k, "final_label": lab, "final_confidence_tier": tier, "final_industrial_context": ctx,
                          "final_industrial_context_confidence_tier": ctier, "final_basis": basis, "protocol_version": PROTOCOL,
                          "evidence_refs": " | ".join(x for x in (r1["annotator1_evidence_url_or_ref"], r2["annotator2_evidence_url_or_ref"]) if x)})
        with open(O / "final_labels.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(final[0]), lineterminator="\n"); w.writeheader(); w.writerows(final)
        rep["final_label_counts"] = dict(Counter(x["final_label"] for x in final))
        rep["final_industrial_context_counts"] = dict(Counter(x["final_industrial_context"] for x in final))
        rep["final_basis_counts"] = dict(Counter(x["final_basis"] for x in final))
    rep["validation_errors"] = errs[:200]; rep["n_validation_errors"] = len(errs)
    rep["status"] = ("REJECTED_FIX_INPUTS" if errs else "FINAL_LABELS_WRITTEN" if final else
                     "AWAITING_ADJUDICATION" if need else "READY_FOR_FINAL (rerun with --adj on an empty sheet)")
    (O / "intake_report.json").write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print(rep["status"], json.dumps(rep.get("agreement")), "need_adjudication", len(need))
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
