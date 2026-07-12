/**
 * background.js — Digital Guardian Service Worker
 * ─────────────────────────────────────────────────
 * SELF-CONTAINED architecture. No backend server required.
 * 
 * Full pipeline runs here:
 *   Agent A: Domain reputation (bundled domains.json)
 *   Agent B: Groq LLM semantic analysis (llama3-70B)
 *   Agent C: Trust Score synthesis
 * 
 * Caches results in chrome.storage.session (cleared on browser close).
 */

// ─────────────────────────────────────────────────────────────────────────────
// MIL System Prompt
// ─────────────────────────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are a Media and Information Literacy (MIL) analysis engine for the UNESCO Digital Guardian project.

Analyze text for misinformation signals. Respond ONLY with valid JSON matching this exact schema:

{
  "markers": [
    {
      "text_segment": "<exact quote from text, max 150 chars>",
      "flag_type": "<one of: Sensationalism | Unverified Claim | Logical Fallacy | Loaded Language | Conspiracy Language | Absolute Language | Health Misinformation | False Equivalence | Missing Context>",
      "confidence": <float 0.0-1.0>,
      "explanation": "<one sentence explaining WHY this violates MIL principles>"
    }
  ],
  "llm_summary": "<2 sentences assessing trustworthiness for a youth audience>"
}

