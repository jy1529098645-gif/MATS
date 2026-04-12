import json
import re
import difflib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import streamlit as st

from llm_service import ask_llm
from search_service import search_papers_with_diagnostics_live
from agent_service import (
    run_researcher,
    run_theorist,
    run_methodologist,
    run_critic,
    run_gap_analyst,
    run_verifier,
    run_editor,
)


def _safe_json_dumps(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _emit(progress_callback, value, message, payload=None):
    if progress_callback:
        try:
            progress_callback(value, message, payload)
        except TypeError:
            progress_callback(value, message)


def _emit_progress(progress_callback, value, message, payload=None):
    merged_payload = {"type": "progress"}
    if isinstance(payload, dict):
        merged_payload.update(payload)

    if progress_callback:
        try:
            progress_callback(value, message, merged_payload)
        except TypeError:
            progress_callback(value, message)


def _truncate_text(text: str, max_chars: int = 1000) -> str:
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _safe_text(value, fallback=""):
    return str(value).strip() if value is not None else fallback


def _safe_bool(value, fallback=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ["true", "yes", "1"]:
            return True
        if v in ["false", "no", "0"]:
            return False
    return fallback


def _safe_list(value, max_items=8):
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        s = str(item).strip()
        if s:
            cleaned.append(s)
    return cleaned[:max_items]


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


def _run_structured_llm(prompt: str, fallback: dict):
    try:
        raw = ask_llm(prompt)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            return fallback
        return parsed
    except Exception:
        return fallback


def clean_doi(doi):
    if not doi:
        return ""
    doi = str(doi).strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "").strip()
    return doi


def normalize_title_key(title: str) -> str:
    title = str(title or "").lower().strip()
    title = re.sub(r"\([^)]*\)", " ", title)
    title = re.sub(r"[^a-z0-9\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()

    stop_words = {
        "the", "a", "an", "of", "on", "for", "in", "and", "to", "with",
        "via", "using", "through", "from", "how", "does", "do"
    }
    tokens = [t for t in title.split() if t not in stop_words]
    return " ".join(tokens)


def titles_near_duplicate(t1: str, t2: str) -> bool:
    k1 = normalize_title_key(t1)
    k2 = normalize_title_key(t2)

    if not k1 or not k2:
        return False
    if k1 == k2:
        return True
    if k1 in k2 or k2 in k1:
        return True

    sim = difflib.SequenceMatcher(None, k1, k2).ratio()
    return sim >= 0.97


def deduplicate_final_papers(papers: List[dict], target_count: int):
    kept = []
    duplicates_removed = 0

    seen_dois = set()
    seen_titles = []

    for p in papers:
        doi = clean_doi(p.get("doi"))
        title = p.get("title", "")

        duplicate = False

        if doi:
            if doi in seen_dois:
                duplicate = True
            else:
                seen_dois.add(doi)

        if not duplicate:
            for prev_title in seen_titles:
                if titles_near_duplicate(title, prev_title):
                    duplicate = True
                    break

        if duplicate:
            duplicates_removed += 1
            continue

        kept.append(p)
        seen_titles.append(title)

        if len(kept) >= target_count:
            break

    return kept, duplicates_removed


def _paper_inline_citation(p: dict) -> str:
    authors = str(p.get("authors", "") or "").strip()
    year = str(p.get("year", "Unknown year") or "Unknown year").strip()
    author_parts = [a.strip() for a in authors.split(",") if a.strip()]
    surnames = []
    for part in author_parts[:3]:
        tokens = [t for t in re.split(r"\s+", part) if t]
        if tokens:
            surnames.append(tokens[-1])
    if not surnames:
        return f"Unknown, {year}"
    if len(surnames) == 1:
        return f"{surnames[0]}, {year}"
    if len(surnames) == 2:
        return f"{surnames[0]} & {surnames[1]}, {year}"
    return f"{surnames[0]} et al., {year}"


def build_paper_text(papers: List[dict]) -> str:
    blocks = []
    for idx, p in enumerate(papers, start=1):
        blocks.append(
            f"Paper ID: {idx}\n"
            f"Preferred inline citation: {_paper_inline_citation(p)}\n"
            f"Title: {p.get('title', '')}\n"
            f"Authors: {p.get('authors', '')}\n"
            f"Year: {p.get('year', '')}\n"
            f"Source: {p.get('source', '')}\n"
            f"Abstract: {_truncate_text(p.get('summary', ''), 1200)}\n"
            f"Evidence strength: {p.get('evidence_strength', 'Moderate')} ({p.get('evidence_score', 50)}/100)\n"
            f"Research fit score: {p.get('research_fit_score', 55)}/100\n"
            f"Domain fit: {p.get('domain_fit_label', 'adjacent')}\n"
            f"Paper type: {p.get('paper_type_label', 'theory/other')}\n"
            f"Off-target risk: {p.get('off_target_risk_score', 40)}/100\n"
            f"Open access: {p.get('is_oa', False)}\n"
            f"Why recommended: {p.get('recommendation_reason', '')}"
        )
    return "\n\n".join(blocks)


def average_research_fit(papers: List[dict]) -> float:
    vals = []
    for p in papers:
        try:
            vals.append(float(p.get("research_fit_score", 0)))
        except Exception:
            pass
    return sum(vals) / len(vals) if vals else 0.0


def average_off_target_risk(papers: List[dict]) -> float:
    vals = []
    for p in papers:
        try:
            vals.append(float(p.get("off_target_risk_score", 0)))
        except Exception:
            pass
    return sum(vals) / len(vals) if vals else 100.0


def domain_fit_distribution(papers: List[dict]) -> dict:
    counts = {
        "direct": 0,
        "mostly direct": 0,
        "adjacent": 0,
        "off-target": 0,
    }
    for p in papers:
        label = str(p.get("domain_fit_label", "adjacent")).strip().lower()
        if label in counts:
            counts[label] += 1
        else:
            counts["adjacent"] += 1
    return counts


def direct_ratio(papers: List[dict]) -> float:
    if not papers:
        return 0.0
    dist = domain_fit_distribution(papers)
    direct_like = dist.get("direct", 0) + dist.get("mostly direct", 0)
    return direct_like / max(1, len(papers))


def add_trace(state: dict, agent_name: str, action: str, details: str = "", progress_callback=None):
    entry = {
        "agent": agent_name,
        "action": action,
        "details": details,
    }
    state.setdefault("trace", []).append(entry)

    if progress_callback:
        _emit(
            progress_callback,
            state.get("metrics", {}).get("step_count", 0),
            f"{agent_name}: {action}...",
            payload={
                "type": "workflow",
                "agent": agent_name,
                "action": action,
                "details": details,
            }
        )


def pop_next_task(state: dict):
    tasks = state.get("tasks", [])
    if not tasks:
        return None
    return tasks.pop(0)


def clear_downstream_outputs_after_retrieval(state: dict):
    state["query_planner_review"] = {}
    state["researcher"] = {}
    state["theorist"] = {}
    state["methodologist"] = {}
    state["critic"] = {}
    state["gap_analyst"] = {}
    state["verifier"] = {}
    state["editor"] = ""
    state["editor_error"] = ""
    state["flags"]["analysis_bundle_done"] = False


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_query_planner_initial(
    original_query: str,
    final_search_query: str,
    selected_option_json: str,
):
    selected_option = json.loads(selected_option_json) if selected_option_json else {}

    prompt = f"""
You are a Query Planner Agent inside a multi-agent academic research system.

Original user query:
{original_query}

Current final search query:
{final_search_query}

Selected interpretation:
{json.dumps(selected_option, ensure_ascii=False)}

Task:
Create an initial routing plan before retrieval.

Return JSON only in this exact format:
{{
  "planner_summary": "1 concise paragraph",
  "query_type": "clear / ambiguous / broad / narrow / exploratory",
  "search_focus": "balanced / narrow_core / broad_exploration",
  "theorist_needed": true,
  "critic_needed": true,
  "verifier_needed": true,
  "refinement_if_weak_results": "1 short sentence",
  "priority_questions": ["question 1", "question 2", "question 3"],
  "risk_flags": ["flag 1", "flag 2"]
}}

Rules:
- Be conservative.
- Do not invent facts about papers that have not yet been retrieved.
- Base your judgment only on the query and selected interpretation.
- Return valid JSON only.
"""
    fallback = {
        "planner_summary": "The query appears workable for balanced retrieval and downstream evidence checking.",
        "query_type": "clear",
        "search_focus": "balanced",
        "theorist_needed": True,
        "critic_needed": True,
        "verifier_needed": True,
        "refinement_if_weak_results": "If the retrieved papers are too adjacent or off-target, tighten toward core-domain papers.",
        "priority_questions": [],
        "risk_flags": [],
    }

    parsed = _run_structured_llm(prompt, fallback)
    return {
        "planner_summary": _safe_text(parsed.get("planner_summary")),
        "query_type": _safe_text(parsed.get("query_type"), "clear"),
        "search_focus": _safe_text(parsed.get("search_focus"), "balanced"),
        "theorist_needed": _safe_bool(parsed.get("theorist_needed"), True),
        "critic_needed": _safe_bool(parsed.get("critic_needed"), True),
        "verifier_needed": _safe_bool(parsed.get("verifier_needed"), True),
        "refinement_if_weak_results": _safe_text(parsed.get("refinement_if_weak_results")),
        "priority_questions": _safe_list(parsed.get("priority_questions")),
        "risk_flags": _safe_list(parsed.get("risk_flags")),
    }


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_query_planner_review(
    original_query: str,
    final_search_query: str,
    selected_option_json: str,
    papers_json: str,
    diagnostics_json: str,
    prior_planner_json: str,
):
    selected_option = json.loads(selected_option_json) if selected_option_json else {}
    papers = json.loads(papers_json) if papers_json else []
    diagnostics = json.loads(diagnostics_json) if diagnostics_json else {}
    prior_planner = json.loads(prior_planner_json) if prior_planner_json else {}

    compact_papers = []
    for p in papers[:15]:
        compact_papers.append({
            "title": p.get("title", ""),
            "year": p.get("year", ""),
            "source": p.get("source", ""),
            "research_fit_score": p.get("research_fit_score", 0),
            "domain_fit_label": p.get("domain_fit_label", ""),
            "off_target_risk_score": p.get("off_target_risk_score", 0),
            "recommendation_reason": p.get("recommendation_reason", ""),
        })

    prompt = f"""
You are a Query Planner Agent reviewing the first retrieval pass inside a multi-agent academic research system.

Original user query:
{original_query}

Current final search query:
{final_search_query}

Selected interpretation:
{json.dumps(selected_option, ensure_ascii=False)}

Initial planning layer:
{json.dumps(prior_planner, ensure_ascii=False)}

Diagnostics:
{json.dumps(diagnostics, ensure_ascii=False)}

Retrieved papers (compact):
{json.dumps(compact_papers, ensure_ascii=False)}

Task:
Judge whether the retrieval appears focused enough, and whether the system should refine retrieval before final synthesis.

Return JSON only in this exact format:
{{
  "review_summary": "1 concise paragraph",
  "retrieval_assessment": "good / acceptable / weak",
  "should_refine": true,
  "refinement_reason": "1 concise sentence",
  "revised_search_focus": "balanced / narrow_core / broad_exploration",
  "revised_strict_core_only": false,
  "revised_prefer_abstracts": true,
  "priority_issues": ["issue 1", "issue 2"],
  "notes_for_router": ["note 1", "note 2"]
}}

Rules:
- Be conservative. Only recommend refinement when the retrieved set seems meaningfully off-target, too adjacent, too noisy, or too weak.
- Do not invent paper content.
- Return valid JSON only.
"""
    fallback = {
        "review_summary": "The first retrieval pass appears usable for downstream analysis, with no strong need for immediate refinement.",
        "retrieval_assessment": "acceptable",
        "should_refine": False,
        "refinement_reason": "",
        "revised_search_focus": "balanced",
        "revised_strict_core_only": False,
        "revised_prefer_abstracts": True,
        "priority_issues": [],
        "notes_for_router": [],
    }

    parsed = _run_structured_llm(prompt, fallback)
    return {
        "review_summary": _safe_text(parsed.get("review_summary")),
        "retrieval_assessment": _safe_text(parsed.get("retrieval_assessment"), "acceptable"),
        "should_refine": _safe_bool(parsed.get("should_refine"), False),
        "refinement_reason": _safe_text(parsed.get("refinement_reason")),
        "revised_search_focus": _safe_text(parsed.get("revised_search_focus"), "balanced"),
        "revised_strict_core_only": _safe_bool(parsed.get("revised_strict_core_only"), False),
        "revised_prefer_abstracts": _safe_bool(parsed.get("revised_prefer_abstracts"), True),
        "priority_issues": _safe_list(parsed.get("priority_issues")),
        "notes_for_router": _safe_list(parsed.get("notes_for_router")),
    }


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_researcher(original_query: str, final_search_query: str, paper_text: str):
    return run_researcher(original_query, final_search_query, paper_text)


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_theorist(original_query: str, final_search_query: str, paper_text: str):
    return run_theorist(original_query, final_search_query, paper_text)


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_methodologist(
    original_query: str,
    final_search_query: str,
    paper_text: str,
):
    return run_methodologist(
        original_query,
        final_search_query,
        paper_text,
    )


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_critic(
    original_query: str,
    final_search_query: str,
    paper_text: str,
):
    return run_critic(
        original_query,
        final_search_query,
        paper_text,
    )


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_gap_analyst(
    original_query: str,
    final_search_query: str,
    paper_text: str,
    researcher_json: str,
    theorist_json: str,
    methodologist_json: str,
    critic_json: str
):
    researcher_output = json.loads(researcher_json) if researcher_json else {}
    theorist_output = json.loads(theorist_json) if theorist_json else {}
    methodologist_output = json.loads(methodologist_json) if methodologist_json else {}
    critic_output = json.loads(critic_json) if critic_json else {}
    return run_gap_analyst(
        original_query,
        final_search_query,
        paper_text,
        researcher_output,
        theorist_output,
        methodologist_output,
        critic_output
    )


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_verifier(
    original_query: str,
    final_search_query: str,
    paper_text: str,
    researcher_json: str,
    theorist_json: str,
    methodologist_json: str,
    critic_json: str,
    gap_json: str
):
    researcher_output = json.loads(researcher_json) if researcher_json else {}
    theorist_output = json.loads(theorist_json) if theorist_json else {}
    methodologist_output = json.loads(methodologist_json) if methodologist_json else {}
    critic_output = json.loads(critic_json) if critic_json else {}
    gap_output = json.loads(gap_json) if gap_json else {}
    return run_verifier(
        original_query,
        final_search_query,
        paper_text,
        researcher_output,
        theorist_output,
        methodologist_output,
        critic_output,
        gap_output
    )


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_editor(
    original_query: str,
    final_search_query: str,
    paper_text: str,
    researcher_json: str,
    theorist_json: str,
    methodologist_json: str,
    critic_json: str,
    gap_json: str,
    verifier_json: str,
    strategy_summary_json: str,
):
    researcher_output = json.loads(researcher_json) if researcher_json else {}
    theorist_output = json.loads(theorist_json) if theorist_json else {}
    methodologist_output = json.loads(methodologist_json) if methodologist_json else {}
    critic_output = json.loads(critic_json) if critic_json else {}
    gap_output = json.loads(gap_json) if gap_json else {}
    verifier_output = json.loads(verifier_json) if verifier_json else {}
    strategy_summary = json.loads(strategy_summary_json) if strategy_summary_json else {}

    return run_editor(
        original_query,
        final_search_query,
        paper_text,
        researcher_output,
        theorist_output,
        methodologist_output,
        critic_output,
        gap_output,
        verifier_output,
        strategy_summary
    )


def build_strategy_summary_for_editor(state: dict) -> dict:
    selected_option = state.get("selected_option", {}) or {}
    settings = state.get("settings", {}) or {}
    diagnostics = state.get("diagnostics", {}) or {}
    planner = state.get("query_planner", {}) or {}
    planner_review = state.get("query_planner_review", {}) or {}
    intent_profile = selected_option.get("intent_profile", {}) if isinstance(selected_option, dict) else {}

    strategy_points = [
        f"Interpretation applied: {selected_option.get('label', 'Direct query mode')}",
        f"Final search query: {state.get('final_search_query', '')}",
        f"Sort mode: {settings.get('sort_mode', 'Balanced')}",
        f"Sources searched: {', '.join(settings.get('source_filters', [])) if settings.get('source_filters') else 'All enabled'}",
        f"Prefer abstracts: {settings.get('prefer_abstracts', True)}",
        f"Strict core papers only: {settings.get('strict_core_only', False)}",
        f"Open access only: {settings.get('open_access_only', False)}",
    ]

    if planner.get("planner_summary"):
        strategy_points.append(f"Planner summary: {planner.get('planner_summary')}")
    if planner.get("search_focus"):
        strategy_points.append(f"Planner search focus: {planner.get('search_focus')}")
    if planner_review.get("review_summary"):
        strategy_points.append(f"Post-retrieval planner review: {planner_review.get('review_summary')}")
    if planner_review.get("retrieval_assessment"):
        strategy_points.append(f"Planner retrieval assessment: {planner_review.get('retrieval_assessment')}")

    year_range = settings.get("year_range")
    if year_range and isinstance(year_range, (list, tuple)) and len(year_range) == 2:
        strategy_points.append(f"Year filter: {year_range[0]}–{year_range[1]}")
    else:
        strategy_points.append("Year filter: Any time")

    include_terms = intent_profile.get("include", []) if isinstance(intent_profile, dict) else []
    exclude_terms = intent_profile.get("exclude", []) if isinstance(intent_profile, dict) else []
    domain_bias = intent_profile.get("domain_bias", "") if isinstance(intent_profile, dict) else ""

    if include_terms:
        strategy_points.append(f"Boosted concepts: {', '.join(include_terms[:6])}")
    if exclude_terms:
        strategy_points.append(f"Downweighted concepts: {', '.join(exclude_terms[:6])}")
    if domain_bias:
        strategy_points.append(f"Domain bias: {domain_bias}")

    if state.get("metrics", {}).get("duplicates_removed", 0) > 0:
        strategy_points.append(f"Final duplicate papers removed: {state.get('metrics', {}).get('duplicates_removed', 0)}")

    return {
        "original_query": state.get("original_query", ""),
        "final_search_query": state.get("final_search_query", ""),
        "applied_interpretation": selected_option.get("label", ""),
        "strategy_points": strategy_points,
        "retrieval_funnel": diagnostics.get("retrieval_funnel", {}),
        "retained_examples": diagnostics.get("retained_examples", []),
        "pushed_down_examples": diagnostics.get("pushed_down_examples", []),
        "selection_logic": diagnostics.get("selection_logic", []),
    }


def create_initial_state(
    original_query: str,
    final_search_query: str,
    selected_option=None,
    paper_count: int = 10,
    sort_mode: str = "Balanced",
    year_range=None,
    prefer_abstracts: bool = True,
    strict_core_only: bool = False,
    open_access_only: bool = False,
    source_filters=None,
):
    selected_option = selected_option or {}
    source_filters = source_filters or []

    return {
        "original_query": original_query,
        "final_search_query": final_search_query,
        "selected_option": selected_option,
        "settings": {
            "paper_count": paper_count,
            "sort_mode": sort_mode,
            "year_range": year_range,
            "prefer_abstracts": prefer_abstracts,
            "strict_core_only": strict_core_only,
            "open_access_only": open_access_only,
            "source_filters": source_filters,
        },
        "query_planner": {},
        "query_planner_review": {},
        "papers": [],
        "diagnostics": {},
        "researcher": {},
        "theorist": {},
        "methodologist": {},
        "critic": {},
        "gap_analyst": {},
        "verifier": {},
        "editor": "",
        "editor_error": "",
        "flags": {
            "planning_done": False,
            "planner_review_done": False,
            "retrieval_done": False,
            "retrieval_refined": False,
            "analysis_bundle_done": False,
            "done": False,
        },
        "tasks": [
            {"type": "query_planner_initial", "reason": "initial planning", "priority": 5}
        ],
        "trace": [],
        "metrics": {
            "step_count": 0,
            "retrieval_rounds": 0,
            "duplicates_removed": 0,
        },
    }


def query_planner_initial_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 8, "Query Planner Agent: planning retrieval and analysis route...")

    result = cached_run_query_planner_initial(
        state["original_query"],
        state["final_search_query"],
        _safe_json_dumps(state.get("selected_option", {}))
    )
    state["query_planner"] = result
    state["flags"]["planning_done"] = True

    add_trace(
        state,
        "QueryPlannerAgent",
        "plan_initial",
        f"query_type={result.get('query_type', '')}, search_focus={result.get('search_focus', '')}",
        progress_callback=progress_callback,
    )
    return state


def query_planner_review_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 84, "Query Planner Agent: reviewing retrieval quality...")

    compact_papers = []
    for p in state.get("papers", [])[:15]:
        compact_papers.append({
            "title": p.get("title", ""),
            "year": p.get("year", ""),
            "source": p.get("source", ""),
            "research_fit_score": p.get("research_fit_score", 0),
            "domain_fit_label": p.get("domain_fit_label", ""),
            "off_target_risk_score": p.get("off_target_risk_score", 0),
            "recommendation_reason": p.get("recommendation_reason", ""),
        })

    result = cached_run_query_planner_review(
        state["original_query"],
        state["final_search_query"],
        _safe_json_dumps(state.get("selected_option", {})),
        _safe_json_dumps(compact_papers),
        _safe_json_dumps(state.get("diagnostics", {})),
        _safe_json_dumps(state.get("query_planner", {})),
    )

    state["query_planner_review"] = result
    state["flags"]["planner_review_done"] = True

    add_trace(
        state,
        "QueryPlannerAgent",
        "plan_review",
        f"retrieval_assessment={result.get('retrieval_assessment', '')}, should_refine={result.get('should_refine', False)}",
        progress_callback=progress_callback,
    )
    return state


