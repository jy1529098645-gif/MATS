import json
import re
from llm_service import ask_llm


def _extract_json(text: str):
    text = (text or "").strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    text = re.sub(r"^```json", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^```", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start_obj = text.find("{")
    end_obj = text.rfind("}")
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        candidate = text[start_obj:end_obj + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    raise ValueError("Failed to parse JSON from LLM output.")


def _safe_list(value, max_items=6):
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        s = str(item).strip()
        if s:
            cleaned.append(s)
    return cleaned[:max_items]


def _safe_text(value, fallback=""):
    return str(value).strip() if value is not None else fallback


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


def _run_structured_agent(prompt: str, fallback: dict):
    try:
        raw = ask_llm(prompt)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            return fallback
        return parsed
    except Exception:
        return fallback


def run_researcher(query: str, final_search_query: str, paper_text: str) -> dict:
    prompt = f"""
You are a senior academic research analyst.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Task:
Return a structured research overview.

Return JSON only in this format:
{{
  "coverage_summary": "1 concise paragraph",
  "dominant_themes": ["theme 1", "theme 2", "theme 3"],
  "repeated_findings": ["finding 1", "finding 2", "finding 3"],
  "mature_zones": ["area 1", "area 2"],
  "uneven_zones": ["area 1", "area 2"],
  "narrative": "2-3 paragraph analytical overview"
}}

Rules:
- Use only the provided materials.
- Do not invent evidence.
- Keep list items concise.
"""
    fallback = {
        "coverage_summary": "",
        "dominant_themes": [],
        "repeated_findings": [],
        "mature_zones": [],
        "uneven_zones": [],
        "narrative": ""
    }
    parsed = _run_structured_agent(prompt, fallback)
    return {
        "coverage_summary": _safe_text(parsed.get("coverage_summary")),
        "dominant_themes": _safe_list(parsed.get("dominant_themes")),
        "repeated_findings": _safe_list(parsed.get("repeated_findings")),
        "mature_zones": _safe_list(parsed.get("mature_zones")),
        "uneven_zones": _safe_list(parsed.get("uneven_zones")),
        "narrative": _safe_text(parsed.get("narrative")),
    }


def run_theorist(query: str, final_search_query: str, paper_text: str, researcher_output: dict) -> dict:
    prompt = f"""
You are a conceptual and theoretical analyst.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Researcher output:
{json.dumps(researcher_output, ensure_ascii=False)}

Task:
Return a structured conceptual reading of the literature.

Return JSON only in this format:
{{
  "core_frames": ["frame 1", "frame 2", "frame 3"],
  "distinctions": ["distinction 1", "distinction 2"],
  "tensions": ["tension 1", "tension 2"],
  "blind_spots": ["blind spot 1", "blind spot 2"],
  "narrative": "2-3 paragraph conceptual analysis"
}}

Rules:
- Use only the provided materials.
- Do not invent evidence.
"""
    fallback = {
        "core_frames": [],
        "distinctions": [],
        "tensions": [],
        "blind_spots": [],
        "narrative": ""
    }
    parsed = _run_structured_agent(prompt, fallback)
    return {
        "core_frames": _safe_list(parsed.get("core_frames")),
        "distinctions": _safe_list(parsed.get("distinctions")),
        "tensions": _safe_list(parsed.get("tensions")),
        "blind_spots": _safe_list(parsed.get("blind_spots")),
        "narrative": _safe_text(parsed.get("narrative")),
    }


def run_methodologist(
    query: str,
    final_search_query: str,
    paper_text: str,
    researcher_output: dict,
    theorist_output: dict
) -> dict:
    prompt = f"""
You are a methodology reviewer.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Researcher output:
{json.dumps(researcher_output, ensure_ascii=False)}

Theorist output:
{json.dumps(theorist_output, ensure_ascii=False)}

Task:
Return a structured methodological reading.

Return JSON only in this format:
{{
  "dominant_study_types": ["type 1", "type 2", "type 3"],
  "evidence_profile": "1 concise paragraph",
  "strong_method_areas": ["area 1", "area 2"],
  "thin_method_areas": ["area 1", "area 2"],
  "method_gaps": ["gap 1", "gap 2"],
  "narrative": "2-3 paragraph methodological assessment"
}}

Rules:
- Use only the provided materials.
- Do not invent evidence.
"""
    fallback = {
        "dominant_study_types": [],
        "evidence_profile": "",
        "strong_method_areas": [],
        "thin_method_areas": [],
        "method_gaps": [],
        "narrative": ""
    }
    parsed = _run_structured_agent(prompt, fallback)
    return {
        "dominant_study_types": _safe_list(parsed.get("dominant_study_types")),
        "evidence_profile": _safe_text(parsed.get("evidence_profile")),
        "strong_method_areas": _safe_list(parsed.get("strong_method_areas")),
        "thin_method_areas": _safe_list(parsed.get("thin_method_areas")),
        "method_gaps": _safe_list(parsed.get("method_gaps")),
        "narrative": _safe_text(parsed.get("narrative")),
    }


def run_critic(
    query: str,
    final_search_query: str,
    paper_text: str,
    researcher_output: dict,
    theorist_output: dict,
    methodologist_output: dict
) -> dict:
    prompt = f"""
You are a critical academic reviewer.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Researcher output:
{json.dumps(researcher_output, ensure_ascii=False)}

Theorist output:
{json.dumps(theorist_output, ensure_ascii=False)}

Methodologist output:
{json.dumps(methodologist_output, ensure_ascii=False)}

Task:
Return a structured critical assessment.

Return JSON only in this format:
{{
  "overstatement_risks": ["risk 1", "risk 2"],
  "scope_biases": ["bias 1", "bias 2"],
  "off_target_patterns": ["pattern 1", "pattern 2"],
  "weak_zones": ["zone 1", "zone 2"],
  "narrative": "2-3 paragraph critical review"
}}

Rules:
- Use only the provided materials.
- Do not invent evidence.
"""
    fallback = {
        "overstatement_risks": [],
        "scope_biases": [],
        "off_target_patterns": [],
        "weak_zones": [],
        "narrative": ""
    }
    parsed = _run_structured_agent(prompt, fallback)
    return {
        "overstatement_risks": _safe_list(parsed.get("overstatement_risks")),
        "scope_biases": _safe_list(parsed.get("scope_biases")),
        "off_target_patterns": _safe_list(parsed.get("off_target_patterns")),
        "weak_zones": _safe_list(parsed.get("weak_zones")),
        "narrative": _safe_text(parsed.get("narrative")),
    }


def run_gap_analyst(
    query: str,
    final_search_query: str,
    paper_text: str,
    researcher_output: dict,
    theorist_output: dict,
    methodologist_output: dict,
    critic_output: dict
) -> dict:
    prompt = f"""
You are a research gap analyst.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Researcher output:
{json.dumps(researcher_output, ensure_ascii=False)}

Theorist output:
{json.dumps(theorist_output, ensure_ascii=False)}

Methodologist output:
{json.dumps(methodologist_output, ensure_ascii=False)}

Critic output:
{json.dumps(critic_output, ensure_ascii=False)}

Task:
Return meaningful research gaps grounded in the retrieved set.

Return JSON only in this format:
{{
  "topic_gaps": ["gap 1", "gap 2"],
  "population_or_context_gaps": ["gap 1", "gap 2"],
  "conceptual_gaps": ["gap 1", "gap 2"],
  "methodological_gaps": ["gap 1", "gap 2"],
  "next_research_needs": ["need 1", "need 2", "need 3"],
  "narrative": "2-3 paragraph research gap analysis"
}}

Rules:
- Use only the provided materials.
- Do not invent evidence.
- Avoid generic 'more research is needed' statements.
"""
    fallback = {
        "topic_gaps": [],
        "population_or_context_gaps": [],
        "conceptual_gaps": [],
        "methodological_gaps": [],
        "next_research_needs": [],
        "narrative": ""
    }
    parsed = _run_structured_agent(prompt, fallback)
    return {
        "topic_gaps": _safe_list(parsed.get("topic_gaps")),
        "population_or_context_gaps": _safe_list(parsed.get("population_or_context_gaps")),
        "conceptual_gaps": _safe_list(parsed.get("conceptual_gaps")),
        "methodological_gaps": _safe_list(parsed.get("methodological_gaps")),
        "next_research_needs": _safe_list(parsed.get("next_research_needs")),
        "narrative": _safe_text(parsed.get("narrative")),
    }


def run_verifier(
    query: str,
    final_search_query: str,
    paper_text: str,
    researcher_output: dict,
    theorist_output: dict,
    methodologist_output: dict,
    critic_output: dict,
    gap_output: dict
) -> dict:
    prompt = f"""
You are an academic evidence verifier.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Researcher output:
{json.dumps(researcher_output, ensure_ascii=False)}

Theorist output:
{json.dumps(theorist_output, ensure_ascii=False)}

Methodologist output:
{json.dumps(methodologist_output, ensure_ascii=False)}

Critic output:
{json.dumps(critic_output, ensure_ascii=False)}

Gap output:
{json.dumps(gap_output, ensure_ascii=False)}

Task:
Return a structured evidence verification layer.

Return JSON only in this format:
{{
  "strongly_supported": ["point 1", "point 2", "point 3"],
  "moderately_supported": ["point 1", "point 2"],
  "weakly_supported": ["point 1", "point 2"],
  "uncertain": ["point 1", "point 2"],
  "confidence_level": "High / Medium / Low",
  "confidence_reason": "1 concise paragraph",
  "narrative": "1-2 paragraph synthesis"
}}

Rules:
- Use only the provided materials.
- Do not invent evidence.
- Keep claims concise.
"""
    fallback = {
        "strongly_supported": [],
        "moderately_supported": [],
        "weakly_supported": [],
        "uncertain": [],
        "confidence_level": "Medium",
        "confidence_reason": "",
        "narrative": ""
    }
    parsed = _run_structured_agent(prompt, fallback)
    return {
        "strongly_supported": _safe_list(parsed.get("strongly_supported")),
        "moderately_supported": _safe_list(parsed.get("moderately_supported")),
        "weakly_supported": _safe_list(parsed.get("weakly_supported")),
        "uncertain": _safe_list(parsed.get("uncertain")),
        "confidence_level": _safe_text(parsed.get("confidence_level"), "Medium"),
        "confidence_reason": _safe_text(parsed.get("confidence_reason")),
        "narrative": _safe_text(parsed.get("narrative")),
    }


def run_editor(
    query: str,
    final_search_query: str,
    paper_text: str,
    researcher_output: dict,
    theorist_output: dict,
    methodologist_output: dict,
    critic_output: dict,
    gap_output: dict,
    verifier_output: dict,
    strategy_summary: dict
) -> str:
    prompt = f"""
You are the final synthesis editor for a professional research product.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Strategy summary:
{json.dumps(strategy_summary, ensure_ascii=False)}

Researcher output:
{json.dumps(researcher_output, ensure_ascii=False)}

Theorist output:
{json.dumps(theorist_output, ensure_ascii=False)}

Methodologist output:
{json.dumps(methodologist_output, ensure_ascii=False)}

Critic output:
{json.dumps(critic_output, ensure_ascii=False)}

Gap output:
{json.dumps(gap_output, ensure_ascii=False)}

Verifier output:
{json.dumps(verifier_output, ensure_ascii=False)}

Task:
Write a polished final Research Brief.

Requirements:
- Use only the provided materials.
- Do not invent evidence, references, or metadata.
- Do not include a references section.
- It must sound like a mature research intelligence product.
- It must be direct, readable, and evidence-aware.

Use exactly this structure:

Research Brief

Bottom Line
[1 short but substantive paragraph]

What This Literature Actually Covers
[1 paragraph]

Strongest Signals
[2 paragraphs]

Conceptual Framing
[1 paragraph]

Methodological Reading
[1 paragraph]

Where the Evidence Is Thin
[1 paragraph]

Research Gaps
[1 paragraph]

What This Means for Your Query
[1 paragraph]

Best Next Directions
[1 paragraph]

Confidence & Scope Note
[1 paragraph]

Style rules:
- No AI clichés
- No fake certainty
- Paragraph-based
- Professional and direct
"""
    try:
        return ask_llm(prompt).strip()
    except Exception as e:
        return f"Error: {str(e)}"