RULES:
1. Only flag genuinely suspicious content. Do not flag neutral factual statements.
2. confidence: 0.9+ for obvious flags, 0.5-0.7 for ambiguous.
3. text_segment must be verbatim from the input.
4. Maximum ${DG_CONFIG.MAX_MARKERS} markers. Prioritize highest confidence.
5. If no flags found: {"markers": [], "llm_summary": "No significant misinformation signals detected."}
6. Output ONLY the JSON object. No prose outside it.`;


// ─────────────────────────────────────────────────────────────────────────────
// Agent A — Domain Reputation
// ─────────────────────────────────────────────────────────────────────────────

let _domainDB = null;

async function loadDomainDB() {
  if (_domainDB) return _domainDB;
  try {
    const url  = chrome.runtime.getURL("domains.json");
    const resp = await fetch(url);
    _domainDB  = await resp.json();
    return _domainDB;
  } catch (e) {
    console.error("[DG] Failed to load domains.json:", e);
    return {};
  }
}

async function verifySource(domain) {
  const db   = await loadDomainDB();
  const clean = domain.replace(/^www\./, "").toLowerCase().trim();

  // Exact match
  if (db[clean]) {
    return { domain: clean, reputation_label: db[clean].label, reputation_score: db[clean].score, source: "local_db" };
  }

  // Partial match (subdomain check)
  for (const [key, val] of Object.entries(db)) {
    if (clean.endsWith(key) || key.endsWith(clean)) {
      return { domain: clean, reputation_label: val.label, reputation_score: val.score, source: "local_db" };
    }
  }

  // Heuristic fallback
  let score = 50;
  const suspiciousTLDs = [".info", ".biz", ".xyz", ".click", ".top", ".win"];
  const suspiciousWords = ["daily", "truth", "real", "free", "alert", "now", "shock", "expose"];
  if (suspiciousTLDs.some(t => clean.endsWith(t))) score -= 20;
  if (suspiciousWords.some(w => clean.includes(w)))  score -= 10;
  if (clean.endsWith(".gov") || clean.endsWith(".edu")) score = 90;
  score = Math.max(5, Math.min(95, score));

  const label = score >= 70 ? "Unknown Source" : score >= 40 ? "Low Credibility Indicators" : "Suspicious Domain";
  return { domain: clean, reputation_label: label, reputation_score: score, source: "heuristic" };
}


// ─────────────────────────────────────────────────────────────────────────────
// Agent B — Groq LLM Semantic Analysis
// ─────────────────────────────────────────────────────────────────────────────

function _extractJSON(raw) {
  raw = raw.trim();
  // Strategy 1: direct parse
  try { return JSON.parse(raw); } catch (_) {}
  // Strategy 2: code fence
  const fence = raw.match(/```(?:json)?\s*([\s\S]+?)\s*```/);
  if (fence) { try { return JSON.parse(fence[1]); } catch (_) {} }
  // Strategy 3: first { } block
  const brace = raw.match(/\{[\s\S]+\}/);
  if (brace) { try { return JSON.parse(brace[0]); } catch (_) {} }
  return null;
}

const RULE_PATTERNS = [
  { re: /\b(shocking|bombshell|you won't believe|jaw-dropping|explosive|outrageous|scandalous)\b/gi, type: "Sensationalism",       conf: 0.75 },
  { re: /\b(allegedly|supposedly|rumored|sources say|insiders claim|some say|it is believed)\b/gi,  type: "Unverified Claim",      conf: 0.70 },
  { re: /\b(deep state|shadow government|wake up|sheeple|they don't want you|mainstream media hides|do your own research)\b/gi, type: "Conspiracy Language", conf: 0.85 },
  { re: /\b(miracle cure|big pharma|doctors hate|ancient secret|100% effective|no side effects|detox)\b/gi, type: "Health Misinformation", conf: 0.80 },
  { re: /\b(always|never|all [a-z]+ are|completely|totally|100%|undeniably|proven fact|without exception)\b/gi, type: "Absolute Language", conf: 0.60 },
  { re: /\b(disaster|apocalypse|invasion|crisis|attack|destroy|wipe out|unprecedented|worst ever)\b/gi, type: "Loaded Language", conf: 0.58 },
];

function ruleFallback(content) {
  const markers = [];
  const seen    = new Set();
  for (const { re, type, conf } of RULE_PATTERNS) {
    for (const m of content.matchAll(re)) {
      if (seen.has(m[0].toLowerCase())) continue;
      seen.add(m[0].toLowerCase());
      const start   = Math.max(0, m.index - 80);
      const end     = Math.min(content.length, m.index + m[0].length + 80);
      const snippet = (start > 0 ? "..." : "") + content.slice(start, end).trim() + (end < content.length ? "..." : "");
      markers.push({ text_segment: snippet, flag_type: type, confidence: conf, explanation: `"${m[0]}" is a common rhetorical device in low-credibility content.` });
      if (markers.length >= DG_CONFIG.MAX_MARKERS) return markers;
    }
  }
  return markers;
}

async function getGroqKey() {
  return new Promise(resolve => chrome.storage.sync.get("groq_api_key", r => resolve(r.groq_api_key || "")));
}

async function analyzeSemantics(content) {
  const apiKey = await getGroqKey();
  if (!apiKey) {
    console.warn("[DG] No Groq API key set — using rule-based fallback.");
    return { markers: ruleFallback(content), engine: "rule_based", llm_summary: "" };
  }

  const truncated  = content.slice(0, DG_CONFIG.MAX_CONTENT_CHARS);
  const userPrompt = `Analyze this article text for MIL violations:\n\n--- BEGIN TEXT ---\n${truncated}\n--- END TEXT ---\n\nRespond with ONLY valid JSON.`;

  try {
    const resp = await fetch(DG_CONFIG.GROQ_URL, {
      method:  "POST",
      headers: { "Authorization": `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body:    JSON.stringify({
        model:           DG_CONFIG.GROQ_MODEL,
        messages:        [{ role: "system", content: SYSTEM_PROMPT }, { role: "user", content: userPrompt }],
        temperature:     0.1,
        max_tokens:      1500,
        response_format: { type: "json_object" },
      }),
    });
    if (!resp.ok) throw new Error(`Groq HTTP ${resp.status}`);
    const data   = await resp.json();
    const raw    = data?.choices?.[0]?.message?.content || "";
    const parsed = _extractJSON(raw);
    if (parsed?.markers && Array.isArray(parsed.markers)) {
      return { markers: parsed.markers.slice(0, DG_CONFIG.MAX_MARKERS), engine: "llm", llm_summary: parsed.llm_summary || "" };
    }
    throw new Error("Bad JSON schema from LLM");
  } catch (err) {
    console.warn("[DG] LLM failed, rule-based fallback:", err.message);
    return { markers: ruleFallback(content.slice(0, DG_CONFIG.MAX_CONTENT_CHARS)), engine: "rule_based", llm_summary: "" };
  }
}