def retrieval_agent(state: dict, progress_callback=None, refinement: bool = False) -> dict:
    settings = dict(state.get("settings", {}) or {})
    selected_option = state.get("selected_option", {}) or {}
    intent_profile = selected_option.get("intent_profile", {}) if isinstance(selected_option, dict) else {}
    planner = state.get("query_planner", {}) or {}
    planner_review = state.get("query_planner_review", {}) or {}
    requested_count = int(settings.get("paper_count", 10))

    # 多取一些，给最终强去重留空间
    internal_retrieval_count = requested_count + 8

    if refinement:
        settings["prefer_abstracts"] = planner_review.get(
            "revised_prefer_abstracts",
            settings.get("prefer_abstracts", True)
        )

        if planner_review.get("revised_strict_core_only", False):
            settings["strict_core_only"] = True
        elif planner.get("search_focus") == "narrow_core":
            settings["strict_core_only"] = True

        state["flags"]["retrieval_refined"] = True

    _emit_progress(
        progress_callback,
        16 if not refinement else 52,
        "Retrieval Agent: searching academic sources..." if not refinement else "Retrieval Agent: refining retrieval..."
    )

    result = search_papers_with_diagnostics_live(
        query=state["final_search_query"],
        paper_count=internal_retrieval_count,
        sort_mode=settings.get("sort_mode", "Balanced"),
        year_range=settings.get("year_range"),
        prefer_abstracts=settings.get("prefer_abstracts", True),
        intent_profile=intent_profile,
        original_query=state["original_query"],
        strict_core_only=settings.get("strict_core_only", False),
        open_access_only=settings.get("open_access_only", False),
        source_filters=settings.get("source_filters", []),
        progress_callback=progress_callback,
    )

    raw_papers = result.get("papers", []) or []
    deduped_papers, duplicates_removed = deduplicate_final_papers(raw_papers, requested_count)

    diagnostics = result.get("diagnostics", {}) or {}
    funnel = diagnostics.get("retrieval_funnel", {}) or {}
    funnel["final_count"] = len(deduped_papers)
    diagnostics["retrieval_funnel"] = funnel
    diagnostics["duplicates_removed_in_final_stage"] = duplicates_removed

    state["papers"] = deduped_papers
    state["diagnostics"] = diagnostics
    state["settings"] = settings
    state["flags"]["retrieval_done"] = True
    state["flags"]["planner_review_done"] = False
    state["query_planner_review"] = {}
    state["metrics"]["retrieval_rounds"] += 1
    state["metrics"]["duplicates_removed"] += duplicates_removed

    add_trace(
        state,
        "RetrievalAgent",
        "retrieve_refined" if refinement else "retrieve",
        f"papers={len(deduped_papers)}, duplicates_removed={duplicates_removed}, strict_core_only={settings.get('strict_core_only', False)}",
        progress_callback=progress_callback,
    )

    if refinement:
        clear_downstream_outputs_after_retrieval(state)

    return state


