"""Investigation-product tests (real-data investigation, print report, mock-data isolation).
Python side: static/source-tree + contract checks. The model/render checks live in tests/*.test.mjs (npm test);
test_node_suites runs the model suite here when node is available."""
import hashlib, json, re, shutil, subprocess, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
DEMO = ROOT / "public/data/thermwatch_historical.json"
BAD = re.compile(r"Lanjigarh|SYN-EVT|SYN-OBS|SYN-MRK|LANJIGARH_ASSESSMENT", re.I)


def judge_facing_files():
    for base in ("src", "public"):
        for p in (ROOT / base).rglob("*"):
            if p.is_file() and p.suffix in (".js", ".jsx", ".json", ".html", ".css", ".md"):
                yield p
    yield ROOT / "index.html"


class MockIsolation(unittest.TestCase):
    def test_no_mock_references_in_judge_facing_tree(self):
        # 'Lanjigarh Refinery power station' (GEM registry id L100000102479) is a REAL facility row in the
        # context layer and is allowed there only; every other judge-facing file must be free of mock markers.
        for p in judge_facing_files():
            t = p.read_text(errors="ignore")
            if p.name == "thermwatch_context.json":
                d = json.loads(t); self.assertEqual([f["id"] for f in d["facilities"] if "lanjigarh" in f["name"].lower()], ["L100000102479"])
                d["facilities"] = [f for f in d["facilities"] if f["id"] != "L100000102479"]; t = json.dumps(d)
            self.assertIsNone(BAD.search(t), str(p))

    def test_mock_data_and_legacy_shell_are_absent(self):
        for gone in ("src/data", "src/services/demoStore.js", "src/components/investigation/InvestigationBody.jsx", "public/demo", "legacy", "backend",
                     "public/thermwatch_demo.html", "src/components/intel/ThermWatchConsole.jsx", "src/components/intel/AlertBar.jsx",
                     "data-pipeline/sample_data.py", "data-pipeline/run_pipeline.py", "data-pipeline/build_backend_data.py"):
            self.assertFalse((ROOT / gone).exists(), gone)
        self.assertFalse(list(ROOT.rglob("fire_events.json")), "mock fire_events.json must not exist")
        self.assertFalse(any("load_demo_json" in p.read_text(errors="ignore") for p in (ROOT / "data-pipeline").rglob("*.py") if p.name != Path(__file__).name))
        for p in (ROOT / "src").rglob("*.js*"): self.assertNotIn("legacy/", p.read_text(), str(p))

    def test_app_entry_is_v7_shell_on_real_store_only(self):
        app = (ROOT / "src/App.jsx").read_text()
        for v7 in ("Sidebar", "MapView", "AlertsDrawer", "InvestigationDrawer"): self.assertIn(v7, app)
        for gone in ("ThermWatchConsole", "AlertBar", "demoStore", "switchDataMode"): self.assertNotIn(gone, app)
        services = "".join(p.read_text() for p in (ROOT / "src/services").glob("*.js"))
        self.assertIn("thermwatch_historical.json", services); self.assertNotRegex(services, r"demo|fire_events|syntheticMarkers")


class RealContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.d = json.load(open(DEMO))

    def test_sources_are_real_and_unconfirmed(self):
        for s in self.d["sources"]:
            self.assertRegex(s["source_id"], r"^SRC-[0-9a-f]{10}$"); self.assertEqual(s["uncertainty"]["cause"], "Not confirmed")
            self.assertTrue(all(re.match(r"^EVT-[0-9a-f]{10}-\d{3}$", e["event_id"]) for e in s["events"]))
        self.assertTrue(all(p["source_id"].startswith("SRC-") for p in self.d["map_points"]))

    def test_ml_untrained_and_no_f1(self):
        self.assertEqual(self.d["ml_status"]["state"], "READY_NOT_TRAINED"); self.assertEqual(self.d["ml_status"]["eligible_labels"], 0)
        self.assertNotRegex(json.dumps(self.d), r"\bF1\b|f1_score")

    def test_pihs_and_alert_values_come_from_pipeline_rules(self):
        import sys; sys.path.insert(0, str(HERE)); import intel_core as IC
        for s in self.d["sources"]:
            a, sp = s["activity"], s["spatial"]
            p = IC.pihs({"active_days": a["active_days"], "night_frac": a["night_share"], "detection_count": a["detections"], "event_count": a["events"], "spatial_extent_m": sp["extent_m"]})
            self.assertEqual((p["pihs_flag"], p["pihs_score"], p["pihs_reasons"]), (s["intelligence"]["pihs_flag"], s["intelligence"]["pihs_score"], s["intelligence"]["pihs_reasons"]), s["source_id"])

    def test_demo_contract_pinned(self):
        pinned = (ROOT / "tests/fixtures/thermwatch_historical.sha256").read_text().strip()
        self.assertEqual(hashlib.sha256(DEMO.read_bytes()).hexdigest(), pinned)
        self.assertEqual(self.d["generated_at"], self.d["data_timestamp"])


class NodeSuites(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_node_suites(self):
        r = subprocess.run(["node", "--test", "tests/investigation.test.mjs"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
