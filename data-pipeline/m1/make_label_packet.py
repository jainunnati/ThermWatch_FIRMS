"""Blind human-annotation packet for registry sources (packet schema v1.1; protocol v1.0 UNCHANGED).

Evidence fields use the definitions RECOVERED from the frozen v1.0 packet: each formula reproduced the frozen pilot
values for all 87 LINKED pilot sources (see `verify_recovered_definitions`). Three frozen fields could NOT be
recovered (xsat_pair_frac, neigh_750m, neigh_2km); they are kept in the header but left empty, with
`unrecovered_fields` naming them. Nothing is guessed. Annotation/adjudication columns are identical to v1.0.

Read-only over Step C/D outputs and raw FIRMS CSVs. Deterministic. Hidden from annotators: source/registry IDs,
strata, inclusion probabilities, draw order, crosswalk data, AI-assisted labels, model outputs.

  python3 m1/make_label_packet.py --registry REG --membership MEMB --raw-dir RAW --coverage LEDGER \
      --ids IDS --out OUT [--salt-version v1.1]
"""
import argparse, csv, glob, gzip, hashlib, hmac, json, math, os, statistics as S, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thermwatch_core.schema import make_physical_key   # noqa: E402  (same identity as Step C)

PROTOCOL_VERSION = "annotation-protocol-v1.0"
PACKET_SCHEMA = "packet-v1.1"
EARTH_R = 6371008.8
TI4_SATURATION_K = 367.0
UNRECOVERED = ["xsat_pair_frac", "neigh_750m", "neigh_2km"]
SAT_LABEL = (("N20", "N20"), ("SNPP", "N"), ("N21", "N21"))
ANNOTATOR_FIELDS = [f"annotator{i}_{k}" for i in (1, 2) for k in (
    "id", "label", "confidence_tier", "evidence_type", "evidence_url_or_ref", "evidence_date", "industrial_context",
    "industrial_context_confidence_tier", "industrial_context_evidence_ref", "notes", "timestamp_utc")]
ADJ_FIELDS = ["adjudicator_id", "adjudicated_label", "adjudicated_confidence_tier", "adjudicated_industrial_context",
              "adjudicated_industrial_context_confidence_tier", "adjudication_basis", "adjudication_notes",
              "adjudication_timestamp_utc"]
EVIDENCE = ["annotation_id", "protocol_version", "packet_schema_version", "centroid_lat", "centroid_lon",
            "location_precision_deg", "spatial_extent_m", "first_seen_utc", "last_seen_utc", "active_days",
            "observation_count", "n_events", "duration_days", "max_gap_d", "median_gap_d", "frp_median", "frp_max",
            "ti4_median", "ti4_max", "ti4_sat_frac", "night_frac", "conf_high_frac", "neigh_750m", "neigh_2km",
            "span_frac", "modal_month_frac", "sat_mix", "n_obs_N20", "n_obs_SNPP", "n_obs_N21", "n_obs_sp", "n_obs_nrt",
            "grade_composition", "xsat_pair_frac", "unrecovered_fields", "thermal_detection_scope",
            "snpp_unverified_coverage_days_in_window", "noaa20_unverified_coverage_days_in_window",
            "noaa21_unverified_coverage_days_in_window", "coverage_note", "facility_context_status", "landcover_status"]
HEADER = EVIDENCE + ANNOTATOR_FIELDS + ADJ_FIELDS


def hav(a, b, c, d):
    r = math.radians
    x = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(min(1.0, x)))


