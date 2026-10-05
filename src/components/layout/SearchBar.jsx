import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useApp } from '../../context/AppContext.jsx';
import { searchAll } from '../../services/search.js';

export default function SearchBar() {
  const { events, facilities, focusLocation, viewOnMap, openInvestigation, openFacility } = useApp();
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const ref = useRef(null);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(query), 120);
    return () => clearTimeout(id);
  }, [query]);

  const results = useMemo(() => searchAll(debounced, { events, facilities }), [debounced, events, facilities]);

  useEffect(() => {
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  function choose(r) {
    if (!r) return;
    if (r.kind === 'event') {
      viewOnMap(r.id);
      openInvestigation(r.id);
    } else if (r.kind === 'facility') {
      focusLocation(r.lat, r.lng, 14);
      openFacility(r.id);
    } else {
      focusLocation(r.lat, r.lng, 12);
    }
    setOpen(false);
  }

  function onKeyDown(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(i + 1, results.length - 1)); setOpen(true); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); choose(results[active]); }
    else if (e.key === 'Escape') setOpen(false);
  }

  return (
    <div className="search" ref={ref}>
      <div className="search__box">
        <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.8" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="m10.6 10.6 3.6 3.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
        <input
          type="search"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Search event ID, facility, type or lat, lng"
          aria-label="Search events, facilities or coordinates"
          role="combobox"
          aria-expanded={open && !!query}
          aria-controls="search-results"
        />
        {query && (
          <button type="button" className="icon-btn icon-btn--sm" aria-label="Clear search" onClick={() => { setQuery(''); setOpen(false); }}>
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8m0-8-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          </button>
        )}
      </div>
      {open && debounced.trim() && (
        <ul className="search__results" id="search-results" role="listbox">
          {results.length === 0 && <li className="search__empty">No events or facilities match “{debounced}”. Try an event ID, a facility name, or coordinates like 19.71, 83.40.</li>}
          {results.map((r, i) => (
            <li key={`${r.kind}-${r.id}`} role="option" aria-selected={i === active}>
              <button type="button" className={i === active ? 'is-active' : ''} onMouseEnter={() => setActive(i)} onClick={() => choose(r)}>
                <span className="search__label">{r.label}</span>
                <span className="search__sub">{r.sublabel}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
