import React from 'react';
import { useApp } from '../../context/AppContext.jsx';

const ICONS = {
  map: <path d="M1.5 4 6 2l4 2 4.5-2v10L10 14l-4-2-4.5 2zM6 2v10m4-8v10" />,
  alerts: <path d="M8 1.8 15 14H1zM8 6v4m0 2v.5" />,
  activity: <path d="M1 8h3l2-5 4 10 2-5h3" />,
  facilities: <path d="M1.5 14.5V7l4 2.5V7l4 2.5V3.5h5v11zM1 14.5h14" />,
  help: <path d="M8 15A7 7 0 1 0 8 1a7 7 0 0 0 0 14zM6 6a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6 1v.6M8 11.5v.5" />,
};

const NAV = [
  { key: null, label: 'Map', icon: 'map' },
  { key: 'alerts', label: 'Alerts', icon: 'alerts' },
  { key: 'activity', label: 'Activity', icon: 'activity' },
  { key: 'facilities', label: 'Facilities', icon: 'facilities' },
];

function NavButton({ item, active, onClick, badge }) {
  return (
    <button type="button" className={`nav-btn ${active ? 'is-active' : ''}`} aria-current={active ? 'page' : undefined} onClick={onClick}>
      <svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" strokeLinecap="round">{ICONS[item.icon]}</svg>
      <span className="nav-btn__label">{item.label}</span>
      {badge > 0 && <span className="nav-btn__badge" aria-label={`${badge} new`}>{badge > 99 ? '99+' : badge}</span>}
    </button>
  );
}

export default function Sidebar() {
  const { section, setSection, toggleSection, newAlertCount } = useApp();
  return (
    <nav className="sidebar" aria-label="Primary">
      <div className="brand" title="ThermWatch — SIH26162">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.2" fill="#FF6A2B" /><circle cx="12" cy="12" r="7" fill="none" stroke="#FF6A2B" strokeOpacity=".55" strokeWidth="1.4" /><circle cx="12" cy="12" r="10.5" fill="none" stroke="#FF6A2B" strokeOpacity=".25" strokeWidth="1.2" /></svg>
        <span className="brand__name">ThermWatch</span>
      </div>
      <div className="sidebar__nav">
        {NAV.map((item) => (
          <NavButton
            key={item.label}
            item={item}
            active={section === item.key}
            onClick={() => (item.key ? toggleSection(item.key) : setSection(null))}
            badge={item.key === 'alerts' ? newAlertCount : 0}
          />
        ))}
      </div>
      <div className="sidebar__foot">
        <NavButton item={{ key: 'help', label: 'Help', icon: 'help' }} active={section === 'help'} onClick={() => toggleSection('help')} />
      </div>
    </nav>
  );
}
