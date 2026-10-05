import React from 'react';
import { useApp } from '../../context/AppContext.jsx';

export default function BaseMapSwitch() {
  const { baseMap, setBaseMap } = useApp();
  return (
    <div className="segmented" role="radiogroup" aria-label="Base map">
      {[['roadmap', 'Standard'], ['satellite', 'Satellite']].map(([v, label]) => (
        <button key={v} type="button" role="radio" aria-checked={baseMap === v} className={baseMap === v ? 'is-on' : ''} onClick={() => setBaseMap(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}
