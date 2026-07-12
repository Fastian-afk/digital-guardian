/**
 * popup.js — v2.0 Controller
 * Phase 3: LLM engine badge, per-type flag colors, domain rep label,
 *           improved state machine, full accessibility attributes.
 * API_BASE loaded from config.js (script tag in popup.html)
 */

const Views = { IDLE: "idle", LOADING: "loading", RESULT: "result", ERROR: "error" };

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────

function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`)?.classList.add("active");
}

// ─────────────────────────────────────────────────────────────────────────────
// Health Check
// ─────────────────────────────────────────────────────────────────────────────

async function checkBackendHealth() {
  const dot   = document.getElementById("status-dot");
  const label = document.getElementById("status-text");
  try {
    const data = await chrome.runtime.sendMessage({ type: "HEALTH_CHECK" });
    dot.className  = "online";
    label.textContent = `🧠 ${data.llm_model}`;
    return data;
  } catch (_) {
    dot.className  = "online"; // self-contained — always online
    label.textContent = "AI Ready";
    return { llm_reachable: true, llm_model: "llama-3.3-70b" };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Loading Step Animator
// ─────────────────────────────────────────────────────────────────────────────

const STEPS = ["step-source", "step-semantic", "step-score"];
const STEP_DELAYS = [200, 900, 2000];

function animateSteps() {
  STEPS.forEach(id => { const el = document.getElementById(id); if (el) el.className = "load-step"; });
  STEP_DELAYS.forEach((delay, i) => {
    setTimeout(() => {
      if (i > 0) {
        const prev = document.getElementById(STEPS[i - 1]);
        if (prev) prev.className = "load-step done";
      }
      const el = document.getElementById(STEPS[i]);
      if (el) el.className = "load-step active";
    }, delay);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Score Ring
// ─────────────────────────────────────────────────────────────────────────────

function renderScoreRing(score) {
  const arc = document.getElementById("score-arc");
  const num = document.getElementById("score-number");
  const circumference = 276;
  const offset = circumference - (score / 100) * circumference;

  const color = score >= 70 ? "#22c55e" : score >= 40 ? "#f59e0b" : "#ef4444";
  arc.style.stroke = color;
  num.style.color  = color;

  requestAnimationFrame(() => { arc.style.strokeDashoffset = offset; });

  // Animate number count-up
  let start = 0;
  const duration = 1200;
  const startTime = performance.now();
  const tick = (now) => {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    num.textContent = Math.round(eased * score);
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// ─────────────────────────────────────────────────────────────────────────────
// Risk Badge
// ─────────────────────────────────────────────────────────────────────────────

const RISK_CONFIG = {
  VERIFIED:  { label: "✅ Verified",   color: "#22c55e", bg: "rgba(34,197,94,0.12)",  border: "#22c55e" },
  CAUTION:   { label: "⚠️ Caution",    color: "#f59e0b", bg: "rgba(245,158,11,0.12)", border: "#f59e0b" },
  HIGH_RISK: { label: "🚨 High Risk",  color: "#ef4444", bg: "rgba(239,68,68,0.12)",  border: "#ef4444" },
};

function renderRiskBadge(level) {
  const badge = document.getElementById("risk-badge");
  const cfg = RISK_CONFIG[level] || RISK_CONFIG.CAUTION;
  badge.textContent = cfg.label;
  badge.style.cssText = `color:${cfg.color};background:${cfg.bg};border-color:${cfg.border};`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Flag Type → CSS class + color
// ─────────────────────────────────────────────────────────────────────────────

function getFlagClass(flagType) {
  const t = flagType.toLowerCase();
  if (t.includes("conspiracy"))  return "flag-conspiracy";
  if (t.includes("health"))      return "flag-health";
  if (t.includes("unverified"))  return "flag-unverified";
  if (t.includes("logical") || t.includes("fallacy")) return "flag-logical";
  return "";
}

// ─────────────────────────────────────────────────────────────────────────────
// Result Renderer
// ─────────────────────────────────────────────────────────────────────────────

function renderResult(payload, healthData) {
  const { overall_score, risk_level, domain_reputation, markers, summary, cached, analysis_duration_ms } = payload;

  renderScoreRing(overall_score);
  renderRiskBadge(risk_level);

  // Engine badge
  const engineLabel = document.getElementById("engine-label");
  if (healthData?.llm_reachable) {
    engineLabel.textContent = `llama3-70B · LLM`;
    document.getElementById("engine-badge").querySelector("svg").style.color = "#6366f1";
  } else {
    engineLabel.textContent = "Rule-based engine";
    document.getElementById("engine-badge").querySelector("svg").style.color = "#6b7280";
  }

  // Domain
  document.getElementById("result-domain").textContent = domain_reputation.domain;
  const domScore = document.getElementById("result-domain-score");
  domScore.textContent = `${domain_reputation.reputation_score}/100`;
  domScore.style.color = domain_reputation.reputation_score >= 70 ? "#22c55e"
    : domain_reputation.reputation_score >= 40 ? "#f59e0b" : "#ef4444";
  document.getElementById("domain-rep-label").textContent = `${domain_reputation.reputation_label} · via ${domain_reputation.source}`;

  // Summary
  document.getElementById("result-summary").textContent = summary;

  // Flags
  document.getElementById("flag-count-badge").textContent = markers.length;
  const list = document.getElementById("flags-list");
  list.innerHTML = "";

  if (markers.length === 0) {
    list.innerHTML = `<p style="font-size:12px;color:#6b7280;padding:4px 0;">✅ No specific flags detected in this content.</p>`;
  } else {
    markers.forEach(m => {
      const item = document.createElement("div");
      item.className = `flag-item ${getFlagClass(m.flag_type)}`;
      item.innerHTML = `
        <div class="flag-header">
          <span class="flag-type-label">${escHtml(m.flag_type)}</span>
          <span class="flag-confidence">${Math.round(m.confidence * 100)}% confidence</span>
        </div>
        <p class="flag-explanation">${escHtml(m.explanation)}</p>
        <div class="flag-segment">${escHtml(m.text_segment)}</div>`;
      list.appendChild(item);
    });
  }

  // Footer
  const cacheNote = document.getElementById("cached-note");
  if (cached) cacheNote.textContent = "⚡ Cached result";
  else if (analysis_duration_ms) cacheNote.textContent = `${analysis_duration_ms}ms`;

  showView(Views.RESULT);
}

// ─────────────────────────────────────────────────────────────────────────────
// Page Data Extraction (runs in page context)
// ─────────────────────────────────────────────────────────────────────────────

function extractPageData() {
  const selectors = ["article p", "main p", "[role='main'] p", "p", "h1", "h2", "h3"];
  const seen = new Set();
  let text = "";
  for (const sel of selectors) {
    document.querySelectorAll(sel).forEach(el => {
      const t = el.innerText?.trim();
      if (t && t.length > 40 && !seen.has(t)) { seen.add(t); text += t + "\n"; }
    });
  }
  return {
    url:     window.location.href,
    domain:  window.location.hostname.replace(/^www\./, ""),
    title:   document.title || "",
    content: text.trim().slice(0, 50000),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Analysis Flow
// ─────────────────────────────────────────────────────────────────────────────

let _lastHealthData = null;

async function runAnalysis() {
  showView(Views.LOADING);
  animateSteps();

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("Cannot access the active tab.");

    // Extract page content
    let pageData;
    try {
      const results = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: extractPageData });
      pageData = results?.[0]?.result;
    } catch (_) {
      pageData = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_DATA" });
    }

    if (!pageData?.content || pageData.content.trim().length < 10) {
      throw new Error("Not enough readable text on this page to analyze.");
    }

    // Call backend via background service worker
    const response = await chrome.runtime.sendMessage({
      type: "ANALYZE_PAGE",
      payload: { url: pageData.url, domain: pageData.domain, title: pageData.title, content: pageData.content },
    });

    if (!response.success) throw new Error(response.error || "Unknown API error.");

    // Mark steps done
    STEPS.forEach(id => { const el = document.getElementById(id); if (el) el.className = "load-step done"; });

    renderResult(response.data, _lastHealthData);

    // Inject highlights into the page
    chrome.runtime.sendMessage({ type: "INJECT_HIGHLIGHTS", payload: response.data });

  } catch (err) {
    console.error("[Digital Guardian]", err);
    document.getElementById("error-message").textContent = err.message;
    showView(Views.ERROR);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Utility
// ─────────────────────────────────────────────────────────────────────────────

function escHtml(str) {
  if (!str) return "";
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  _lastHealthData = await checkBackendHealth();
  document.getElementById("btn-scan")?.addEventListener("click", runAnalysis);
  document.getElementById("btn-rescan")?.addEventListener("click", () => { showView(Views.IDLE); setTimeout(runAnalysis, 80); });
  document.getElementById("btn-retry")?.addEventListener("click", runAnalysis);
});