def evidence(obs):
    """Recovered definitions. `obs`: list of dicts with t(iso), sat, lat, lon, frp, ti4, conf, dn."""
    obs = sorted(obs, key=lambda o: o["t"]); ts = [datetime.fromisoformat(o["t"]) for o in obs]; n = len(obs)
    days = sorted({t.date() for t in ts}); dur = (ts[-1] - ts[0]).total_seconds() / 86400
    gaps = [(b - a).total_seconds() / 86400 for a, b in zip(ts, ts[1:])]           # between consecutive observations
    months = {}
    for t in ts: months[t.month] = months.get(t.month, 0) + 1
    cla, clo = sum(o["lat"] for o in obs) / n, sum(o["lon"] for o in obs) / n
    return {"active_days": len(days), "observation_count": n, "duration_days": dur,
            "max_gap_d": max(gaps) if gaps else None, "median_gap_d": S.median(gaps) if gaps else None,
            "frp_median": S.median(o["frp"] for o in obs), "frp_max": max(o["frp"] for o in obs),
            "ti4_median": S.median(o["ti4"] for o in obs), "ti4_max": max(o["ti4"] for o in obs),
            "ti4_sat_frac": sum(o["ti4"] >= TI4_SATURATION_K for o in obs) / n,
            "night_frac": sum(o["dn"] == "N" for o in obs) / n, "conf_high_frac": sum(o["conf"] == "h" for o in obs) / n,
            "span_frac": len(days) / (math.ceil(dur) + 1), "modal_month_frac": max(months.values()) / n,
            "spatial_extent_m": max(hav(cla, clo, o["lat"], o["lon"]) for o in obs),
            "sat_mix": "+".join(lbl for lbl, code in SAT_LABEL if any(o["sat"] == code for o in obs)),
            "centroid": (cla, clo), "first": ts[0], "last": ts[-1]}


