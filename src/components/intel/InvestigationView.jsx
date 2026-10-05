import React, { useState } from 'react';
import { Step, KV, Table, Note, Sub, Tile, Tiles } from './parts.jsx';
import { EventTimeline, SplitBar, BarRows } from './charts.jsx';
import { COPY, PIHS_RULES, f1, pct, utc, label } from '../../intel/investigationModel.js';

export const SECTIONS = [
  ['id', '1 · Identity'], ['obs', '2 · Observations'], ['persist', '3 · Persistence & Activity'], ['events', '4 · Events'], ['thermal', '5 · Thermal'],
  ['spatial', '6 · Spatial'], ['facility', '7 · Facility & attribution'], ['coverage', '8 · Coverage'], ['alert', '9 · Alert Priority'], ['ml', '10 · ML'], ['limits', '11 · Limitations'],
];
export const ALL_SECTIONS = SECTIONS.map(([k]) => k);
const PAGE = 15;
const fmtDur = (d) => (d === null ? '—' : d === 0 ? 'single time' : d < 1 ? `${(d * 24).toFixed(1)} h` : `${d.toFixed(1)} d`);

function EventTable({ rows, printMode }) {
  const [page, setPage] = useState(0); const [onlyActive, setOnlyActive] = useState(false);
  const list = onlyActive && !printMode ? rows.filter((r) => r.status === 'active') : rows;
  const shown = printMode ? list : list.slice(page * PAGE, page * PAGE + PAGE);
  const cols = [
    { key: 'idx', label: '#', num: true }, { key: 'event_id', label: 'Event ID', render: (r) => <span className="mono">{r.event_id}</span> },
    { key: 'first', label: 'First observation', render: (r) => utc(r.first) }, { key: 'last', label: 'Last observation', render: (r) => utc(r.last) },
    { key: 'duration', label: 'Span', num: true, render: (r) => fmtDur(r.duration_days) }, { key: 'observations', label: 'Obs', num: true },
    { key: 'sat', label: 'Satellites (obs)', render: (r) => r.sat_list.map((s) => `${s.label} ×${s.count}`).join(', ') || '—' },
    { key: 'cen', label: 'Centroid', render: (r) => (r.centroid ? <span className="mono">{r.centroid[0].toFixed(4)}, {r.centroid[1].toFixed(4)}</span> : '—') },
    { key: 'off', label: 'Offset from source', num: true, render: (r) => (r.centroid_offset_m === null ? '—' : `${Math.round(r.centroid_offset_m)} m`) },
    { key: 'gap', label: 'Since prev. event', num: true, render: (r) => (r.gap_days_since_prev === null ? '—' : `${r.gap_days_since_prev.toFixed(1)} d`) },
    { key: 'status', label: 'Status' },
  ];
  const rowsK = shown.map((r) => ({ ...r, __key: r.event_id }));
  return (
    <>
      {!printMode && <div className="inv-toolbar-row"><label className="small"><input type="checkbox" checked={onlyActive} onChange={(e) => { setOnlyActive(e.target.checked); setPage(0); }} /> Only events active at data cut-off</label></div>}
      <Table columns={cols} rows={rowsK} caption={`Events of this source (${list.length}${list.length !== rows.length ? ` of ${rows.length}` : ''}), oldest first`} />
      {!printMode && list.length > PAGE && <div className="tw-pager"><button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>‹ Prev</button><span>{page + 1} / {Math.ceil(list.length / PAGE)}</span><button type="button" disabled={(page + 1) * PAGE >= list.length} onClick={() => setPage(page + 1)}>Next ›</button></div>}
      <p className="small muted">“Since prev. event” is elapsed time between the end of one event and the start of the next. It is not interpreted as inactivity: satellites only sample the source at overpasses.</p>
    </>
  );
}

