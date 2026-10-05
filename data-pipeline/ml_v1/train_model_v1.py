"""Train the ThermWatch classifier ONLY if the label gate passes. Otherwise stops (exit 2) with NO_DEFENSIBLE_SUPERVISED_TRAINING_YET.
  python3 ml_v1/train_model_v1.py --features feature_table_v1.csv --out model_dir"""
import argparse, csv, json, pickle, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import labels_v1 as LB, evaluate_model_v1 as EV
from build_features_v1 import FEATURES
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
MODEL_VERSION = "ml_v1-model-1"

def matrix(feat_rows):
    return np.array([[float(r[f]) if r[f] not in ("", None) else np.nan for f in FEATURES] for r in feat_rows], dtype=float)

def grouped_split(y, groups, seed=0):
    """Return (train_idx, test_idx): one fold of StratifiedGroupKFold(5); groups (site complexes) never span both."""
    sgk = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    return next(sgk.split(np.zeros(len(y)), y, groups))

def train(feat_rows, labels, seed=0):
    lab = {x["source_id"]: x for x in labels}; rows = [r for r in feat_rows if r["source_id"] in lab]
    X = matrix(rows); y = np.array([lab[r["source_id"]]["label"] for r in rows]); g = np.array([lab[r["source_id"]]["site_complex_id"] for r in rows])
    tr, te = grouped_split(y, g, seed)
    assert not set(g[tr]) & set(g[te]), "site complex leaked across split"
    models = {"logistic_regression": make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)),
              "random_forest": make_pipeline(SimpleImputer(strategy="median", add_indicator=True), RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=seed))}
    res = {}
    for name, m in models.items():
        m.fit(X[tr], y[tr]); classes = list(m.classes_)
        res[name] = {"model": m, "eval": EV.evaluate(list(y[te]), list(m.predict(X[te])), m.predict_proba(X[te]), classes)}
    return res, {"n_train": len(tr), "n_test": len(te), "train_groups": len(set(g[tr])), "test_groups": len(set(g[te]))}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--features", required=True); ap.add_argument("--out", required=True); ap.add_argument("--ledger", default=LB.LEDGER); a = ap.parse_args()
    labels = LB.eligible_labels(a.ledger); gt = LB.gate(labels); print(json.dumps(gt, indent=1))
    if not gt["passes"]:
        print("NO_DEFENSIBLE_SUPERVISED_TRAINING_YET: training stopped; no model was created."); sys.exit(2)
    res, split = train(list(csv.DictReader(open(a.features))), labels)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for name, v in res.items(): pickle.dump(v["model"], open(out / f"{name}.pkl", "wb"))
    json.dump({"model_version": MODEL_VERSION, "features": FEATURES, "split": split, "gate": gt, "eval": {k: v["eval"] for k, v in res.items()}}, open(out / "model_metadata.json", "w"), indent=1)
