"""Simple non-expert decision workflow (YES / UNSURE) for the pilot.
  build : python3 m1/simple_review_v1.py build OUT_DIR      -> simple_review.html (one reusable page, all 10 candidates)
  import: python3 m1/simple_review_v1.py import DECISIONS.json LEDGER_IN LEDGER_OUT
The page shows AI-curated background (clearly labelled) and records ONLY the human's YES/UNSURE + which evidence was shown.
Importing fills the ANNOTATOR_1 template rows (record_kind HUMAN_DECISION). It never creates Annotator 2, an adjudication or
a final label; validate_final_label() keeps blocking until those exist."""
import csv, html, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_research_v1 as ER
AUD = "/mnt/user-data/outputs/pilot10_research_pass1_audit"; ERD = "/mnt/user-data/outputs/evidence_research_v1"
PLAIN = {"STEEL_METAL": "STEEL / METAL", "THERMAL_POWER": "THERMAL POWER (coal power plant)", "UNRESOLVED_MULTI_TYPE": "STEEL / METAL or THERMAL POWER (two kinds of plant nearby)"}
# one plain sentence per evidence item, restating ONLY what the research row claims (no new claims)
SAY = {
 "P01-AI1": "The company's own website gives the factory's address in Sitakunda.", "P01-AI2": "GEM database entry for the plant (this is where the candidate came from, so it is not independent).",
 "P02-AI2": "A government environmental-clearance record names the company and the Mangatta project.", "P02-AI3": "The company's compliance page lists dated environmental monitoring reports.",
 "P02-AI1": "GEM database entry for the plant (not independent).",
 "P03-AI1": "The company's 2025 annual report describes the steel plant at Siyaljori, Bokaro.", "P03-AI2": "India's Ministry of Steel annual report (2023-24) lists the integrated plant.",
 "P04-AI1": "A 2022 government document says the cement works has a 75 MW captive power plant.",
 "P05-AI1": "GEM database entry for the power station (not independent).", "P05-AI2": "Wikipedia list of Telangana power stations (weak, general reference).",
 "P06-AI1": "The company's page about its new 50 MW coal power plant project.", "P06-AI2": "The company's Dec-2024 half-year report says the new plant's equipment was still being installed.",
 "P07-AI1": "The company's 2025 sustainability report describes the Hazira steel complex and its power plants.", "P07-AI2": "A March-2025 government clearance document for the Hazira complex.",
 "P08-AI1": "GEM database entry for the mill's captive power station (not independent).",
 "P09-AI1": "The company's website describes the Bhandara steel plant and its processes.", "P09-AI2": "A 2016 Maharashtra Pollution Control Board public-hearing record for the company.",
 "P10-AI1": "JSW's 2025-26 annual report describes Dolvi Works, a large integrated steel plant.", "P10-AI2": "A July-2025 Maharashtra Pollution Control Board summary describing the Dolvi steel plant."}
EXTRA_RISK = {"P04": "The power plant sits inside a cement works. A cement kiln is very hot and could be the real source.",
              "P06": "The site is a chemical factory with an older 38 MW coal unit (running since 2016) and a new 50 MW unit that was still being commissioned in late 2025. Any of these could be the source.",
              "P07": "This is a huge steel complex with several power plants. We cannot tell which part the hotspot belongs to.",
              "P08": "The power station belongs to a paper mill. The mill's own boilers could be the source.",
              "P05": "We found no independent document about this power station; only the database entry and Wikipedia.",
              "P09": "The regulator record is from 2016, ten years before the hotspot was seen."}


def site(u):
    for k, v in (("gem.wiki", "Global Energy Monitor (GEM)"), ("wikipedia", "Wikipedia"), ("environmentclearance", "Govt. of India environment clearance"),
                 ("mpcb", "Maharashtra Pollution Control Board"), ("steel.gov.in", "Ministry of Steel, India"), ("jswsteel", "JSW Steel"), ("amns", "AM/NS India"),
                 ("sitara", "Sitara Chemical Industries"), ("sunflag", "Sunflag Iron & Steel"), ("eslsteel", "ESL Steel"), ("csppl", "Crest Steel & Power"), ("gphispat", "GPH Ispat")):
        if k in u: return v
    return u.split("/")[2]


