import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext.jsx';
import { CLASSIFICATIONS, CLASSIFICATION_ORDER } from '../../config/classification.js';
import { SEVERITIES, SEVERITY_ORDER } from '../../config/severity.js';
import { INDUSTRIAL_TYPES, INDUSTRIAL_TYPE_ORDER } from '../../config/industrialTypes.js';
import { BEHAVIOUR_FILTERS } from '../../config/behaviour.js';
import { countBy, defaultFilters } from '../../utils/filters.js';
import { SeveritySwatch } from '../ui/Swatches.jsx';

function Row({ checked, onChange, disabled, children, count, hint }) {
  return (
    <label className={`layer-row ${disabled ? 'is-disabled' : ''}`} title={hint}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} disabled={disabled} />
      <span className="layer-row__label">{children}</span>
      {count !== undefined && <span className="layer-row__count">{count}</span>}
    </label>
  );
}

function Group({ title, note, children }) {
  return (
    <fieldset className="layer-group">
      <legend className="layer-group__title">{title}</legend>
      {note && <p className="layer-group__note">{note}</p>}
      {children}
    </fieldset>
  );
}

export default function LayersPanel() {
  const { filters, setFilters, timeMatched, facilities } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const counts = useMemo(() => ({
    classes: countBy(timeMatched, (e) => e.classification.key),
    severities: countBy(timeMatched, (e) => e.severity || 'low'),
    types: countBy(timeMatched.filter((e) => e.classification.key === 'industrial'), (e) => e.classification.industrialType || 'other'),
    behaviour: {
      abnormal: timeMatched.filter((e) => e.behaviour === 'abnormal').length,
      elevated: timeMatched.filter((e) => e.behaviour === 'elevated').length,
      persistent: timeMatched.filter((e) => e.persistentSource === true).length,
    },
  }), [timeMatched]);

  const set = (group, key, value) => setFilters((f) => ({ ...f, [group]: { ...f[group], [key]: value } }));
  const activeCount = useMemo(() => {
    const d = defaultFilters();
    let n = 0;
    for (const g of Object.keys(d)) for (const k of Object.keys(d[g])) if (d[g][k] !== filters[g][k]) n += 1;
    return n;
  }, [filters]);
  const industrialOff = !filters.classes.industrial;
  const profiles = facilities.filter((f) => f.historicalProfile?.footprint).length;

  return (
    <div className="layers" ref={ref}>
      <button type="button" className={`map-btn ${open ? 'is-active' : ''}`} aria-expanded={open} aria-controls="layers-panel" onClick={() => setOpen((v) => !v)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5 1 5l7 3.5L15 5zM1 8l7 3.5L15 8M1 11l7 3.5 7-3.5" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
        Layers
        {activeCount > 0 && <span className="map-btn__badge">{activeCount}</span>}
      </button>

      {open && (
        <div id="layers-panel" className="layers-panel" role="dialog" aria-label="Map layers and filters">
          <Group title="Source classification">
            {CLASSIFICATION_ORDER.map((k) => (
              <Row key={k} checked={filters.classes[k]} onChange={(v) => set('classes', k, v)} count={counts.classes[k] || 0}>
                <span className="swatch" style={{ background: CLASSIFICATIONS[k].color }} />
                {CLASSIFICATIONS[k].label}
              </Row>
            ))}
          </Group>

          <Group title="Severity">
            {SEVERITY_ORDER.map((k) => (
              <Row key={k} checked={filters.severities[k]} onChange={(v) => set('severities', k, v)} count={counts.severities[k] || 0} hint={k === 'low' ? 'Other ranked monitored sources (Alert Priority LOW). Off by default so the map shows alert points first.' : `Alert points: Alert Priority ${SEVERITIES[k].label.toUpperCase()}. ${SEVERITIES[k].description}`}>
                <SeveritySwatch severity={k} />
                {SEVERITIES[k].label}
              </Row>
            ))}
          </Group>

          <Group title="Industrial type" note={industrialOff ? 'Enable Industrial above to use these.' : 'Applies to Industrial events only.'}>
            {INDUSTRIAL_TYPE_ORDER.map((k) => (
              <Row key={k} checked={filters.industrialTypes[k]} onChange={(v) => set('industrialTypes', k, v)} disabled={industrialOff} count={counts.types[k] || 0}>
                {INDUSTRIAL_TYPES[k].label}
              </Row>
            ))}
          </Group>

          <Group title="Behaviour" note="Show only events with the checked behaviour. Nothing checked shows all.">
            {Object.values(BEHAVIOUR_FILTERS).map((b) => (
              <Row
                key={b.key}
                checked={filters.behaviours[b.key]}
                onChange={(v) => set('behaviours', b.key, v)}
                count={counts.behaviour[b.key]}
                hint={b.key === 'persistent' ? 'Matches only events the backend flags as persistent sources. The frontend never infers this.' : 'Behaviour status comes from the backend assessment.'}
              >
                {b.label}
              </Row>
            ))}
          </Group>

          <Group title="Context">
            <Row checked={filters.context.facilities} onChange={(v) => set('context', 'facilities', v)} count={facilities.length}>
              <span className="swatch swatch--facility" />
              Facilities / OSM
            </Row>
            <Row checked={false} onChange={() => {}} disabled hint="No land-cover layer is supplied by the current data source.">
              Land-cover / context <em className="layer-row__na">not in data</em>
            </Row>
          </Group>

          <Group title="Historical">
            <Row checked={filters.historical.events} onChange={(v) => set('historical', 'events', v)} hint="Events outside the current time filter, drawn dimmed without severity animation.">
              <span className="swatch swatch--hist" />
              Historical thermal events
            </Row>
            <Row checked={filters.historical.facilityActivity} onChange={(v) => set('historical', 'facilityActivity', v)} count={profiles} hint="Historical thermal footprint (centroid + median spread) for facilities with a profile.">
              <span className="swatch swatch--footprint" />
              Historical facility activity
            </Row>
          </Group>

          <button type="button" className="text-btn" onClick={() => setFilters(defaultFilters())} disabled={activeCount === 0}>
            Reset filters
          </button>
        </div>
      )}
    </div>
  );
}
