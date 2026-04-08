import datetime
import copy
from io import BytesIO

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from search_service import generate_query_options, sort_existing_papers_for_display
from ats_pipeline import run_ats


st.set_page_config(
    page_title="Academic ATS 1.0",
    page_icon="📚",
    layout="wide"
)

st.markdown(
    """
    <style>
        .main .block-container {
            max-width: 100%;
            padding-top: 1.2rem;
            padding-left: 1.2rem;
            padding-right: 1.2rem;
            padding-bottom: 1.5rem;
        }

        .recommended-tiers {
            margin-top: -0.4rem;
            margin-bottom: 0.8rem;
            font-size: 0.92rem;
            color: #666;
        }

        .recommended-tiers span {
            display: inline-block;
            margin-right: 0.45rem;
            margin-bottom: 0.35rem;
            padding: 0.18rem 0.55rem;
            border-radius: 999px;
            background: rgba(100, 100, 100, 0.10);
            border: 1px solid rgba(100, 100, 100, 0.18);
        }

        .panel-box {
            border: 1px solid rgba(120,120,120,0.18);
            border-radius: 14px;
            padding: 1rem 1rem 0.7rem 1rem;
            background: rgba(255,255,255,0.02);
            margin-bottom: 1rem;
            height: fit-content;
        }

        .panel-title {
            font-size: 1.08rem;
            font-weight: 700;
            margin-bottom: 0.7rem;
        }

        .panel-subtitle {
            font-size: 0.92rem;
            color: #666;
            margin-top: -0.15rem;
            margin-bottom: 0.8rem;
        }

        .paper-meta {
            font-size: 0.95rem;
            color: #666;
            margin-bottom: 0.35rem;
        }

        .why-recommended {
            border-left: 4px solid rgba(59,130,246,0.8);
            padding: 0.65rem 0.85rem;
            margin: 0.6rem 0 0.8rem 0;
            background: rgba(59,130,246,0.08);
            border-radius: 0.45rem;
        }

        .evidence-chip {
            display: inline-block;
            padding: 0.16rem 0.55rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
            margin-right: 0.4rem;
            margin-bottom: 0.35rem;
        }

        .chip-strong {
            background: rgba(34,197,94,0.14);
            color: rgb(21,128,61);
            border: 1px solid rgba(34,197,94,0.25);
        }

        .chip-moderate {
            background: rgba(245,158,11,0.14);
            color: rgb(180,83,9);
            border: 1px solid rgba(245,158,11,0.25);
        }

        .chip-limited {
            background: rgba(239,68,68,0.12);
            color: rgb(185,28,28);
            border: 1px solid rgba(239,68,68,0.22);
        }

        .compact-abstract {
            color: #444;
            line-height: 1.55;
            margin-top: 0.35rem;
        }

        .left-sticky-note {
            font-size: 0.92rem;
            color: #666;
            margin-bottom: 0.8rem;
        }

        .split-helper {
            font-size: 0.9rem;
            color: #666;
            margin-top: -0.2rem;
            margin-bottom: 0.8rem;
        }

        .cache-note {
            font-size: 0.9rem;
            color: #666;
            margin-top: -0.25rem;
            margin-bottom: 0.65rem;
        }

        .sort-note {
            font-size: 0.9rem;
            color: #666;
            margin-top: -0.25rem;
            margin-bottom: 0.65rem;
        }

        .brief-box {
            border: 1px solid rgba(59,130,246,0.18);
            border-radius: 14px;
            padding: 1rem 1rem 0.9rem 1rem;
            background: rgba(59,130,246,0.04);
            margin-bottom: 1rem;
        }

        .brief-title {
            font-size: 1.08rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }

        .strategy-box {
            border: 1px solid rgba(16,185,129,0.18);
            border-radius: 14px;
            padding: 1rem 1rem 0.9rem 1rem;
            background: rgba(16,185,129,0.04);
            margin-bottom: 1rem;
        }

        .strategy-title {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }

        .trace-row {
            border-left: 3px solid rgba(99,102,241,0.45);
            padding: 0.55rem 0.75rem;
            margin-bottom: 0.55rem;
            background: rgba(99,102,241,0.05);
            border-radius: 0.45rem;
        }

        .trace-agent {
            font-weight: 700;
            font-size: 0.95rem;
            margin-bottom: 0.15rem;
        }

        .trace-action {
            color: #444;
            font-size: 0.92rem;
        }

        .planner-box {
            border-left: 4px solid rgba(168,85,247,0.75);
            padding: 0.7rem 0.85rem;
            margin: 0.25rem 0 0.8rem 0;
            background: rgba(168,85,247,0.06);
            border-radius: 0.45rem;
        }

        .review-box {
            border-left: 4px solid rgba(14,165,233,0.75);
            padding: 0.7rem 0.85rem;
            margin: 0.25rem 0 0.8rem 0;
            background: rgba(14,165,233,0.06);
            border-radius: 0.45rem;
        }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    '<h1 style="font-size: 3rem; font-weight: 800; margin-top: 0; margin-bottom: 0.2rem; line-height: 1.1;"><span style="color: #1F2937;">Academic </span><span style="color: #2563EB;">ATS</span></h1>',
    unsafe_allow_html=True
)
st.write("AI-powered academic research assistant")

DEFAULT_MIN_YEAR = 1990
DEFAULT_MAX_YEAR = datetime.datetime.now().year
DEFAULT_SOURCES = ["Semantic Scholar", "OpenAlex", "Crossref", "Google Scholar"]
SORT_MODES = [
    "Balanced",
    "Newest first",
    "Research fit",
    "Relevance score",
    "Evidence strength",
    "Open access first",
]



def _split_brief_into_sections(brief_text: str):
    lines = [line.strip() for line in (brief_text or "").splitlines()]
    sections = []
    current_title = None
    current_body = []

    known_headings = {
        "Research Brief",
        "# Research Brief",
        "## Bottom Line",
        "## What This Literature Actually Covers",
        "## Strongest Signals",
        "## Conceptual Framing",
        "## Methodological Reading",
        "## Where the Evidence Is Thin",
        "## Research Gaps",
        "## What This Means for Your Query",
        "## Best Next Directions",
        "## Confidence & Scope Note",
        "Bottom Line",
        "What This Literature Actually Covers",
        "Strongest Signals",
        "Conceptual Framing",
        "Methodological Reading",
        "Where the Evidence Is Thin",
        "Research Gaps",
        "What This Means for Your Query",
        "Best Next Directions",
        "Confidence & Scope Note",
    }

    def normalize_heading(line: str):
        return line.lstrip("#").strip()

    for line in lines:
        if not line:
            if current_body and current_body[-1] != "":
                current_body.append("")
            continue

        if line in known_headings:
            normalized = normalize_heading(line)
            if current_title is not None or current_body:
                sections.append((current_title, "\n".join(current_body).strip()))
            current_title = normalized
            current_body = []
        else:
            current_body.append(line)

    if current_title is not None or current_body:
        sections.append((current_title, "\n".join(current_body).strip()))

    # 去掉完全重复的 section
    deduped = []
    seen = set()
    for title, body in sections:
        key = (title or "", body or "")
        if key not in seen:
            seen.add(key)
            deduped.append((title, body))

    return deduped


def build_research_brief_pdf_bytes(brief_text: str, original_query: str = "", final_search_query: str = "") -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Research Brief",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BriefTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        spaceAfter=10,
        textColor="#1F2937",
    )
    meta_style = ParagraphStyle(
        "BriefMeta",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        spaceAfter=6,
        textColor="#4B5563",
    )
    heading_style = ParagraphStyle(
        "BriefHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=15,
        spaceBefore=8,
        spaceAfter=5,
        textColor="#2563EB",
    )
    body_style = ParagraphStyle(
        "BriefBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        spaceAfter=7,
        textColor="#111827",
    )

    # 清理重复标题，避免 PDF 中重复出现两份 Research Brief
    clean_text = (brief_text or "").strip()

    while "# Research Brief" in clean_text:
        clean_text = clean_text.replace("# Research Brief", "Research Brief")

    # 如果正文里重复出现多个 Research Brief，只保留第一份
    marker = "Research Brief"
    first_idx = clean_text.find(marker)
    if first_idx != -1:
        second_idx = clean_text.find(marker, first_idx + len(marker))
        if second_idx != -1:
            clean_text = clean_text[:second_idx].strip()

    sections = _split_brief_into_sections(clean_text)

    story = []
    story.append(Paragraph("Research Brief", title_style))

    if original_query:
        story.append(Paragraph(f"<b>Original query:</b> {original_query}", meta_style))
    if final_search_query:
        story.append(Paragraph(f"<b>Final search query:</b> {final_search_query}", meta_style))
    story.append(Spacer(1, 6))

    for idx, (section_title, section_body) in enumerate(sections):
        if section_title == "Research Brief":
            continue

        if section_title:
            story.append(Paragraph(section_title, heading_style))

        if section_body:
            paragraphs = [p.strip() for p in section_body.split("\n\n") if p.strip()]
            for para in paragraphs:
                para = para.replace("\n", "<br/>")
                story.append(Paragraph(para, body_style))

        if idx < len(sections) - 1:
            story.append(Spacer(1, 3))

    doc.build(story)
    return buffer.getvalue()

if "query_options_data" not in st.session_state:
    st.session_state.query_options_data = None
if "selected_search_query" not in st.session_state:
    st.session_state.selected_search_query = None
if "selected_option_index" not in st.session_state:
    st.session_state.selected_option_index = None
if "selected_option_payload" not in st.session_state:
    st.session_state.selected_option_payload = None
if "custom_query_value" not in st.session_state:
    st.session_state.custom_query_value = ""
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "last_run_settings" not in st.session_state:
    st.session_state.last_run_settings = None
if "panel_split_ratio" not in st.session_state:
    st.session_state.panel_split_ratio = 34
if "last_cache_clear_time" not in st.session_state:
    st.session_state.last_cache_clear_time = None
if "display_view_mode" not in st.session_state:
    st.session_state.display_view_mode = "Compact"


def clamp_progress(value):
    try:
        v = float(value)
    except Exception:
        v = 0.0
    if 0 <= v <= 1:
        v = v * 100
    return max(0, min(100, int(round(v))))


def update_progress(progress_bar, status_box, value, text):
    value = clamp_progress(value)
    progress_bar.progress(value)
    status_box.info(f"⏳ {text}")


def truncate_text(text: str, limit: int = 220) -> str:
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."

def make_safe_pdf_filename(original_query: str) -> str:
    query = (original_query or "research_brief").strip().lower()

    # 把空格变成下划线
    query = query.replace(" ", "_")

    # 去掉不适合做文件名的字符
    query = "".join(ch for ch in query if ch.isalnum() or ch in ["_", "-"])

    # 避免文件名太长
    query = query[:50].strip("_")

    if not query:
        query = "research_brief"

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"research_brief_{query}_{today}.pdf"


def render_evidence_chip(strength: str, score: int):
    strength = (strength or "Moderate").lower()

    if strength == "strong":
        cls = "chip-strong"
        label = "Strong evidence"
    elif strength == "limited":
        cls = "chip-limited"
        label = "Limited evidence"
    else:
        cls = "chip-moderate"
        label = "Moderate evidence"

    st.markdown(
        f"""
        <span class="evidence-chip {cls}">{label}</span>
        <span class="paper-meta">score: {score}/100</span>
        """,
        unsafe_allow_html=True
    )


def get_sort_note(sort_mode: str) -> str:
    notes = {
        "Balanced": "综合考虑研究匹配度、最终分数、年份和开放获取情况。",
        "Newest first": "优先显示最新发表的论文，再参考研究匹配度和综合分数。",
        "Research fit": "优先显示最贴合当前研究问题的论文。",
        "Relevance score": "按系统综合相关性分数排序。",
        "Evidence strength": "优先显示证据更强、支持性更高的论文。",
        "Open access first": "优先显示可直接获取的开放获取论文，再考虑质量。",
    }
    return notes.get(sort_mode, "")


def render_score_breakdown(paper: dict):
    breakdown = paper.get("evidence_breakdown", {}) or {}
    if not breakdown:
        st.caption("No score breakdown available.")
        return

    friendly_labels = {
        "query_match": "Query match",
        "abstract_support": "Abstract support",
        "recency": "Recency",
        "domain_fit": "Domain fit",
        "open_access": "Open access",
        "off_target_risk": "Off-target risk",
    }

    for key in ["query_match", "abstract_support", "recency", "domain_fit", "open_access"]:
        if key in breakdown:
            value = int(breakdown.get(key, 0))
            st.write(f"**{friendly_labels.get(key, key)}:** {value}/100")
            st.progress(value)

    if "off_target_risk" in breakdown:
        risk = int(breakdown.get("off_target_risk", 0))
        st.write(f"**Off-target risk:** {risk}/100")
        st.progress(risk)


def render_strategy_summary(result: dict):
    st.markdown("<div class='strategy-box'>", unsafe_allow_html=True)
    st.markdown("<div class='strategy-title'>🧭 Retrieval Strategy Summary</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='panel-subtitle'>说明这次是怎么搜的、怎么筛的、为什么一些论文被保留，而另一些被压下去。</div>",
        unsafe_allow_html=True
    )

    if not result:
        st.info("Run Search 后，这里会显示本次检索策略摘要。")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    strategy = result.get("strategy_summary", {}) or {}
    diagnostics = result.get("diagnostics", {}) or {}
    funnel = strategy.get("retrieval_funnel", {}) or diagnostics.get("retrieval_funnel", {})

    points = strategy.get("strategy_points", [])
    if points:
        for item in points:
            st.write(f"- {item}")

    if funnel:
        st.markdown("**Retrieval funnel**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Candidates", funnel.get("retrieved_total", 0))
        c2.metric("After filters", funnel.get("after_filters", 0))
        c3.metric("Stage-2 pool", funnel.get("stage2_pool", 0))
        c4.metric("Final kept", funnel.get("final_count", 0))

    selection_logic = strategy.get("selection_logic", [])
    if selection_logic:
        with st.expander("Why these papers were prioritized", expanded=False):
            for item in selection_logic:
                st.write(f"- {item}")

    retained_examples = strategy.get("retained_examples", [])
    if retained_examples:
        with st.expander("Why some papers were kept", expanded=False):
            for item in retained_examples:
                st.write(f"**{item.get('title', 'Untitled')}**")
                st.write(item.get("reason", ""))
                st.divider()

    pushed_down_examples = strategy.get("pushed_down_examples", [])
    if pushed_down_examples:
        with st.expander("Why some papers were pushed down", expanded=False):
            for item in pushed_down_examples:
                st.write(f"**{item.get('title', 'Untitled')}**")
                st.write(item.get("reason", ""))
                st.divider()

    st.markdown("</div>", unsafe_allow_html=True)


def render_papers_content(result_like: dict, view_mode: str, display_sort_mode: str):
    papers = result_like.get("papers", [])
    if not papers:
        st.warning("No papers found.")
        return

    st.subheader("📚 Retrieved Papers")

    if result_like.get("final_search_query"):
        st.write(f"**Final Search Query:** {result_like.get('final_search_query', '')}")

    settings = result_like.get("settings", {})
    if settings:
        year_range = settings.get("year_range")
        year_text = (
            f"{year_range[0]}–{year_range[1]}"
            if isinstance(year_range, (list, tuple)) and len(year_range) == 2
            else "Any time"
        )

        sources_text = ", ".join(settings.get("source_filters", [])) if settings.get("source_filters") else "All enabled"
        st.caption(
            f"Run settings: initial_rank={settings.get('sort_mode', 'N/A')} | "
            f"current_view_sort={display_sort_mode} | "
            f"year={year_text} | "
            f"paper_count={settings.get('paper_count', 'N/A')} | "
            f"prefer_abstracts={settings.get('prefer_abstracts', 'N/A')} | "
            f"strict_core_only={settings.get('strict_core_only', False)} | "
            f"open_access_only={settings.get('open_access_only', False)} | "
            f"sources={sources_text} | "
            f"view={view_mode}"
        )

    st.markdown(
        f"<div class='sort-note'>当前排序说明：{get_sort_note(display_sort_mode)}</div>",
        unsafe_allow_html=True
    )

    if result_like.get("intent_applied"):
        st.caption(f"Intent applied: {result_like.get('intent_applied')}")

    for i, p in enumerate(papers, start=1):
        title = p.get("title", "No title")
        authors = p.get("authors", "Unknown authors")
        year = p.get("year", "Unknown year")
        source = p.get("source", "Unknown source")
        url = p.get("url", "")
        summary = p.get("summary", "No abstract available.")
        ranking_reason = p.get("ranking_reason", "")
        evidence_strength = p.get("evidence_strength", "Moderate")
        evidence_score = p.get("evidence_score", 50)
        recommendation_reason = p.get("recommendation_reason", ranking_reason)
        is_oa = p.get("is_oa", False)

        st.write(f"**{i}. {title}**")
        st.markdown(
            f"<div class='paper-meta'><b>Authors:</b> {authors} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Year:</b> {year} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Source:</b> {source} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Open access:</b> {is_oa}</div>",
            unsafe_allow_html=True
        )

        render_evidence_chip(evidence_strength, evidence_score)

        if recommendation_reason:
            st.markdown(
                f"""
                <div class="why-recommended">
                    <b>Why recommended:</b> {recommendation_reason}
                </div>
                """,
                unsafe_allow_html=True
            )

        if url:
            st.write(f"[Open paper page]({url})")

        with st.expander("Why this score?", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Final score", p.get("relevance_score", 0))
            c2.metric("Research fit", p.get("research_fit_score", 0))
            c3.metric("Off-target risk", p.get("off_target_risk_score", 0))
            render_score_breakdown(p)
            if p.get("ranking_reason"):
                st.caption(p.get("ranking_reason"))

        if view_mode == "Compact":
            st.markdown(
                f"<div class='compact-abstract'>{truncate_text(summary, 220)}</div>",
                unsafe_allow_html=True
            )
        else:
            if "relevance_score" in p:
                st.write(f"**Relevance Score:** {p['relevance_score']}")
            if "research_fit_score" in p:
                st.write(f"**Research fit score:** {p['research_fit_score']}")
            if "domain_fit_label" in p:
                st.write(f"**Domain fit:** {p['domain_fit_label']}")
            if "paper_type_label" in p:
                st.write(f"**Paper type:** {p['paper_type_label']}")
            st.write(summary)

        st.divider()


def render_final_brief(result: dict):
    st.markdown("<div class='brief-box'>", unsafe_allow_html=True)
    st.markdown("<div class='brief-title'>📄 Research Brief</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='panel-subtitle'>默认优先展示最终成品结论；更深层的多 agent 分析轨迹与检索策略说明可在下方继续查看。</div>",
        unsafe_allow_html=True
    )

    if not result:
        st.info("Run Search 后，这里会显示最终的 Research Brief。")
    else:
        if result.get("editor"):
            brief_text = result.get("editor", "")
            st.write(brief_text)

            try:
                pdf_bytes = build_research_brief_pdf_bytes(
                    brief_text=brief_text,
                    original_query=result.get("original_query", ""),
                    final_search_query=result.get("final_search_query", ""),
                )

                pdf_filename = make_safe_pdf_filename(
                    result.get("original_query", "")
                )

                st.download_button(
                    label="Download Research Brief as PDF",
                    data=pdf_bytes,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    use_container_width=False,
                    key="download_research_brief_pdf",
                )
            except Exception as e:
                st.caption(f"PDF export unavailable: {str(e)}")
        else:
            verifier = result.get("verifier", {}) or {}
            if verifier:
                st.warning("Editor was blocked because the verifier judged the current evidence too weak after refinement.")
                if verifier.get("confidence_reason"):
                    st.write(verifier.get("confidence_reason"))
            else:
                st.info("No final brief available.")

    st.markdown("</div>", unsafe_allow_html=True)

def render_structured_agent(name: str, payload: dict):
    st.write(f"**{name} summary**")
    narrative = payload.get("narrative", "")
    if narrative:
        st.write(narrative)

    keys_to_hide = {"narrative"}
    for key, value in payload.items():
        if key in keys_to_hide:
            continue
        if isinstance(value, list) and value:
            st.write(f"**{key.replace('_', ' ').title()}**")
            for item in value:
                st.write(f"- {item}")
        elif isinstance(value, str) and value.strip():
            st.write(f"**{key.replace('_', ' ').title()}**")
            st.write(value)


def render_analysis_trace(result: dict):
    st.markdown("<div class='panel-box'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-title'>🧠 Analytical Trace</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='left-sticky-note'>多 agent 的结构化分析轨迹默认折叠，只有需要查看推理分轨时才展开。</div>",
        unsafe_allow_html=True
    )

    if not result:
        st.info("Run Search 后，这里会显示多 agent 分析轨迹。")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    planner = result.get("query_planner", {}) or {}
    planner_review = result.get("query_planner_review", {}) or {}

    if planner:
        with st.expander("Query Planner — Initial", expanded=False):
            if planner.get("planner_summary"):
                st.markdown(
                    f"<div class='planner-box'><b>Planner summary:</b> {planner.get('planner_summary')}</div>",
                    unsafe_allow_html=True
                )
            c1, c2, c3 = st.columns(3)
            c1.metric("Query type", planner.get("query_type", ""))
            c2.metric("Search focus", planner.get("search_focus", ""))
            c3.metric("Verifier needed", str(planner.get("verifier_needed", True)))

            if planner.get("priority_questions"):
                st.write("**Priority questions**")
                for item in planner.get("priority_questions", []):
                    st.write(f"- {item}")

            if planner.get("risk_flags"):
                st.write("**Risk flags**")
                for item in planner.get("risk_flags", []):
                    st.write(f"- {item}")

            if planner.get("refinement_if_weak_results"):
                st.write("**Refinement plan if weak results**")
                st.write(planner.get("refinement_if_weak_results"))

    if planner_review:
        with st.expander("Query Planner — Post-Retrieval Review", expanded=False):
            if planner_review.get("review_summary"):
                st.markdown(
                    f"<div class='review-box'><b>Review summary:</b> {planner_review.get('review_summary')}</div>",
                    unsafe_allow_html=True
                )
            c1, c2, c3 = st.columns(3)
            c1.metric("Assessment", planner_review.get("retrieval_assessment", ""))
            c2.metric("Should refine", str(planner_review.get("should_refine", False)))
            c3.metric("Revised focus", planner_review.get("revised_search_focus", ""))

            if planner_review.get("priority_issues"):
                st.write("**Priority issues**")
                for item in planner_review.get("priority_issues", []):
                    st.write(f"- {item}")

            if planner_review.get("notes_for_router"):
                st.write("**Notes for router**")
                for item in planner_review.get("notes_for_router", []):
                    st.write(f"- {item}")

            if planner_review.get("refinement_reason"):
                st.write("**Refinement reason**")
                st.write(planner_review.get("refinement_reason"))

    with st.expander("Researcher", expanded=False):
        render_structured_agent("Researcher", result.get("researcher", {}) or {})

    with st.expander("Theorist", expanded=False):
        render_structured_agent("Theorist", result.get("theorist", {}) or {})

    with st.expander("Methodologist", expanded=False):
        render_structured_agent("Methodologist", result.get("methodologist", {}) or {})

    with st.expander("Critic", expanded=False):
        render_structured_agent("Critic", result.get("critic", {}) or {})

    with st.expander("Research Gap Analyst", expanded=False):
        render_structured_agent("Research Gap Analyst", result.get("gap_analyst", {}) or {})

    with st.expander("Verifier", expanded=False):
        render_structured_agent("Verifier", result.get("verifier", {}) or {})

    st.markdown("</div>", unsafe_allow_html=True)


def render_collaboration_trace(result: dict):
    st.markdown("<div class='panel-box'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-title'>🤝 Collaboration Trace</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='left-sticky-note'>多 agent 的协作轨迹默认折叠，只有需要查看 Router 决策和 refinement 过程时才展开。</div>",
        unsafe_allow_html=True
    )

    if not result:
        st.info("Run Search 后，这里会显示 collaboration trace。")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    metrics = result.get("collaboration_metrics", {}) or {}
    trace = result.get("collaboration_trace", []) or []

    c1, c2, c3 = st.columns(3)
    c1.metric("Workflow steps", metrics.get("step_count", 0))
    c2.metric("Retrieval rounds", metrics.get("retrieval_rounds", 0))
    c3.metric("Duplicates removed", metrics.get("duplicates_removed", 0))

    with st.expander("Collaboration Trace", expanded=False):
        if not trace:
            st.caption("No collaboration trace available.")
        else:
            for idx, item in enumerate(trace, start=1):
                agent = item.get("agent", "Agent")
                action = item.get("action", "action")
                details = item.get("details", "")

                st.markdown(
                    f"""
                    <div class="trace-row">
                        <div class="trace-agent">{idx}. {agent}</div>
                        <div class="trace-action"><b>{action}</b>{' — ' + details if details else ''}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    st.markdown("</div>", unsafe_allow_html=True)


def render_left_workspace(result: dict):
    render_final_brief(result)
    render_collaboration_trace(result)
    render_analysis_trace(result)
    render_strategy_summary(result)


def smart_progress_callback(progress_bar, status_box):
    def _callback(*args):
        progress = 0
        stage = "Running..."

        if len(args) >= 2:
            arg1, arg2 = args[0], args[1]
            if isinstance(arg1, str) and not isinstance(arg2, str):
                stage = arg1
                progress = arg2
            elif isinstance(arg2, str) and not isinstance(arg1, str):
                progress = arg1
                stage = arg2
            else:
                progress = arg1
                stage = str(arg2)

        update_progress(progress_bar, status_box, progress, stage)

    return _callback


def ensure_query_options(raw_query: str):
    if not raw_query.strip():
        return None

    if st.session_state.query_options_data and (
        st.session_state.query_options_data.get("original_query", "").strip() == raw_query.strip()
    ):
        return st.session_state.query_options_data

    data = generate_query_options(raw_query)
    st.session_state.query_options_data = data
    st.session_state.selected_search_query = None
    st.session_state.selected_option_index = None
    st.session_state.selected_option_payload = None
    st.session_state.custom_query_value = ""
    return data


def get_effective_query_selection(raw_query: str):
    data = ensure_query_options(raw_query)
    if not data:
        return None, None, None

    options = data.get("options", [])
    recommended_index = data.get("recommended_index", 0)

    if st.session_state.selected_search_query:
        return (
            st.session_state.selected_search_query,
            st.session_state.selected_option_payload,
            data
        )

    if options:
        if not isinstance(recommended_index, int) or recommended_index < 0 or recommended_index >= len(options):
            recommended_index = 0

        opt = options[recommended_index]
        st.session_state.selected_option_index = recommended_index
        st.session_state.selected_search_query = opt.get("search_query", raw_query.strip())
        st.session_state.selected_option_payload = opt
        return st.session_state.selected_search_query, opt, data

    fallback_payload = {
        "label": raw_query.strip(),
        "search_query": raw_query.strip(),
        "reason": "Fallback direct search.",
        "confidence": 0.5,
        "intent_profile": {}
    }
    st.session_state.selected_search_query = raw_query.strip()
    st.session_state.selected_option_payload = fallback_payload
    return raw_query.strip(), fallback_payload, data


def clear_all_caches():
    st.cache_data.clear()
    st.session_state.query_options_data = None
    st.session_state.selected_search_query = None
    st.session_state.selected_option_index = None
    st.session_state.selected_option_payload = None
    st.session_state.custom_query_value = ""
    st.session_state.analysis_result = None
    st.session_state.last_run_settings = None
    st.session_state.last_cache_clear_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


top_action_col1, top_action_col2 = st.columns([1, 5])

with top_action_col1:
    if st.button("Clear Cache"):
        clear_all_caches()
        st.success("Cache cleared.")
        st.rerun()

with top_action_col2:
    if st.session_state.last_cache_clear_time:
        st.markdown(
            f"<div class='cache-note'>Last cache clear: {st.session_state.last_cache_clear_time}</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            "<div class='cache-note'>Cache enabled for preview search, query understanding, retrieval, and ATS analysis.</div>",
            unsafe_allow_html=True
        )

split_ratio = st.slider(
    "Panel width",
    min_value=20,
    max_value=60,
    value=st.session_state.panel_split_ratio,
    step=1,
    help="调整左侧分析区和右侧结果区的宽度比例。"
)
st.session_state.panel_split_ratio = split_ratio
st.markdown(
    f"<div class='split-helper'>当前布局：左侧 {split_ratio}% / 右侧 {100 - split_ratio}%</div>",
    unsafe_allow_html=True
)

left_weight = max(1, split_ratio)
right_weight = max(1, 100 - split_ratio)

left_col, right_col = st.columns([left_weight, right_weight], gap="large")

with left_col:
    render_left_workspace(st.session_state.analysis_result)

with right_col:
    query = st.text_input("Enter your research topic:")

    if st.button("Understand Query"):
        if not query.strip():
            st.warning("Please enter a research topic first.")
            st.stop()

        with st.spinner("Understanding your query from real search evidence..."):
            ensure_query_options(query)

    if st.session_state.query_options_data and (
        st.session_state.query_options_data.get("original_query", "").strip() == query.strip()
    ):
        data = st.session_state.query_options_data
        options = data.get("options", [])
        recommended_index = data.get("recommended_index", 0)

        st.subheader("🔍 Query Understanding")
        st.write(f"**Original Query:** {data.get('original_query', '')}")

        if options:
            radio_labels = []
            for i, opt in enumerate(options):
                prefix = "⭐ Recommended" if i == recommended_index else f"Option {i + 1}"
                confidence = float(opt.get("confidence", 0.0))
                radio_labels.append(
                    f"{prefix}: {opt.get('label', '')} | "
                    f"confidence={confidence:.2f} | "
                    f"{opt.get('reason', '')}"
                )

            custom_option_label = "None of these / I want to type my own query"
            radio_labels.append(custom_option_label)

            if not isinstance(recommended_index, int) or recommended_index < 0 or recommended_index >= len(options):
                recommended_index = 0

            ui_default_index = recommended_index
            if st.session_state.selected_option_index is not None:
                if 0 <= st.session_state.selected_option_index < len(options):
                    ui_default_index = st.session_state.selected_option_index

            selected_option = st.radio(
                "Choose the intended meaning:",
                radio_labels,
                index=ui_default_index
            )

            if selected_option == custom_option_label:
                custom_query = st.text_input(
                    "Enter your corrected academic search query:",
                    value=st.session_state.custom_query_value
                )
                st.session_state.custom_query_value = custom_query

                if custom_query.strip():
                    st.session_state.selected_search_query = custom_query.strip()
                    st.session_state.selected_option_index = None
                    st.session_state.selected_option_payload = {
                        "label": "Custom query",
                        "search_query": custom_query.strip(),
                        "reason": "User-entered custom search query.",
                        "confidence": 1.0,
                        "intent_profile": {}
                    }
                    st.write(f"**Selected Search Query:** {st.session_state.selected_search_query}")

            elif selected_option in radio_labels:
                selected_index = radio_labels.index(selected_option)
                if 0 <= selected_index < len(options):
                    selected_search_query = options[selected_index]["search_query"]
                    st.session_state.selected_option_index = selected_index
                    st.session_state.selected_search_query = selected_search_query
                    st.session_state.selected_option_payload = options[selected_index]
                    st.write(f"**Selected Search Query:** {st.session_state.selected_search_query}")

    st.subheader("⚙️ Retrieval Settings")

    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        paper_count = st.number_input(
            "Paper count",
            min_value=3,
            max_value=500,
            value=10,
            step=1
        )
        st.markdown(
            """
            <div class="recommended-tiers">
                Recommended:
                <span>5</span>
                <span>10</span>
                <span>20</span>
                <span>50</span>
                <span>100+</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        sort_mode = st.selectbox(
            "Sort mode",
            SORT_MODES,
            index=0
        )

    with col3:
        prefer_abstracts = st.checkbox("Prefer abstracts", value=True)

    with col4:
        strict_core_only = st.checkbox("Strict core papers only", value=False)

    with col5:
        open_access_only = st.checkbox("Open access only", value=False)

    with col6:
        current_view_index = 0 if st.session_state.display_view_mode == "Compact" else 1
        view_mode = st.selectbox(
            "Paper view",
            ["Compact", "Detailed"],
            index=current_view_index,
            key="paper_view_selector"
        )
        st.session_state.display_view_mode = view_mode

    source_filters = st.multiselect(
        "Sources",
        options=DEFAULT_SOURCES,
        default=DEFAULT_SOURCES,
        help="Choose which academic sources to search."
    )

    use_year_range = st.checkbox("Use year range filter", value=False)

    if use_year_range:
        year_range = st.slider(
            "Year range",
            min_value=DEFAULT_MIN_YEAR,
            max_value=DEFAULT_MAX_YEAR,
            value=(2018, DEFAULT_MAX_YEAR),
            step=1
        )
    else:
        year_range = None
        st.caption("Year range: Any time")

    if strict_core_only:
        st.caption("Strict mode: only core papers are prioritized; adjacent/background papers are not used unless necessary.")

    if open_access_only:
        st.caption("Open access only: only papers with detected OA access will be kept.")

    if not source_filters:
        st.warning("Please select at least one source.")

    if st.button("Run Search & Analysis"):
        if not query.strip():
            st.warning("Please enter a research topic first.")
            st.stop()

        if not source_filters:
            st.warning("Please select at least one source.")
            st.stop()

        progress_bar = st.progress(0)
        status_box = st.empty()

        try:
            update_progress(progress_bar, status_box, 5, "Understanding query intent...")
            final_query, selected_option_payload, _ = get_effective_query_selection(query)

            if not final_query:
                st.warning("Could not prepare a search query.")
                st.stop()

            update_progress(progress_bar, status_box, 15, "Preparing retrieval settings...")
            update_progress(progress_bar, status_box, 25, "Checking cache and starting pipeline...")

            callback = smart_progress_callback(progress_bar, status_box)

            result = run_ats(
                original_query=query,
                final_search_query=final_query,
                selected_option=selected_option_payload,
                paper_count=int(paper_count),
                sort_mode=sort_mode,
                year_range=year_range,
                prefer_abstracts=prefer_abstracts,
                strict_core_only=strict_core_only,
                open_access_only=open_access_only,
                source_filters=source_filters,
                progress_callback=callback
            )

            update_progress(progress_bar, status_box, 95, "Rendering final results...")
            update_progress(progress_bar, status_box, 100, "Done.")

            st.session_state.analysis_result = result
            st.session_state.last_run_settings = {
                "paper_count": int(paper_count),
                "sort_mode": sort_mode,
                "year_range": year_range,
                "prefer_abstracts": prefer_abstracts,
                "strict_core_only": strict_core_only,
                "open_access_only": open_access_only,
                "source_filters": source_filters,
                "selected_search_query": final_query,
                "view_mode": view_mode
            }
            st.session_state.display_view_mode = view_mode

            status_box.success("✅ ATS pipeline finished.")
            st.rerun()

        except Exception as e:
            progress_bar.progress(0)
            status_box.error(f"❌ Pipeline failed: {str(e)}")

    if st.session_state.analysis_result:
        result = copy.deepcopy(st.session_state.analysis_result)
        result["papers"] = sort_existing_papers_for_display(
            result.get("papers", []),
            sort_mode=sort_mode
        )

        st.markdown("---")

        if st.session_state.last_run_settings:
            last = st.session_state.last_run_settings
            st.caption(
                f"Last run query: {last.get('selected_search_query', '')} | "
                f"initial_rank={last.get('sort_mode')} | "
                f"current_view_sort={sort_mode} | "
                f"paper_count={last.get('paper_count')} | "
                f"prefer_abstracts={last.get('prefer_abstracts')} | "
                f"strict_core_only={last.get('strict_core_only')} | "
                f"open_access_only={last.get('open_access_only')} | "
                f"sources={', '.join(last.get('source_filters', []))} | "
                f"view={st.session_state.display_view_mode} | "
                f"year_range={last.get('year_range') if last.get('year_range') else 'Any time'}"
            )

        render_papers_content(
            result,
            view_mode=st.session_state.display_view_mode,
            display_sort_mode=sort_mode
        )