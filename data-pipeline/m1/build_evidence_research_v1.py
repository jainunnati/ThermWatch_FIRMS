"""Build EVIDENCE_RESEARCH_V1 pilot artifacts (deterministic; no labels).  python3 m1/build_evidence_research_v1.py OUT_DIR"""
import csv, html, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, "/home/claude/gem")
import evidence_research_v1 as ER, label_expansion_v1 as LX, register_match as RM
R72D = "/mnt/user-data/outputs/review72_evidence_v1"; LXD = "/mnt/user-data/outputs/label_expansion_v1"
rd = lambda p: list(csv.DictReader(open(p)))


def page(c, r):
    f = {k: html.escape(str(v)) for k, v in c.items()}
    opts = "".join(f"<option>{x}</option>" for x in [""] + ER.CATEGORIES)
    stance = "".join(f"<option>{x}</option>" for x in ["", "SUPPORTS", "CONTRADICTS", "NEUTRAL"])
    cls = "".join(f"<option>{x}</option>" for x in [""] + sorted(ER.FINAL_CLASSES))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evidence research {f['source_id']}</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--line:#ccc;--warn:#fff4e5;--wb:#c77700}}@media (prefers-color-scheme:dark){{:root{{--bg:#141414;--fg:#eee;--line:#444;--warn:#2b2110;--wb:#e0a040}}}}
