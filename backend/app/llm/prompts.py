"""
prompts.py — Prompt Engineering for Digital Guardian
─────────────────────────────────────────────────────
All prompts enforce deterministic JSON output from the local LLM.
Designed for Llama-3-8B-Instruct and compatible models via Ollama.

Engineering principle: The LLM is a structured-output machine.
We never ask it to "think freely" — we constrain it to a schema.
"""

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — Injected once per session
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Media and Information Literacy (MIL) analysis engine built for the UNESCO Digital Guardian project.

Your ONLY job is to analyze text for misinformation signals and return structured JSON.

You MUST always respond with valid JSON that matches this exact schema. No prose, no explanation outside the JSON:

{
  "markers": [
    {
      "text_segment": "<exact quote from the text, max 150 chars>",
      "flag_type": "<one of: Sensationalism | Unverified Claim | Logical Fallacy | Loaded Language | Conspiracy Language | Absolute Language | Health Misinformation | AI Hallucination Marker | False Equivalence | Missing Context>",
      "confidence": <float between 0.0 and 1.0>,
      "explanation": "<one sentence explaining WHY this is flagged, referencing MIL principles>"
    }
  ],
  "llm_summary": "<2 sentences max: overall assessment of the text's trustworthiness for a youth audience>"
}

RULES:
1. Only flag what is genuinely suspicious. Do not flag neutral factual statements.
2. confidence must reflect genuine certainty: 0.9+ for obvious flags, 0.5-0.7 for ambiguous ones.
3. text_segment must be a verbatim substring from the input text.
4. If no flags are found, return: {"markers": [], "llm_summary": "No significant misinformation signals detected."}
5. Maximum 8 markers per chunk. Prioritize the most impactful ones.
6. NEVER output anything outside the JSON object."""


# ─────────────────────────────────────────────────────────────────────────────
# User Prompt Template
# ─────────────────────────────────────────────────────────────────────────────

def build_analysis_prompt(text_chunk: str, chunk_index: int, total_chunks: int) -> str:
    """
    Builds the user-turn prompt for a given text chunk.
    Includes chunk context to help the LLM understand scope.
    """
    return f"""Analyze the following text excerpt for Media and Information Literacy (MIL) violations.
This is chunk {chunk_index + 1} of {total_chunks} from the article.

--- BEGIN TEXT ---
{text_chunk.strip()}
--- END TEXT ---

Respond with ONLY a valid JSON object matching the schema. No markdown, no code fences, no explanation outside JSON."""


# ─────────────────────────────────────────────────────────────────────────────
# Synthesis Prompt — Final summary from all chunk results
# ─────────────────────────────────────────────────────────────────────────────

def build_synthesis_prompt(all_flags_summary: str, domain: str, domain_label: str) -> str:
    """
    Builds a final synthesis prompt to generate a cohesive summary
    after all chunks have been analyzed.
    """
    return f"""You are a Media and Information Literacy expert writing a summary for a youth audience (ages 14-25).

Domain analyzed: {domain} (credibility rating: {domain_label})

Flags detected across the article:
{all_flags_summary}

Write a 2-3 sentence plain-English summary of the article's trustworthiness.
- Use simple language a 16-year-old can understand.
- Be specific about what was wrong (or right).
- End with a clear action: what should the reader do?

Respond with ONLY a JSON object:
{{"summary": "<your 2-3 sentence summary here>"}}"""
