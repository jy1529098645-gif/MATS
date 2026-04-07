import json
import streamlit as st

from multi_agent_system import run_multi_agent_collaboration


def build_strategy_summary(
    original_query: str,
    final_search_query: str,
    selected_option: dict,
    settings: dict,
    diagnostics: dict,
    query_planner: dict = None,
    query_planner_review: dict = None,
    collaboration_metrics: dict = None,
):
    selected_option = selected_option or {}
    query_planner = query_planner or {}
    query_planner_review = query_planner_review or {}
    collaboration_metrics = collaboration_metrics or {}
    intent_profile = selected_option.get("intent_profile", {}) if isinstance(selected_option, dict) else {}

    strategy_points = [
        f"Interpretation applied: {selected_option.get('label', 'Direct query mode')}",
        f"Final search query: {final_search_query}",
        f"Sort mode: {settings.get('sort_mode', 'Balanced')}",
        f"Sources searched: {', '.join(settings.get('source_filters', [])) if settings.get('source_filters') else 'All enabled'}",
        f"Prefer abstracts: {settings.get('prefer_abstracts', True)}",
        f"Strict core papers only: {settings.get('strict_core_only', False)}",
        f"Open access only: {settings.get('open_access_only', False)}",
    ]

    if query_planner.get("planner_summary"):
        strategy_points.append(f"Planner summary: {query_planner.get('planner_summary')}")
    if query_planner.get("search_focus"):
        strategy_points.append(f"Planner search focus: {query_planner.get('search_focus')}")

    if query_planner_review.get("review_summary"):
        strategy_points.append(f"Post-retrieval planner review: {query_planner_review.get('review_summary')}")
    if query_planner_review.get("retrieval_assessment"):
        strategy_points.append(f"Planner retrieval assessment: {query_planner_review.get('retrieval_assessment')}")
    if query_planner_review.get("refinement_reason"):
        strategy_points.append(f"Planner refinement reason: {query_planner_review.get('refinement_reason')}")

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

    if collaboration_metrics.get("duplicates_removed", 0) > 0:
        strategy_points.append(f"Final duplicate papers removed: {collaboration_metrics.get('duplicates_removed', 0)}")

    return {
        "original_query": original_query,
        "final_search_query": final_search_query,
        "applied_interpretation": selected_option.get("label", ""),
        "strategy_points": strategy_points,
        "retrieval_funnel": diagnostics.get("retrieval_funnel", {}),
        "retained_examples": diagnostics.get("retained_examples", []),
        "pushed_down_examples": diagnostics.get("pushed_down_examples", []),
        "selection_logic": diagnostics.get("selection_logic", []),
    }


def _emit(progress_callback, value, message, payload=None):
    if progress_callback:
        try:
            progress_callback(value, message, payload)
        except TypeError:
            progress_callback(value, message)


@st.cache_data(ttl=60 * 20, show_spinner=False)
def cached_run_multi_agent(
    original_query: str,
    final_search_query: str,
    selected_option_json: str,
    paper_count: int,
    sort_mode: str,
    year_range_json: str,
    prefer_abstracts: bool,
    strict_core_only: bool,
    open_access_only: bool,
    source_filters_json: str,
):
    selected_option = json.loads(selected_option_json) if selected_option_json else {}
    year_range = json.loads(year_range_json) if year_range_json else None
    source_filters = json.loads(source_filters_json) if source_filters_json else []

    return run_multi_agent_collaboration(
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
        progress_callback=None,
    )


def run_ats(
    original_query: str,
    final_search_query: str,
    selected_option=None,
    paper_count: int = 5,
    sort_mode: str = "Balanced",
    year_range=None,
    prefer_abstracts: bool = True,
    strict_core_only: bool = False,
    open_access_only: bool = False,
    source_filters=None,
    progress_callback=None,
):
    selected_option = selected_option or {}
    source_filters = source_filters or []

    settings = {
        "paper_count": paper_count,
        "sort_mode": sort_mode,
        "year_range": year_range,
        "prefer_abstracts": prefer_abstracts,
        "strict_core_only": strict_core_only,
        "open_access_only": open_access_only,
        "source_filters": source_filters,
    }

    if progress_callback:
        _emit(progress_callback, 4, "Initializing multi-agent collaboration...")
        state = run_multi_agent_collaboration(
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
            progress_callback=progress_callback,
        )
    else:
        state = cached_run_multi_agent(
            original_query=original_query,
            final_search_query=final_search_query,
            selected_option_json=json.dumps(selected_option, sort_keys=True, ensure_ascii=False),
            paper_count=paper_count,
            sort_mode=sort_mode,
            year_range_json=json.dumps(year_range, ensure_ascii=False),
            prefer_abstracts=prefer_abstracts,
            strict_core_only=strict_core_only,
            open_access_only=open_access_only,
            source_filters_json=json.dumps(source_filters, ensure_ascii=False),
        )

    papers = state.get("papers", [])
    diagnostics = state.get("diagnostics", {})
    query_planner = state.get("query_planner", {}) or {}
    query_planner_review = state.get("query_planner_review", {}) or {}
    collaboration_metrics = state.get("metrics", {}) or {}

    strategy_summary = build_strategy_summary(
        original_query=original_query,
        final_search_query=final_search_query,
        selected_option=selected_option,
        settings=settings,
        diagnostics=diagnostics,
        query_planner=query_planner,
        query_planner_review=query_planner_review,
        collaboration_metrics=collaboration_metrics,
    )

    if not papers:
        _emit(progress_callback, 100, "No papers found.")
        return {
            "original_query": original_query,
            "final_search_query": final_search_query,
            "papers": [],
            "query_planner": query_planner,
            "query_planner_review": query_planner_review,
            "researcher": {},
            "theorist": {},
            "methodologist": {},
            "critic": {},
            "gap_analyst": {},
            "verifier": {},
            "editor": "",
            "intent_applied": selected_option.get("label", ""),
            "settings": settings,
            "strategy_summary": strategy_summary,
            "diagnostics": diagnostics,
            "cache_hit_hint": "mixed-cache",
            "collaboration_trace": state.get("trace", []),
            "collaboration_metrics": collaboration_metrics,
        }

    _emit(progress_callback, 100, "ATS pipeline complete.")

    return {
        "original_query": original_query,
        "final_search_query": final_search_query,
        "papers": papers,
        "query_planner": query_planner,
        "query_planner_review": query_planner_review,
        "researcher": state.get("researcher", {}),
        "theorist": state.get("theorist", {}),
        "methodologist": state.get("methodologist", {}),
        "critic": state.get("critic", {}),
        "gap_analyst": state.get("gap_analyst", {}),
        "verifier": state.get("verifier", {}),
        "editor": state.get("editor", ""),
        "intent_applied": selected_option.get("label", ""),
        "settings": settings,
        "strategy_summary": strategy_summary,
        "diagnostics": diagnostics,
        "cache_hit_hint": "mixed-cache",
        "collaboration_trace": state.get("trace", []),
        "collaboration_metrics": collaboration_metrics,
    }