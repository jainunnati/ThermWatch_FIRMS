"""Self-contained tests for ingest_annotations.py.

Every packet row and every annotation value here is a SYNTHETIC TEST FIXTURE, created in a temporary directory and
deleted afterwards. No real packet, record, candidate or human label is read or written. The header is the frozen
annotation-protocol-v1.0 packet header, so the tests also guard against accidental schema drift in the intake tool.
"""
import csv, json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

INGEST = Path(__file__).resolve().parent / "ingest_annotations.py"
N = 6  # fixture rows
HEADER = [
    "annotation_id", "protocol_version", "centroid_lat", "centroid_lon", "location_precision_deg", "spatial_extent_m",
    "first_seen_utc", "last_seen_utc", "active_days", "observation_count", "n_events", "duration_days", "max_gap_d",
    "median_gap_d", "frp_median", "frp_max", "ti4_median", "ti4_max", "ti4_sat_frac", "night_frac", "conf_high_frac",
    "neigh_750m", "neigh_2km", "span_frac", "modal_month_frac", "sat_mix", "n_obs_N20", "n_obs_SNPP", "xsat_pair_frac",
    "thermal_detection_scope", "snpp_unverified_coverage_days_in_window", "noaa20_unverified_coverage_days_in_window",
    "coverage_note", "facility_context_status", "landcover_status",
    "annotator1_id", "annotator1_label", "annotator1_confidence_tier", "annotator1_evidence_type",
    "annotator1_evidence_url_or_ref", "annotator1_evidence_date", "annotator1_industrial_context",
    "annotator1_industrial_context_confidence_tier", "annotator1_industrial_context_evidence_ref", "annotator1_notes",
    "annotator1_timestamp_utc",
    "annotator2_id", "annotator2_label", "annotator2_confidence_tier", "annotator2_evidence_type",
    "annotator2_evidence_url_or_ref", "annotator2_evidence_date", "annotator2_industrial_context",
    "annotator2_industrial_context_confidence_tier", "annotator2_industrial_context_evidence_ref", "annotator2_notes",
    "annotator2_timestamp_utc",
    "adjudicator_id", "adjudicated_label", "adjudicated_confidence_tier", "adjudicated_industrial_context",
    "adjudicated_industrial_context_confidence_tier", "adjudication_basis", "adjudication_notes",
    "adjudication_timestamp_utc"]
EVIDENCE = [c for c in HEADER if not c.startswith(("annotator", "adjud"))]


def fixture_packet():
    rows = []
    for i in range(N):
        r = {c: "" for c in HEADER}
        r.update({c: f"fixture-{c}-{i}" for c in EVIDENCE})
        r["annotation_id"] = f"ANN-fixture{i:04d}"; r["protocol_version"] = "annotation-protocol-v1.0"
        rows.append(r)
    return rows


def fill(i, label, tier="LOW", ctx="UNKNOWN_INSUFFICIENT", etype="FIRMS_PATTERN_ONLY", ref="", date="", ctier="", cref="", who=None):
    p = f"annotator{i}_"
    return {p + "id": who or f"fixture-annot-{i}", p + "label": label, p + "confidence_tier": tier, p + "evidence_type": etype,
            p + "evidence_url_or_ref": ref, p + "evidence_date": date, p + "industrial_context": ctx,
            p + "industrial_context_confidence_tier": ctier, p + "industrial_context_evidence_ref": cref,
            p + "timestamp_utc": "2000-01-01T00:00:00Z"}


