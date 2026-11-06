// Empty = this site's own origin: on Azure the FastAPI backend serves the built
// frontend, and in development Vite proxies /api to it. Set VITE_API_URL only
// when the API runs on a different host.
export const API_BASE_URL = import.meta.env.VITE_API_URL || "";

console.log("API_BASE_URL", API_BASE_URL);