def researcher_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 88, "Researcher Agent: mapping the literature...")
    paper_text = build_paper_text(state.get("papers", []))
    result = cached_run_researcher(
        state["original_query"],
        state["final_search_query"],
        paper_text
    )
    state["researcher"] = result
    add_trace(state, "ResearcherAgent", "analyze", "literature coverage and dominant themes", progress_callback=progress_callback)
    return state


def theorist_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 90, "Theorist Agent: building conceptual framing...")
    paper_text = build_paper_text(state.get("papers", []))
    result = cached_run_theorist(
        state["original_query"],
        state["final_search_query"],
        paper_text,
    )
    state["theorist"] = result
    add_trace(state, "TheoristAgent", "analyze", "conceptual framing and tensions", progress_callback=progress_callback)
    return state


def methodologist_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 92, "Methodologist Agent: reading the evidence profile...")
    paper_text = build_paper_text(state.get("papers", []))
    result = cached_run_methodologist(
        state["original_query"],
        state["final_search_query"],
        paper_text,
    )
    state["methodologist"] = result
    add_trace(state, "MethodologistAgent", "analyze", "study types, evidence profile, method gaps", progress_callback=progress_callback)
    return state


def critic_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 94, "Critic Agent: checking scope and overclaim risks...")
    paper_text = build_paper_text(state.get("papers", []))
    result = cached_run_critic(
        state["original_query"],
        state["final_search_query"],
        paper_text,
    )
    state["critic"] = result
    add_trace(state, "CriticAgent", "analyze", "weak zones, bias, off-target patterns", progress_callback=progress_callback)
    return state


