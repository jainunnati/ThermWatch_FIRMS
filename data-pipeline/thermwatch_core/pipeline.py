"""Orchestration: RawBatch -> validated -> sources/events -> list of §14 objects."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .assessment import build_assessment
from .events import EventParams, form_events
from .facility import FacilityDataset, FacilityParams, associate_event, normalize_facilities, to_facility_attribution
from .ingest import RawBatch
from .validation import ValidationParams, normalize_and_validate


def run_core(batch: RawBatch, *, validation_params=ValidationParams(), event_params=EventParams(),
             as_of_utc=None, opportunity_by_source=None, facilities=None,
             facility_params=FacilityParams(), **assess_kwargs):
    """Returns (assessments, validation_report, event_result). Only the most recent event of each source
    is assessed by default (`latest_only`); older events remain available in event_result."""
    report = normalize_and_validate(batch, validation_params)
    result = form_events(report.observations, event_params, as_of_utc=as_of_utc)
    processed = datetime.now(timezone.utc)

    # Normalize the supplied facility dataset once. Association itself is still
    # evaluated separately for each assessed event/source. None means that no
    # facility dataset was supplied; an empty supplied dataset remains an explicit
    # NOT_COMPUTED state under the facility module's contract.
    facility_dataset = facilities if isinstance(facilities, FacilityDataset) else (
        normalize_facilities(facilities) if facilities is not None else None
    )

    # Backward-compatible test/integration hook: older callers could inject a
    # pre-built §14 facility object through `facility=`. Keep that path only when
    # no dataset is supplied; production dataset wiring uses `facilities=`.
    legacy_facility = assess_kwargs.pop("facility", None)
    if facilities is not None and legacy_facility is not None:
        raise ValueError("Pass either facilities=... or a pre-built facility=..., not both")

    out = []
    for sid, src in result.sources.items():
        eid = src.event_ids[-1]
        facility_attr = (
            legacy_facility if legacy_facility is not None else
            to_facility_attribution(associate_event(result, eid, facility_dataset, facility_params))
        )
        out.append(build_assessment(
            result, eid, opportunity=(opportunity_by_source or {}).get(sid),
            facility=facility_attr, processed_utc=processed, validation_stats=report.stats,
            **assess_kwargs))
    return out, report, result


def write_outputs(assessments, report, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "assessments.json").write_text(json.dumps(assessments, indent=1))
    (outdir / "validation_report.json").write_text(json.dumps(report.stats, indent=1))
    with open(outdir / "exclusion_ledger.jsonl", "w") as f:
        for e in report.ledger():
            f.write(json.dumps(e) + "\n")
    with open(outdir / "field_flags.jsonl", "w") as f:
        for oid, flag, detail in report.flags:
            f.write(json.dumps({"observation_id": oid, "flag": flag, "detail": detail}) + "\n")
