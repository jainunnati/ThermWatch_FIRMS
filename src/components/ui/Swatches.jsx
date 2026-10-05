import React from 'react';
import { SEVERITIES } from '../../config/severity.js';

/** Small static illustration of a severity treatment (neutral colour). */
export function SeveritySwatch({ severity }) {
  const s = SEVERITIES[severity];
  if (!s) return null;
  return (
    <span className={`sev-swatch sev-swatch--${s.treatment}`} style={{ '--s': `${Math.round(s.markerSize * 0.55)}px` }} aria-hidden="true">
      <span className="sev-swatch__dot" />
    </span>
  );
}
