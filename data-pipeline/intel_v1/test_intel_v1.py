"""intel_v1 tests (synthetic feature dicts; contract check on real output if present)."""
import json, os, sys, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); import intel_core as IC
OUT = Path(os.environ.get("INTEL_OUT", "/home/claude/intel/out/thermwatch_intel.json"))
def F(**k):
    d = {"source_id": "SRC-t", "active_days": "30", "night_frac": "0.9", "detection_count": "60", "event_count": "8", "spatial_extent_m": "300",
         "recent_30d_detections": "4", "frp_max": "40", "frp_mean": "8", "first_seen": "2026-01-02T00:00:00+00:00", "last_seen": "2026-09-30T00:00:00+00:00",
         "latitude": 21.0, "longitude": 80.0}
    d.update({x: str(v) for x, v in k.items()}); return d
ATTR = {"top": "STEEL_METAL", "top_pct": 82, "all": {"STEEL_METAL": 82, "OTHER_UNKNOWN": 18}, "confidence": "LOW", "nearest_name": "Crest Steel", "nearest_type": "STEEL_METAL", "nearest_km": 0.97}
class PIHS(unittest.TestCase):
    def test_persistent_case(self):
        p = IC.pihs(F()); self.assertTrue(p["pihs_flag"]); self.assertEqual(p["pihs_score"], 8)
    def test_non_persistent(self):
        p = IC.pihs(F(active_days=1, detection_count=1, night_frac=0, event_count=1, spatial_extent_m=0)); self.assertFalse(p["pihs_flag"]); self.assertEqual(p["pihs_score"], 0)
    def test_boundaries(self):
        self.assertIn("PERSISTENT_ACTIVITY", IC.pihs(F(active_days=20))["pihs_reasons"]); self.assertNotIn("PERSISTENT_ACTIVITY", IC.pihs(F(active_days=19))["pihs_reasons"])
        self.assertIn("SPATIALLY_COMPACT", IC.pihs(F(spatial_extent_m=750))["pihs_reasons"]); self.assertNotIn("SPATIALLY_COMPACT", IC.pihs(F(spatial_extent_m=751))["pihs_reasons"])
        self.assertNotIn("NIGHT_DOMINANT", IC.pihs(F(detection_count=2))["pihs_reasons"])   # night needs >=3 detections
    def test_missing_values_not_zero(self):
        p = IC.pihs(F(night_frac="")); self.assertEqual((p["pihs_flag"], p["pihs_score"], p["pihs_reasons"]), (False, None, ["INSUFFICIENT_DATA"]))
    def test_deterministic(self): self.assertEqual(IC.pihs(F()), IC.pihs(F()))
class Alerts(unittest.TestCase):
    def test_score_bounds_and_tier(self):
        a = IC.alert(F(), IC.pihs(F()), ATTR); self.assertTrue(0 <= a["alert_priority_score"] <= 1); self.assertEqual(a["alert_tier"], "HIGH")
    def test_distance_cannot_dominate(self):
        f = F(active_days=1, detection_count=1, night_frac=0, event_count=1, spatial_extent_m=0, recent_30d_detections=0)
        a = IC.alert(f, IC.pihs(f), dict(ATTR, top_pct=100)); self.assertLessEqual(a["alert_priority_score"], 0.10 + 0.15 / 60 + 1e-9); self.assertEqual(a["alert_tier"], "LOW")   # facility term capped at 0.10 (+1-day persistence)
    def test_unknown_attribution(self):
        a = IC.alert(F(), IC.pihs(F()), None); self.assertEqual(a["alert_components"]["facility_context"], 0.0); self.assertNotIn("FACILITY_CONTEXT", a["alert_reason_codes"])
    def test_no_alert_edge_case(self):
        f = F(active_days=1, detection_count=1, night_frac=0, event_count=1, spatial_extent_m=0, recent_30d_detections=0, frp_max=1, frp_mean=1)
        a = IC.alert(f, IC.pihs(f), None); self.assertLess(a["alert_priority_score"], 0.01); self.assertEqual(a["alert_tier"], "LOW"); self.assertEqual(a["alert_reason_codes"], [])
class WhyCard(unittest.TestCase):
    def test_language(self):
        c = IC.why_card(1, F(), IC.pihs(F()), IC.alert(F(), IC.pihs(F()), ATTR), ATTR, "complete")
        self.assertEqual(c["cause"], "Not confirmed"); self.assertIn("Cause not confirmed", c["explanation"]); self.assertIn("relative weight", c["attribution_statement"])
        blob = json.dumps(c).lower(); self.assertNotIn("% probability", blob); self.assertNotIn("confirmed cause", blob.replace("not confirmed", ""))
        self.assertTrue(any("0.97 km" in s for s in c["activity_summary"]))
    def test_no_facility(self):
        c = IC.why_card(1, F(), IC.pihs(F()), IC.alert(F(), IC.pihs(F()), None), None, "complete")
        self.assertEqual((c["confidence"], c["nearby_facilities"]), ("UNKNOWN", [])); self.assertIn("No documented facility", c["explanation"])
class Benchmark(unittest.TestCase):
    def test_gihs_runner_synthetic(self):
        import gihs_benchmark as GB
        r = GB.run([(21.0, 80.0), (25.0, 85.0)], [(21.001, 80.0), (50.0, 10.0)])   # synthetic points; second GIHS point outside region
        self.assertEqual(r["gihs_in_region"], 1); self.assertEqual(r["by_radius_km"]["0.5"]["pihs_near_gihs"], (1, 2)); self.assertIn("not accuracy", r["note"])
@unittest.skipUnless(OUT.exists(), "demo output not built")
class Contract(unittest.TestCase):
    def test_contract(self):
        j = json.load(open(OUT))
        for k in ("contract_version", "summary", "alerts", "ml_status", "disclaimer"): self.assertIn(k, j)
        self.assertEqual(j["ml_status"]["state"], "READY_NOT_TRAINED"); self.assertEqual(j["ml_status"]["eligible_labels"], 0)
        self.assertTrue(1 <= len(j["alerts"]) <= 20); self.assertEqual([a["alert_rank"] for a in j["alerts"]], list(range(1, len(j["alerts"]) + 1)))
        for a in j["alerts"]:
            self.assertEqual(a["cause"], "Not confirmed"); self.assertTrue(not a["attribution"] or sum(a["attribution"].values()) == 100)
        self.assertNotIn("probability", json.dumps(j["alerts"]).lower())
if __name__ == "__main__":
    unittest.main()
