"""Cross-source physical-observation identity, deduplication and the alias ledger (Step 6D).

The same physical detection can arrive twice: inside two overlapping raw files, or as a raw FIRMS row AND a
cleaned-export row. `Observation.physical_key` (mode/file/attribute-free) identifies it. This module collapses
each key to ONE canonical observation and records every dropped copy in an alias ledger, so nothing is
silently lost or double counted.

Canonical choice is deterministic and independent of input order:
  1. more raw-provenance fields present (scan, track, version, secondary brightness) wins - raw beats clean;
  2. then source_file (lexicographic), then row_number, then observation_id.
No attribute is merged or invented across copies. If copies DISAGREE on a measured attribute the conflict is
recorded in the ledger (relation ATTRIBUTE_CONFLICT) - the canonical copy's values are kept untouched.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

_PROVENANCE_FIELDS = ("scan_km", "track_km", "version_raw", "brightness_k_secondary")
_COMPARED = (("frp_mw", 1e-6), ("brightness_k", 1e-6), ("day_night", None), ("confidence_class", None))


def provenance_richness(o) -> int:
    return sum(1 for f in _PROVENANCE_FIELDS if getattr(o, f) is not None)


def _canonical_rank(o):
    return (-provenance_richness(o), o.source_file or "", o.row_number if o.row_number is not None else -1,
            o.observation_id)


def attribute_conflicts(a, b) -> list:
    out = []
    for f, tol in _COMPARED:
        x, y = getattr(a, f), getattr(b, f)
        if x is None or y is None:
            continue                       # one side missing is not a conflict
        if (abs(x - y) > tol) if tol is not None else (x != y):
            out.append({"field": f, "canonical": x, "alias": y})
    return out


@dataclass
class DedupResult:
    observations: list                      # canonical observations, sorted by (timestamp, physical_key)
    alias_ledger: list                      # one dict per DROPPED copy
    stats: dict = field(default_factory=dict)


def dedup_cross_source(observations) -> DedupResult:
    groups = defaultdict(list)
    for o in observations:
        groups[o.physical_key].append(o)
    canon, ledger, relations, pairs = [], [], Counter(), Counter()
    for key in sorted(groups):
        g = sorted(groups[key], key=_canonical_rank)
        c = g[0]
        canon.append(c)
        for a in g[1:]:
            conf = attribute_conflicts(c, a)
            rel = "ATTRIBUTE_CONFLICT" if conf else ("SAME_FILE_REPEAT" if a.source_file == c.source_file else "IDENTICAL_COPY")
            relations[rel] += 1
            pairs[(c.source_file, a.source_file)] += 1
            ledger.append({
                "physical_key": key, "relation": rel,
                "canonical_observation_id": c.observation_id, "canonical_source_file": c.source_file,
                "canonical_row": c.row_number, "canonical_data_mode": c.data_mode.value,
                "alias_observation_id": a.observation_id, "alias_source_file": a.source_file,
                "alias_row": a.row_number, "alias_data_mode": a.data_mode.value,
                "attribute_conflicts": conf,
            })
    canon.sort(key=lambda o: (o.timestamp_utc, o.physical_key))
    stats = {"n_input": len(observations), "n_unique_physical": len(canon), "n_alias_rows": len(ledger),
             "relations": dict(relations),
             "alias_file_pairs": [{"canonical_file": k[0], "alias_file": k[1], "n": v} for k, v in sorted(pairs.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))],
             "n_attribute_conflicts": relations.get("ATTRIBUTE_CONFLICT", 0)}
    assert stats["n_input"] == stats["n_unique_physical"] + stats["n_alias_rows"]
    return DedupResult(canon, ledger, stats)
