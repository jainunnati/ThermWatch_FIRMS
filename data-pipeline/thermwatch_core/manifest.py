"""Reproducible run manifest / provenance (Step 6D).

Records WHAT was run on WHICH bytes with WHICH code and parameters. `manifest_sha256` hashes the canonical JSON
of everything except wall-clock fields (created_utc, host), so two runs of identical inputs/code/params give the
same hash. The code fingerprint hashes every thermwatch_core/*.py file.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .schema import PIPELINE_VERSION, SCHEMA_VERSION

MANIFEST_VERSION = "run-manifest-1"
_VOLATILE = ("created_utc", "environment")


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def code_fingerprint(package_dir=None) -> dict:
    d = Path(package_dir) if package_dir else Path(__file__).resolve().parent
    files = {p.name: sha256_file(p) for p in sorted(d.glob("*.py"))}
    agg = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"files": files, "aggregate_sha256": agg}


def _jsonable(x):
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return _jsonable(dataclasses.asdict(x))
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted(_jsonable(v) for v in x)
    if isinstance(x, datetime):
        return x.isoformat()
    if isinstance(x, Path):
        return str(x)
    return x


def _git_commit(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:
        return None


def _pkg_versions():
    out = {}
    for m in ("numpy", "pandas", "sklearn"):
        try:
            out[m] = __import__(m).__version__
        except Exception:
            out[m] = None
    return out


def build_run_manifest(*, run_name: str, inputs, params=None, outputs=None, reference_time_utc=None, notes=None) -> dict:
    """inputs: list of paths or (label, path). Hashes the bytes. outputs: optional list of paths (hashed if present)."""
    def entry(i):
        label, path = (i if isinstance(i, tuple) else (Path(i).name, i))
        p = Path(path)
        return {"label": label, "sha256": sha256_file(p), "bytes": p.stat().st_size}
    m = {
        "manifest_version": MANIFEST_VERSION, "run_name": run_name,
        "pipeline_version": PIPELINE_VERSION, "schema_version": SCHEMA_VERSION,
        "code": code_fingerprint(), "inputs": [entry(i) for i in inputs],
        "parameters": _jsonable(params or {}),
        "reference_time_utc": _jsonable(reference_time_utc),
        "outputs": [entry(o) for o in (outputs or []) if Path(o if not isinstance(o, tuple) else o[1]).exists()],
        "notes": list(notes or []),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(),
                        "packages": _pkg_versions(), "git_commit": _git_commit(Path(__file__).resolve().parent)},
    }
    m["manifest_sha256"] = manifest_hash(m)
    return m


def manifest_hash(m: dict) -> str:
    body = {k: v for k, v in m.items() if k not in _VOLATILE and k != "manifest_sha256"}
    return hashlib.sha256(json.dumps(_jsonable(body), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
