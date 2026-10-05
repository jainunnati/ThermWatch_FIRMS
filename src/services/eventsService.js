import { loadRealStore } from './realStore.js';

/** @returns {Promise<{events: object[], skippedInvalid: number, warnings: string[]}>} */
export async function listEvents() {
  const store = await loadRealStore();
  return { events: store.events, skippedInvalid: store.skippedInvalid, warnings: store.warnings };
}
