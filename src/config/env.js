// Environment access in one place. Never hardcode keys in components.
const env = (typeof import.meta !== 'undefined' && import.meta.env) || {};

export const GOOGLE_MAPS_API_KEY = env.VITE_GOOGLE_MAPS_API_KEY || '';
