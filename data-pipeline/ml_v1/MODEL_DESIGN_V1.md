# MODEL_DESIGN_V1
```
                 ┌── Heuristic Attribution (attribution_mvp_v1: proximity weights; baseline + fallback)
FIRMS → Features ┤
                 └── ML Classifier (train_model_v1; only after the label gate passes)
                         ↓
                    Attribution → Alert
```
- **Target:** Level-2 facility context first (STEEL_METAL vs THERMAL_POWER), using validator-passing labels only (`labels_v1.py`).
- **Features:** the 30 columns marked allowed in `FEATURE_MANIFEST_V1.md`. Median imputation adds missing-value indicators; empty context means unknown, not zero.
- **Split:** `StratifiedGroupKFold` by `site_complex_id` (GEM sites within 5 km merged). There is an assert that no complex spans train and test.
- **Models:** class-balanced logistic regression (interpretable baseline) and random forest. No deep learning.
- **Metrics (`evaluate_model_v1`):**
  - per-class precision/recall/F1, macro F1 and confusion matrix;
  - ROC-AUC only for 2 classes with ≥10 test examples per class;
  - Brier/calibration only with ≥50 test examples;
  - ablation with/without GEM features is required (see the leakage audit).
- **Comparison:** `evaluate_model_v1.compare` puts the heuristic top category (relative weight, **not** a probability) beside the ML prediction and probability, and marks correctness only where a valid label exists.
- **Inference:** `inference_v1.predict_source(features, facilities, model_dir)` returns `predicted_class, class_probabilities, attribution_weights, confidence, top_features, explanation, model_version, mode`. Without a trained model it returns `mode=HEURISTIC_FALLBACK`, with `class_probabilities=None` and the heuristic disclaimer.
- **Training guard:** `train_model_v1.py` exits with code 2 and prints `NO_DEFENSIBLE_SUPERVISED_TRAINING_YET` unless the gate passes. No model file is written otherwise.