body{{font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;max-width:980px;background:var(--bg);color:var(--fg)}}
.warn{{background:var(--warn);border-left:4px solid var(--wb);padding:10px 14px}} fieldset{{border:1px solid var(--line);margin:12px 0}}
label{{display:block;margin:6px 0}} input,select,textarea{{width:100%;box-sizing:border-box;font:inherit}} textarea{{min-height:60px}}
table{{border-collapse:collapse}} td{{border:1px solid var(--line);padding:4px 8px}} pre{{white-space:pre-wrap;overflow-x:auto}}</style></head><body>
<h1>Evidence research: <code>{f['source_id']}</code></h1>
<div class="warn"><strong>GEM proximity, FIRMS behaviour, OSM tags, WorldCover class and distance are each insufficient.</strong>
A label needs a dated, referenced item that places <em>this hotspot</em> on the facility/process area (SPATIOTEMPORAL_LINK). Record counter-evidence searches every time.
AI/chatbot output is not evidence and AI is not an annotator. Work independently; do not look at the other annotator's entries.</div>
<h2>Candidate facts (not evidence of attribution)</h2><table>
<tr><td>Site complex (mandatory unit of independence)</td><td><strong>{f['site_complex_id']}</strong></td></tr>
<tr><td>Facility candidate</td><td>{f['facility_name']} ({f['facility_type']})</td></tr><tr><td>Distance</td><td>{f['distance_km']} km</td></tr>
<tr><td>Hotspot centroid</td><td>{f['source_lat']}, {f['source_lon']}</td></tr><tr><td>Facility point</td><td>{f['facility_lat']}, {f['facility_lon']}</td></tr>
<tr><td>Competing facilities ≤2 km</td><td>{f['competing']}</td></tr>
<tr><td>Look here</td><td><a href="https://www.google.com/maps/@{f['source_lat']},{f['source_lon']},1200m/data=!3m1!1e3" target="_blank" rel="noopener">hotspot satellite view</a> ·
<a href="https://www.google.com/maps/@{f['facility_lat']},{f['facility_lon']},1500m/data=!3m1!1e3" target="_blank" rel="noopener">facility view</a>{' · <a href="' + f['reference'] + '" target="_blank" rel="noopener">GEM page</a>' if c['reference'].startswith('http') else ''}</td></tr></table>
<form id="f" onsubmit="return false"><fieldset><legend>Your role</legend>
<label>Role <select id="role"><option>ANNOTATOR_1</option><option>ANNOTATOR_2</option><option>ADJUDICATOR</option></select></label>
<label>Your reviewer ID (a person, not an AI) <input id="rid" required></label></fieldset>
<fieldset id="items"><legend>Evidence items (one per source you consulted)</legend><div class="it">
<label>Category <select class="cat">{opts}</select></label><label>Stance <select class="st">{stance}</select></label>
<label>URL / reference <input class="url"></label><label>Evidence date / valid period <input class="dt" placeholder="YYYY-MM-DD or range"></label>
<label>What it shows at the hotspot location (required for SPATIOTEMPORAL_LINK) <textarea class="link"></textarea></label><label>Summary <textarea class="sum"></textarea></label></div></fieldset>
<button type="button" onclick="addItem()">+ add evidence item</button>
<fieldset><legend>Counter-evidence (mandatory)</legend><label>What did you search for that could contradict this attribution (fields, burn scars, other plants, idle periods)? <textarea id="ces" required></textarea></label>
<label>Counter-evidence found <textarea id="ce"></textarea></label></fieldset>
<fieldset><legend>Adjudicator only</legend><label>Final label <select id="fl">{cls}</select></label>
<label>Conflict status <select id="cs"><option></option><option>NONE</option><option>RESOLVED</option><option>UNRESOLVED</option></select></label></fieldset>
<button type="button" onclick="exp()">Export ledger rows (CSV)</button></form><pre id="out" aria-live="polite"></pre>
<script>
const C={json.dumps({k: c[k] for k in ('source_id', 'proposed_label', 'facility_type', 'reference', 'distance_km', 'competing_n', 'site_complex_id')})};
const COLS={json.dumps(ER.LEDGER_COLUMNS)};
function addItem(){{const d=document.querySelector('.it').cloneNode(true);d.querySelectorAll('input,textarea').forEach(e=>e.value='');d.querySelectorAll('select').forEach(e=>e.selectedIndex=0);document.getElementById('items').appendChild(d);}}
function q(v){{v=String(v??'');return /[",\\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;}}
function exp(){{const role=document.getElementById('role').value,rid=document.getElementById('rid').value.trim();
 if(!rid||!document.getElementById('ces').value.trim()){{document.getElementById('out').textContent='Reviewer ID and counter-evidence search are mandatory.';return;}}
 const base={{source_id:C.source_id,proposed_label:C.proposed_label,label_tier:'UNRESOLVED',label_confidence:'',facility_type:C.facility_type,facility_reference:C.reference,
  facility_distance_km:C.distance_km,counter_evidence:document.getElementById('ce').value,competing_candidates:C.competing_n,site_complex_id:C.site_complex_id,role:role,reviewer_id:rid,
  counter_evidence_searched:document.getElementById('ces').value}};
 const rows=[];
 if(role==='ADJUDICATOR'){{rows.push(Object.assign({{}},base,{{record_kind:'ADJUDICATION',reviewer_status:'ADJUDICATED',adjudication_status:'ADJUDICATED',
   final_label:document.getElementById('fl').value,conflict_status:document.getElementById('cs').value}}));}}
 document.querySelectorAll('.it').forEach((d,i)=>{{const cat=d.querySelector('.cat').value;if(!cat)return;rows.push(Object.assign({{}},base,{{record_kind:'EVIDENCE_ITEM',
   evidence_item_id:C.source_id+'-'+role+'-'+(i+1),evidence_category:cat,evidence_stance:d.querySelector('.st').value,evidence_type:cat,evidence_url_or_reference:d.querySelector('.url').value,
   evidence_date:d.querySelector('.dt').value,evidence_valid_period:d.querySelector('.dt').value,hotspot_location_link:d.querySelector('.link').value,evidence_summary:d.querySelector('.sum').value,
   reviewer_status:'EVIDENCE_FOUND_UNREVIEWED',adjudication_status:'NOT_STARTED'}}));}});
 document.getElementById('out').textContent=rows.map(r=>COLS.map(k=>q(r[k])).join(',')).join('\\n')||'No evidence items entered.';}}
</script></body></html>"""


def main(out):
    out = Path(out); (out / "pilot10_html").mkdir(parents=True, exist_ok=True)
    sites = [s for s in RM.sites() if s["lat"] is not None and 5 <= s["lat"] <= 39 and 66 <= s["lon"] <= 99]
    sc = LX.site_complexes(sites)
    r72 = rd(f"{R72D}/review72_evidence_packet.csv"); r72p = rd(f"{R72D}/review72_research_priority.csv")
    ex = rd(f"{LXD}/label_expansion_candidates_v1.csv"); exp = rd(f"{LXD}/label_expansion_research_priority_v1.csv")
    cof = lambda r: sc[f"{r['gem_facility_type']}:{r['gem_facility_id']}"] if "gem_facility_type" in r else r["site_complex_id"]
    pilot = ER.select_pilot10(r72, r72p, ex, exp, cof)
    rows, ledger = [], []
    for i, p in enumerate(pilot, 1):
        r = p["row"]; is72 = p["source"] == "REVIEW72"
        c = {"pilot_id": f"P{i:02d}", "source_id": r["source_id"], "origin": p["source"], "proposed_label": p["cls"], "pilot_reason": p["reason"],
             "site_complex_id": p["sc"], "facility_name": r["gem_facility_name"] if is72 else r["facility_name"], "facility_type": r["gem_facility_type"] if is72 else r["facility_type"],
             "facility_lat": r["gem_lat"] if is72 else r["facility_lat"], "facility_lon": r["gem_lon"] if is72 else r["facility_lon"],
             "source_lat": r["source_lat"], "source_lon": r["source_lon"], "distance_km": r["distance_km"],
             "competing": (r["counter_evidence"] if is72 else r["rejection_reason"]) or "none in GEM", "competing_n": r["competing_facility_count_2km"],
             "reference": r["gem_reference"] if is72 else r["registry_reference"], "evidence_status": "NO_EVIDENCE", "reviewer_status": "NEEDS_RESEARCH",
             "html": f"pilot10_html/{r['source_id']}.html"}
        rows.append(c); (out / c["html"]).write_text(page(c, r))
        base = {k: "" for k in ER.LEDGER_COLUMNS}
        base.update(source_id=c["source_id"], proposed_label=c["proposed_label"], label_tier="UNRESOLVED", facility_type=c["facility_type"], facility_reference=c["reference"],
                    facility_distance_km=c["distance_km"], competing_candidates=c["competing_n"], site_complex_id=c["site_complex_id"], adjudication_status="NOT_STARTED")
        for role in ("ANNOTATOR_1", "ANNOTATOR_2"): ledger.append({**base, "record_kind": "EVIDENCE_ITEM", "role": role, "reviewer_status": "NEEDS_RESEARCH"})
        ledger.append({**base, "record_kind": "ADJUDICATION", "role": "ADJUDICATOR", "reviewer_status": "NOT_STARTED"})
    cols = [k for k in rows[0] if k != "competing_n"]
    with open(out / "pilot10_packet.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", lineterminator="\n"); w.writeheader(); w.writerows(rows)
    with open(out / "evidence_research_ledger_v1.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ER.LEDGER_COLUMNS, lineterminator="\n"); w.writeheader(); w.writerows(ledger)
    idx = "".join(f"<li><a href='{html.escape(c['html'])}'>{c['pilot_id']} · {html.escape(c['proposed_label'])} · {html.escape(c['facility_name'])} · {c['site_complex_id']}</a> ({html.escape(c['pilot_reason'])})</li>" for c in rows)
    (out / "pilot10_index.html").write_text(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Pilot 10</title></head><body style='font:14px system-ui;padding:16px'><h1>EVIDENCE_RESEARCH_V1 pilot (10 candidates)</h1><p><strong>Proposed labels are facility-context candidates, not answers.</strong> Annotators work independently; the adjudicator works last.</p><ol>{idx}</ol></body></html>")
    summ = {"pilot": [{k: c[k] for k in ("pilot_id", "source_id", "origin", "proposed_label", "site_complex_id", "pilot_reason")} for c in rows],
            "by_class": {k: sum(c["proposed_label"] == k for c in rows) for k in sorted({c["proposed_label"] for c in rows})},
            "distinct_site_complexes": len({c["site_complex_id"] for c in rows}),
            "distinct_5deg_cells": len({(int(float(c['source_lat']) // 5), int(float(c['source_lon']) // 5)) for c in rows}),
            "ledger_rows": len(ledger), "final_labels_allowed_now": sum(1 for c in rows if not ER.validate_final_label(ledger, c["source_id"]))}
    (out / "pilot10_summary.json").write_text(json.dumps(summ, indent=1) + "\n"); print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "evidence_research_out")