def gap_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 96, "Gap Agent: identifying research gaps...")
    paper_text = build_paper_text(state.get("papers", []))
    result = cached_run_gap_analyst(
        state["original_query"],
        state["final_search_query"],
        paper_text,
        _safe_json_dumps(state.get("researcher", {})),
        _safe_json_dumps(state.get("theorist", {})),
        _safe_json_dumps(state.get("methodologist", {})),
        _safe_json_dumps(state.get("critic", {}))
    )
    state["gap_analyst"] = result
    add_trace(state, "GapAgent", "analyze", "topic, conceptual and methodological gaps", progress_callback=progress_callback)
    return state


def verifier_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 97, "Verifier Agent: checking evidence confidence...")
    paper_text = build_paper_text(state.get("papers", []))
    result = cached_run_verifier(
        state["original_query"],
        state["final_search_query"],
        paper_text,
        _safe_json_dumps(state.get("researcher", {})),
        _safe_json_dumps(state.get("theorist", {})),
        _safe_json_dumps(state.get("methodologist", {})),
        _safe_json_dumps(state.get("critic", {})),
        _safe_json_dumps(state.get("gap_analyst", {}))
    )
    state["verifier"] = result
    add_trace(state, "VerifierAgent", "analyze", f"confidence={result.get('confidence_level', 'Medium')}", progress_callback=progress_callback)
    return state


