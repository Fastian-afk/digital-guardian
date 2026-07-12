# ⚡ Digital Guardian — UNESCO MIL Hackathon 2026

> **A sovereign, privacy-first AI Trust Layer for the web.**  
> Real-time misinformation detection with explainable AI, built for youth.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![LLM](https://img.shields.io/badge/LLM-llama3--70B%20via%20Groq-f97316?logo=meta)](https://groq.com)
[![Extension](https://img.shields.io/badge/Chrome%20Extension-MV3-4285F4?logo=googlechrome&logoColor=white)](https://developer.chrome.com/docs/extensions/mv3/)

---

## 🎯 What is Digital Guardian?

Digital Guardian is a **real-time Trust Layer** — a Chrome browser extension backed by a local FastAPI server — that analyzes news articles and social media content for misinformation, sensationalism, and bias.

It provides **explainable Trust Scores** powered by llama3-70B (via Groq) so youth users understand *why* content was flagged — not just *that* it was. Every flag comes with a plain-English MIL-aligned explanation.

### Core Principles
| Principle | Implementation |
|-----------|---------------|
| 🔒 **Data Sovereignty** | No browsing data sent to third parties. Analysis via Groq is text-only, no PII. |
| 🧠 **Explainable AI** | Every Trust Score backed by specific, labeled `ExplainabilityMarker` objects |
| ⚡ **Real-time** | <2 second analysis. Cached results return in <50ms |
| 🎯 **Youth-first UX** | Plain English summaries, color-coded risk, visual highlights |
| 🛡️ **Zero local storage** | No model downloads. Groq API = 0 bytes disk usage |

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Chrome Browser                           │
│                                                                  │
│  ┌─────────────────────┐   ┌──────────────────────────────────┐ │
│  │   Popup UI          │   │   Content Script (content.js)    │ │
│  │   popup.html/css/js │◄──│   • DOM scraper                  │ │
│  │   • Trust Score     │   │   • Shadow DOM Trust Badge       │ │
│  │   • Risk Badge      │   │   • TreeWalker highlight engine  │ │
│  │   • Flag Explorer   │   └──────────────────────────────────┘ │
│  └──────────┬──────────┘                │                        │
│             │    background.js (MV3 Service Worker)              │
└─────────────┼──────────────────────────-┼────────────────────────┘
              │ POST /api/v1/analyze       │ RENDER_HIGHLIGHTS msg
              ▼
┌─────────────────────────────────────────────────────────────────┐
│              FastAPI Backend  (localhost:8000)                   │
│                                                                  │
│  POST /api/v1/analyze                                           │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                Multi-Agent Pipeline                    │    │
│  │                                                        │    │
│  │  Agent A: Source Verifier                              │    │
│  │  ├─ Query local SQLite domain_reputation table         │    │
│  │  └─ Heuristic fallback (TLD + keyword scoring)         │    │
│  │                                                        │    │
│  │  Agent B: Semantic Analyzer (Dual-Engine)              │    │
│  │  ├─ PRIMARY: Groq API → llama3-70b-8192               │    │
│  │  │   • MIL-aligned prompt with JSON schema enforcement │    │
│  │  │   • 3-strategy JSON extraction fallback             │    │
│  │  └─ FALLBACK: Rule-based NLP (6 pattern categories)    │    │
│  │                                                        │    │
│  │  Agent C: Synthesizer                                  │    │
│  │  ├─ Composite score: Domain(40%) + Semantic(60%)       │    │
│  │  └─ Adaptive youth-readable plain-English summary      │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
│  SQLite DB  ──  analyzed_urls (6h TTL cache)                    │
│             └─  domain_reputation (20 seeded domains)            │
└─────────────────────────────────────────────────────────────────┘
              │ HTTP
              ▼
    ┌─────────────────┐
    │   Groq API      │   llama-3.3-70b-versatile
    │   (free tier)   │   ~500 tok/sec, JSON mode
    └─────────────────┘
```

---

## 📊 Trust Score Algorithm

```
Final Score = (Domain Reputation Score × 40%) + (Semantic Score × 60%)

Semantic Score = 100 − Σ(marker.confidence × 8.0)   [max penalty: −60]

Risk Levels:
  ✅ VERIFIED   → Score ≥ 70   (Green)
  ⚠️ CAUTION   → Score 40–69  (Yellow)
  🚨 HIGH_RISK  → Score < 40   (Red)
```

**Flag Types (detected by llama3-70B):**
- `Sensationalism` · `Unverified Claim` · `Logical Fallacy`
- `Loaded Language` · `Conspiracy Language` · `Absolute Language`
- `Health Misinformation` · `AI Hallucination Marker`
- `False Equivalence` · `Missing Context`

---

## 📁 Project Structure

```
digital-guardian/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, lifespan
│   │   ├── config.py                # Pydantic Settings (.env driven)
│   │   ├── schemas/analysis.py      # AnalysisRequest, TrustPayload, markers
│   │   ├── routers/analyze.py       # POST /analyze, GET /health + cache logic
│   │   ├── agents/
│   │   │   ├── source_verifier.py   # Agent A
│   │   │   ├── semantic_analyzer.py # Agent B (LLM + fallback)
│   │   │   └── synthesizer.py       # Agent C
│   │   ├── llm/
│   │   │   ├── client.py            # Groq API client, JSON extraction
│   │   │   └── prompts.py           # MIL-aligned prompt engineering
│   │   ├── db/database.py           # Async SQLite, models, seeding
│   │   └── utils/logger.py          # Structured logging
│   ├── run.py                       # Dev server launcher
│   ├── requirements.txt
│   └── .env                         # GROQ_API_KEY goes here
│
├── extension/
│   ├── manifest.json                # MV3, minimal permissions
│   ├── background.js                # Service worker, API relay
│   ├── content.js                   # DOM scraper, Shadow DOM, highlights
│   ├── popup/
│   │   ├── popup.html
│   │   ├── popup.css
│   │   └── popup.js
│   └── icons/
│
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12
- Google Chrome
- [Free Groq API key](https://console.groq.com) (2 min signup)

### 1 — Backend Setup

```powershell
cd "d:\UNESCO HACKATHON\backend"
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2 — Configure Groq API Key

Edit `backend/.env`:
```
GROQ_API_KEY=gsk_your_key_here
LLM_MODEL=llama-3.3-70b-versatile
```

### 3 — Start the Server

```powershell
python run.py
# → http://127.0.0.1:8000
# → Swagger UI: http://127.0.0.1:8000/docs
```

### 4 — Load the Chrome Extension

1. `chrome://extensions/` → enable **Developer Mode**
2. **Load unpacked** → select `d:\UNESCO HACKATHON\extension\`
3. Pin the **Digital Guardian** shield icon

### 5 — Scan a Page

Navigate to any news site → click the shield → **Scan This Page**

---

## 🌐 API Reference

### `POST /api/v1/analyze`

```json
// Request
{
  "url": "https://naturalnews.com/article",
  "domain": "naturalnews.com",
  "title": "SHOCKING: Secret Cure",
  "content": "Scientists allegedly proven..."
}

// Response (TrustPayload)
{
  "url": "...",
  "overall_score": 12,
  "risk_level": "HIGH_RISK",
  "domain_reputation": {
    "domain": "naturalnews.com",
    "reputation_label": "Known Misinformation",
    "reputation_score": 8,
    "source": "local_db"
  },
  "markers": [
    {
      "text_segment": "allegedly proven that this miracle remedy cures cancer",
      "flag_type": "Unverified Claim",
      "confidence": 0.95,
      "explanation": "This claim lacks credible sources and violates MIL verification principles."
    }
  ],
  "summary": "...",
  "cached": false,
  "analysis_duration_ms": 1844
}
```

### `GET /api/v1/health`
Returns `llm_reachable: true/false`, `llm_model`, `db_status`.

---

## 📋 Development Phases

| Phase | Status | Deliverable |
|-------|--------|-------------|
| **Phase 1** | ✅ Done | FastAPI + rule-based NLP + extension UI |
| **Phase 2** | ✅ Done | Groq LLM (llama3-70B) + dual-engine fallback |
| **Phase 3** | ✅ Done | Polished extension UI, animations, per-type flags |
| **Phase 4** | ✅ Done | Documentation, README, UNESCO submission |

---

## 🏆 UNESCO MIL Alignment

| Judging Criterion | Digital Guardian Response |
|-------------------|--------------------------|
| **MIL Consistency** | Directly tackles the "Trust Challenge" — detects sensationalism, conspiracy language, health misinformation per MIL frameworks |
| **Clarity & UX** | Youth-first design, plain English summaries, color-coded risk levels, visual page highlights |
| **Innovation** | Multi-agent sovereign AI pipeline, llama3-70B semantic reasoning, XAI explainability markers |
| **Feasibility** | Runs on any Windows machine, free Groq API, <2s analysis, zero ML dependencies |

---

## 👤 Author

**Imaad Fazal** — Applied AI/ML Intern @ TechGIS | CS Undergraduate, FAST-NUCES  
**UNESCO MIL Youth Hackathon 2026** — Competing for Voice Festival, Thessaloniki, Greece 🇬🇷

---

*Digital Guardian treats AI safety as a structural engineering problem, not a behavioral suggestion.*