export function InvestigationContent({ inv, printMode = false, open, onToggle }) {
  const S = (id, n, title, status, summary, children, major) => <Step key={id} id={`inv-${id}`} n={n} title={title} status={status} summary={summary} open={open?.has(id)} onToggle={() => onToggle?.(id)} printMode={printMode} major={major}>{children}</Step>;
  const { identity: id, observations: ob, persistence: ps, thermal: th, events: ev, coverage: cv, alert: al, attribution: at, facility: fa, ml } = inv;
  const missingRequired = ps.checks.filter((c) => c.required && !c.met);
  return (
    <div className="steps">
      {S('id', 1, 'Source identity', 'complete', 'A persistent spatial source: a set of FIRMS observations that ThermWatch physically deduplicated and associated to one location.', (
        <KV rows={[
          ['Source ID', <span className="mono">{inv.source_id}</span>],
          ['Alert queue rank', inv.run.monitored ? `#${inv.rank} of ${inv.run.monitored.toLocaleString()} monitored sources (by Alert Priority)` : `#${inv.rank}`],
          ['Latitude / longitude', <span className="mono">{id.lat.toFixed(5)}, {id.lon.toFixed(5)}</span>],
          ['First seen', utc(id.first_seen)], ['Last seen', utc(id.last_seen)],
          ['Observation span', `${f1(id.durationDays, 1)} days${id.durationDerived ? ' (derived from first/last seen)' : ''}`],
          ['Source grade', <><span className="mono">{id.grade}</span> — data-processing provenance: a mix of standard-processing and near-real-time FIRMS observations (not physics).</>],
          ['Spatial extent', `${f1(id.extentM, 0)} m (bounding-box diagonal of the source’s observations)`],
          ['Data window', `${inv.run.window} · run ${inv.run.id} · ${inv.run.status}`],
        ]} />
      ))}
      {S('obs', 2, 'Observations', 'complete', 'Counts and statistics across all satellite overpasses associated with this source.', (<>
        <Tiles>
          <Tile v={ob.detections.toLocaleString()} t="Detections" /><Tile v={ob.activeDays} t="Active days" /><Tile v={ob.events} t="Events" />
          <Tile v={`${f1(th.frpMax, 2)} MW`} t="FRP max" /><Tile v={`${f1(th.frpMean, 2)} MW`} t="FRP mean" />
          <Tile v={th.ti4Median === null ? 'n/a' : `${f1(th.ti4Median, 1)} K`} t="TI4 median" hint={th.ti4Median === null ? 'not in contract for this source' : null} />
          <Tile v={th.ti4Max === null ? 'n/a' : `${f1(th.ti4Max, 1)} K`} t="TI4 max" /><Tile v={pct(th.nightShare, 1)} t="Night share" /><Tile v={th.recent30} t="Detections, last 30 d of record" />
        </Tiles>
        <Sub title="Satellites (observations across all events)"><BarRows rows={ev.satTotals.map((s) => ({ label: s.label, value: s.count }))} /></Sub>
        <Note tone={ev.reconcilesWithDetections ? 'info' : 'warn'}>{ev.reconcilesWithDetections ? `Event observation counts sum to ${ev.totalObs.toLocaleString()}, matching the source’s detection count.` : `Event observation counts sum to ${ev.totalObs.toLocaleString()} but the source reports ${ob.detections.toLocaleString()} detections; investigate before relying on event totals.`}</Note>
      </>))}
      {S('persist', 3, 'Persistence & Activity', 'complete', 'ThermWatch’s core signal: how repeatedly and how compactly this location produces thermal detections. Used to rank investigation, not to assert a cause.', (<>
        <div className={`inv-callout ${ps.flag ? 'inv-callout--pihs' : ''}`}>
          <div><div className="inv-callout__k">PIHS detector ({ps.version})</div><div className="inv-callout__v">{ps.flag ? 'PIHS CANDIDATE' : 'NOT A PIHS CANDIDATE'}</div></div>
          <div><div className="inv-callout__k">PIHS score</div><div className="inv-callout__v">{ps.score ?? 'n/a'} / 8</div></div>
          <div><div className="inv-callout__k">Reason codes</div><ul className="codes">{(ps.reasons || []).map((r) => <li key={r}>{r}</li>)}</ul></div>
        </div>
        {!ps.flag && missingRequired.length > 0 && <Note tone="muted">Not flagged because required rule{missingRequired.length > 1 ? 's' : ''} not met: {missingRequired.map((c) => `${c.code} (${c.field === 'night_share' ? pct(c.value, 1) : c.field === 'extent_m' ? `${f1(c.value, 0)} m` : c.value})`).join('; ')}. A PIHS flag needs PERSISTENT_ACTIVITY + NIGHT_DOMINANT + SPATIALLY_COMPACT.</Note>}
        <Tiles>
          <Tile v={ob.detections.toLocaleString()} t="Total detections" /><Tile v={ob.activeDays} t="Active days" hint={`${pct(id.activeDayShare, 0)} of days in the observation span`} />
          <Tile v={ob.events} t="Events (repeated)" hint={`median ${ev.medianObs} obs/event`} /><Tile v={`${f1(id.durationDays, 0)} d`} t="Observation span" />
          <Tile v={pct(th.nightShare, 1)} t="Night share" /><Tile v={`${f1(id.extentM, 0)} m`} t="Spatial extent" hint="compactness threshold: ≤ 750 m" />
          <Tile v={th.recent30} t="Recent activity" hint="detections in last 30 d of record" />
        </Tiles>
        <Sub title="Repeated-event behaviour">
          <KV rows={[['Events formed', ob.events], ['Largest event', `${ev.maxObs} observations`], ['Longest event span', fmtDur(ev.longest)], ['Events still active at data cut-off', ev.activeCount], ['Active days / span', `${ob.activeDays} of ${Math.round(id.durationDays + 1)} days (${pct(id.activeDayShare, 0)})`]]} />
        </Sub>
        <Sub title="Spatial compactness">
          <KV rows={[['Source extent', `${f1(id.extentM, 0)} m vs 750 m compactness threshold — ${id.extentM <= 750 ? 'compact' : 'wider than threshold'}`], ['Furthest event centroid from source centroid', ev.maxCentroidOffsetM === null ? '—' : `${Math.round(ev.maxCentroidOffsetM)} m`]]} />
        </Sub>
        <Sub title="PIHS rule check (actual values vs documented thresholds)">
          <Table columns={[
            { key: 'code', label: 'Rule', render: (r) => <><span className="mono">{r.code}</span>{r.required ? <span className="small muted"> · required for flag</span> : null}</> },
            { key: 'text', label: 'Requirement' },
            { key: 'value', label: 'Actual', num: true, render: (r) => (r.field === 'night_share' ? pct(r.value, 1) : r.field === 'extent_m' ? `${f1(r.value, 0)} m` : r.value ?? '—') },
            { key: 'met', label: 'Met', render: (r) => (r.met ? '✓ yes' : '✗ no') }, { key: 'pts', label: 'Points', num: true, render: (r) => (r.met ? `+${r.points}` : '0') },
          ]} rows={ps.checks.map((c) => ({ ...c, __key: c.code }))} />
          <Note tone={ps.matchesPipeline ? 'info' : 'warn'}>{ps.matchesPipeline ? `Recomputing the ${PIHS_RULES.length} rules from this source’s real values reproduces the pipeline’s stored reasons, score (${ps.recomputed.score}) and flag.` : 'Recomputed rules differ from the pipeline’s stored PIHS result. The stored pipeline result is shown above; treat this source with extra caution.'}</Note>
        </Sub>
        <Note>{COPY.persistenceNote}</Note>
      </>), true)}
      {S('events', 4, 'Event investigation', 'complete', `${ev.count} events formed under ThermWatch’s event-formation rules; ${ev.activeCount} still active at data cut-off.`, (<>
        <EventTimeline rows={ev.rows} window={cv.window} unknownDays={cv.streams.flatMap((s) => s.unverifiedInWindow)} unknownLabel="Unknown-coverage days (any stream)" />
        <EventTable rows={ev.rows} printMode={printMode} />
        <Note>{COPY.eventNote}</Note>
      </>))}
      {S('thermal', 5, 'Thermal behaviour', 'partial', 'Summary statistics only. The real pipeline produces no historical baseline, anomaly score or fusion score, so none is shown.', (<>
        <Tiles>
          <Tile v={`${f1(th.frpMax, 2)} MW`} t="FRP max" /><Tile v={`${f1(th.frpMean, 2)} MW`} t="FRP mean" /><Tile v={th.frpRatio === null ? '—' : `${f1(th.frpRatio, 2)}×`} t="FRP max ÷ mean" hint="input to intensity-jump signal" />
          <Tile v={th.ti4Median === null ? 'n/a' : `${f1(th.ti4Median, 1)} K`} t="TI4 median" /><Tile v={th.ti4Max === null ? 'n/a' : `${f1(th.ti4Max, 1)} K`} t="TI4 max" /><Tile v={th.recent30} t="Detections, last 30 d" />
        </Tiles>
        <Sub title="Day / night distribution of detections"><SplitBar parts={[{ label: 'Night', value: th.nightShare, cls: 'sb-night' }, { label: 'Day', value: th.dayShare, cls: 'sb-day' }]} caption="Share of this source’s detections acquired at night (real field night_share); day = remainder." /></Sub>
        <Sub title="Intensity-jump signal (alert-priority-v1)">
          <KV rows={[['Component value (0–1)', f1(th.intensityJumpComponent, 3)], ['Reason code INTENSITY_ABOVE_OWN_BASELINE', th.intensityFlag ? 'Present (component ≥ 0.5)' : 'Not present'], ['Definition', 'min(1, (FRP max ÷ FRP mean − 1) ÷ 4), requires ≥ 3 detections. “Baseline” here means this source’s own FRP mean, not an external historical baseline.']]} />
        </Sub>
        <Note tone="muted">{COPY.thermalNote} FRP in megawatts; TI4 = VIIRS I-4 brightness temperature in kelvin{th.ti4Median === null ? ' (not present in the contract for this source)' : ''}.</Note>
      </>))}
      {S('spatial', 6, 'Spatial behaviour', 'complete', 'Where the observations sit relative to the source centroid and to documented facilities.', (
        <KV rows={[['Centroid', <span className="mono">{id.lat.toFixed(5)}, {id.lon.toFixed(5)}</span>], ['Extent (bbox diagonal)', `${f1(id.extentM, 0)} m`], ['Event centroids, max offset', ev.maxCentroidOffsetM === null ? '—' : `${Math.round(ev.maxCentroidOffsetM)} m`], ['Nearest documented facility', fa.none ? 'None within 5 km' : `${fa.name} · ${fa.distanceKm.toFixed(2)} km`]]} />
      ))}
      {S('facility', 7, 'Facility context & heuristic attribution', 'context', 'Shown separately on purpose: proximity is context; attribution weights are a heuristic built from it.', (<>
        <Sub title="Facility context">
          {fa.none ? <p className="muted">No documented facility within 5 km of this source.</p> : <KV rows={[['Nearest documented facility', fa.name], ['Facility type', label(fa.type)], ['Distance', `${fa.distanceKm.toFixed(3)} km`]]} />}
          <Note>{COPY.facilityNote}</Note>
        </Sub>
        <Sub title="Heuristic attribution">
          {at.entries.length ? <BarRows rows={at.entries.map(([k, v]) => ({ label: label(k), value: v }))} max={100} suffix="%" /> : <p className="muted">No facility within 5 km: attribution unknown.</p>}
          <KV rows={[['Attribution confidence', at.confidence], ['Cause', <b>Cause: {COPY.cause}</b>]]} />
          <Note>{COPY.attributionNote}</Note>
        </Sub>
      </>))}
      {S('coverage', 8, 'Coverage', cv.anyUnverified ? 'partial' : 'complete', `Coverage within this source’s own window (${cv.window[0]} → ${cv.window[1]}, ${cv.windowDays} days), from the real coverage ledger.`, (<>
        <Note tone="warn"><b>{COPY.coverageRule}</b> {cv.ledgerRule}</Note>
        <Table columns={[
          { key: 'label', label: 'Stream' }, { key: 'status', label: 'Status in window', render: (r) => (r.complete ? 'Complete' : `${r.unverifiedInWindow.length} unverified days`) },
          { key: 'unv', label: 'Unverified (unknown) days', num: true, render: (r) => r.unverifiedInWindow.length },
          { key: 'part', label: 'Partial boundary days in window', render: (r) => r.partialInWindow.join(', ') || 'none' },
          { key: 'led', label: 'Ledger days (whole run)', num: true, render: (r) => r.ledgerDays },
        ]} rows={cv.streams.map((s) => ({ ...s, __key: s.key }))} />
        {cv.streams.filter((s) => s.unverifiedInWindow.length).map((s) => <p key={s.key} className="small muted"><b>{s.label} unknown-coverage dates:</b> {s.unverifiedInWindow.join(', ')}</p>)}
        <p className="small muted">Reason meanings — {Object.entries(cv.reasonMeaning).map(([k, v]) => `${k}: ${v}`).join(' · ')}.</p>
        <KV rows={[['Contract coverage statement', inv.sourceCoverageStatus]]} />
      </>))}
      {S('alert', 9, 'Alert Priority', 'complete', `${al.tier} · ${f1(al.stored, 4)} — a triage ranking (${al.version}).`, (<>
        <div className="inv-callout"><div><div className="inv-callout__k">Priority level</div><div className="inv-callout__v">{al.tier}</div></div><div><div className="inv-callout__k">Priority score (0–1)</div><div className="inv-callout__v">{f1(al.stored, 4)}</div></div>
          <div><div className="inv-callout__k">Reason codes</div><ul className="codes">{al.reasons.map((r) => <li key={r}>{r}</li>)}</ul></div></div>
        <Table columns={[
          { key: 'key', label: 'Component', render: (r) => label(r.key) }, { key: 'component', label: 'Value (0–1)', num: true, render: (r) => f1(r.component, 3) },
          { key: 'weight', label: 'Weight', num: true, render: (r) => r.weight.toFixed(2) }, { key: 'contribution', label: 'Contribution', num: true, render: (r) => f1(r.contribution, 4) }, { key: 'rule', label: 'How the component is defined' },
        ]} rows={al.rows.map((r) => ({ ...r, __key: r.key }))} />
        <BarRows rows={al.rows.map((r) => ({ label: label(r.key), value: r.contribution }))} max={0.35} fmt={(v) => v.toFixed(3)} />
        <Note tone={al.reconciles ? 'info' : 'warn'}>{al.reconciles ? `Weighted components sum to ${f1(al.sum, 4)}, matching the stored score.` : `Weighted components sum to ${f1(al.sum, 4)} but the stored score is ${f1(al.stored, 4)}.`} Tiers: {al.tierRule}. Ties are broken by source ID.</Note>
        <Note>{COPY.alertNote}</Note>
      </>))}
      {S('ml', 10, 'Machine learning', 'context', null, (<>
        <div className="inv-callout inv-callout--ml"><div><div className="inv-callout__k">Supervised ML</div><div className="inv-callout__v">NOT TRAINED</div></div>
          <div><div className="inv-callout__k">Quality gate</div><div className="inv-callout__v">NOT SATISFIED</div></div><div><div className="inv-callout__k">Defensible labels</div><div className="inv-callout__v">{ml.eligible_labels}</div></div></div>
        <p>{COPY.mlWhy}</p>
        <KV rows={[['Status', `${ml.state} — ${ml.message}`], ['Gate', ml.blocked_because], ['Verdict', ml.verdict], ['Fallback', `${ml.fallback} (heuristic, not a classifier)`], ['Ready components', ml.checks.join(' · ')]]} />
        <Note tone="muted">This source has no classifier output. ThermWatch does not display classifier probabilities or accuracy figures.</Note>
      </>))}
      {S('limits', 11, 'Limitations & caveats', 'info', null, (<ul className="inv-list">{inv.caveats.map((c) => <li key={c}>{c}</li>)}<li>Data are validated historical FIRMS data (window {inv.run.window}, status {inv.run.status}); this is not a live incident finding.</li></ul>))}
    </div>
  );
}

export function PrintReport({ inv, generatedAt = new Date().toISOString() }) {
  return (
    <article className="report" data-testid="print-report" data-source-id={inv.source_id}>
      <header className="report__head">
        <div><p className="report__brand">ThermWatch · SIH26162</p><h1 className="report__title">Source investigation report</h1></div>
        <dl className="report__meta"><div><dt>Source</dt><dd className="mono">{inv.source_id}</dd></div><div><dt>Generated</dt><dd>{utc(generatedAt)}</dd></div>
          <div><dt>Data status</dt><dd>Historical (validated) data to {inv.run.timestamp.slice(0, 10)} · run {inv.run.id}</dd></div></dl>
      </header>
      <p className="report__warning">VALIDATED HISTORICAL DATA — real FIRMS-derived ThermWatch source, not a live incident finding. Cause: {COPY.cause}. Alert Priority is a triage ranking, not a probability.</p>
      <InvestigationContent inv={inv} printMode />
      <footer className="report__foot">ThermWatch is investigation-prioritisation decision support. A satellite detection is not a confirmed fire, persistence is not proof of industrial activity, attribution weights are heuristic, and unknown coverage is not interpreted as no fire.</footer>
    </article>
  );
}