def _run_parallel_job(job_name: str, fn):
    return fn()


def parallel_analysis_agent(state: dict, progress_callback=None) -> dict:
    papers = state.get("papers", [])
    paper_text = build_paper_text(papers)
    # Always run Theorist if the UI exposes a dedicated Theorist panel.
    # Otherwise users see an empty block when planner heuristics skip it.
    should_use_theorist = True

    _emit_progress(progress_callback, 90, "Parallel analysis wave 1/3: independent Researcher and Methodologist reviews...")

    wave1_jobs = {
        "researcher": lambda: run_researcher(
            state["original_query"],
            state["final_search_query"],
            paper_text,
        ),
        "methodologist": lambda: run_methodologist(
            state["original_query"],
            state["final_search_query"],
            paper_text,
        ),
    }

    wave1_results = {}
    with ThreadPoolExecutor(max_workers=len(wave1_jobs)) as executor:
        future_map = {
            executor.submit(_run_parallel_job, job_name, fn): job_name
            for job_name, fn in wave1_jobs.items()
        }
        for future in as_completed(future_map):
            job_name = future_map[future]
            try:
                wave1_results[job_name] = future.result()
            except Exception as e:
                raise RuntimeError(f"Parallel wave 1 failed in {job_name}: {e}") from e

    state["researcher"] = wave1_results.get("researcher", {})
    state["methodologist"] = wave1_results.get("methodologist", {})
    add_trace(state, "ResearcherAgent", "parallel_complete", "wave1 independent review complete", progress_callback=progress_callback)
    add_trace(state, "MethodologistAgent", "parallel_complete", "wave1 independent review complete", progress_callback=progress_callback)

    if should_use_theorist:
        _emit_progress(progress_callback, 92, "Parallel analysis wave 2/3: independent Theorist and Critic reviews...")

        wave2_jobs = {
            "theorist": lambda: run_theorist(
                state["original_query"],
                state["final_search_query"],
                paper_text,
            ),
            "critic": lambda: run_critic(
                state["original_query"],
                state["final_search_query"],
                paper_text,
            ),
        }
    else:
        _emit_progress(progress_callback, 92, "Parallel analysis wave 2/3: independent Critic review...")
        wave2_jobs = {
            "critic": lambda: run_critic(
                state["original_query"],
                state["final_search_query"],
                paper_text,
            ),
        }

    wave2_results = {}
    with ThreadPoolExecutor(max_workers=len(wave2_jobs)) as executor:
        future_map = {
            executor.submit(_run_parallel_job, job_name, fn): job_name
            for job_name, fn in wave2_jobs.items()
        }
        for future in as_completed(future_map):
            job_name = future_map[future]
            try:
                wave2_results[job_name] = future.result()
            except Exception as e:
                raise RuntimeError(f"Parallel wave 2 failed in {job_name}: {e}") from e

    if should_use_theorist:
        state["theorist"] = wave2_results.get("theorist", {})
        add_trace(state, "TheoristAgent", "parallel_complete", "wave2 independent review complete", progress_callback=progress_callback)
    else:
        state["theorist"] = {}

    state["critic"] = wave2_results.get("critic", {})
    add_trace(state, "CriticAgent", "parallel_complete", "wave2 independent review complete", progress_callback=progress_callback)
    _emit_progress(progress_callback, 95, "Parallel analysis wave 3/3: Gap Analyst and Verifier integration...")

    gap_result = run_gap_analyst(
        state["original_query"],
        state["final_search_query"],
        paper_text,
        state.get("researcher", {}),
        state.get("theorist", {}),
        state.get("methodologist", {}),
        state.get("critic", {}),
    )
    state["gap_analyst"] = gap_result
    add_trace(state, "GapAgent", "parallel_complete", "wave3 gap analysis complete", progress_callback=progress_callback)

    verifier_result = run_verifier(
        state["original_query"],
        state["final_search_query"],
        paper_text,
        state.get("researcher", {}),
        state.get("theorist", {}),
        state.get("methodologist", {}),
        state.get("critic", {}),
        state.get("gap_analyst", {}),
    )
    state["verifier"] = verifier_result
    add_trace(state, "VerifierAgent", "parallel_complete", f"wave3 verification complete, confidence={state['verifier'].get('confidence_level', 'Medium')}", progress_callback=progress_callback)

    state["flags"]["analysis_bundle_done"] = True
    add_trace(state, "ParallelAnalysisAgent", "complete", "post-retrieval independent reviews and integration finished", progress_callback=progress_callback)
    return state


