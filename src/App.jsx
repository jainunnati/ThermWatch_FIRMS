import React from 'react';
import Sidebar from './components/layout/Sidebar.jsx';
import SearchBar from './components/layout/SearchBar.jsx';
import MapView from './components/map/MapView.jsx';
import LayersPanel from './components/map/LayersPanel.jsx';
import BaseMapSwitch from './components/map/BaseMapSwitch.jsx';
import TimeControl from './components/map/TimeControl.jsx';
import MapLegend from './components/map/MapLegend.jsx';
import AlertsDrawer from './components/alerts/AlertsDrawer.jsx';
import ActivityDrawer from './components/activity/ActivityDrawer.jsx';
import FacilitiesDrawer from './components/facilities/FacilitiesDrawer.jsx';
import HelpDrawer from './components/help/HelpDrawer.jsx';
import InvestigationDrawer from './components/investigation/InvestigationDrawer.jsx';
import { useApp } from './context/AppContext.jsx';
import ErrorBoundary from './components/ui/ErrorBoundary.jsx';

function DataBanner() {
  const { load, retry, time } = useApp();
  if (load.status === 'error') {
    return (
      <div className="data-banner data-banner--error" role="alert">
        <span>Real ThermWatch data could not be loaded. {load.error} No substitute dataset is shown.</span>
        <button type="button" className="btn btn--sm" onClick={retry}>Retry</button>
      </div>
    );
  }
  if (load.status === 'ready' && load.error) {
    return (
      <div className="data-banner data-banner--warn" role="status">
        <span>Last background refresh failed ({load.error}). Showing data from {new Date(load.updatedAt).toISOString().slice(11, 16)} UTC.</span>
        <button type="button" className="btn btn--sm" onClick={retry}>Retry</button>
      </div>
    );
  }
  if (load.warnings?.length) {
    return <div className="data-banner data-banner--warn" role="status"><span>{load.warnings.join(' ')}</span></div>;
  }
  if (time.mode === 'historical') {
    return <div className="data-banner data-banner--hist" role="status"><span>Historical mode — showing recorded acquisitions in the selected UTC range. Ranked sources without packaged acquisition times are hidden in this mode.</span></div>;
  }
  return null;
}

export default function App() {
  const { section, investigationOpen } = useApp();
  return (
    <div className="app-shell">
      <Sidebar />
      <main className={`workspace${section ? ' has-left' : ''}${investigationOpen ? ' has-right' : ''}`}>
        <ErrorBoundary name="Map" title="The map stopped working">
          <MapView />
        </ErrorBoundary>
        <div className="topbar">
          <SearchBar />
          <TimeControl />
          <div className="topbar__right">
            <BaseMapSwitch />
            <LayersPanel />
          </div>
        </div>
        <DataBanner />
        <MapLegend />
        <AlertsDrawer />
        <ActivityDrawer />
        <FacilitiesDrawer />
        <HelpDrawer />
        <ErrorBoundary name="Investigation" title="The investigation panel stopped working">
          <InvestigationDrawer />
        </ErrorBoundary>
      </main>
    </div>
  );
}
