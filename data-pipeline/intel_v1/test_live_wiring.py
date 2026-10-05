"""Live-feed credential/area wiring (no network: requests.get is replaced).
  python3 data-pipeline/intel_v1/test_live_wiring.py"""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import config, ingest_firms as IF, live_update as LU

FAKE = "0123456789abcdef0123456789abcdef"   # test-only placeholder, not a credential


class Wiring(unittest.TestCase):
    def test_variable_name_is_firms_map_key_everywhere(self):
        self.assertIn('os.getenv("FIRMS_MAP_KEY"', (ROOT / "config.py").read_text())
        self.assertIn("FIRMS_MAP_KEY=", (ROOT / ".env.example").read_text())
        self.assertIn("${{ secrets.FIRMS_MAP_KEY }}", (ROOT.parent / ".github/workflows/thermwatch-live.yml").read_text())

    def test_live_fetch_requests_all_india_area_not_dev_region(self):
        seen = []
        class R:
            text = "latitude,longitude,acq_date,acq_time\n"
            def raise_for_status(self): pass
        with mock.patch.object(config, "FIRMS_MAP_KEY", FAKE), mock.patch.object(IF.requests, "get", lambda url, timeout: seen.append(url) or R()), mock.patch.object(IF.time, "sleep", lambda s: None):
            LU.fetch_live()
        self.assertEqual(len(seen), 3)
        for u in seen:
            self.assertIn(f"/{LU.BBOX}/1/", u); self.assertNotIn(config.REGION_BBOX, u)
        self.assertEqual({u.split("/")[-4] for u in seen}, set(LU.SOURCES))

    def test_missing_key_publishes_unavailable_not_fake_data(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "live.json"
            env = {"PATH": "/usr/bin:/bin", "FIRMS_MAP_KEY": ""}
            r = subprocess.run([sys.executable, str(HERE / "live_update.py"), "--indexes", str(HERE / "live_indexes"), "--out", str(out)], env=env, cwd=d, capture_output=True, text=True, timeout=300)
            j = json.loads(out.read_text())
            self.assertEqual(j["pipeline_status"], "LIVE_FEED_UNAVAILABLE"); self.assertEqual(j["live_sources"], [])
            self.assertEqual(j["system_stats"]["live_observations"], 0)

    def test_rejected_key_is_not_echoed(self):
        class R:
            text = "Invalid MAP_KEY.\n"
            def raise_for_status(self): pass
        with mock.patch.object(config, "FIRMS_MAP_KEY", FAKE), mock.patch.object(IF.requests, "get", lambda url, timeout: R()):
            with self.assertRaises(IF.FirmsAuthError) as cm:
                IF.fetch_window("VIIRS_SNPP_NRT", None, 1, use_cache=False, bbox=LU.BBOX)
        self.assertNotIn(FAKE, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