def editor_agent(state: dict, progress_callback=None) -> dict:
    _emit_progress(progress_callback, 98, "Editor Agent: building final Research Brief...")
    paper_text = build_paper_text(state.get("papers", []))
    strategy_summary = build_strategy_summary_for_editor(state)

    result = cached_run_editor(
        state["original_query"],
        state["final_search_query"],
        paper_text,
        _safe_json_dumps(state.get("researcher", {})),
        _safe_json_dumps(state.get("theorist", {})),
        _safe_json_dumps(state.get("methodologist", {})),
        _safe_json_dumps(state.get("critic", {})),
        _safe_json_dumps(state.get("gap_analyst", {})),
        _safe_json_dumps(state.get("verifier", {})),
        _safe_json_dumps(strategy_summary),
    )
    if isinstance(result, dict):
        state["editor"] = str(result.get("brief", "") or "").strip()
        state["editor_error"] = str(result.get("error", "") or "").strip()
    else:
        state["editor"] = str(result or "").strip()
        state["editor_error"] = ""
    add_trace(state, "EditorAgent", "synthesize", "final brief built" if state.get("editor") else "final brief unavailable", progress_callback=progress_callback)
    return state


def should_run_theorist(state: dict) -> bool:
    planner = state.get("query_planner", {}) or {}
    if planner.get("theorist_needed", True):
        return True

    q = (state.get("original_query", "") or "").lower()
    conceptual_terms = [
        "theory", "concept", "framework", "meaning", "narrative",
        "ethics", "interpret", "interpretation", "philosophy",
        "story", "storytelling", "design", "experience"
    ]
    return any(term in q for term in conceptual_terms)


