"""Evidence research pass 2 (research only; no annotation, no labels). Records what this pass's web searches actually found.
FACT = stated by the source; INFERENCE = marked; NOT ESTABLISHED = insufficient. python3 m1/evidence_research_pass2.py OUT_DIR"""
import csv, html, json, sys
from pathlib import Path
C = {c["id"]: c for c in json.load(open("/mnt/user-data/outputs/adjudicator_review_v1/adjudicator_review_content.json"))}
COLS = ["candidate_id", "facility", "FIRMS_first_seen", "FIRMS_last_seen", "evidence_type", "source_name", "source_date", "event_date", "evidence_url",
        "hotspot_specific", "facility_specific", "unit_specific", "connection_to_hotspot", "credibility_notes", "counter_evidence", "research_conclusion",
        "evidence_strength", "researcher_notes"]
# (cid, type, source, source_date, event_date, url, facility_specific, unit_specific, credibility, fact/inference note)
E = [
 ("P01", "NEWS_INCIDENT", "The Daily Star (Bangladesh)", "year not shown in retrieved text", "not in 2026 window", "https://www.thedailystar.net/node/1474666", "YES", "YES",
  "established national daily; quotes fire station officer and company", "FACT: molten iron fell on workers while receiving it from a furnace at GPH Ispat (~5:30am). Pre-dates detection window."),
 ("P01", "NEWS_INCIDENT", "The Business Standard (Bangladesh)", "year not shown in retrieved text", "a 22 September (year not shown)", "https://www.tbsnews.net/bangladesh/7-burnt-gph-ispat-factory-melted-iron-fell-them-136387", "YES", "NO",
  "established outlet; quotes police and hospital", "FACT: 7 workers burnt by molten iron; article also states 11 workers burnt in a 2017 furnace blast. Outside window."),
 ("P01", "NEWS_INCIDENT", "United News of Bangladesh", "2025-04-13", "2025-04-13", "https://unb.com.bd/news/tag/138208", "YES", "YES",
  "quotes company statement", "FACT: lift-cable accident in ECR building; not a thermal event; outside window."),
 ("P02", "NO_INCIDENT_FOUND", "web search (facility name + fire/accident)", "", "", "", "UNCERTAIN", "NO", "only GEM (not independent) describes rotary kilns/induction furnaces",
  "NOT ESTABLISHED: no independent dated record found."),
 ("P03", "NEWS_INCIDENT", "The Daily Pioneer", "2019", "2019 (Sunday, ~9am)", "https://www.dailypioneer.com/2019/state-editions/technical-snag-leads-to-fire-at-vedanta-electro-steel.html", "YES", "YES",
  "regional daily; quotes eyewitness and company", "FACT: transformer/generator fire in the captive power unit inside the integrated steel plant. Outside window."),
 ("P03", "NEWS_INCIDENT", "Deccan Herald (PTI)", "2021-09-28", "2021-09-27", "https://www.deccanherald.com/amp/story/india%2F3-die-in-esl-steel-plant-during-lift-maintenance-1035099.html", "YES", "YES",
  "wire service", "FACT: 3 elevator contractors died at blast furnace 2 during maintenance. Not a thermal event; outside window."),
 ("P09", "NEWS_INCIDENT", "The Hitavada", "2024-01-03", "2024-01-02 ~03:15", "https://thehitavada.com/Encyc/2024/1/3/Blast-in-Sunflag-Co-3-staffers-injured-5-suffer-minor-burns.html", "YES", "YES",
  "regional daily", "FACT: blast in the electric arc furnace splashed molten metal; 3 badly burnt. Outside window (2024)."),
 ("P09", "FACILITY_DOCUMENTATION", "IIFL company summary", "not stated", "", "https://live-next.indiainfoline.com/company/sunflag-iron-steel-company-ltd/summary", "YES", "YES",
  "secondary company profile", "FACT: plant has sponge-iron plant, mini blast furnace, sinter plant, captive power, steel melt shop. Context only."),
 ("P10", "PRODUCTION_REPORT", "Angel One (company production update)", "2026-02-10", "January 2026", "https://www.angelone.in/news/hindi/stocks/jsw-steel-reports-24-75-lakh-tonnes-crude-steel-output-in-january-2026", "NO", "NO",
  "financial news summarising company disclosure", "FACT: Jan-2026 output fell 2% YoY due to shutdowns in India and a US outage; facilities not named. NOT ESTABLISHED for Dolvi."),
 ("P10", "PROJECT_STATUS", "GMK Center", "not stated", "construction completion expected March 2026", "https://gmk.center/news/jsw-steel-zapustit-novuju-domennuju-pech-na-metkombinate-v-dolvi-v-2026-godu/amp/", "YES", "YES",
  "trade press", "FACT: new blast furnace at Dolvi expected to be completed March 2026. INFERENCE (unverified): construction/commissioning activity existed on site around the 2026-01-01 detection."),
]
INC = {"P01": ("NOT FOUND", "Several earlier GPH Ispat accidents reported (incl. molten-iron/furnace); none dated in 2026-01-01..2026-09-27."),
       "P02": ("NOT FOUND", "No incident report found for Crest Steel Mangatta."),
       "P03": ("NOT FOUND", "Earlier ESL incidents (2019 power-unit fire; 2021 BF2 lift accident); none in 2026 window. SAIL Bokaro results excluded (different plant)."),
       "P09": ("NOT FOUND", "EAF blast 2024-01-02 reported; nothing in 2026 window. Bhandara Ordnance Factory blasts excluded (different site)."),
       "P10": ("NOT FOUND", "No incident report found for 2026-01-01/02 at Dolvi; January 2026 shutdowns mentioned without naming the plant (UNCERTAIN relevance)."),
       "P04": ("NOT SEARCHED", "Not researched in pass 2."), "P05": ("NOT SEARCHED", "Not in pass-2 scope."), "P06": ("NOT SEARCHED", "Not researched in pass 2."),
       "P07": ("NOT SEARCHED", "Not researched in pass 2."), "P08": ("NOT SEARCHED", "Not researched in pass 2.")}


