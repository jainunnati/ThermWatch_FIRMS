"""Stable inference interface. Uses a trained model only if one exists; otherwise the heuristic Attribution MVP (fallback).
Heuristic outputs are relative attribution weights, never presented as probabilities."""
import json, pickle, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "m1"))
import attribution_mvp_v1 as AM
from build_features_v1 import FEATURES
KEYS = ["predicted_class", "class_probabilities", "attribution_weights", "confidence", "top_features", "explanation", "model_version", "mode"]

def predict_source(source_features, facilities=(), model_dir=None):
    md = Path(model_dir) if model_dir else None
    if md and (md / "logistic_regression.pkl").exists():
        import numpy as np
        m = pickle.load(open(md / "logistic_regression.pkl", "rb")); meta = json.load(open(md / "model_metadata.json"))
        x = np.array([[float(source_features[f]) if source_features.get(f) not in ("", None) else np.nan for f in FEATURES]])
        p = m.predict_proba(x)[0]; cls = list(m.classes_); top = cls[int(p.argmax())]
        return {"predicted_class": top, "class_probabilities": {c: round(float(v), 4) for c, v in zip(cls, p)}, "attribution_weights": None,
                "confidence": "MODEL_PROBABILITY (calibration per model_metadata.json)", "top_features": [], "explanation": "ML classifier output",
                "model_version": meta["model_version"], "mode": "ML"}
    src = {"source_id": source_features["source_id"], "lat": float(source_features["centroid_lat"]), "lon": float(source_features["centroid_lon"]),
           "active_days": int(source_features["active_days"]), "night_frac": float(source_features["night_frac"]), "observation_count": int(source_features["detection_count"])}
    h = AM.attribute(src, list(facilities))
    return {"predicted_class": h["ranked"][0][0] if h["ranked"] else None, "class_probabilities": None, "attribution_weights": h["weights"] or None,
            "confidence": h["confidence"], "top_features": h["facts"], "explanation": h["why"] + " " + AM.DISCLAIMER,
            "model_version": AM.METHODOLOGY_VERSION, "mode": "HEURISTIC_FALLBACK"}
