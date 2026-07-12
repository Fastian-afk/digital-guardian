/**
 * config.js — Digital Guardian Extension Configuration
 * ──────────────────────────────────────────────────────
 * SELF-CONTAINED: No backend server required.
 * The Groq API key is entered once by the user and stored
 * securely in chrome.storage.sync (never in source code).
 */

const DG_CONFIG = {
  GROQ_MODEL:   "llama-3.3-70b-versatile",
  GROQ_URL:     "https://api.groq.com/openai/v1/chat/completions",
  DOMAIN_WEIGHT:   0.40,
  SEMANTIC_WEIGHT: 0.60,
  MAX_CONTENT_CHARS: 12000,
  MAX_MARKERS:       8,
};