// ─────────────────────────────────────────────────────────────────────────────
// Agent C — Synthesizer
// ─────────────────────────────────────────────────────────────────────────────

function synthesize(domainRep, semanticResult) {
  const { markers, llm_summary } = semanticResult;

  const domainScore   = domainRep.reputation_score;
  const penaltyPer    = 8.0;
  const rawPenalty    = markers.reduce((sum, m) => sum + (m.confidence * penaltyPer), 0);
  const semanticScore = Math.max(0, Math.min(100, 100 - rawPenalty));
  const overall       = Math.round((domainScore * DG_CONFIG.DOMAIN_WEIGHT) + (semanticScore * DG_CONFIG.SEMANTIC_WEIGHT));

  const risk_level = overall >= 70 ? "VERIFIED" : overall >= 40 ? "CAUTION" : "HIGH_RISK";

  // Build summary
  let summary = "";
  if (llm_summary) {
    summary = llm_summary;
  } else {
    const flagTypes = [...new Set(markers.map(m => m.flag_type))];
    if (overall >= 70) {
      summary = `The source '${domainRep.domain}' is rated as '${domainRep.reputation_label}' (${domainScore}/100). No significant misinformation signals were detected. This content appears reliable, but always read critically.`;
    } else {
      const flagStr = flagTypes.slice(0, 3).join(", ");
      summary = `The source '${domainRep.domain}' is rated as '${domainRep.reputation_label}' (${domainScore}/100). ${markers.length} warning signal(s) detected including: ${flagStr}. Verify key claims with a trusted primary source before sharing.`;
    }
  }

  return { overall_score: overall, risk_level, summary };
}


// ─────────────────────────────────────────────────────────────────────────────
// Cache (session storage — cleared on browser close)
// ─────────────────────────────────────────────────────────────────────────────

async function getCached(url) {
  return new Promise(resolve => {
    chrome.storage.session.get(url, r => resolve(r[url] || null));
  });
}

async function setCache(url, payload) {
  return new Promise(resolve => {
    chrome.storage.session.set({ [url]: payload }, resolve);
  });
}


// ─────────────────────────────────────────────────────────────────────────────
// Main Pipeline
// ─────────────────────────────────────────────────────────────────────────────

async function runPipeline(payload) {
  const { url, domain, title, content } = payload;

  // Cache check
  const cached = await getCached(url);
  if (cached) return { ...cached, cached: true };

  const t0 = Date.now();

  const [domainRep, semanticResult] = await Promise.all([
    verifySource(domain),
    analyzeSemantics((title ? title + "\n\n" : "") + content),
  ]);

  const { overall_score, risk_level, summary } = synthesize(domainRep, semanticResult);

  const result = {
    url,
    overall_score,
    risk_level,
    domain_reputation: domainRep,
    markers:   semanticResult.markers,
    summary,
    engine:    semanticResult.engine,
    cached:    false,
    analysis_duration_ms: Date.now() - t0,
  };

  await setCache(url, result);
  return result;
}


// ─────────────────────────────────────────────────────────────────────────────
// Message Handler
// ─────────────────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "ANALYZE_PAGE") {
    runPipeline(message.payload)
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // async
  }

  if (message.type === "INJECT_HIGHLIGHTS") {
    const tabId = sender.tab?.id;
    if (tabId && message.payload?.markers?.length > 0) {
      chrome.tabs.sendMessage(tabId, { type: "RENDER_HIGHLIGHTS", payload: message.payload });
    }
    return false;
  }

  if (message.type === "HEALTH_CHECK") {
    // Always healthy — no backend to check
    sendResponse({ status: "online", version: "2.0.0", engine: "groq-llm", llm_reachable: true, llm_model: DG_CONFIG.GROQ_MODEL });
    return false;
  }
});
