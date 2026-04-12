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

def _has_meaningful_content(parsed: dict) -> bool:
    if not isinstance(parsed, dict):
        return False
    for value in parsed.values():
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and any(str(x).strip() for x in value):
            return True
        if isinstance(value, dict) and value:
            return True
    return False


def _fallback_methodologist_output() -> dict:
    return {
        "dominant_study_types": ["empirical studies and reviews"],
        "evidence_profile": "The available set appears usable for identifying recurring associations, but the evidence is uneven for causal interpretation and long-term mechanisms.",
        "strong_method_areas": ["association mapping", "review-level synthesis"],
        "thin_method_areas": ["longitudinal evidence", "behavioral measurement"],
        "method_gaps": ["more causal designs", "better behavioral data"],
        "narrative": "The methodological signal in the retrieved set is sufficient for broad evidence mapping, but it is weaker for directionality, mediation, and long-term development. Cross-sectional or review-oriented evidence appears to dominate, so conclusions should be framed as association-aware rather than strongly causal.",
    }


def _fallback_critic_output() -> dict:
    return {
        "overstatement_risks": ["association may be overstated as causation"],
        "scope_biases": ["retrieval may overrepresent one interpretation of the query"],
        "off_target_patterns": ["some adjacent papers may remain in the final set"],
        "weak_zones": ["thin coverage outside the dominant interpretation"],
        "narrative": "The critical layer should remain cautious about overclaiming. The retrieved evidence may strongly support a dominant interpretation of the query while still underrepresenting alternative meanings, adjacent domains, or broader contextual explanations.",
    }






def _fallback_gap_analyst_output() -> dict:
    return {
        "topic_gaps": [
            "The retrieved set is thinner on more specific subtopics than on the core framing of the query."
        ],
        "population_or_context_gaps": [
            "The literature appears limited across diverse player groups, settings, or longer-term usage contexts."
        ],
        "conceptual_gaps": [
            "Important concepts are discussed, but their boundaries and relationships are not always defined consistently across papers."
        ],
        "methodological_gaps": [
            "The evidence base would benefit from larger samples, stronger causal designs, and better-aligned outcome measures."
        ],
        "next_research_needs": [
            "Tighter subtopic comparisons",
            "More direct tests of the key mechanisms",
            "Better alignment between design claims and measured outcomes"
        ],
        "narrative": "The gap-analysis layer suggests that the retrieved literature is good for mapping the dominant terrain of the topic, but less complete when the question becomes more specific, comparative, or mechanism-focused. The clearest missing pieces are stronger conceptual separation of key constructs, broader coverage across contexts and populations, and more methodologically consistent tests of the claims that design or theory papers often advance.",
    }


def _ensure_gap_payload(parsed: dict) -> dict:
    fallback = _fallback_gap_analyst_output()
    parsed = parsed if isinstance(parsed, dict) else {}
    merged = dict(fallback)
    merged.update(parsed)

    for key in ["topic_gaps", "population_or_context_gaps", "conceptual_gaps", "methodological_gaps", "next_research_needs"]:
        value = _safe_list(merged.get(key))
        if not value:
            value = fallback[key]
        merged[key] = value

    narrative = _safe_text(merged.get("narrative"))
    if not narrative:
        narrative = fallback["narrative"]
    merged["narrative"] = narrative
    return merged

def _fallback_verifier_output() -> dict:
    return {
        "strongly_supported": [
            "The retrieved papers support a usable high-level synthesis, but not all claims are equally strong."
        ],
        "moderately_supported": [
            "Several recurring patterns appear across the paper set, though they are not always supported by the same study designs.",
            "The literature provides some converging support for the dominant interpretation of the query."
        ],
        "weakly_supported": [
            "Some finer-grained causal or mechanism-level claims remain under-supported in the retrieved set."
        ],
        "uncertain": [
            "Claims requiring strong causal inference, long-term effects, or broad generalization remain uncertain."
        ],
        "confidence_level": "Medium",
        "confidence_reason": "The retrieved paper set is strong enough for a practical literature overview, but the support is uneven across claim types. Broad thematic patterns are more reliable than precise causal or universal claims.",
        "narrative": "The verifier judges this evidence base as usable but mixed. The strongest support lies in recurring themes and broad patterns that appear across multiple papers, while more specific causal, comparative, or mechanism-level claims should be stated cautiously.",
        "evidence_chain_summary": "The strongest chain of support comes from patterns that recur across multiple retrieved papers and align with the dominant themes identified by other agents. Support weakens for more specific claims that depend on a smaller subset of papers, limited abstracts, or less direct domain matches, and becomes uncertain where the literature appears thin, adjacent, or methodologically uneven."
    }


