"""Evaluation utilities (only meaningful on validator-eligible labels with grouped splits)."""
import numpy as np
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix, f1_score, roc_auc_score, brier_score_loss

def evaluate(y_true, y_pred, proba=None, classes=None, min_auc_per_class=10, min_calib=50):
    classes = classes or sorted(set(y_true) | set(y_pred))
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=classes, zero_division=0)
    out = {"classes": classes, "per_class": {c: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4), "f1": round(float(f[i]), 4), "support": int(s[i])} for i, c in enumerate(classes)},
           "macro_f1": round(float(f1_score(y_true, y_pred, labels=classes, average="macro", zero_division=0)), 4),
           "confusion_matrix": confusion_matrix(y_true, y_pred, labels=classes).tolist(), "roc_auc": None, "brier": None, "notes": []}
    if proba is not None and len(classes) == 2:
        yb = np.array([1 if y == classes[1] else 0 for y in y_true])
        if min(yb.sum(), len(yb) - yb.sum()) >= min_auc_per_class: out["roc_auc"] = round(float(roc_auc_score(yb, proba[:, 1])), 4)
        else: out["notes"].append(f"ROC-AUC withheld: fewer than {min_auc_per_class} test examples in a class")
        if len(yb) >= min_calib: out["brier"] = round(float(brier_score_loss(yb, proba[:, 1])), 4)
        else: out["notes"].append(f"calibration withheld: fewer than {min_calib} test examples")
    return out

def compare(rows):
    """rows: [{source_id, heuristic_top, heuristic_weight_pct, ml_pred, ml_prob, label}] -> adds correctness where a valid label exists.
    Heuristic weights are relative attribution weights, NOT probabilities."""
    return [dict(r, heuristic_correct=(r["heuristic_top"] == r["label"]) if r.get("label") else None, ml_correct=(r["ml_pred"] == r["label"]) if r.get("label") else None) for r in rows]
