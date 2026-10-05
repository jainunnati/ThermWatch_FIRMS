"""Streaming (low-memory) 6D source/event formation for the full Jan-Oct dataset (M1 / Step C).

`events.form_events` is NOT modified and remains the ORACLE. This module re-implements the same decision rules over a
time-ordered stream using compact arrays instead of Observation objects, and is verified against the oracle
(see tests/test_streaming.py and m1_equivalence.py).

Semantics preserved (same constants, same arithmetic, same order):
  * processing order = (timestamp, physical_key); dedup is the existing `identity.dedup_cross_source`, applied per UTC day
    bucket (a physical key contains the acquisition minute, so all copies of one key are always in the same day);
  * 1.0e-2 degree cell hash; candidate = any earlier member within source_radius_m (haversine);
  * candidate valid only if the observation is within max_source_extent_m of the source's running centroid;
  * nearest valid source, tie -> smaller source_id; ambiguity logged; new source id = events._new_source_id (reused);
  * new event when the gap to the source's previous observation exceeds event_window_hours;
  * as-of exclusion (observations after as_of are skipped and counted).
One purely computational addition: a candidate whose |dlat| exceeds PREFILTER_DEG is skipped before haversine.
It can never change a result (great-circle distance >= R*|dlat|; 0.004 deg ~ 445 m > 375 m) - equivalence tests cover it.

NOT supported (raises): pixel_aware=True (needs a global pre-pass over all pixel sizes), non-real data modes.
Source-file names stored in Observation.source_file are manifest-relative basenames, so the dedup tie-break rule
(provenance richness, then source_file, then row, then observation_id - UNCHANGED from 6D) does not depend on directories.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import pickle
import re
import resource
import time
from array import array
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .events import EventParams, _new_source_id
from .geo import haversine_m
from .identity import dedup_cross_source
from .ingest import load_firms_csv
from .manifest import code_fingerprint, sha256_file
from .schema import DataMode, ModeMixingError, make_physical_key
from .validation import ValidationParams, normalize_and_validate

REFERENCE_TIME_UTC = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)   # owner-approved fixed reference time
CELL = 0.01
PREFILTER_DEG = 0.004
MAX_LABELS = 8
_MASK = (1 << 256) - 1
_FILE_RE = re.compile(r"^(VIIRS_[A-Z0-9]+_(SP|NRT))_(\d{4}-\d{2}-\d{2})_(\d+)days\.csv$")
TIE_BREAK_DOC = ("dedup canonical choice (UNCHANGED 6D rule): 1) more raw-provenance fields present (scan, track, version, "
                 "secondary brightness); 2) source_file lexicographic (manifest basename); 3) row_number; 4) observation_id. "
                 "No SP/NRT preference is applied. Note 'NRT' sorts before 'SP' in file names, so an SP/NRT duplicate with equal "
                 "provenance would keep the NRT copy; there are 0 such overlaps in the Jan-Oct dataset.")


# ----------------------------------------------------------------------------- canonical digests
class MultisetDigest:
    """Order-independent digest of a set of lines (sum of SHA-256 values mod 2^256) plus the line count.
    This is a canonical-equivalence tool, NOT a byte-identity claim about any serialized file."""
    def __init__(self):
        self.n, self.acc = 0, 0

    def add(self, line: str):
        self.n += 1
        self.acc = (self.acc + int.from_bytes(hashlib.sha256(line.encode()).digest(), "big")) & _MASK

    def hexdigest(self) -> str:
        return f"{self.n}:{self.acc:064x}"


def _j(x):
    return json.dumps(x, separators=(",", ":"))


def line_source(sid, anchor, n, cen, bb, extent, first_iso, last_iso, eids):
    return _j([sid, anchor, n, list(cen), list(bb), extent, first_iso, last_iso, list(eids)])


def line_event(eid, sid, n, start_iso, end_iso, cen, bb, state, sensors):
    return _j([eid, sid, n, start_iso, end_iso, list(cen), list(bb), state, sorted(sensors.items())])


def line_assign(pk, sid, eid):
    return f"{pk}|{sid}|{eid}"


def line_ambiguity(oid, cands, assigned):
    return _j([oid, sorted(cands.items()), assigned])


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def oracle_digests(result) -> dict:
    """Canonical digests of an `events.EventFormationResult` (the oracle), using the same line builders."""
    ds = {k: MultisetDigest() for k in ("sources", "events", "assignments", "ambiguity")}
    for sid, s in result.sources.items():
        bb = s.bbox
        ds["sources"].add(line_source(sid, s.anchor_physical_key, len(s.observation_ids), s.centroid,
                                      (bb["lat"][0], bb["lat"][1], bb["lon"][0], bb["lon"][1]), s.extent_m,
                                      s.first_utc.isoformat(), s.last_utc.isoformat(), s.event_ids))
    for eid, e in result.events.items():
        bb = e.bbox
        ds["events"].add(line_event(eid, e.source_id, len(e.observation_ids), e.start_utc.isoformat(), e.end_utc.isoformat(),
                                    e.centroid, (bb["lat"][0], bb["lat"][1], bb["lon"][0], bb["lon"][1]), e.state, e.sensors))
    for oid, (sid, eid) in result.assignment.items():
        ds["assignments"].add(line_assign(result.observations[oid].physical_key, sid, eid))
    for a in result.diagnostics["ambiguous_assignments"]:
        ds["ambiguity"].add(line_ambiguity(a["observation_id"], a["candidates"], a["assigned"]))
    d = result.diagnostics
    scalars = {k: d[k] for k in ("n_observations", "n_sources", "n_events", "singleton_source_fraction",
                                 "events_per_source_max", "n_ambiguous_assignments", "extent_cap_rejections",
                                 "n_source_id_collisions", "n_duplicate_physical_keys", "n_excluded_after_as_of")}
    return {"digests": {k: v.hexdigest() for k, v in ds.items()}, "scalars": scalars}


# ----------------------------------------------------------------------------- streaming core
class StreamingFormer:
    def __init__(self, params: EventParams = EventParams(), as_of_utc=REFERENCE_TIME_UTC, allow_mixed_modes=False,
                 on_ambiguity=None):
        if params.pixel_aware:
            raise NotImplementedError("streaming path does not support pixel_aware (needs a global pre-pass)")
        self.p, self.as_of = params, as_of_utc
        self.as_of_ts = int(as_of_utc.timestamp())
        self.allow_mixed = allow_mixed_modes
        self.modes = set()
        self.on_ambiguity = on_ambiguity
        self.kl_cache = {}
        # per observation (processing order)
        self.o_lat, self.o_lon = array("d"), array("d")
        self.o_ts, self.o_src, self.o_ep = array("q"), array("I"), array("I")
        self.o_sensor, self.o_prod = array("B"), array("B")
        self.sensor_tab, self.prod_tab = {}, {}
        # per source
        self.sids, self.sid_idx = [], {}
        self.s_latsum, self.s_lonsum = array("d"), array("d")
        self.s_n, self.s_nep, self.s_curep = array("I"), array("I"), array("I")
        self.s_anchor, self.s_last = array("I"), array("q")
        self.s_minlat, self.s_maxlat, self.s_minlon, self.s_maxlon = array("d"), array("d"), array("d"), array("d")
        # per episode (event)
        self.e_src, self.e_ord, self.e_n = array("I"), array("I"), array("I")
        self.e_start, self.e_end = array("q"), array("q")
        self.e_minlat, self.e_maxlat, self.e_minlon, self.e_maxlon = array("d"), array("d"), array("d"), array("d")
        self.e_labels = array("I")
        self.label_tab = {}
        self.index = {}
        self.collisions, self.n_ambiguous, self.extent_rej, self.n_after = [], 0, 0, 0
        self.last_key = None
        self.n_added = 0

    # -- helpers
    @staticmethod
    def _tab(tab, k, cap=255):
        v = tab.get(k)
        if v is None:
            v = tab[k] = len(tab)
            if v > cap:
                raise OverflowError("lookup table overflow")
        return v

    def add(self, o):
        if not o.data_mode.is_real_firms:
            raise ModeMixingError(f"streaming path accepts real FIRMS modes only, got {o.data_mode.value}")
        self.modes.add(o.data_mode)
        if len(self.modes) > 1 and not self.allow_mixed:
            raise ModeMixingError(f"Event formation refuses mixed data modes: {sorted(m.value for m in self.modes)}")
        ts = int(o.timestamp_utc.timestamp())
        pk = o.physical_key
        if self.last_key is not None and (ts, pk) < self.last_key:
            raise ValueError("observations must arrive in (timestamp, physical_key) order")
        if self.last_key is not None and (ts, pk) == self.last_key:
            raise ValueError(f"duplicate physical key reached the stream (dedup first): {pk}")
        self.last_key = (ts, pk)
        if ts > self.as_of_ts:
            self.n_after += 1
            return
        P = self.p
        lat, lon = o.latitude, o.longitude
        ci, cj = math.floor(lat / CELL), math.floor(lon / CELL)
        kl = int(math.ceil(P.source_radius_m / (CELL * 111_000.0))) + 1
        kn = int(math.ceil(P.source_radius_m / (CELL * 111_000.0 * max(0.05, math.cos(math.radians(lat)))))) + 1
        o_lat, o_lon, o_src, index = self.o_lat, self.o_lon, self.o_src, self.index
        cands = {}
        for di in range(-kl, kl + 1):
            base = (ci + di + 10000) * 40000 + 20000
            for dj in range(-kn, kn + 1):
                arr = index.get(base + cj + dj)
                if arr is None:
                    continue
                for mi in arr:
                    mlat = o_lat[mi]
                    if abs(lat - mlat) > PREFILTER_DEG:
                        continue
                    d = haversine_m(lat, lon, mlat, o_lon[mi])
                    if d <= P.source_radius_m:
                        s = o_src[mi]
                        if d < cands.get(s, float("inf")):
                            cands[s] = d
        valid = {}
        for s, d in cands.items():
            n = self.s_n[s]
            clat, clon = self.s_latsum[s] / n, self.s_lonsum[s] / n
            if haversine_m(lat, lon, clat, clon) <= P.max_source_extent_m:
                valid[s] = d
            else:
                self.extent_rej += 1
        sids = self.sids
        if valid:
            s = min(valid, key=lambda k: (valid[k], sids[k]))
            if len(valid) > 1:
                self.n_ambiguous += 1
                if self.on_ambiguity:
                    self.on_ambiguity(o.observation_id, {sids[k]: round(v, 1) for k, v in sorted(valid.items(), key=lambda kv: sids[kv[0]])}, sids[s])
        else:
            sid = _new_source_id(pk, self.sid_idx, self.collisions)
            s = len(sids)
            sids.append(sid)
            self.sid_idx[sid] = s
            self.s_latsum.append(0.0); self.s_lonsum.append(0.0)
            self.s_n.append(0); self.s_nep.append(0); self.s_curep.append(0)
            self.s_anchor.append(len(self.o_ts)); self.s_last.append(ts)
            self.s_minlat.append(lat); self.s_maxlat.append(lat); self.s_minlon.append(lon); self.s_maxlon.append(lon)
        gap_h = (ts - self.s_last[s]) / 3600.0 if self.s_n[s] else None
        label = o.sensor_label or "UNKNOWN"
        if self.s_nep[s] == 0 or gap_h > P.event_window_hours:
            e = len(self.e_src)
            self.s_nep[s] += 1
            self.s_curep[s] = e
            self.e_src.append(s); self.e_ord.append(self.s_nep[s]); self.e_n.append(0)
            self.e_start.append(ts); self.e_end.append(ts)
            self.e_minlat.append(lat); self.e_maxlat.append(lat); self.e_minlon.append(lon); self.e_maxlon.append(lon)
            self.e_labels.extend([0] * MAX_LABELS)
        else:
            e = self.s_curep[s]
        # accumulate (same addition order as the oracle)
        self.s_n[s] += 1
        self.s_latsum[s] += lat; self.s_lonsum[s] += lon; self.s_last[s] = ts
        if lat < self.s_minlat[s]: self.s_minlat[s] = lat
        if lat > self.s_maxlat[s]: self.s_maxlat[s] = lat
        if lon < self.s_minlon[s]: self.s_minlon[s] = lon
        if lon > self.s_maxlon[s]: self.s_maxlon[s] = lon
        self.e_n[e] += 1
        self.e_end[e] = ts
        if lat < self.e_minlat[e]: self.e_minlat[e] = lat
        if lat > self.e_maxlat[e]: self.e_maxlat[e] = lat
        if lon < self.e_minlon[e]: self.e_minlon[e] = lon
        if lon > self.e_maxlon[e]: self.e_maxlon[e] = lon
        li = self._tab(self.label_tab, label, MAX_LABELS - 1)
        self.e_labels[e * MAX_LABELS + li] += 1
        mi = len(self.o_ts)
        o_lat.append(lat); o_lon.append(lon); self.o_ts.append(ts); o_src.append(s); self.o_ep.append(e)
        self.o_sensor.append(self._tab(self.sensor_tab, (o.instrument, o.satellite)))
        self.o_prod.append(self._tab(self.prod_tab, (o.source_product, o.data_mode.value)))
        key = (ci + 10000) * 40000 + cj + 20000
        a = index.get(key)
        if a is None:
            a = index[key] = array("I")
        a.append(mi)
        self.n_added += 1

    def _pk(self, i):
        ins, sat = self._sensor_by_code[self.o_sensor[i]]
        return make_physical_key(ins, sat, datetime.fromtimestamp(self.o_ts[i], timezone.utc), self.o_lat[i], self.o_lon[i])

    def finalize(self, emit_source, emit_event, emit_assign) -> dict:
        """Emit canonical records through callbacks; returns the diagnostics dict (same keys/semantics as the oracle)."""
        self._sensor_by_code = {v: k for k, v in self.sensor_tab.items()}
        prod_by_code = {v: k for k, v in self.prod_tab.items()}
        labels = {v: k for k, v in self.label_tab.items()}
        n_src, n_obs, n_ep = len(self.sids), len(self.o_ts), len(self.e_src)
        # members grouped by source / by episode (stable counting sort => processing order inside each group)
        def group(keys, n_groups, counts):
            offs = array("Q", [0]) * (n_groups + 1)
            for g in range(n_groups):
                offs[g + 1] = offs[g] + counts[g]
            fill = array("Q", offs[:-1])
            order = array("I", [0]) * n_obs
            for i in range(n_obs):
                g = keys[i]
                order[fill[g]] = i
                fill[g] += 1
            return offs, order
        offs, order = group(self.o_src, n_src, self.s_n)
        e_offs, e_order = group(self.o_ep, n_ep, self.e_n)
        # NOTE: centroids use builtin sum() over members in processing order, exactly like geo.mean_centroid. CPython >= 3.12
        # sums floats with compensated summation, so a naive running sum differs in the last bit; the in-loop running sums
        # (used for the 2000 m extent decision) are naive on purpose because the oracle's loop is naive too.
        singles, max_ev = 0, 0
        for s in range(n_src):
            n = self.s_n[s]
            mem = order[offs[s]:offs[s + 1]]
            clat, clon = sum(self.o_lat[i] for i in mem) / n, sum(self.o_lon[i] for i in mem) / n
            ext = max(haversine_m(self.o_lat[i], self.o_lon[i], clat, clon) for i in mem)
            sid = self.sids[s]
            eids = [f"EVT-{sid[4:]}-{k:03d}" for k in range(1, self.s_nep[s] + 1)]
            a = self.s_anchor[s]
            emit_source(sid, self._pk(a), n, (clat, clon),
                        (self.s_minlat[s], self.s_maxlat[s], self.s_minlon[s], self.s_maxlon[s]), ext,
                        _iso(self.o_ts[a]), _iso(self.s_last[s]), eids)
            singles += (n == 1)
            max_ev = max(max_ev, len(eids))
        for e in range(n_ep):
            s = self.e_src[e]
            n = self.e_n[e]
            emem = e_order[e_offs[e]:e_offs[e + 1]]
            sens = {labels[k]: self.e_labels[e * MAX_LABELS + k] for k in range(MAX_LABELS)
                    if k in labels and self.e_labels[e * MAX_LABELS + k]}
            state = "active" if (self.as_of_ts - self.e_end[e]) / 3600.0 <= self.p.event_window_hours else "archived"
            emit_event(f"EVT-{self.sids[s][4:]}-{self.e_ord[e]:03d}", self.sids[s], n, _iso(self.e_start[e]), _iso(self.e_end[e]),
                       (sum(self.o_lat[i] for i in emem) / n, sum(self.o_lon[i] for i in emem) / n),
                       (self.e_minlat[e], self.e_maxlat[e], self.e_minlon[e], self.e_maxlon[e]), state, sens)
        for i in range(n_obs):
            s, e = self.o_src[i], self.o_ep[i]
            emit_assign(self._pk(i), self.sids[s], f"EVT-{self.sids[s][4:]}-{self.e_ord[e]:03d}", *prod_by_code[self.o_prod[i]])
        return {"n_observations": n_obs, "n_sources": n_src, "n_events": n_ep,
                "singleton_source_fraction": (singles / n_src) if n_src else None,
                "events_per_source_max": max_ev, "n_ambiguous_assignments": self.n_ambiguous,
                "extent_cap_rejections": self.extent_rej, "n_source_id_collisions": len(self.collisions),
                "n_duplicate_physical_keys": 0, "n_excluded_after_as_of": self.n_after}


# ----------------------------------------------------------------------------- manifest + staging pipeline
def build_input_manifest(raw_dir) -> list:
    """One entry per CSV. Product/grade/satellite are parsed from the file name; an unrecognised name is refused."""
    out = []
    for p in sorted(Path(raw_dir).glob("*.csv")):
        m = _FILE_RE.match(p.name)
        if not m:
            raise ValueError(f"unrecognised FIRMS file name (refusing to guess product/grade): {p.name}")
        product, grade = m.group(1), m.group(2)
        out.append({"file": p.name, "path": str(p), "sha256": sha256_file(p), "bytes": p.stat().st_size,
                    "product": product, "grade": grade, "satellite_stream": product.split("_")[1],
                    "start_date": m.group(3), "days": int(m.group(4)),
                    "mode": (DataMode.HISTORICAL if grade == "SP" else DataMode.NRT).value})
    return out


def load_validated(entry, vparams=None, ref=REFERENCE_TIME_UTC):
    """Existing loader + validator for one manifest entry (shared by the streaming stage and the in-memory oracle)."""
    vparams = vparams or ValidationParams(reference_time_utc=ref)
    b = load_firms_csv(entry["path"], DataMode(entry["mode"]), product=entry["product"], ingested_utc=ref)
    b.source_file = entry["file"]                 # manifest-relative, directory independent
    return normalize_and_validate(b, vparams)


def _peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def stage_files(entries, workdir, outdir, obs_filter=None, log=print):
    days_dir = Path(workdir) / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    for f in days_dir.glob("*.pkl"):
        f.unlink()
    per_file, flags_total, excl_total = [], Counter(), Counter()
    grade_mismatch = Counter()
    with gzip.open(Path(outdir) / "exclusion_ledger.jsonl.gz", "wt") as led, gzip.open(Path(outdir) / "field_flags.jsonl.gz", "wt") as fl:
        for k, ent in enumerate(entries, 1):
            rep = load_validated(ent)
            for e in rep.exclusions:
                led.write(_j({"file": ent["file"], "row": e.row_number, "reason": e.reason, "detail": e.detail}) + "\n")
            for oid, flag, detail in rep.flags:
                fl.write(_j([ent["file"], oid, flag, detail]) + "\n")
            flags_total.update(rep.stats["flags_by_reason"]); excl_total.update(rep.stats["exclusions_by_reason"])
            obs = rep.observations
            n_filtered = 0
            if obs_filter is not None:
                kept = [o for o in obs if obs_filter(o)]
                n_filtered, obs = len(obs) - len(kept), kept
            for o in obs:       # grade cross-check: file-name grade vs the FIRMS `version` column (flag only)
                is_nrt_ver = "NRT" in (o.version_raw or "").upper()
                if is_nrt_ver != (ent["grade"] == "NRT"):
                    grade_mismatch[ent["file"]] += 1
            by_day = defaultdict(list)
            for o in obs:
                by_day[o.timestamp_utc.date().isoformat()].append(o)
            for d, lst in by_day.items():
                with open(days_dir / f"{d}.pkl", "ab") as fh:
                    pickle.dump(lst, fh, protocol=4)
            st = rep.stats
            per_file.append({"file": ent["file"], "sha256": ent["sha256"], "product": ent["product"], "grade": ent["grade"],
                             "mode": ent["mode"], "n_input": st["n_input"], "n_valid": st["n_valid"], "n_excluded": st["n_excluded"],
                             "status": st["status"], "n_dropped_by_obs_filter": n_filtered})
            if k % 20 == 0:
                log(f"  staged {k}/{len(entries)} files, peak RSS {_peak_mb():.0f} MB")
    return {"per_file": per_file, "flags_by_reason": dict(flags_total), "exclusions_by_reason": dict(excl_total),
            "grade_version_mismatch_rows": sum(grade_mismatch.values()), "grade_version_mismatch_files": dict(grade_mismatch)}


def _iter_days(workdir):
    for p in sorted((Path(workdir) / "days").glob("*.pkl")):
        lst = []
        with open(p, "rb") as fh:
            while True:
                try:
                    lst.extend(pickle.load(fh))
                except EOFError:
                    break
        yield p.stem, lst


def run_stream(raw_dir, outdir, workdir, *, entries=None, obs_filter=None, params=EventParams(), write_outputs=True,
               log=print, run_name="m1-stream"):
    """Manifest -> per-file validation -> UTC-day buckets -> per-day dedup -> streaming formation -> outputs + digests."""
    t0 = time.time()
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    entries = entries if entries is not None else build_input_manifest(raw_dir)
    t_manifest = time.time() - t0
    t1 = time.time()
    staging = stage_files(entries, workdir, outdir, obs_filter, log)
    t_stage = time.time() - t1
    t2 = time.time()
    digs = {k: MultisetDigest() for k in ("sources", "events", "assignments", "ambiguity")}
    amb_f = gzip.open(outdir / "ambiguous_assignments.jsonl.gz", "wt") if write_outputs else None

    def on_amb(oid, cands, assigned):
        line = line_ambiguity(oid, cands, assigned)
        digs["ambiguity"].add(line)
        if amb_f: amb_f.write(line + "\n")

    former = StreamingFormer(params, REFERENCE_TIME_UTC, allow_mixed_modes=True, on_ambiguity=on_amb)
    alias_f = gzip.open(outdir / "alias_ledger.jsonl.gz", "wt") if write_outputs else None
    dd = {"n_input": 0, "n_unique_physical": 0, "n_alias_rows": 0, "relations": Counter()}
    for day, lst in _iter_days(workdir):
        r = dedup_cross_source(lst)
        dd["n_input"] += r.stats["n_input"]; dd["n_unique_physical"] += r.stats["n_unique_physical"]
        dd["n_alias_rows"] += r.stats["n_alias_rows"]; dd["relations"].update(r.stats["relations"])
        if alias_f:
            for a in r.alias_ledger:
                alias_f.write(_j(a) + "\n")
        for o in r.observations:
            former.add(o)
        del lst, r
    if alias_f: alias_f.close()
    if amb_f: amb_f.close()
    t_form = time.time() - t2
    t3 = time.time()
    fs = gzip.open(outdir / "sources.jsonl.gz", "wt") if write_outputs else None
    fe = gzip.open(outdir / "events.jsonl.gz", "wt") if write_outputs else None
    fa = gzip.open(outdir / "assignments.tsv.gz", "wt") if write_outputs else None
    if fa: fa.write("physical_key\tsource_id\tevent_id\tsource_product\tdata_mode\n")

    def e_src(*a):
        ln = line_source(*a); digs["sources"].add(ln)
        if fs: fs.write(ln + "\n")

    def e_evt(*a):
        ln = line_event(*a); digs["events"].add(ln)
        if fe: fe.write(ln + "\n")

    def e_asg(pk, sid, eid, prod, mode):
        digs["assignments"].add(line_assign(pk, sid, eid))
        if fa: fa.write(f"{pk}\t{sid}\t{eid}\t{prod}\t{mode}\n")

    diag = former.finalize(e_src, e_evt, e_asg)
    for f in (fs, fe, fa):
        if f: f.close()
    t_final = time.time() - t3
    summary = {
        "run_name": run_name, "reference_time_utc": REFERENCE_TIME_UTC.isoformat(),
        "params": {"source_radius_m": params.source_radius_m, "event_window_hours": params.event_window_hours,
                   "max_source_extent_m": params.max_source_extent_m, "pixel_aware": params.pixel_aware,
                   "mixed_real_modes_allowed_internally": True},
        "dedup_tie_break": TIE_BREAK_DOC,
        "inputs": [{k: e[k] for k in ("file", "sha256", "bytes", "product", "grade", "mode")} for e in entries],
        "staging": staging, "dedup": {**dd, "relations": dict(dd["relations"])},
        "diagnostics": diag, "source_id_collisions": former.collisions,
        "digests": {k: v.hexdigest() for k, v in digs.items()},
        "timing_s": {"manifest_sha256": round(t_manifest, 1), "stage_validate": round(t_stage, 1),
                     "dedup_and_form": round(t_form, 1), "finalize_emit": round(t_final, 1), "total": round(time.time() - t0, 1)},
        "peak_rss_mb": round(_peak_mb(), 0),
        "code": code_fingerprint(),
    }
    if write_outputs:
        (outdir / "stream_run_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    return summary
