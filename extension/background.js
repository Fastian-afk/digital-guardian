/**
 * background.js — Service Worker (Manifest V3)
 * Handles communication between popup and content scripts.
 * API_BASE is loaded from config.js (injected via manifest web_accessible_resources).
 */

import "./config.js";
// API_BASE is defined in config.js and available globally in the service worker scope

// ─────────────────────────────────────────────────────────────────────────────
// Message Handler — Receives requests from popup.js
// ─────────────────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "ANALYZE_PAGE") {
    handleAnalyzeRequest(message.payload)
      .then((result) => sendResponse({ success: true, data: result }))
      .catch((error) => sendResponse({ success: false, error: error.message }));

    // Return true to indicate async sendResponse
    return true;
  }

  if (message.type === "INJECT_HIGHLIGHTS") {
    // Forward highlight instruction to the active content script
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]?.id) {
        chrome.tabs.sendMessage(tabs[0].id, {
          type: "RENDER_HIGHLIGHTS",
          payload: message.payload,
        });
      }
    });
    return false;
  }
});


// ─────────────────────────────────────────────────────────────────────────────
// Core: POST to FastAPI /analyze
// ─────────────────────────────────────────────────────────────────────────────

async function handleAnalyzeRequest(payload) {
  const response = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errBody = await response.text();
    throw new Error(`API Error ${response.status}: ${errBody}`);
  }

  return await response.json();
}


// ─────────────────────────────────────────────────────────────────────────────
// Extension Install / Update Events
// ─────────────────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    console.log("[Digital Guardian] Extension installed. Backend must be running at http://127.0.0.1:8000");
  }
});
