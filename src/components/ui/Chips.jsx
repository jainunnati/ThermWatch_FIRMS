import React from 'react';
import { classificationOf } from '../../config/classification.js';
import { SEVERITIES } from '../../config/severity.js';
import { BEHAVIOUR_STATUSES, PRIORITIES } from '../../config/behaviour.js';

export function ClassChip({ classKey }) {
  const c = classificationOf(classKey);
  return (
    <span className="chip-tag">
      <span className="swatch" style={{ background: c.color }} />
      {c.label}
    </span>
  );
}

export function SeverityChip({ severity }) {
  if (!severity) return <span className="chip-tag chip-tag--muted">Alert Priority not supplied</span>;
  return <span className={`chip-tag chip-tag--sev-${severity}`}>Alert Priority {SEVERITIES[severity].label}</span>;
}

export function BehaviourChip({ behaviour }) {
  const b = BEHAVIOUR_STATUSES[behaviour] || BEHAVIOUR_STATUSES.not_assessed;
  return <span className={`chip-tag chip-tag--${b.tone}`}>{b.label}</span>;
}

export function PriorityChip({ priority }) {
  if (!priority) return <span className="chip-tag chip-tag--muted">Priority not assessed</span>;
  return <span className={`chip-tag chip-tag--${PRIORITIES[priority].tone}`}>{PRIORITIES[priority].label} priority</span>;
}
