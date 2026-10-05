"""ml_v1 tests. Training-path tests use SYNTHETIC fixture labels in temp dirs only (code-path verification; never reported, never saved)."""
import csv, hashlib, json, os, shutil, sys, tempfile, unittest
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "m1"))
import build_features_v1 as BF, labels_v1 as LB, train_model_v1 as TM, evaluate_model_v1 as EV, inference_v1 as INF
TABLE = Path(os.environ.get("ML_TABLE", "/home/claude/mlo/feature_table_v1.csv"))
FORBIDDEN = {"candidate_group", "candidate_subgroup", "candidate_reason", "sampling_weight", "inclusion_prob", "stratum", "evidence_priority", "candidate_decision",
             "decision", "final_label", "adjudication_status", "reviewer_status", "proposed_label", "label", "evidence_status", "research_conclusion", "source_id",
             "registry_id", "site_complex_id", "centroid_lat", "centroid_lon", "first_seen_utc", "last_seen_utc", "attr_", "hypothesis", "firms_type"}
class Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp()); ids = sorted(l for l in open("/home/claude/ml_ids_6892.txt").read().split())[:3]
        cls.a = BF.build(ids, cls.d / "a.csv"); cls.b = BF.build(ids, cls.d / "b.csv")
    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.d, True)
    def test_deterministic(self): self.assertEqual((self.d / "a.csv").read_bytes(), (self.d / "b.csv").read_bytes())
    def test_schema_stable(self): self.assertEqual(list(self.a[0]), BF.COLUMNS); self.assertEqual(len(BF.FEATURES), 30)
    def test_no_forbidden_features(self):
        for f in BF.FEATURES: self.assertFalse(any(f == x or f.startswith(x) for x in FORBIDDEN), f)
        self.assertTrue(all(BF.MANIFEST[k][4] in ("YES", "NO") for k in BF.MANIFEST))
    def test_missing_context_is_empty_not_zero(self):
        for r in self.a:
            if r["osm_status"] != "OK": self.assertTrue(all(r[k] == "" for k in BF.FEATURES if k.startswith("osm_")))
    @unittest.skipUnless(TABLE.exists(), "full table absent")
    def test_full_table(self):
        R = list(csv.DictReader(open(TABLE))); self.assertEqual(len(R), 6892); self.assertEqual(list(R[0]), BF.COLUMNS)
class Training(unittest.TestCase):
    def synth(self, n_groups=20, per=4):
        rng = np.random.default_rng(0); rows, labels = [], []
        for gi in range(n_groups):
            cls = "STEEL_METAL" if gi % 2 else "THERMAL_POWER"
            for k in range(per):
                sid = f"SYN-{gi}-{k}"; r = {f: str(rng.normal(1 if cls == "STEEL_METAL" else 0, 1)) for f in BF.FEATURES}; r["source_id"] = sid; rows.append(r)
                labels.append({"source_id": sid, "label": cls, "site_complex_id": f"SC-SYN-{gi}"})
        return rows, labels
    def test_grouped_split_no_leak(self):
        rows, labels = self.synth(); y = np.array([x["label"] for x in labels]); g = np.array([x["site_complex_id"] for x in labels])
        tr, te = TM.grouped_split(y, g); self.assertFalse(set(g[tr]) & set(g[te]))
    def test_train_path_runs_on_synthetic(self):
        rows, labels = self.synth(); res, split = TM.train(rows, labels)
        self.assertEqual(set(res), {"logistic_regression", "random_forest"}); self.assertGreater(split["test_groups"], 0)
        self.assertIn("macro_f1", res["logistic_regression"]["eval"])
    def test_metric_withholding(self):
        e = EV.evaluate(["A", "B", "A"], ["A", "A", "A"], np.array([[.6, .4]] * 3), ["A", "B"]); self.assertIsNone(e["roc_auc"]); self.assertIsNone(e["brier"])
class Gate(unittest.TestCase):
    def test_real_labels_block_training(self):
        g = LB.gate(LB.eligible_labels()); self.assertEqual(g["eligible_labels"], 0); self.assertEqual(g["verdict"], "NO_DEFENSIBLE_SUPERVISED_TRAINING_YET")
    def test_cli_stops_without_model(self):
        import subprocess; d = Path(tempfile.mkdtemp())
        p = subprocess.run([sys.executable, str(HERE / "train_model_v1.py"), "--features", str(TABLE), "--out", str(d / "m")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2); self.assertFalse((d / "m").exists()); shutil.rmtree(d, True)
class Inference(unittest.TestCase):
    def test_fallback_schema(self):
        f = {"source_id": "SRC-x", "centroid_lat": "21.0", "centroid_lon": "80.0", "active_days": "30", "night_frac": "0.9", "detection_count": "50"}
        out = INF.predict_source(f, [("STEEL", "S1", "steel one", 21.001, 80.001)])
        self.assertEqual(list(out), INF.KEYS); self.assertEqual(out["mode"], "HEURISTIC_FALLBACK"); self.assertIsNone(out["class_probabilities"])
        self.assertEqual(sum(out["attribution_weights"].values()), 100); self.assertIn("not calibrated probabilities", out["explanation"])
        self.assertEqual(INF.predict_source(f, [])["confidence"], "UNKNOWN")
class Unchanged(unittest.TestCase):
    def test_artifacts_unchanged(self):
        for d in ("annotation_v1_frozen_placeholder",): pass
        for d in ("adjudication_pass1", "annotator1_pass1", "annotator2_pass1", "label_factory_v1", "label_expansion_v1", "evidence_research_v1"):
            for line in open(f"/mnt/user-data/outputs/{d}/SHA256SUMS.txt"):
                h, f = line.split(None, 1); f = f.strip()
                if "(combined)" in f: continue
                self.assertEqual(hashlib.sha256(open(f"/mnt/user-data/outputs/{d}/{f}", "rb").read()).hexdigest(), h, f"{d}/{f}")
if __name__ == "__main__":
    unittest.main()