def critic_requests_refinement(state: dict) -> bool:
    if state["flags"].get("retrieval_refined", False):
        return False

    critic = state.get("critic", {}) or {}
    papers = state.get("papers", [])
    if not critic or not papers:
        return False

    off_target = average_off_target_risk(papers)
    dr = direct_ratio(papers)

    off_target_patterns = critic.get("off_target_patterns", []) or []
    weak_zones = critic.get("weak_zones", []) or []
    scope_biases = critic.get("scope_biases", []) or []

    if off_target >= 45 and len(off_target_patterns) >= 1:
        return True
    if dr < 0.6 and len(weak_zones) >= 1:
        return True
    if off_target >= 40 and len(scope_biases) >= 2:
        return True

    return False


def verifier_blocks_editor(state: dict) -> bool:
    verifier = state.get("verifier", {}) or {}
    if not verifier:
        return True

    conf = str(verifier.get("confidence_level", "Medium")).strip().lower()
    if conf == "low":
        return True

    strongly_supported = len(verifier.get("strongly_supported", []) or [])
    weakly_supported = len(verifier.get("weakly_supported", []) or [])
    uncertain = len(verifier.get("uncertain", []) or [])

    if conf == "medium" and (weakly_supported + uncertain) > (strongly_supported + 1):
        return True

    return False


def should_refine_retrieval(state: dict) -> bool:
    if state["flags"].get("retrieval_refined", False):
        return False

    papers = state.get("papers", [])
    if not papers:
        return False

    planner_review = state.get("query_planner_review", {}) or {}

    if planner_review.get("should_refine", False):
        return True

    fit = average_research_fit(papers)
    off_target = average_off_target_risk(papers)
    dr = direct_ratio(papers)

    if fit < 60:
        return True
    if off_target > 50:
        return True
    if dr < 0.5:
        return True
    return False


