/**
 * content.js — Injected into every page at document_idle
 * 
 * Responsibilities:
 *  1. DOM scraping — extract text content from the page.
 *  2. Shadow DOM overlay injection — renders the Trust Badge.
 *  3. Text highlighting engine — maps ExplainabilityMarkers to DOM text nodes.
 * 
 * DESIGN RULE: This script NEVER modifies the host page's DOM directly for styling.
 * All UI is encapsulated in a Shadow DOM root to prevent CSS bleed.
 */

(function () {
  "use strict";

  // Prevent double-injection
  if (window.__digitalGuardianInjected) return;
  window.__digitalGuardianInjected = true;

  // ─────────────────────────────────────────────────────────────────────────
  // DOM Scraper
  // ─────────────────────────────────────────────────────────────────────────

  function scrapePageContent() {
    const selectors = ["article p", "main p", "p", "h1", "h2", "h3"];
    const seen = new Set();
    let text = "";

    for (const selector of selectors) {
      document.querySelectorAll(selector).forEach((el) => {
        const t = el.innerText?.trim();
        if (t && t.length > 30 && !seen.has(t)) {
          seen.add(t);
          text += t + "\n";
        }
      });
    }

    return text.trim().slice(0, 50000); // Cap at API max_length
  }

  function getPageMeta() {
    const url = window.location.href;
    const domain = window.location.hostname.replace(/^www\./, "");
    const title = document.title || "";
    return { url, domain, title };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Trust Badge — Shadow DOM Overlay
  // ─────────────────────────────────────────────────────────────────────────

  let shadowHost = null;
  let shadowRoot = null;

  function injectShadowHost() {
    if (shadowHost) return; // Already injected

    shadowHost = document.createElement("div");
    shadowHost.id = "dg-shadow-host";
    shadowHost.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 2147483647;
      font-family: sans-serif;
    `;
    document.body.appendChild(shadowHost);
    shadowRoot = shadowHost.attachShadow({ mode: "open" });
  }

  function renderTrustBadge(payload) {
    if (!shadowRoot) injectShadowHost();

    const { overall_score, risk_level, summary, domain_reputation, markers, cached } = payload;

    const colors = {
      VERIFIED:  { bg: "#0d1f0d", border: "#22c55e", text: "#22c55e", label: "✅ VERIFIED" },
      CAUTION:   { bg: "#1f1a0d", border: "#f59e0b", text: "#f59e0b", label: "⚠️ CAUTION" },
      HIGH_RISK: { bg: "#1f0d0d", border: "#ef4444", text: "#ef4444", label: "🚨 HIGH RISK" },
    };
    const theme = colors[risk_level] || colors["CAUTION"];

    const markerListHTML = markers.slice(0, 5).map((m) => `
      <div class="marker">
        <span class="flag-type">${escHtml(m.flag_type)}</span>
        <span class="confidence">${Math.round(m.confidence * 100)}%</span>
        <p class="explanation">${escHtml(m.explanation)}</p>
        <blockquote class="segment">"${escHtml(m.text_segment.slice(0, 120))}…"</blockquote>
      </div>
    `).join("") || '<p class="no-flags">No specific flags detected.</p>';

    shadowRoot.innerHTML = `
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        :host { all: initial; }
        #dg-badge {
          width: 340px;
          background: #0a0a0a;
          border: 1.5px solid ${theme.border};
          border-radius: 16px;
          overflow: hidden;
          box-shadow: 0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04);
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          color: #e5e7eb;
          transition: all 0.2s ease;
        }
        #dg-badge.collapsed #dg-body { display: none; }
        #dg-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          background: ${theme.bg};
          cursor: pointer;
          user-select: none;
        }
        .dg-brand { font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; color: #6b7280; }
        .dg-score-wrap { display: flex; align-items: center; gap: 10px; }
        .dg-score {
          font-size: 26px;
          font-weight: 800;
          color: ${theme.text};
          line-height: 1;
        }
        .dg-risk-label {
          font-size: 11px;
          font-weight: 700;
          color: ${theme.text};
          letter-spacing: 0.5px;
        }
        .dg-toggle { font-size: 14px; color: #6b7280; cursor: pointer; padding: 4px; }
        #dg-body { padding: 14px 16px; border-top: 1px solid #1f1f1f; }
        .dg-section-title {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 1.2px;
          color: #6b7280;
          margin-bottom: 6px;
          margin-top: 12px;
        }
        .dg-section-title:first-child { margin-top: 0; }
        .dg-summary { font-size: 12.5px; line-height: 1.6; color: #d1d5db; }
        .dg-domain {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: #111;
          border-radius: 8px;
          padding: 8px 12px;
          margin-top: 4px;
        }
        .dg-domain-name { font-size: 12px; color: #9ca3af; }
        .dg-domain-score {
          font-size: 12px;
          font-weight: 700;
          color: ${theme.text};
        }
        .marker {
          background: #111;
          border-left: 3px solid ${theme.border};
          border-radius: 0 8px 8px 0;
          padding: 8px 10px;
          margin-bottom: 8px;
        }
        .flag-type {
          font-size: 11px;
          font-weight: 700;
          color: ${theme.text};
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .confidence {
          float: right;
          font-size: 11px;
          color: #6b7280;
          font-weight: 600;
        }
        .explanation {
          font-size: 11.5px;
          color: #9ca3af;
          margin-top: 4px;
          line-height: 1.5;
        }
        .segment {
          font-size: 11px;
          color: #6b7280;
          font-style: italic;
          margin-top: 4px;
          border: none;
          padding: 0;
        }
        .no-flags { font-size: 12px; color: #6b7280; }
        .dg-cached-tag {
          font-size: 10px;
          color: #4b5563;
          text-align: right;
          margin-top: 10px;
        }
        #dg-close {
          position: absolute;
          top: 8px; right: 8px;
          background: none; border: none;
          color: #4b5563; cursor: pointer;
          font-size: 16px; line-height: 1;
        }
      </style>

      <div id="dg-badge">
        <div id="dg-header">
          <div>
            <div class="dg-brand">Digital Guardian</div>
            <div class="dg-risk-label">${theme.label}</div>
          </div>
          <div class="dg-score-wrap">
            <div class="dg-score">${overall_score}</div>
            <div style="font-size:10px;color:#6b7280;">/100</div>
          </div>
          <div class="dg-toggle" id="dg-toggle-btn">▲</div>
        </div>

        <div id="dg-body">
          <div class="dg-section-title">Summary</div>
          <p class="dg-summary">${escHtml(summary)}</p>

          <div class="dg-section-title">Source Reputation</div>
          <div class="dg-domain">
            <span class="dg-domain-name">${escHtml(domain_reputation.domain)}</span>
            <span class="dg-domain-score">${escHtml(domain_reputation.reputation_label)} · ${domain_reputation.reputation_score}/100</span>
          </div>

          <div class="dg-section-title">Flags (${markers.length})</div>
          ${markerListHTML}

          ${cached ? '<div class="dg-cached-tag">⚡ From cache</div>' : ''}
        </div>
      </div>
    `;

    // Toggle collapse
    shadowRoot.getElementById("dg-toggle-btn").addEventListener("click", () => {
      const badge = shadowRoot.getElementById("dg-badge");
      const isCollapsed = badge.classList.toggle("collapsed");
      shadowRoot.getElementById("dg-toggle-btn").textContent = isCollapsed ? "▼" : "▲";
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Text Highlight Engine
  // ─────────────────────────────────────────────────────────────────────────

  function highlightMarkers(markers) {
    if (!markers || markers.length === 0) return;

    const RISK_COLORS = {
      "Sensationalism":              "#f59e0b33",
      "Unverified Claim":            "#ef444433",
      "Conspiracy Language":         "#8b5cf633",
      "Absolute Language":           "#f97316",
      "Loaded Language":             "#ef444422",
      "Health Misinformation Marker":"#ef444444",
    };

    markers.forEach((marker) => {
      const snippet = marker.text_segment
        .replace(/^\.\.\./, "").replace(/\.\.\.$/, "").trim();
      if (!snippet || snippet.length < 10) return;

      // Search for the snippet text in all paragraph nodes
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node;

      while ((node = walker.nextNode())) {
        const idx = node.nodeValue.indexOf(snippet.slice(0, 60));
        if (idx === -1) continue;

        try {
          const range = document.createRange();
          range.setStart(node, idx);
          range.setEnd(node, Math.min(idx + snippet.length, node.nodeValue.length));

          const highlight = document.createElement("mark");
          highlight.style.cssText = `
            background: ${RISK_COLORS[marker.flag_type] || "#f59e0b33"};
            border-bottom: 2px solid ${RISK_COLORS[marker.flag_type]?.replace("33", "cc") || "#f59e0b"};
            border-radius: 3px;
            cursor: pointer;
            padding: 0 2px;
          `;
          highlight.title = `[${marker.flag_type}] ${marker.explanation}`;

          range.surroundContents(highlight);
          break; // Only highlight the first occurrence
        } catch (_) {
          // Range errors (e.g., cross-node) — skip silently
        }
      }
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Message Listener — receives RENDER_HIGHLIGHTS from background.js
  // ─────────────────────────────────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "RENDER_HIGHLIGHTS") {
      renderTrustBadge(message.payload);
      highlightMarkers(message.payload.markers);
    }
    if (message.type === "GET_PAGE_DATA") {
      const content = scrapePageContent();
      const meta = getPageMeta();
      return Promise.resolve({ ...meta, content });
    }
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Utility
  // ─────────────────────────────────────────────────────────────────────────

  function escHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

})();