def _ensure_verifier_payload(parsed: dict) -> dict:
    fallback = _fallback_verifier_output()
    parsed = parsed if isinstance(parsed, dict) else {}
    merged = dict(fallback)
    merged.update(parsed)

    for key in ["strongly_supported", "moderately_supported", "weakly_supported", "uncertain"]:
        value = _safe_list(merged.get(key))
        if not value:
            value = fallback[key]
        merged[key] = value

    for key in ["confidence_level", "confidence_reason", "narrative", "evidence_chain_summary"]:
        value = _safe_text(merged.get(key))
        if not value:
            value = fallback[key]
        merged[key] = value

    level = merged["confidence_level"].strip().capitalize()
    if level not in ["High", "Medium", "Low"]:
        level = fallback["confidence_level"]
    merged["confidence_level"] = level
    return merged

def _run_structured_agent(
    prompt: str,
    fallback: dict,
    provider: str = "openai",
    model: str | None = None,
    max_tokens: int | None = None,
    backup_provider: str | None = "openai",
    backup_model: str | None = "gpt-5.4-mini",
):
    attempts = []
    primary_provider = (provider or "openai").strip().lower()
    attempts.append((primary_provider, model, max_tokens))

    backup_provider_norm = (backup_provider or "").strip().lower()
    if backup_provider_norm and backup_provider_norm != primary_provider:
        attempts.append((backup_provider_norm, backup_model, max_tokens))

    for attempt_provider, attempt_model, attempt_max_tokens in attempts:
        try:
            raw = ask_llm(
                prompt=prompt,
                provider=attempt_provider,
                model=attempt_model,
                max_tokens=attempt_max_tokens,
            )
            parsed = _extract_json(raw)
            if isinstance(parsed, dict) and _has_meaningful_content(parsed):
                return parsed
        except Exception:
            continue

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
    parsed = _run_structured_agent(
        prompt,
        fallback,
        provider="openai",
        model="gpt-5.4-mini",
        max_tokens=2200,
    )
    return {
        "coverage_summary": _safe_text(parsed.get("coverage_summary")),
        "dominant_themes": _safe_list(parsed.get("dominant_themes")),
        "repeated_findings": _safe_list(parsed.get("repeated_findings")),
        "mature_zones": _safe_list(parsed.get("mature_zones")),
        "uneven_zones": _safe_list(parsed.get("uneven_zones")),
        "narrative": _safe_text(parsed.get("narrative")),
    }


def run_theorist(query: str, final_search_query: str, paper_text: str, researcher_output: dict | None = None) -> dict:
    prompt = f"""
You are a conceptual and theoretical analyst.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Task:
Return a structured conceptual reading of the literature.

Important independence rule:
- Work directly from the retrieved paper summaries and metadata.
- Do not rely on or be influenced by other agent outputs.
- Treat this as an independent conceptual reading of the same evidence set.

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
    parsed = _run_structured_agent(
        prompt,
        fallback,
        provider="openai",
        model="gpt-5.4-mini",
        max_tokens=2200,
    )
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
    researcher_output: dict | None = None,
    theorist_output: dict | None = None
) -> dict:
    prompt = f"""
You are a methodology reviewer.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Task:
Return a structured methodological reading.