def router_agent(state: dict) -> dict:
    task = pop_next_task(state)
    if task:
        return task

    papers = state.get("papers", [])

    if not state["flags"].get("planning_done", False):
        return {"type": "query_planner_initial", "reason": "planning not done", "priority": 5}

    if not state["flags"].get("retrieval_done", False):
        return {"type": "retrieve", "reason": "retrieval not done", "priority": 10}

    if not papers:
        return {"type": "finish", "reason": "no papers found", "priority": 999}

    if not state["flags"].get("planner_review_done", False):
        return {"type": "query_planner_review", "reason": "post-retrieval review missing", "priority": 15}

    if should_refine_retrieval(state):
        return {"type": "retrieve_refinement", "reason": "query planner or metrics recommend refinement", "priority": 18}

    if not state["flags"].get("analysis_bundle_done", False):
        return {"type": "analysis_parallel", "reason": "post-retrieval multi-agent analysis not done", "priority": 20}

    if critic_requests_refinement(state):
        return {"type": "retrieve_refinement", "reason": "critic found scope / off-target issues", "priority": 56}

    if verifier_blocks_editor(state):
        if not state["flags"].get("retrieval_refined", False):
            return {"type": "retrieve_refinement", "reason": "verifier blocked editor due to weak confidence", "priority": 75}
        return {"type": "finish", "reason": "verifier blocked editor after refinement; stop without final brief", "priority": 999}

    if not state.get("editor"):
        return {"type": "editor", "reason": "final synthesis missing", "priority": 90}

    return {"type": "finish", "reason": "workflow complete", "priority": 999}


def execute_task(state: dict, task: dict, progress_callback=None) -> dict:
    task_type = task.get("type")

    if task_type == "query_planner_initial":
        return query_planner_initial_agent(state, progress_callback=progress_callback)
    if task_type == "query_planner_review":
        return query_planner_review_agent(state, progress_callback=progress_callback)
    if task_type == "retrieve":
        return retrieval_agent(state, progress_callback=progress_callback, refinement=False)
    if task_type == "retrieve_refinement":
        return retrieval_agent(state, progress_callback=progress_callback, refinement=True)
    if task_type == "analysis_parallel":
        return parallel_analysis_agent(state, progress_callback=progress_callback)
    if task_type == "researcher":
        return researcher_agent(state, progress_callback=progress_callback)
    if task_type == "theorist":
        return theorist_agent(state, progress_callback=progress_callback)
    if task_type == "methodologist":
        return methodologist_agent(state, progress_callback=progress_callback)
    if task_type == "critic":
        return critic_agent(state, progress_callback=progress_callback)
    if task_type == "gap_analyst":
        return gap_agent(state, progress_callback=progress_callback)
    if task_type == "verifier":
        return verifier_agent(state, progress_callback=progress_callback)
    if task_type == "editor":
        return editor_agent(state, progress_callback=progress_callback)
    if task_type == "finish":
        state["flags"]["done"] = True
        add_trace(state, "RouterAgent", "finish", task.get("reason", ""), progress_callback=progress_callback)
        return state

    state["flags"]["done"] = True
    add_trace(state, "RouterAgent", "finish", f"unknown task={task_type}", progress_callback=progress_callback)
    return state


def run_multi_agent_collaboration(
    original_query: str,
    final_search_query: str,
    selected_option=None,
    paper_count: int = 10,
    sort_mode: str = "Balanced",
    year_range=None,
    prefer_abstracts: bool = True,
    strict_core_only: bool = False,
    open_access_only: bool = False,
    source_filters=None,
    progress_callback=None,
    max_steps: int = 18,
):
    state = create_initial_state(
        original_query=original_query,
        final_search_query=final_search_query,
        selected_option=selected_option,
        paper_count=paper_count,
        sort_mode=sort_mode,
        year_range=year_range,
        prefer_abstracts=prefer_abstracts,
        strict_core_only=strict_core_only,
        open_access_only=open_access_only,
        source_filters=source_filters,
    )

    add_trace(state, "RouterAgent", "start", "multi-agent collaboration started", progress_callback=progress_callback)

    while not state["flags"].get("done", False) and state["metrics"]["step_count"] < max_steps:
        state["metrics"]["step_count"] += 1

        task = router_agent(state)
        route_details = f"step={state['metrics']['step_count']}, next={task.get('type')}, reason={task.get('reason', '')}"
        add_trace(
            state,
            "RouterAgent",
            "route",
            route_details,
            progress_callback=progress_callback,
        )
        _emit(
            progress_callback,
            0,
            f"RouterAgent: routing to {task.get('type')}...",
            payload={
                "type": "workflow",
                "agent": "RouterAgent",
                "action": "route_status",
                "details": f"routing to {task.get('type')}",
            }
        )
        state = execute_task(state, task, progress_callback=progress_callback)

    # 只在 verifier 没拦住的情况下才兜底出 editor
    if not state.get("editor") and state.get("papers") and not verifier_blocks_editor(state):
        state = editor_agent(state, progress_callback=progress_callback)

    state["flags"]["done"] = True
    _emit_progress(progress_callback, 100, "Multi-agent collaboration complete.")
    return state