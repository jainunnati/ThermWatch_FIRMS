import { loadRealStore } from './realStore.js';

export async function listFacilities() {
  return (await loadRealStore()).facilities;
}
