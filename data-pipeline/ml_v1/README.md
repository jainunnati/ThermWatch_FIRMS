# ThermWatch ml_v1: ML foundation (no model trained: label gate fails)
1. **Features:** `python3 ml_v1/build_features_v1.py --ids IDS.txt --out feature_table_v1.csv`. `feature_table_v1.csv` covers the 6,892 sources with a GEM site within 5 km.
2. **Train:** `python3 ml_v1/train_model_v1.py --features feature_table_v1.csv --out model/`. Currently it stops with `NO_DEFENSIBLE_SUPERVISED_TRAINING_YET` (exit 2).
3. **Infer:** `inference_v1.predict_source(...)`. This is the heuristic fallback until a model exists.
4. **Test:** `python3 -m unittest ml_v1.test_ml_v1` (12 tests; the training-path tests use synthetic fixtures in temp folders only).

Docs: `FEATURE_MANIFEST_V1.md`, `LEAKAGE_AUDIT_V1.md`, `LABEL_READINESS_V1.md`, `MODEL_DESIGN_V1.md`.

The ML modules read the Step D registry, ledgers and validator but never modify them.