def candidates():
    P = list(csv.DictReader(open(f"{ERD}/pilot10_packet.csv"))); I = list(csv.DictReader(open(f"{AUD}/pilot10_ai_research_items.csv")))
    S = {r["pilot_id"]: r for r in csv.DictReader(open(f"{AUD}/pilot10_status.csv"))}; out = []
    for p in sorted(P, key=lambda r: r["pilot_id"]):
        its = [i for i in I if i["pilot_id"] == p["pilot_id"]]
        its.sort(key=lambda i: (0 if i["independence"].startswith("INDEPENDENT") else 1, i["item"]))
        shown = its[:4]; st = S[p["pilot_id"]]
        risks = []
        if p["competing"] and not p["competing"].startswith("none"): risks.append("Another plant is nearby: " + p["competing"].replace("COAL", "coal power").replace("STEEL", "steel"))
        if p["pilot_id"] in EXTRA_RISK: risks.append(EXTRA_RISK[p["pilot_id"]])
        risks.append("No picture or record was found showing the hotspot itself on the plant's working area.")
        risks.append("Fires on nearby fields or waste ground can appear close to a plant.")
        out.append({"id": p["pilot_id"], "source_id": p["source_id"], "cls": PLAIN.get(p["proposed_label"], p["proposed_label"]), "facility": p["facility_name"],
                    "hs": [float(p["source_lat"]), float(p["source_lon"])], "fac": [float(p["facility_lat"]), float(p["facility_lon"])], "km": float(p["distance_km"]),
                    "evidence": [{"item": i["item"], "source": site(i["url"]), "url": i["url"], "date": i["evidence_date"] or "date not stated",
                                  "say": SAY.get(i["item"], "Background document about the facility."), "independent": i["independence"].startswith("INDEPENDENT")} for i in shown],
                    "risks": risks, "hotspot_link": st["hotspot_to_facility_evidence"],
                    "conclusion": "The facility is confirmed by documents, but nothing we found shows that this particular hotspot came from the plant's working area."
                    if any(i["independence"].startswith("INDEPENDENT") for i in its) else
                    "We only found a database entry for this facility, and nothing showing that this particular hotspot came from it."})
    return out


def build(out):
    C = candidates(); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    data = json.dumps(C, ensure_ascii=False)
    page = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ThermWatch: simple evidence check</title><style>
