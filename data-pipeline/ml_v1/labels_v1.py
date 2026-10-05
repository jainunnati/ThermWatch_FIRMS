"""ML-eligible labels = adjudicated labels that pass the UNCHANGED validator (evidence_research_v1.validate_final_label)."""
import csv, sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "m1"))
import evidence_research_v1 as ER
LEDGER = "/mnt/user-data/outputs/adjudication_pass1/evidence_research_ledger_v1_3_A1A2ADJ.csv"
TRAINABLE = {"STEEL_METAL", "THERMAL_POWER", "LNG_GAS", "WILDFIRE", "AGRICULTURAL_BURNING", "INDUSTRIAL_FIRE"}
GATE = {"min_per_class": 30, "min_site_complexes_per_class": 8, "min_classes": 2}

def eligible_labels(ledger=LEDGER):
    L = list(csv.DictReader(open(ledger))); out = []
    for sid in sorted({r["source_id"] for r in L}):
        adj = [r for r in L if r["source_id"] == sid and r["record_kind"] == "ADJUDICATION"]
        if adj and adj[0]["final_label"] in TRAINABLE and not ER.validate_final_label(L, sid):
            out.append({"source_id": sid, "label": adj[0]["final_label"], "site_complex_id": adj[0]["site_complex_id"]})
    return out

def gate(labels):
    by = {}
    for x in labels: by.setdefault(x["label"], []).append(x)
    ok = {c: len(v) >= GATE["min_per_class"] and len({x["site_complex_id"] for x in v}) >= GATE["min_site_complexes_per_class"] for c, v in by.items()}
    passing = [c for c, v in ok.items() if v]
    return {"eligible_labels": len(labels), "per_class": {c: len(v) for c, v in by.items()},
            "site_complexes_per_class": {c: len({x["site_complex_id"] for x in v}) for c, v in by.items()},
            "classes_passing": passing, "passes": len(passing) >= GATE["min_classes"],
            "verdict": "TRAINING_ALLOWED" if len(passing) >= GATE["min_classes"] else "NO_DEFENSIBLE_SUPERVISED_TRAINING_YET"}
