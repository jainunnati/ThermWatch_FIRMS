import React, { useEffect, useRef } from 'react';

/**
 * Side drawer floating over the map. Escape closes it. No backdrop, so the
 * map stays usable while a drawer is open.
 */
export default function Drawer({ open, onClose, side = 'left', title, actions, children, className = '' }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape' && ref.current?.contains(document.activeElement)) onClose?.();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <section ref={ref} className={`drawer drawer--${side} ${className}`} aria-label={title}>
      <header className="drawer__head">
        <h2 className="drawer__title">{title}</h2>
        <div className="drawer__actions">
          {actions}
          <button type="button" className="icon-btn" onClick={onClose} aria-label={`Close ${title}`}>
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5l9 9m0-9-9 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          </button>
        </div>
      </header>
      <div className="drawer__body">{children}</div>
    </section>
  );
}