:root{--bg:#fff;--fg:#1b1b1b;--mut:#5a5a5a;--card:#f6f6f4;--line:#ddd;--yes:#1d7a46;--uns:#9a6700;--rule:#fff6db;--ruleb:#c99400}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--mut:#aaa;--card:#1e1e1e;--line:#333;--yes:#3fb27a;--uns:#e0a83a;--rule:#2a2410;--ruleb:#c99400}}
*{box-sizing:border-box}body{margin:0;font:17px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}
main{max-width:760px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px;margin:0 0 4px}h2{font-size:18px;margin:22px 0 8px}
.card{background:var(--card);border-radius:12px;padding:14px 16px;margin:10px 0}.q{font-size:19px;font-weight:600}
.rule{background:var(--rule);border-left:5px solid var(--ruleb);border-radius:8px;padding:12px 14px;margin:18px 0;font-size:16px}
.ev{border-top:1px solid var(--line);padding:10px 0}.ev:first-child{border-top:0}.src{font-weight:600}.tag{font-size:13px;color:var(--mut)}
ul{margin:6px 0;padding-left:22px}.btns{display:grid;gap:12px;margin-top:18px}
button.big{font:600 20px system-ui;padding:20px;border-radius:14px;border:3px solid;cursor:pointer;background:var(--bg);color:var(--fg)}
button.yes{border-color:var(--yes)}button.copy{font:13px system-ui;padding:3px 8px;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--fg);cursor:pointer}button.uns{border-color:var(--uns)}button:focus-visible{outline:3px solid #4a90e2;outline-offset:2px}
.top{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;color:var(--mut);font-size:15px}
svg{width:100%;max-width:420px;height:auto;display:block}a{color:inherit}.done{font-size:18px}.small{font-size:14px;color:var(--mut)}
input{font:inherit;padding:10px;border-radius:8px;border:1px solid var(--line);width:100%;background:var(--bg);color:var(--fg)}
</style></head><body><main id="app"></main><script>
const C=__DATA__; let i=0, who='', role='', D={};
const KEY=()=>'tw_simple_review_v2|'+role+'|'+who.toLowerCase();          // answers stored per person AND role
const save=()=>{try{localStorage.setItem(KEY(),JSON.stringify(D))}catch(e){}};
const load=()=>{try{D=JSON.parse(localStorage.getItem(KEY())||'{}')}catch(e){D={}}};
try{localStorage.removeItem('tw_simple_review')}catch(e){}                   // drop old shared v1 storage
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const FRAMED=(()=>{try{return window.self!==window.top}catch(e){return true}})();
function ext(url,label){return `<a class="ext" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a> <button type="button" class="copy" onclick="cp(this,'${esc(url)}')">copy link</button>`;}
function cp(b,u){const done=()=>{b.textContent='copied';setTimeout(()=>b.textContent='copy link',1500)};
 try{navigator.clipboard.writeText(u).then(done,()=>fallback())}catch(e){fallback()}
 function fallback(){const t=document.createElement('textarea');t.value=u;document.body.appendChild(t);t.select();try{document.execCommand('copy');done()}catch(e){prompt('Copy this link:',u)}t.remove()}}
const NOTICE=FRAMED?`<div class="rule" role="note"><b>You are viewing this inside a preview window.</b> Reading and answering work normally here, but links may not open and the download may be blocked. For links: use <b>copy link</b> and paste into a new browser tab. Best: download <code>simple_review.html</code> and open it directly in your browser.</div>`:'';
function mapSVG(c){const [a,b]=c.hs,[x,y]=c.fac, cx=(a+x)/2, cy=(b+y)/2, k=Math.cos(cx*Math.PI/180);
 const span=Math.max(Math.abs(a-x),Math.abs(b-y)*k,0.004)*1.6, s=v=>200+v/span*170;
 const P=(la,lo)=>[s((lo-cy)*k),s(-(la-cx))]; const [h1,h2]=P(a,b),[f1,f2]=P(x,y);
 return `<svg viewBox="0 0 400 400" role="img" aria-label="Sketch: hotspot and facility points, ${c.km.toFixed(2)} km apart"><rect width="400" height="400" rx="12" fill="none" stroke="currentColor" opacity=".2"/>
 <line x1="${h1}" y1="${h2}" x2="${f1}" y2="${f2}" stroke="currentColor" stroke-dasharray="6 6" opacity=".5"/>
 <circle cx="${f1}" cy="${f2}" r="12" fill="#4a7bd1"/><text x="${f1+16}" y="${f2+5}" font-size="15" fill="currentColor">facility (database point)</text>
 <circle cx="${h1}" cy="${h2}" r="10" fill="#e4572e"/><text x="${h1+14}" y="${h2-10}" font-size="15" fill="currentColor">hotspot</text></svg>`;}
function render(){const app=document.getElementById('app'); setTimeout(()=>{if(NOTICE&&!document.getElementById('notice'))app.insertAdjacentHTML('afterbegin','<div id="notice">'+NOTICE+'</div>')},0);
 if(!who){app.innerHTML=`<h1>Simple evidence check</h1><div class="card">You will see ${C.length} candidates, one at a time. For each, answer <b>YES</b> or <b>UNSURE</b>. It takes about a minute each.</div>
 <label for="who"><b>Your name or initials</b> (so the record shows a person made the decision)</label><input id="who" autocomplete="off">
 <fieldset style="border:0;padding:0;margin:14px 0"><legend><b>Which reviewer are you?</b></legend>
 <label><input type="radio" name="role" value="ANNOTATOR_1" style="width:auto"> First reviewer (Annotator 1)</label>
 <label><input type="radio" name="role" value="ANNOTATOR_2" style="width:auto"> Second reviewer (Annotator 2), a different person who has NOT seen the first reviewer's answers</label></fieldset>
 <div class="btns"><button class="big uns" onclick="start()">Start</button></div>`;return;}
 if(i>=C.length){const n=Object.keys(D).length;app.innerHTML=`<h1>All done (${n} of ${C.length} answered)</h1><div class="card done">Thank you. Your answers are <b>your</b> decisions; the research was prepared by AI and is kept separate.
 Nothing becomes a final label until a second person answers independently and a third person settles any disagreement.</div>
 <div class="btns"><button class="big yes" onclick="dl()">Download my answers (send this file to Claude)</button><button class="big uns" onclick="i=0;render()">Review my answers again</button></div>
 <h2>If the download does not work</h2><p class="small">Copy everything in this box and paste it into the chat with Claude.</p><textarea id="ans" readonly rows="8" style="width:100%;font:13px monospace" onclick="this.select()">${esc(answers())}</textarea>
 <div class="btns"><button class="big uns" type="button" onclick="cp(this,answers())">Copy my answers</button></div>`;return;}
 const c=C[i], prev=D[c.id];
 app.innerHTML=`<div class="top"><span>Candidate ${i+1} of ${C.length}</span><span>${prev?'Your answer: '+prev.decision:''}</span></div>
 <h1>Candidate ${esc(c.id)}</h1><div class="card"><div class="small">WHAT ARE WE CHECKING?</div>Proposed class: <b>${esc(c.cls)}</b> &middot; ${esc(c.facility)}
 <p class="q">Does the evidence actually show that this specific hotspot comes from this facility?</p></div>
 <h2>📍 Where is the hotspot?</h2><div class="card">${mapSVG(c)}<p>The hotspot is <b>${c.km.toFixed(2)} km</b> from the facility's database point.
 Hotspot ${c.hs.map(v=>v.toFixed(4)).join(', ')} &middot; Facility ${c.fac.map(v=>v.toFixed(4)).join(', ')}.</p>
 <p><b>Does it fall on the plant's working area?</b> We could not confirm this. No dated image or record was found showing it.</p>
 <p>${ext(`https://www.google.com/maps/@${c.hs[0]},${c.hs[1]},900m/data=!3m1!1e3`,'Open satellite view of the hotspot')} <span class="small">(optional; opens in a new tab; today's imagery, not the date of the fire)</span></p></div>
 <h2>🔎 What evidence did we find?</h2><div class="card">${c.evidence.map(e=>`<div class="ev"><div class="src">${esc(e.source)} <span class="tag">&middot; ${esc(e.date)}${e.independent?'':' &middot; not independent'}</span></div><div>${esc(e.say)}</div>${ext(e.url,'Open source')}</div>`).join('')}
 <p class="small">Collected by AI as background research. These documents are about the facility, not about this hotspot.</p></div>
 <h2>⚠️ What could make this wrong?</h2><div class="card"><ul>${c.risks.map(r=>`<li>${esc(r)}</li>`).join('')}</ul></div>
 <h2>🧠 Plain-English conclusion</h2><div class="card">${esc(c.conclusion)}</div>
 <div class="rule"><b>Choose YES only if the evidence connects the actual hotspot to this facility/class.</b> A nearby facility, a database match, the fire pattern, the distance, map tags or general documents about the plant are <b>not enough by themselves</b>. If you are not sure, choose UNSURE.</div>
 <div class="btns"><button class="big yes" onclick="pick('YES')">✅ YES: the evidence supports the proposed class</button><button class="big uns" onclick="pick('UNSURE')">⚠️ UNSURE: the evidence is not strong enough</button></div>
 <p class="small">${i>0?'<a href="#" onclick="i--;render();return false">← back</a>':''}</p>`; window.scrollTo(0,0);}
function start(){const v=document.getElementById('who').value.trim(), r=document.querySelector('input[name=role]:checked'); if(!v||!r)return; who=v; role=r.value; load(); render();}
function pick(d){const c=C[i]; D[c.id]={decision:d,source_id:c.source_id,evidence_shown:c.evidence.map(e=>e.item),conclusion_shown:c.conclusion,at:new Date().toISOString()}; save();
 if(d==='UNSURE'){document.getElementById('app').insertAdjacentHTML('afterbegin','<div class="card done" role="status">UNSURE recorded. That is a valid scientific result: it means the evidence is not strong enough yet.</div>');}
 i++; setTimeout(render, d==='UNSURE'?1400:300);}
function answers(){return JSON.stringify({tool:'simple_review_v2',role:role,reviewer:who,decisions:D},null,1)}
function dl(){const blob=new Blob([answers()],{type:'application/json'});
 const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='simple_review_'+role+'_'+who.replace(/\\W+/g,'_')+'.json'; a.click();}
render();
</script></body></html>""".replace("__DATA__", data)
    (out / "simple_review.html").write_text(page)
    json.dump(C, open(out / "simple_review_content.json", "w"), indent=1, ensure_ascii=False)
    return C


def import_decisions(dec_path, ledger_in, ledger_out):
    d = json.load(open(dec_path)); who = d["reviewer"].strip()
    if not who or who.upper().startswith(("AI", "CHATGPT", "CLAUDE", "GPT", "LLM")): raise SystemExit("reviewer must be a human name")
    role = d.get("role")
    if role not in ("ANNOTATOR_1", "ANNOTATOR_2"): raise SystemExit("role must be ANNOTATOR_1 or ANNOTATOR_2")
    rows = list(csv.DictReader(open(ledger_in))); n = 0
    others = {r["reviewer_id"].strip().lower() for r in rows if r["role"] in ("ANNOTATOR_1", "ANNOTATOR_2", "ADJUDICATOR") and r["role"] != role and r["reviewer_id"]}
    if who.lower() in others: raise SystemExit(f"reviewer '{who}' already holds another role; annotators/adjudicator must be different people")
    for r in rows:
        x = next((v for v in d["decisions"].values() if v["source_id"] == r["source_id"]), None)
        if x and r["role"] == role and r["record_kind"] == "EVIDENCE_ITEM" and not r["reviewer_id"]:
            if x["decision"] not in ("YES", "UNSURE"): raise SystemExit("decision must be YES or UNSURE")
            r.update(record_kind="HUMAN_DECISION", reviewer_id=who, reviewer_status="DECIDED_" + x["decision"],
                     evidence_stance="SUPPORTS" if x["decision"] == "YES" else "NEUTRAL", evidence_type="HUMAN_JUDGEMENT_ON_AI_CURATED_EVIDENCE",
                     evidence_url_or_reference="shown:" + ";".join(x["evidence_shown"]), evidence_summary="Human YES/UNSURE judgement; evidence was AI-curated background (see pilot10_ai_research_items.csv)",
                     evidence_date=x["at"][:10], counter_evidence_searched="AI-curated risks shown to reviewer", conflict_status="", final_label="", final_confidence="")
            n += 1
    with open(ledger_out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ER.LEDGER_COLUMNS, lineterminator="\n"); w.writeheader(); w.writerows(rows)
    return n


if __name__ == "__main__":
    if sys.argv[1] == "build": print(len(build(sys.argv[2])), "candidates")
    else: print(import_decisions(*sys.argv[2:5]), "ANNOTATOR_1 rows recorded")