def write(path, rows, cols=None):
    cols = cols or HEADER
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(rows)


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="tw_ingest_test_"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.packet = self.d / "packet.csv"; write(self.packet, fixture_packet())

    def run_ingest(self, a1, a2, adj=None, d=None):
        d = d or self.d
        write(d / "a1.csv", a1); write(d / "a2.csv", a2)
        cmd = [sys.executable, str(INGEST), "--packet", str(self.packet), "--a1", str(d / "a1.csv"),
               "--a2", str(d / "a2.csv"), "--out", str(d / "o")]
        if adj is not None: cmd += ["--adj", str(adj)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        with open(d / "o" / "intake_report.json") as f:
            return p.returncode, json.load(f)

    def base(self):
        rows = fixture_packet()
        return [{**r, **fill(1, "WILDFIRE")} for r in rows], [{**r, **fill(2, "WILDFIRE")} for r in rows]

    def adjudicate(self, sheet_rows, **values):
        for s in sheet_rows: s.update(values)
        path = self.d / "adj.csv"; write(path, sheet_rows, cols=list(sheet_rows[0])); return path

    def test_full_agreement_then_final(self):
        a1, a2 = self.base()
        rc, r = self.run_ingest(a1, a2)
        self.assertEqual((rc, r["n_needing_adjudication"], r["agreement"]["level1_raw"]), (0, 0, 1.0))
        rc, r = self.run_ingest(a1, a2, adj=self.d / "o" / "adjudication_sheet.csv")
        self.assertEqual(r["status"], "FINAL_LABELS_WRITTEN"); self.assertEqual(r["final_basis_counts"], {"AGREEMENT": N})

    def test_agreement_takes_lower_tier(self):
        a1, a2 = self.base()
        a1[0].update(fill(1, "WILDFIRE", tier="MEDIUM", etype="PUBLIC_REPORT", ref="fixture-ref", date="2000-01-01"))
        self.run_ingest(a1, a2)
        rc, r = self.run_ingest(a1, a2, adj=self.d / "o" / "adjudication_sheet.csv")
        final = {x["annotation_id"]: x for x in read(self.d / "o" / "final_labels.csv")}
        self.assertEqual(final["ANN-fixture0000"]["final_confidence_tier"], "LOW")

    def test_disagreement_adjudication_flow(self):
        a1, a2 = self.base()
        a2[0].update(fill(2, "UNSURE", tier="")); a2[1].update(fill(2, "AGRICULTURAL_BURNING"))
        rc, r = self.run_ingest(a1, a2)
        self.assertEqual((r["status"], r["n_needing_adjudication"]), ("AWAITING_ADJUDICATION", 2))
        adj = self.adjudicate(read(self.d / "o" / "adjudication_sheet.csv"), adjudicator_id="fixture-adj",
                              adjudicated_label="UNSURE", adjudicated_confidence_tier="",
                              adjudicated_industrial_context="UNKNOWN_INSUFFICIENT",
                              adjudicated_industrial_context_confidence_tier="", adjudication_basis="fixture",
                              adjudication_timestamp_utc="2000-01-01T00:00:00Z")
        rc, r = self.run_ingest(a1, a2, adj=adj)
        self.assertEqual(rc, 0); self.assertEqual(r["final_basis_counts"], {"AGREEMENT": N - 2, "ADJUDICATED": 2})
        self.assertEqual(r["final_label_counts"]["UNSURE"], 2)

    def test_adjudicator_cannot_be_annotator(self):
        a1, a2 = self.base(); a2[0].update(fill(2, "UNSURE", tier="")); self.run_ingest(a1, a2)
        adj = self.adjudicate(read(self.d / "o" / "adjudication_sheet.csv"), adjudicator_id="fixture-annot-1",
                              adjudicated_label="WILDFIRE", adjudicated_confidence_tier="LOW",
                              adjudicated_industrial_context="UNKNOWN_INSUFFICIENT", adjudication_basis="fixture")
        rc, r = self.run_ingest(a1, a2, adj=adj); self.assertEqual(rc, 1)

    def test_rejections(self):
        cases = {
            "high_firms_only": lambda a1, a2: a1[0].update(fill(1, "WILDFIRE", tier="HIGH")),
            "nonfirms_without_ref": lambda a1, a2: a1[0].update(fill(1, "WILDFIRE", tier="MEDIUM", etype="PUBLIC_REPORT")),
            "unsure_with_tier": lambda a1, a2: a1[0].update(fill(1, "UNSURE", tier="LOW")),
            "bad_class": lambda a1, a2: a1[0].update(fill(1, "INDUSTRIAL")),
            "edited_evidence": lambda a1, a2: a1[0].update(frp_max="edited"),
            "same_annotator": lambda a1, a2: a2[0].update(annotator2_id="fixture-annot-1"),
            "filled_other_side": lambda a1, a2: a1[0].update(annotator2_label="WILDFIRE"),
            "missing_row": lambda a1, a2: a1.pop(),
            "ctx_unknown_with_tier": lambda a1, a2: a1[0].update(fill(1, "WILDFIRE", ctier="LOW")),
            "ctx_high_no_ref": lambda a1, a2: a1[0].update(fill(1, "WILDFIRE", ctx="STEEL_METAL", ctier="HIGH")),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                d = self.d / name; d.mkdir()
                a1, a2 = self.base(); mutate(a1, a2)
                rc, r = self.run_ingest(a1, a2, d=d)
                self.assertEqual((rc, r["status"]), (1, "REJECTED_FIX_INPUTS"), name)

    def test_valid_high_with_official_record(self):
        a1, a2 = self.base()
        a1[0].update(fill(1, "PERSISTENT_THERMAL_SOURCE/ROUTINE_PROCESS_HEAT", tier="HIGH",
                          etype="OFFICIAL_RECORD;FIRMS_PATTERN_ONLY", ref="fixture-ref", date="2000-01-01",
                          ctx="STEEL_METAL", ctier="MEDIUM", cref="fixture-ref"))
        rc, r = self.run_ingest(a1, a2); self.assertEqual((rc, r["n_needing_adjudication"]), (0, 1))

    def test_deterministic_outputs(self):
        a1, a2 = self.base(); a2[0].update(fill(2, "UNSURE", tier=""))
        outs = []
        for k in ("r1", "r2"):
            d = self.d / k; d.mkdir(); self.run_ingest(a1, a2, d=d)
            outs.append((d / "o" / "adjudication_sheet.csv").read_bytes())
        self.assertEqual(outs[0], outs[1])


if __name__ == "__main__":
    unittest.main()
