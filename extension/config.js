/**
 * config.js — Digital Guardian Extension Configuration
 * ──────────────────────────────────────────────────────
 * Single source of truth for the backend URL.
 * 
 * PRODUCTION: Points to the deployed Railway/Render cloud backend.
 * LOCAL DEV:  Change BACKEND_URL to "http://127.0.0.1:8000" for local testing.
 * 
 * Judges and end-users need ZERO local setup — the cloud backend handles everything.
 */

const DG_CONFIG = {
  // ── Cloud Backend (for submission / judges / public users) ──
  BACKEND_URL: "https://digital-guardian.up.railway.app",

  // ── Fallback for local development ──
  // Change BACKEND_URL to this if running locally:
  // BACKEND_URL: "http://127.0.0.1:8000",

  API_VERSION: "v1",
};

// Full base URL helper used by background.js and popup.js
const API_BASE = `${DG_CONFIG.BACKEND_URL}/api/${DG_CONFIG.API_VERSION}`;
