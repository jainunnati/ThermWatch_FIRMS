import { useEffect, useState } from 'react';
import { GOOGLE_MAPS_API_KEY } from '../config/env.js';

// Loads the Maps JavaScript API once per page. Handles: missing key, script
// load failure (network / blocked) and Google's auth-failure callback
// (invalid key, API not enabled, referrer not allowed).

let loadPromise = null;
const AUTH_EVENT = 'thermwatch:maps-auth-failure';

// Google calls this global when the key is rejected — possibly after the
// script has loaded and a map already exists.
function registerAuthFailureHook() {
  window.gm_authFailure = () => window.dispatchEvent(new Event(AUTH_EVENT));
}

function loadScript(key) {
  if (window.google?.maps?.Map) return Promise.resolve(window.google.maps);
  if (loadPromise) return loadPromise;
  loadPromise = new Promise((resolve, reject) => {
    const cb = '__thermwatchMapsReady';
    window[cb] = () => {
      delete window[cb];
      resolve(window.google.maps);
    };
    const s = document.createElement('script');
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&loading=async&callback=${cb}`;
    s.async = true;
    s.onerror = () => {
      loadPromise = null;
      s.remove();
      reject(new Error('The Google Maps script could not be loaded. Check the network connection.'));
    };
    document.head.appendChild(s);
  });
  return loadPromise;
}

export function useGoogleMaps() {
  const [state, setState] = useState(() =>
    GOOGLE_MAPS_API_KEY
      ? { status: window.google?.maps?.Map ? 'ready' : 'loading', maps: window.google?.maps || null, error: null }
      : { status: 'error', maps: null, error: 'missing-key' }
  );

  useEffect(() => {
    if (!GOOGLE_MAPS_API_KEY) return undefined;
    let active = true;
    registerAuthFailureHook();
    const onAuth = () => active && setState({ status: 'error', maps: null, error: 'auth' });
    window.addEventListener(AUTH_EVENT, onAuth);
    loadScript(GOOGLE_MAPS_API_KEY)
      .then((maps) => active && setState((s) => (s.error === 'auth' ? s : { status: 'ready', maps, error: null })))
      .catch((err) => active && setState({ status: 'error', maps: null, error: err.message }));
    return () => {
      active = false;
      window.removeEventListener(AUTH_EVENT, onAuth);
    };
  }, []);

  return state;
}
