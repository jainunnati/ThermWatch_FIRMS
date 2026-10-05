"""Product integration tests: contract v2, live runner honesty, workflow, no credentials in frontend."""
import csv, json, os, re, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; sys.path.insert(0, str(HERE)); import live_update as LU
DEMO = ROOT / "public/data/thermwatch_historical.json"; IDX = HERE / "live_indexes"
class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.d = json.load(open(DEMO))
    def test_keys_and_mode(self):
        for k in ("contract_version", "mode", "generated_at", "data_timestamp", "pipeline_run_id", "pipeline_status", "coverage_status", "system_stats", "coverage", "alerts", "sources", "map_points", "ml_status", "disclaimer"):
            self.assertIn(k, self.d)
        self.assertEqual(self.d["mode"], "DEMO"); self.assertNotIn("LIVE", self.d["pipeline_status"])
    def test_real_counts(self):
        s = self.d["system_stats"]; self.assertEqual((s["valid_observations"], s["physical_sources"], s["events"]), (2298169, 1056161, 1277339))
    def test_size_caps(self):
        self.assertLessEqual(len(self.d["sources"]), 300); self.assertLessEqual(len(self.d["map_points"]), 3000); self.assertEqual(len(self.d["alerts"]), 20)
    def test_honesty(self):
        blob = json.dumps(self.d).replace("not calibrated probabilities", "")
        self.assertNotRegex(blob.lower(), r"probabilit"); self.assertTrue(all(a["cause"] == "Not confirmed" for a in self.d["alerts"]))
        self.assertEqual(self.d["ml_status"]["state"], "READY_NOT_TRAINED"); self.assertEqual(self.d["ml_status"]["eligible_labels"], 0)
        self.assertIn("never 'no fire'", self.d["coverage"]["rule"]); self.assertEqual(len(self.d["coverage"]["reason_meaning"]), 4)
    def test_source_event_drilldown(self):
        s = self.d["sources"][0]; self.assertTrue(s["events"]); self.assertTrue(all(e["observations"] >= 1 for e in s["events"]))
class Live(unittest.TestCase):
    def rows(self):
        f = sorted(Path("/home/claude/w/data_jan_oct_final").glob("VIIRS_NOAA21_NRT*"))[-1]; R = list(csv.DictReader(open(f)))[:30]
        return R + [dict(R[0], latitude="35.1", longitude="75.2", acq_time="1200"), dict(R[1])]   # synthetic no-history point + duplicate
    def test_association_new_source_and_dedup(self):
        r = LU.run(self.rows(), IDX); s = r["system_stats"]
        self.assertEqual(s["live_observations"] - 1, s["live_observations_dedup"]); self.assertEqual(r["mode"], "LIVE")
        new = [x for x in r["live_sources"] if x["status"] == "NEW_PROVISIONAL_SOURCE"]
        self.assertTrue(new); self.assertTrue(all(x["pihs"] == "Insufficient history for persistence classification" for x in new))
        self.assertTrue(all(x["cause"] == "Not confirmed" for x in r["live_sources"]))
    def test_unavailable_is_honest(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "l.json"; env = dict(os.environ, FIRMS_MAP_KEY="")
            subprocess.run([sys.executable, str(HERE / "live_update.py"), "--indexes", str(IDX), "--out", str(out)], env=env, check=True, capture_output=True)
            j = json.load(open(out)); self.assertEqual(j["pipeline_status"], "LIVE_FEED_UNAVAILABLE"); self.assertEqual(j["live_sources"], [])
            self.assertIsNone(re.search(r"[A-Fa-f0-9]{32}", out.read_text())); self.assertNotIn("http", j["pipeline_status_detail"])
class Deploy(unittest.TestCase):
    def test_workflow_uses_secret(self):
        w = (ROOT / ".github/workflows/thermwatch-live.yml").read_text()
        self.assertIn("${{ secrets.FIRMS_MAP_KEY }}", w); self.assertIn("schedule:", w); self.assertIsNone(re.search(r"[A-Fa-f0-9]{32}", w))
    def test_no_credentials_in_frontend(self):
        for p in list((ROOT / "src").rglob("*")) + list((ROOT / "public").rglob("*")):
            if p.is_file() and p.suffix in (".js", ".jsx", ".json", ".html", ".css"):
                t = p.read_text(errors="ignore"); self.assertIsNone(re.search(r"(MAP_KEY|map_key)\s*[=:]\s*['\"]?[A-Fa-f0-9]{16,}", t), str(p))
if __name__ == "__main__":
    unittest.main()