def extract(ids, membership, raw_dir):
    key2 = {}
    with gzip.open(membership, "rt") as f:
        next(f)
        for line in f:
            pk, rid, sid, eid, prod, mode = line.rstrip("\n").split("\t")
            if sid in ids: key2[pk] = (sid, eid, prod)
    obs, seen = {}, set()
    for fn in sorted(glob.glob(os.path.join(raw_dir, "*.csv"))):
        with open(fn, newline="") as f:
            for r in csv.DictReader(f):
                t = datetime.strptime(r["acq_date"] + r["acq_time"].zfill(4), "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc)
                pk = make_physical_key(r["instrument"], r["satellite"], t, float(r["latitude"]), float(r["longitude"]))
                if pk in key2 and pk not in seen:
                    seen.add(pk); sid, eid, prod = key2[pk]
                    obs.setdefault(sid, []).append({"t": t.isoformat(), "sat": pk.split("|")[2], "prod": prod, "eid": eid,
                                                    "lat": float(r["latitude"]), "lon": float(r["longitude"]),
                                                    "frp": float(r["frp"]), "ti4": float(r["bright_ti4"]),
                                                    "conf": r["confidence"], "dn": r["daynight"]})
    if len(seen) != len(key2):
        raise SystemExit(f"raw rows matched {len(seen)} of {len(key2)} member keys - refusing to build a partial packet")
    return obs


def fmt(v, nd=3):
    return "" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def main():
    ap = argparse.ArgumentParser()
    for k in ("registry", "membership", "raw-dir", "coverage", "ids", "out"): ap.add_argument("--" + k, required=True)
    ap.add_argument("--salt-version", default="v1.1")
    a = ap.parse_args(); O = Path(a.out); O.mkdir(parents=True, exist_ok=True)
    ids = set(Path(a.ids).read_text().split())
    reg = {}
    with gzip.open(a.registry, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["source_id"] in ids: reg[r["source_id"]] = r
    if set(reg) != ids: raise SystemExit("some ids are not in the registry")
    obs = extract(ids, a.membership, a.raw_dir)
    unver = {}
    for r in csv.DictReader(open(a.coverage)):
        if r["status"] != "OBSERVED": unver.setdefault(r["stream"], set()).add(r["date"])
    salt = f"thermwatch-packet-{a.salt_version}-blinding-salt".encode()
    rows, key = [], []
    for sid in sorted(ids):
        R, o = reg[sid], obs[sid]; e = evidence(o)
        n_sp = sum(x["prod"].endswith("_SP") for x in o)
        if e["observation_count"] != int(R["n_obs"]) or n_sp != int(R["n_obs_sp"]):
            raise SystemExit(f"{sid}: member count disagrees with registry")
        span = {(e["first"].date() + timedelta(i)).isoformat() for i in range((e["last"].date() - e["first"].date()).days + 1)}
        streams = sorted({x["prod"].replace("VIIRS_", "").replace("NOAA", "N").rsplit("_", 1)[0] + "-" + x["prod"].rsplit("_", 1)[1] for x in o})
        aid = "ANN-" + hmac.new(salt, sid.encode(), hashlib.sha256).hexdigest()[:12]
        row = {k: "" for k in HEADER}
        row.update({"annotation_id": aid, "protocol_version": PROTOCOL_VERSION, "packet_schema_version": PACKET_SCHEMA,
                    "centroid_lat": f"{e['centroid'][0]:.3f}", "centroid_lon": f"{e['centroid'][1]:.3f}",
                    "location_precision_deg": "0.001", "spatial_extent_m": fmt(e["spatial_extent_m"]),
                    "first_seen_utc": e["first"].isoformat(), "last_seen_utc": e["last"].isoformat(),
                    "active_days": e["active_days"], "observation_count": e["observation_count"], "n_events": int(R["n_events"]),
                    "sat_mix": e["sat_mix"], "n_obs_N20": sum(x["sat"] == "N20" for x in o),
                    "n_obs_SNPP": sum(x["sat"] == "N" for x in o), "n_obs_N21": sum(x["sat"] == "N21" for x in o),
                    "n_obs_sp": n_sp, "n_obs_nrt": e["observation_count"] - n_sp, "grade_composition": R["grade_composition"],
                    "unrecovered_fields": ";".join(UNRECOVERED),
                    "thermal_detection_scope": "VIIRS 375m " + ", ".join(streams) + ", 2026-01-01..2026-10-01",
                    "snpp_unverified_coverage_days_in_window": len(span & unver.get("VIIRS:N", set())),
                    "noaa20_unverified_coverage_days_in_window": len(span & unver.get("VIIRS:N20", set())),
                    "noaa21_unverified_coverage_days_in_window": len(span & unver.get("VIIRS:N21", set())),
                    "coverage_note": "Days without detections, and unverified-coverage days, are NOT evidence of no thermal activity.",
                    "facility_context_status": "NOT_AVAILABLE_PENDING_STEP_H", "landcover_status": "NOT_AVAILABLE_PENDING_STEP_H"})
        for k in ("duration_days", "max_gap_d", "median_gap_d"): row[k] = fmt(e[k])
        for k in ("frp_median", "frp_max", "ti4_median", "ti4_max"): row[k] = fmt(e[k], 2)
        for k in ("ti4_sat_frac", "night_frac", "conf_high_frac", "span_frac", "modal_month_frac"): row[k] = fmt(e[k])
        rows.append(row); key.append({"annotation_id": aid, "source_id": sid, "registry_id": R["registry_id"]})
    rows.sort(key=lambda r: r["annotation_id"]); key.sort(key=lambda r: r["annotation_id"])
    with open(O / "blind_annotation_label400.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    (O / "blind_annotation_label400.json").write_text(json.dumps({"protocol_version": PROTOCOL_VERSION,
        "packet_schema_version": PACKET_SCHEMA, "n_records": len(rows), "records": rows}, indent=1, sort_keys=True) + "\n")
    (O / "PRIVATE_label400_annotation_key.json").write_text(json.dumps({
        "WARNING": "PRIVATE. Never give to annotators.", "id_definition": "ANN- + 12 hex of HMAC-SHA256(salt, source_id)",
        "salt_version": a.salt_version, "records": key}, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"n_records": len(rows), "columns": len(HEADER)}))


if __name__ == "__main__":
    main()
