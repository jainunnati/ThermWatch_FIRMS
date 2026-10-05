"""EVIDENCE_RESEARCH_V1 - human evidence-research workflow. Creates no labels; AI is not an annotator.
Ledger = the existing 15 core evidence-ledger columns (unchanged, first) + extension columns, one row per evidence item
per annotator, plus one ADJUDICATION row per source. A final label exists only on an adjudication row that passes
validate_final_label()."""
import csv, math, hashlib
from collections import Counter, defaultdict

CORE = ["source_id", "proposed_label", "label_tier", "label_confidence", "facility_type", "facility_reference", "facility_distance_km",
        "evidence_type", "evidence_url_or_reference", "evidence_date", "evidence_summary", "counter_evidence", "competing_candidates",
        "reviewer_status", "adjudication_status"]
EXT = ["site_complex_id", "record_kind", "role", "reviewer_id", "evidence_item_id", "evidence_category", "evidence_stance",
       "hotspot_location_link", "evidence_valid_period", "counter_evidence_searched", "conflict_status", "final_label", "final_confidence"]
LEDGER_COLUMNS = CORE + EXT
INSUFFICIENT = {"GEM_PROXIMITY", "FIRMS_PATTERN", "OSM_TAG", "WORLDCOVER_CLASS", "DISTANCE_ONLY"}
CONTEXTUAL = {"FACILITY_DOCUMENTATION"}
LINKING = {"SPATIOTEMPORAL_LINK"}
CATEGORIES = sorted(INSUFFICIENT | CONTEXTUAL | LINKING)
STANCES = {"SUPPORTS", "CONTRADICTS", "NEUTRAL"}
FINAL_CLASSES = {"STEEL_METAL", "THERMAL_POWER", "LNG_GAS", "WILDFIRE", "AGRICULTURAL_BURNING", "INDUSTRIAL_FIRE", "UNKNOWN"}


def validate_final_label(rows, source_id):
    """Return list of blocking reasons for the source's final label ([] = allowed). rows: all ledger rows."""
    R = [r for r in rows if r["source_id"] == source_id]; why = []
    adj = [r for r in R if r["record_kind"] == "ADJUDICATION"]
    items = [r for r in R if r["record_kind"] == "EVIDENCE_ITEM"]
    if not R or not any(r["site_complex_id"] for r in R): why.append("site_complex_id missing")
    if len(adj) != 1 or not adj[0]["final_label"] or adj[0]["adjudication_status"] != "ADJUDICATED": why.append("adjudication missing or incomplete")
    roles = {(r["role"], r["reviewer_id"]) for r in items}
    a1 = {i for ro, i in roles if ro == "ANNOTATOR_1" and i}; a2 = {i for ro, i in roles if ro == "ANNOTATOR_2" and i}
    if not a1 or not a2: why.append("two independent annotators required")
    if a1 & a2: why.append("annotators must be different people")
    if adj and adj[0]["reviewer_id"] in (a1 | a2): why.append("adjudicator must not be an annotator")
    if any(r["reviewer_id"].strip().upper().startswith(("AI", "CHATGPT", "CLAUDE", "GPT", "LLM")) for r in R): why.append("AI is not an annotator/adjudicator")
    if not items: why.append("no evidence recorded")
    for r in items:
        if r["evidence_category"] not in CATEGORIES: why.append(f"unknown evidence category {r['evidence_category']!r}")
        if not r["counter_evidence_searched"].strip(): why.append("counter-evidence search not recorded"); break
    label = adj[0]["final_label"] if adj else ""
    if label and label != "UNKNOWN":
        sup = [r for r in items if r["evidence_stance"] == "SUPPORTS"]
        if not sup: why.append("evidence absent (no supporting item)")
        elif {r["evidence_category"] for r in sup} <= INSUFFICIENT:
            why.append("only insufficient evidence (" + "/".join(sorted({r['evidence_category'] for r in sup})) + ")")
        link = [r for r in sup if r["evidence_category"] in LINKING and r["evidence_url_or_reference"].strip() and r["evidence_date"].strip() and r["hotspot_location_link"].strip()]
        if not link: why.append("no dated, referenced SPATIOTEMPORAL_LINK placing the hotspot on the facility/process area")
        contra = [r for r in items if r["evidence_stance"] == "CONTRADICTS" and r["evidence_category"] not in INSUFFICIENT]
        if contra and adj[0]["conflict_status"] != "RESOLVED": why.append("conflicting independent evidence unresolved")
    if label and label not in FINAL_CLASSES: why.append(f"final label {label!r} not an allowed class")
    return sorted(set(why))


def select_pilot10(r72_rows, r72_priority, exp_rows, exp_priority, complex_of):
    """Deterministic pilot from existing first-of-complex queues. Returns list of dicts with 'pilot_reason'."""
    cell = lambda la, lo: (math.floor(float(la) / 5), math.floor(float(lo) / 5))
    r72 = {r["source_id"]: r for r in r72_rows}; exp = {r["source_id"]: r for r in exp_rows}
    q72 = [r72[p["source_id"]] for p in sorted(r72_priority, key=lambda p: int(p["research_rank"])) if p["first_in_site_group"] == "1"]
    qex = [exp[p["source_id"]] for p in sorted(exp_priority, key=lambda p: int(p["evidence_priority"])) if p["first_in_site_complex"] == "1"]
    out, used_sc, used_cells = [], set(), Counter()
    def add(r, cls, reason, src):
        sc = complex_of(r); out.append({"source": src, "row": r, "cls": cls, "sc": sc, "reason": reason}); used_sc.add(sc)
        used_cells[cell(r.get("source_lat"), r.get("source_lon"))] += 1
    def pick(queue, cls_key, cls, n, reason, src):
        k = 0
        for prefer_new in (True, False):
            for r in queue:
                if k >= n: return
                if r[cls_key] != cls or complex_of(r) in used_sc: continue
                if prefer_new and used_cells[cell(r["source_lat"], r["source_lon"])]: continue
                add(r, cls, reason, src); k += 1
    pick(q72, "candidate_class", "STEEL_METAL", 3, "steel: REVIEW72 first-of-complex queue", "REVIEW72")
    pick(q72, "candidate_class", "THERMAL_POWER", 3, "thermal power: REVIEW72 first-of-complex queue", "REVIEW72")
    pick(qex, "proposed_context_class", "UNRESOLVED_MULTI_TYPE", 1, "competing steel+coal facilities (ambiguous case)", "LABEL_EXPANSION_V1")
    div = [(r, r["candidate_class"], "REVIEW72") for r in q72] + [(r, r["proposed_context_class"], "LABEL_EXPANSION_V1") for r in qex if r["candidate_decision"] == "REVIEW"]
    for prefer_new in (True, False):
        for r, cls, src in div:
            if len(out) >= 10: break
            if complex_of(r) in used_sc: continue
            if prefer_new and used_cells[cell(r["source_lat"], r["source_lon"])]: continue
            add(r, cls, "site/geographic diversity (new 5-degree cell)" if prefer_new else "site diversity (new complex)", src)
    return out