Important independence rule:
- Work directly from the retrieved paper summaries and metadata.
- Do not rely on or be influenced by other agent outputs.
- Treat this as an independent methodological reading of the same evidence set.

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
    fallback = _fallback_methodologist_output()
    parsed = _run_structured_agent(
        prompt,
        fallback,
        provider="claude",
        model="claude-sonnet-4-6",
        max_tokens=2600,
        backup_provider="openai",
        backup_model="gpt-5.4-mini",
    )
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
    researcher_output: dict | None = None,
    theorist_output: dict | None = None,
    methodologist_output: dict | None = None
) -> dict:
    prompt = f"""
You are a critical academic reviewer.

User topic:
{query}

Final search query:
{final_search_query}

Retrieved paper summaries and metadata:
{paper_text}

Task:
Return a structured critical assessment.

Important independence rule:
- Work directly from the retrieved paper summaries and metadata.
- Do not rely on or be influenced by other agent outputs.
- Treat this as an independent critical reading of the same evidence set.

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
    fallback = _fallback_critic_output()
    parsed = _run_structured_agent(
        prompt,
        fallback,
        provider="claude",
        model="claude-sonnet-4-6",
        max_tokens=2600,
        backup_provider="openai",
        backup_model="gpt-5.4-mini",
    )
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

Integration rule:
- Use the paper summaries as the primary evidence base.
- Use the other agent outputs only as independent viewpoints to compare, reconcile, and triangulate.
- Do not simply repeat another agent's wording; synthesize across perspectives.

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
    fallback = _fallback_gap_analyst_output()
    parsed = _run_structured_agent(
        prompt,
        fallback,
        provider="openai",
        model="gpt-5.4-mini",
        max_tokens=2200,
    )
    parsed = _ensure_gap_payload(parsed)
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

Arbitration rule:
- Treat Researcher, Theorist, Methodologist, Critic, and Gap outputs as independent viewpoints.
- Compare them against the paper summaries and metadata.
- Reward points that converge across multiple viewpoints and the source evidence.
- Downgrade points that depend on only one viewpoint or overreach the retrieved evidence.

Return JSON only in this format:
{{
  "strongly_supported": ["point 1", "point 2", "point 3"],
  "moderately_supported": ["point 1", "point 2"],
  "weakly_supported": ["point 1", "point 2"],
  "uncertain": ["point 1", "point 2"],
  "confidence_level": "High / Medium / Low",
  "confidence_reason": "1 concise paragraph",
  "narrative": "1-2 paragraph synthesis",
  "evidence_chain_summary": "1 concise paragraph explaining how the strongest claims connect to the underlying paper set and where the chain weakens"
}}

Rules:
- Use only the provided materials.
- Do not invent evidence.
- Keep claims concise.
- The evidence_chain_summary must explicitly describe what the strongest chain of support is, what is only moderately supported, and where the chain becomes weak or uncertain.
"""
    fallback = _fallback_verifier_output()
    parsed = _run_structured_agent(
        prompt,
        fallback,
        provider="openai",
        model="gpt-5.4-mini",
        max_tokens=2200,
    )
    parsed = _ensure_verifier_payload(parsed)
    return {
        "strongly_supported": _safe_list(parsed.get("strongly_supported")),
        "moderately_supported": _safe_list(parsed.get("moderately_supported")),
        "weakly_supported": _safe_list(parsed.get("weakly_supported")),
        "uncertain": _safe_list(parsed.get("uncertain")),
        "confidence_level": _safe_text(parsed.get("confidence_level"), "Medium"),
        "confidence_reason": _safe_text(parsed.get("confidence_reason")),
        "narrative": _safe_text(parsed.get("narrative")),
        "evidence_chain_summary": _safe_text(parsed.get("evidence_chain_summary")),
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
) -> dict:
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
- Most paragraphs should cite at least one specific paper inline using the exact format: (Author et al., Year), (Author & Author, Year), or (Author, Year)
- Prefer specific paper-linked claims over generic statements
- When you mention a finding, tension, method pattern, or limitation, anchor it to one or more concrete papers from the retrieved set
- Reduce vague phrases like "the literature suggests" unless they are immediately followed by a concrete inline citation
"""
    try:
        return ask_llm(
            prompt,
            provider="openai",
            model="gpt-5.4-mini",
            max_tokens=2600,
        ).strip()
    except Exception as e:
        return f"Error: {str(e)}"