def imagery(c):
    la, lo = c["hs"]; d = c["first_seen"][:10]
    return [("NASA Worldview (VIIRS true colour + FIRMS layer) on first detection date",
             f"https://worldview.earthdata.nasa.gov/?v={lo-0.05:.4f},{la-0.05:.4f},{lo+0.05:.4f},{la+0.05:.4f}&t={d}&l=VIIRS_NOAA20_Thermal_Anomalies_375m_All,VIIRS_NOAA20_CorrectedReflectance_TrueColor"),
            ("Copernicus Browser (Sentinel-2) centred on hotspot", f"https://browser.dataspace.copernicus.eu/?zoom=15&lat={la:.5f}&lng={lo:.5f}")]


def main(out):
    out = Path(out); (out / "candidate_evidence_pages").mkdir(parents=True, exist_ok=True); rows = []
    for (cid, typ, src, sdate, edate, url, fac, unit, cred, note) in E:
        c = C[cid]
        rows.append({"candidate_id": cid, "facility": c["facility"], "FIRMS_first_seen": c["first_seen"], "FIRMS_last_seen": c["last_seen"], "evidence_type": typ,
                     "source_name": src, "source_date": sdate, "event_date": edate, "evidence_url": url, "hotspot_specific": "NO", "facility_specific": fac, "unit_specific": unit,
                     "connection_to_hotspot": "NO" if typ != "PROJECT_STATUS" else "UNCERTAIN", "credibility_notes": cred,
                     "counter_evidence": "dates do not overlap the FIRMS window" if "outside" in note.lower() else "",
                     "research_conclusion": "INSUFFICIENT EVIDENCE", "evidence_strength": "CONTEXT_ONLY" if fac == "YES" else "NONE", "researcher_notes": note})
    for cid in ("P04", "P05", "P06", "P07", "P08"):
        c = C[cid]
        rows.append({k: "" for k in COLS} | {"candidate_id": cid, "facility": c["facility"], "FIRMS_first_seen": c["first_seen"], "FIRMS_last_seen": c["last_seen"],
                     "evidence_type": "NOT_RESEARCHED_PASS2", "hotspot_specific": "UNCERTAIN", "facility_specific": "UNCERTAIN", "unit_specific": "UNCERTAIN",
                     "connection_to_hotspot": "UNCERTAIN", "research_conclusion": "INSUFFICIENT EVIDENCE", "evidence_strength": "NONE", "researcher_notes": "not researched in pass 2"})
    with open(out / "evidence_research_pass2.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    with open(out / "incident_search_results.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["candidate_id", "facility", "FIRMS_first_seen", "FIRMS_last_seen", "incident_search_result", "summary", "note"])
        for cid in sorted(C):
            w.writerow([cid, C[cid]["facility"], C[cid]["first_seen"], C[cid]["last_seen"], INC[cid][0], INC[cid][1], "No incident found online does not mean no incident occurred."])
    for cid, c in sorted(C.items()):
        ev = [r for r in rows if r["candidate_id"] == cid]
        tl = "".join(f"<li><b>{html.escape(r['event_date'] or r['source_date'] or 'date n/a')}</b>: {html.escape(r['source_name'])}: {html.escape(r['researcher_notes'])}"
                     + (f" <a href='{html.escape(r['evidence_url'])}' target='_blank' rel='noopener noreferrer'>source ↗</a>" if r["evidence_url"] else "") + "</li>" for r in ev)
        im = "".join(f"<li><a href='{html.escape(u)}' target='_blank' rel='noopener noreferrer'>{html.escape(t)} ↗</a> <span class='s'>(link constructed; not inspected; cannot by itself resolve a process unit)</span></li>" for t, u in imagery(c))
        page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{cid} evidence</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:820px;margin:0 auto;padding:16px}}.c{{background:#f5f5f2;border-radius:10px;padding:12px 14px;margin:10px 0}}
@media (prefers-color-scheme:dark){{body{{background:#121212;color:#eee}}.c{{background:#1e1e1e}}a{{color:#9cc3ff}}}}.s{{font-size:13px;opacity:.75}}.big{{font-size:20px;font-weight:700}}</style></head><body>
<h1>{cid}: {html.escape(c['facility'])}</h1><div class="c">Proposed: {html.escape(c['cls'])}<br>FIRMS hotspot {c['hs'][0]:.4f}, {c['hs'][1]:.4f} · {c['km']:.2f} km from facility point<br>
FIRMS detections: first {html.escape(c['first_seen'])} · last {html.escape(c['last_seen'])}</div>
<h2>Hotspot-specific evidence status</h2><div class="c big">INSUFFICIENT EVIDENCE: nothing found links this hotspot to a plant unit.</div>
<h2>Incident search</h2><div class="c"><b>{INC[cid][0]}</b>: {html.escape(INC[cid][1])}<br><i>No incident found online ≠ no incident occurred.</i></div>
<h2>Evidence timeline</h2><div class="c"><ul>{tl}</ul></div><h2>Satellite imagery links</h2><div class="c"><ul>{im}</ul></div>
<h2>Competing explanations</h2><div class="c"><ul>{''.join(f'<li>{html.escape(r)}</li>' for r in c['risks'])}</ul></div>
<h2>Conclusion</h2><div class="c">Facility existence/processes may be documented, but no dated, independent record or inspected image places this FIRMS hotspot on a named process unit. Human decisions (MS, HM, mh) are unchanged.</div></body></html>"""
        (out / "candidate_evidence_pages" / f"{cid}.html").write_text(page)
    print(len(rows), "evidence rows")


if __name__ == "__main__":
    main(sys.argv[1])
