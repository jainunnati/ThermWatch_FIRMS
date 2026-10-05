import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import Drawer from '../ui/Drawer.jsx';
import Empty from '../ui/Empty.jsx';
import InvestigationHeader from './InvestigationHeader.jsx';
import PointInvestigation, { POINT_SECTIONS } from './PointInvestigation.jsx';
import PrintReport from './PrintReport.jsx';
import { InvestigationContent, ALL_SECTIONS } from '../intel/InvestigationView.jsx';
import { useApp } from '../../context/AppContext.jsx';
import { buildInvestigation } from '../../intel/investigationModel.js';

const FIRST = ['id', 'obs'];

function usePrintRoot() {
  const [el, setEl] = useState(null);
  useEffect(() => {
    const node = document.createElement('div');
    node.id = 'print-root';
    document.body.appendChild(node);
    setEl(node);
    return () => node.remove();
  }, []);
  return el;
}

export default function InvestigationDrawer() {
  const { investigationOpen, closeInvestigation, selectedEventId, eventsById, facilities, store, viewOnMap } = useApp();
  const [openSteps, setOpenSteps] = useState(() => new Set(FIRST));
  const printRoot = usePrintRoot();

  const event = selectedEventId ? eventsById.get(selectedEventId) || null : null;
  const inv = useMemo(() => (event?.real?.source && store ? buildInvestigation(event.real.source, store.contract, store.alertCards.get(event.id) || null) : null), [event, store]);
  const facility = useMemo(() => (event?.facility?.id ? facilities.find((f) => f.id === event.facility.id) || null : null), [event, facilities]);
  const allKeys = inv ? ALL_SECTIONS : POINT_SECTIONS;

  // New source → collapse back to the first two steps.
  useEffect(() => { setOpenSteps(new Set(FIRST)); }, [selectedEventId]);

  const toggleStep = useCallback((k) => setOpenSteps((prev) => {
    const next = new Set(prev);
    if (next.has(k)) next.delete(k); else next.add(k);
    return next;
  }), []);
  const allOpen = allKeys.every((k) => openSteps.has(k));

  const print = useCallback(() => {
    if (!event) return;
    const prev = document.title;
    document.title = `ThermWatch-Investigation-${event.id}`;
    window.addEventListener('afterprint', () => { document.title = prev; }, { once: true });
    window.print();
  }, [event]);

  const actions = event ? (
    <button type="button" className="btn btn--print" onClick={print}>
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6V1.5h8V6M4 12H2V6.5h12V12h-2M4.5 9.5h7v5h-7z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
      Print investigation
    </button>
  ) : null;

  return (
    <>
      <Drawer open={investigationOpen} onClose={closeInvestigation} side="right" title="Investigation" actions={actions} className="drawer--wide">
        {!event && <Empty title="Source not found">{selectedEventId} is not in the loaded real data.</Empty>}
        {event && store && (
          <>
            <div className="inv-toolbar">
              <button type="button" className="text-btn" onClick={() => viewOnMap(event.id)}>View on map</button>
              <button type="button" className="text-btn" onClick={() => setOpenSteps(allOpen ? new Set() : new Set(allKeys))}>{allOpen ? 'Collapse all steps' : 'Expand all steps'}</button>
            </div>
            <div className="inv" data-testid="real-investigation" data-source-id={event.id} data-detail={inv ? 'full' : 'ranked'}>
              <InvestigationHeader event={event} facility={facility} />
              {inv
                ? <InvestigationContent inv={inv} open={openSteps} onToggle={toggleStep} />
                : <PointInvestigation event={event} contract={store.contract} open={openSteps} onToggle={toggleStep} />}
            </div>
          </>
        )}
      </Drawer>
      {printRoot && investigationOpen && event && store && createPortal(<PrintReport event={event} inv={inv} contract={store.contract} />, printRoot)}
    </>
  );
}
