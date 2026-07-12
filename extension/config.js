/**
 * config.js — Digital Guardian Extension Configuration
 * ──────────────────────────────────────────────────────
 * The extension is FULLY SELF-CONTAINED.
 * It calls Groq API directly — no backend server required.
 * Judges and users need zero local setup.
 */

const DG_CONFIG = {
  // Groq API — free, no local install, 0 bytes disk usage
  // llama-3.3-70b-versatile: best free model, ~500 tok/sec
  GROQ_API_KEY: "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",
  GROQ_MODEL:   "llama-3.3-70b-versatile",
  GROQ_URL:     "https://api.groq.com/openai/v1/chat/completions",

  // Scoring weights
  DOMAIN_WEIGHT:   0.40,
  SEMANTIC_WEIGHT: 0.60,

  // Analysis limits
  MAX_CONTENT_CHARS: 12000,
  MAX_MARKERS:       8,
};
