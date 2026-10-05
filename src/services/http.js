const BASE = (typeof import.meta !== 'undefined' && import.meta.env?.BASE_URL) || '/';

export class DataError extends Error {
  constructor(message, { status = null, url = null } = {}) {
    super(message);
    this.name = 'DataError';
    this.status = status;
    this.url = url;
  }
}

/** GET a static real-data file shipped in /public/data. No fallback on failure. */
export async function getStatic(path, { signal, timeoutMs = 30000 } = {}) {
  const url = `${BASE.replace(/\/$/, '')}${path}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const onAbort = () => ctrl.abort();
  signal?.addEventListener('abort', onAbort, { once: true });
  try {
    const res = await fetch(url, { signal: ctrl.signal, headers: { Accept: 'application/json' } });
    if (!res.ok) throw new DataError(`${path} returned HTTP ${res.status}`, { status: res.status, url });
    return await res.json();
  } catch (err) {
    if (signal?.aborted) throw err;
    if (err instanceof DataError) throw err;
    throw new DataError(`${path} could not be loaded (${err?.message || err})`, { url });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}
