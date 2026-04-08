import datetime
import copy
import time
from io import BytesIO
from pathlib import Path

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

BASE_DIR = Path(__file__).resolve().parent
logo_path = BASE_DIR / "Picture" / "LOGO4.png"

st.caption(f"BASE_DIR = {BASE_DIR}")
st.caption(f"Trying logo path = {logo_path}")
st.caption(f"Logo exists = {logo_path.exists()}")

if logo_path.exists():
    st.image(str(logo_path), width=200)
else:
    st.error(f"Logo path not found: {logo_path}")

st.markdown(
    """
    <style>
        .main .block-container {
            max-width: 100%;
            padding-top: 0rem;
            padding-left: 1.2rem;
            padding-right: 1.2rem;
            padding-bottom: 1.5rem;
        }

        .panel-box-lite {
            border: 1px solid rgba(120,120,120,0.18);
            border-radius: 14px;
            padding: 1rem 1rem 0.9rem 1rem;
            background: rgba(255,255,255,0.02);
            margin-bottom: 1rem;
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

        .brief-box-lite {
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

        .strategy-box-lite {
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

        .friendly-step {
            border-left: 3px solid rgba(59,130,246,0.45);
            padding: 0.7rem 0.8rem;
            margin-bottom: 0.6rem;
            background: rgba(59,130,246,0.05);
            border-radius: 0.5rem;
        }

        .friendly-step-title {
            font-weight: 700;
            font-size: 0.95rem;
            margin-bottom: 0.18rem;
            color: #111827;
        }

        .friendly-step-body {
            color: #374151;
            line-height: 1.55;
            font-size: 0.93rem;
        }

        .debate-card {
            border: 1px solid rgba(99,102,241,0.16);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.85rem;
            background: rgba(99,102,241,0.04);
        }

        .debate-title {
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.65rem;
            color: #111827;
        }

        .debate-chip-row {
            margin-bottom: 0.7rem;
        }

        .mini-chip {
            display: inline-block;
            padding: 0.18rem 0.55rem;
            margin-right: 0.4rem;
            margin-bottom: 0.4rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
            background: rgba(59,130,246,0.10);
            border: 1px solid rgba(59,130,246,0.18);
            color: #1f2937;
        }

        .debate-section {
            margin-top: 0.45rem;
            line-height: 1.55;
            color: #374151;
        }

        .live-running-box {
            border: 1px solid rgba(37,99,235,0.20);
            border-radius: 14px;
            padding: 0.85rem 1rem;
            margin-bottom: 0.9rem;
            background: rgba(37,99,235,0.05);
        }

        .live-running-title {
            display: flex;
            align-items: center;
            gap: 0.45rem;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            color: #2563eb;
            margin-bottom: 0.35rem;
        }

        .live-running-text {
            font-size: 0.96rem;
            color: #c9d1d9;
            line-height: 1.55;
        }

        .live-dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #2563eb;
            display: inline-block;
            animation: livePulse 1.2s infinite ease-in-out;
        }

        .live-blink {
            animation: liveBlink 1.2s infinite ease-in-out;
        }

        @keyframes livePulse {
            0%   { transform: scale(0.9); opacity: 0.55; }
            50%  { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.55; }
        }

        @keyframes liveBlink {
            0%   { opacity: 0.45; }
            50%  { opacity: 1; }
            100% { opacity: 0.45; }
        }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    '<h1 style="font-size: 3rem; font-weight: 800; margin-top: -0.6rem; margin-bottom: 0.2rem; line-height: 1.1;"><span style="color: #1F2937;">Academic </span><span style="color: #2563EB;">ATS</span></h1>',
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

    clean_text = (brief_text or "").strip()

    while "# Research Brief" in clean_text:
        clean_text = clean_text.replace("# Research Brief", "Research Brief")

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

# Initialize session state variables
if "query_options_data" not in st.session_state: st.session_state.query_options_data = None
if "selected_search_query" not in st.session_state: st.session_state.selected_search_query = None
if "selected_option_index" not in st.session_state: st.session_state.selected_option_index = None
if "selected_option_payload" not in st.session_state: st.session_state.selected_option_payload = None
if "custom_query_value" not in st.session_state: st.session_state.custom_query_value = ""
if "analysis_result" not in st.session_state: st.session_state.analysis_result = None
if "last_run_settings" not in st.session_state: st.session_state.last_run_settings = None

# 设置初始默认比例为 30
if "panel_split_ratio" not in st.session_state: st.session_state.panel_split_ratio = 30

if "last_cache_clear_time" not in st.session_state: st.session_state.last_cache_clear_time = None
if "display_view_mode" not in st.session_state: st.session_state.display_view_mode = "Compact"
if "live_workflow_events" not in st.session_state: st.session_state.live_workflow_events = []
if "live_agent_events" not in st.session_state: st.session_state.live_agent_events = []
if "current_live_stage" not in st.session_state: st.session_state.current_live_stage = ""
if "current_live_agent_label" not in st.session_state: st.session_state.current_live_agent_label = ""
if "current_live_progress" not in st.session_state: st.session_state.current_live_progress = 0
if "current_run_started_at" not in st.session_state: st.session_state.current_run_started_at = None
if "last_run_duration_seconds" not in st.session_state: st.session_state.last_run_duration_seconds = None

def clamp_progress(value):
    try:
        v = float(value)
    except Exception:
        v = 0.0
    if 0 <= v <= 1:
        v = v * 100
    return max(0, min(100, int(round(v))))

def format_duration(seconds):
    try:
        total = max(0, int(round(float(seconds))))
    except Exception:
        total = 0

    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"

def update_progress(value, text):
    st.session_state.current_live_progress = clamp_progress(value)
    st.session_state.current_live_stage = text
    st.session_state.current_live_agent_label = _guess_agent_label_from_stage(text)

def truncate_text(text: str, limit: int = 220) -> str:
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."

def make_safe_pdf_filename(original_query: str) -> str:
    query = (original_query or "research_brief").strip().lower()
    query = query.replace(" ", "_")
    query = "".join(ch for ch in query if ch.isalnum() or ch in ["_", "-"])
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

def _humanize_workflow_entry(item: dict):
    agent = item.get("agent", "System")
    action = str(item.get("action", "")).strip().lower()
    details = str(item.get("details", "")).strip()

    title = f"{agent}"
    body = details if details else "系统正在处理中。"

    if agent == "RouterAgent" and action == "start":
        title = "系统已启动这次检索流程"
        body = "系统开始协调多个 agent，共同完成查询理解、检索、筛选、验证和总结。"
    elif agent == "RouterAgent" and action == "route":
        details_l = details.lower()

        if "next=query_planner_initial" in details_l:
            title = "系统正在理解你的问题"
            body = "下一步会先判断你的问题更可能指向什么研究方向，并规划第一轮检索策略。"
        elif "next=retrieve" in details_l:
            title = "系统正在开始检索论文"
            body = "系统准备去多个学术来源里抓取候选论文，并做第一轮筛选。"
        elif "next=query_planner_review" in details_l:
            title = "系统正在复查第一轮检索结果"
            body = "系统会判断这一轮结果是不是已经够准，还是还需要进一步收紧。"
        elif "next=retrieve_refinement" in details_l:
            title = "系统正在进行更精确的一轮重检索"
            body = "因为当前结果里仍有偏题或相邻领域论文，系统会做一轮更严格的筛选。"
        elif "next=researcher" in details_l:
            title = "系统正在整理这批论文主要讲了什么"
            body = "Researcher 正在提炼主题、共识和整体覆盖范围。"
        elif "next=theorist" in details_l:
            title = "系统正在抽取概念框架"
            body = "Theorist 正在看这批文献背后的核心概念、理论差异和张力。"
        elif "next=methodologist" in details_l:
            title = "系统正在检查方法和证据结构"
            body = "Methodologist 正在看这批文献主要用了什么研究方法，证据是否扎实。"
        elif "next=critic" in details_l:
            title = "系统正在主动挑问题"
            body = "Critic 正在找这批论文里可能的偏题、过度推断和薄弱区域。"
        elif "next=gap_analyst" in details_l:
            title = "系统正在识别研究空白"
            body = "Gap Analyst 正在判断目前文献里哪些问题还没被回答清楚。"
        elif "next=verifier" in details_l:
            title = "系统正在核查哪些结论更可靠"
            body = "Verifier 正在给最终结论做可信度把关，区分强支持、弱支持和不确定部分。"
        elif "next=editor" in details_l:
            title = "系统正在撰写最终 Research Brief"
            body = "Editor 正在把前面多个 agent 的结果整合成最终可读的研究结论。"
        elif "next=finish" in details_l:
            title = "系统已完成本次检索与分析"
            body = "这次查询的多 agent 流程已经结束。"
        else:
            title = "系统正在决定下一步"
            body = details if details else "系统在路由不同 agent 的工作顺序。"

    elif agent == "QueryPlannerAgent" and action == "plan_initial":
        title = "检索策略已经规划好"
        body = "系统完成了第一轮检索规划，准备开始抓取候选论文。"
    elif agent == "QueryPlannerAgent" and action == "plan_review":
        title = "系统完成了第一轮结果复查"
        body = "系统已经判断这批结果的准确度，并决定是否需要再收紧一轮。"
    elif agent == "RetrievalAgent" and action == "retrieve":
        title = "系统完成了一轮候选论文检索"
        body = details if details else "已从多个来源抓取候选论文，并完成初步去重与排序。"
    elif agent == "RetrievalAgent" and action == "retrieve_refined":
        title = "系统完成了一轮更严格的重检索"
        body = details if details else "系统对偏题和相邻领域结果做了进一步压缩。"
    elif action == "finish":
        title = "本次流程结束"
        body = details if details else "系统已完成。"

    return title, body

def _humanize_debate_entry(item: dict):
    title = item.get("title", "Untitled")

    selector_decision = str(item.get("selector_decision", "")).strip().lower()
    critic_decision = str(item.get("critic_decision", "")).strip().lower()
    arbiter_decision = str(item.get("arbiter_decision", "")).strip().lower()

    def zh_decision(d):
        mapping = {
            "keep": "保留",
            "reject": "剔除",
            "uncertain": "待观察"
        }
        return mapping.get(d, d or "未知")

    debate_level = str(item.get("debate_level", "")).strip().lower()
    if debate_level == "high":
        debate_severity = "争议较大"
    elif debate_level == "medium":
        debate_severity = "有一定争议"
    else:
        debate_severity = "基本一致"

    return {
        "title": title,
        "selector_decision": zh_decision(selector_decision),
        "critic_decision": zh_decision(critic_decision),
        "arbiter_decision": zh_decision(arbiter_decision),
        "debate_severity": debate_severity,
        "confidence": float(item.get("confidence", 0.0) or 0.0),
        "selector_reason": item.get("selector_reason", "") or item.get("selector", "") or "暂无说明",
        "critic_reason": item.get("critic_reason", "") or item.get("critic", "") or "暂无说明",
        "arbiter_reason": item.get("arbiter_reason", "") or item.get("arbiter", "") or "暂无说明",
    }

def render_live_agent_activity():
    with st.container():
        st.markdown(
            "<div class='panel-box-lite'>"
            #"<div class='panel-title'>⚔️ Live Agent Interaction</div>"
            #"<div class='left-sticky-note'>把后台 agent 的工作翻译成用户能读懂的话。查询过程中会实时显示系统当前在做什么，以及论文为什么被保留或剔除。</div>"
            "</div>",
            unsafe_allow_html=True
        )

        workflow_events = st.session_state.get("live_workflow_events", []) or []
        adversarial_events = st.session_state.get("live_agent_events", []) or []
        current_stage = st.session_state.get("current_live_stage", "") or ""
        current_agent_label = st.session_state.get("current_live_agent_label", "") or "系统"

        if current_stage:
            st.markdown(
                f"""
                <div class="live-running-box">
                    <div class="live-running-title">
                        <span class="live-dot"></span>
                        <span class="live-blink">CURRENTLY RUNNING</span>
                    </div>
                    <div class="live-running-text">{current_agent_label}：{current_stage}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        if not workflow_events and not adversarial_events:
            st.caption("Run Search 后，这里会实时出现 agent 的动作翻译。")
            return

        if workflow_events:
            with st.expander("系统当前在做什么", expanded=False):
                total = len(workflow_events)
                recent_workflow = workflow_events[-12:]

                for local_idx, item in enumerate(recent_workflow, start=1):
                    global_idx = total - len(recent_workflow) + local_idx
                    title, body = _humanize_workflow_entry(item)
                    is_latest = global_idx == total

                    st.markdown(
                        f"""
                        <div class="friendly-step{' live-blink' if is_latest else ''}">
                            <div class="friendly-step-title">{global_idx}. {title}</div>
                            <div class="friendly-step-body">{body}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

        if adversarial_events:
            with st.expander("论文筛选时发生了什么", expanded=False):
                for raw_item in adversarial_events[-10:]:
                    item = _humanize_debate_entry(raw_item)

                    html = f"""
                    <div class="debate-card">
                        <div class="debate-title">{item.get('title', 'Untitled')}</div>

                        <div class="debate-chip-row">
                            <span class="mini-chip">初筛意见：{item.get('selector_decision', '')}</span>
                            <span class="mini-chip">反方意见：{item.get('critic_decision', '')}</span>
                            <span class="mini-chip">最终裁决：{item.get('arbiter_decision', '')}</span>
                            <span class="mini-chip">{item.get('debate_severity', '')}</span>
                            <span class="mini-chip">把握度 {item.get('confidence', 0.0):.2f}</span>
                        </div>

                        <div class="debate-section">
                            <b>为什么初步想这样判：</b> {item.get('selector_reason', '')}
                        </div>
                        <div class="debate-section">
                            <b>为什么有人反对：</b> {item.get('critic_reason', '')}
                        </div>
                        <div class="debate-section">
                            <b>最后为什么这么定：</b> {item.get('arbiter_reason', '')}
                        </div>
                    </div>
                    """
                    st.markdown(html, unsafe_allow_html=True)

def render_strategy_summary(result: dict):
    with st.container():
        st.markdown(
            "<div class='strategy-box-lite'>"
            "<div class='strategy-title'>🧭 Retrieval Strategy Summary</div>"
            "<div class='panel-subtitle'>说明这次是怎么搜的、怎么筛的、为什么一些论文被保留，而另一些被压下去。</div>"
            "</div>",
            unsafe_allow_html=True
        )

        if not result:
            st.info("Run Search 后，这里会显示本次检索策略摘要。")
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
    with st.container():
        st.markdown(
            "<div class='brief-box-lite'>"
            "<div class='brief-title'>📄 Research Brief</div>"
            "<div class='panel-subtitle'>默认优先展示最终成品结论；更深层的多 agent 分析轨迹与检索策略说明可在下方继续查看。</div>"
            "</div>",
            unsafe_allow_html=True
        )

        if not result:
            st.info("Run Search 后，这里会显示最终的 Research Brief。")
            return

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

def render_structured_agent(name: str, payload: dict):
    st.write(f"**{name} summary**")

    if not payload:
        st.caption(f"{name} did not return structured output in this run.")
        return

    narrative = payload.get("narrative", "")
    if narrative:
        st.write(narrative)

    keys_to_hide = {"narrative"}
    rendered_any = bool(str(narrative).strip())
    for key, value in payload.items():
        if key in keys_to_hide:
            continue
        if isinstance(value, list) and value:
            rendered_any = True
            st.write(f"**{key.replace('_', ' ').title()}**")
            for item in value:
                st.write(f"- {item}")
        elif isinstance(value, str) and value.strip():
            rendered_any = True
            st.write(f"**{key.replace('_', ' ').title()}**")
            st.write(value)

    if not rendered_any:
        st.caption(f"{name} returned an empty payload in this run.")

def render_analysis_trace(result: dict):
    with st.container():
        st.markdown(
            "<div class='panel-box-lite'>"
            "<div class='panel-title'>🧠 Analytical Trace</div>"
            "<div class='left-sticky-note'>多 agent 的结构化分析轨迹默认折叠，只有需要查看推理分轨时才展开。</div>"
            "</div>",
            unsafe_allow_html=True
        )

        if not result:
            st.info("Run Search 后，这里会显示多 agent 分析轨迹。")
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

def render_collaboration_trace(result: dict):
    with st.container():
        st.markdown(
            "<div class='panel-box-lite'>"
            "<div class='panel-title'>🤝 Collaboration Trace</div>"
            "<div class='left-sticky-note'>多 agent 的协作轨迹默认折叠，只有需要查看 Router 决策和 refinement 过程时才展开。</div>"
            "</div>",
            unsafe_allow_html=True
        )

        if not result:
            st.info("Run Search 后，这里会显示 collaboration trace。")
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

def render_left_workspace(result: dict):
    render_final_brief(result)
    render_collaboration_trace(result)
    render_analysis_trace(result)
    render_strategy_summary(result)

def _append_unique_limited(lst, item, max_items=40):
    if not item:
        return
    if item in lst:
        return
    lst.append(item)
    if len(lst) > max_items:
        del lst[0:len(lst) - max_items]

def _update_live_agent_state_from_payload(payload):
    if not isinstance(payload, dict):
        return

    payload_type = str(payload.get("type", payload.get("event_type", ""))).strip().lower()

    if payload_type in ["workflow", "workflow_trace"]:
        workflow_item = payload.get("entry") if isinstance(payload.get("entry"), dict) else {
            "agent": payload.get("agent", "System"),
            "action": payload.get("action", ""),
            "details": payload.get("details", ""),
        }
        _append_unique_limited(st.session_state.live_workflow_events, workflow_item, max_items=50)

    elif payload_type in ["adversarial", "adversarial_trace"]:
        entries = payload.get("entries") if isinstance(payload.get("entries"), list) else [payload]
        for entry in entries:
            debate_item = {
                "title": entry.get("title", "Untitled"),
                "selector_decision": entry.get("selector_decision", ""),
                "critic_decision": entry.get("critic_decision", ""),
                "arbiter_decision": entry.get("arbiter_decision", ""),
                "debate_level": entry.get("debate_level", entry.get("debate_severity", "")),
                "confidence": entry.get("confidence", 0.0),
                "selector_reason": entry.get("selector_reason", ""),
                "critic_reason": entry.get("critic_reason", ""),
                "arbiter_reason": entry.get("arbiter_reason", ""),
            }
            _append_unique_limited(st.session_state.live_agent_events, debate_item, max_items=40)

def _guess_agent_label_from_stage(stage_text: str) -> str:
    t = (stage_text or "").lower()

    if "query planner" in t:
        return "Query Planner"
    if "retrieval agent" in t or "searching academic sources" in t or "refining retrieval" in t:
        return "Retrieval Agent"
    if "researcher agent" in t:
        return "Researcher"
    if "theorist agent" in t:
        return "Theorist"
    if "methodologist agent" in t:
        return "Methodologist"
    if "critic agent" in t:
        return "Critic"
    if "gap agent" in t:
        return "Gap Analyst"
    if "verifier agent" in t:
        return "Verifier"
    if "editor agent" in t or "research brief" in t:
        return "Editor"
    if "screening batch" in t:
        return "Adversarial Screening"
    return "System"

def smart_progress_callback(stage_container=None):
    def _callback(*args):
        progress = 0
        stage = "Running..."
        payload = None

        if len(args) >= 1:
            progress = args[0]
        if len(args) >= 2:
            stage = str(args[1])
        if len(args) >= 3:
            payload = args[2]

        st.session_state.current_live_progress = clamp_progress(progress)
        st.session_state.current_live_stage = stage
        st.session_state.current_live_agent_label = _guess_agent_label_from_stage(stage)

        if payload is not None:
            _update_live_agent_state_from_payload(payload)

        if stage_container is not None:
            render_current_stage_inline(stage_container)

    return _callback

def render_current_stage_inline(container=None):
    current_stage = st.session_state.get("current_live_stage", "") or ""
    current_agent_label = st.session_state.get("current_live_agent_label", "") or "System"
    current_progress = int(st.session_state.get("current_live_progress", 0) or 0)
    current_run_started_at = st.session_state.get("current_run_started_at")
    last_run_duration_seconds = st.session_state.get("last_run_duration_seconds")

    if not current_stage:
        if container is not None and hasattr(container, "empty"):
            container.empty()
        return

    elapsed_text = ""
    if current_run_started_at:
        elapsed_seconds = max(0, time.time() - float(current_run_started_at))
        elapsed_text = f"Running time: {format_duration(elapsed_seconds)}"
    elif last_run_duration_seconds is not None:
        elapsed_text = f"Last run time: {format_duration(last_run_duration_seconds)}"

    elapsed_html = ""
    if elapsed_text:
        # 下面这里的颜色改成了 #8b949e
        elapsed_html = f'<div style="margin-top: 0.45rem; font-size: 0.88rem; color: #8b949e;">{elapsed_text}</div>'

    html = f"""
        <div class="live-running-box">
            <div class="live-running-title">
                <span class="live-dot"></span>
                <span class="live-blink">CURRENTLY RUNNING</span>
            </div>
            <div class="live-running-text">{current_agent_label}：{current_stage}</div>
            <div style="margin-top: 0.85rem;">
                <div style="width: 100%; height: 10px; background: rgba(37,99,235,0.10); border-radius: 999px; overflow: hidden;">
                    <div style="width: {current_progress}%; height: 100%; background: #2563eb; border-radius: 999px;"></div>
                </div>
                <div style="margin-top: 0.45rem; font-size: 0.88rem; color: #8b949e;">Progress: {current_progress}%</div>
                {elapsed_html}
            </div>
        </div>
    """

    if container is not None and hasattr(container, "empty"):
        container.empty()
        container.markdown(html, unsafe_allow_html=True)
    else:
        st.markdown(html, unsafe_allow_html=True)

def ensure_query_options(raw_query: str):
    if not raw_query.strip():
        return None

    # 如果缓存里的 query 和当前输入一致，直接返回数据，不在函数里画 UI
    if st.session_state.query_options_data and (st.session_state.query_options_data.get("original_query", "").strip() == raw_query.strip()):
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
    st.session_state.live_workflow_events = []
    st.session_state.live_agent_events = []
    st.session_state.current_live_stage = ""
    st.session_state.current_live_agent_label = ""
    st.session_state.current_live_progress = 0
    st.session_state.current_run_started_at = None
    st.session_state.last_run_duration_seconds = None


# =====================================================================
# 页面布局核心逻辑（双栏动态切割）
# =====================================================================
split_ratio = st.session_state.panel_split_ratio
left_weight = max(1, split_ratio)
right_weight = max(1, 100 - split_ratio)

left_col, right_col = st.columns([left_weight, right_weight], gap="large")

with left_col:
    # 这里是你要求的原汁原味的左侧功能
    render_left_workspace(st.session_state.analysis_result)

with right_col:
    # 核心工作区
    st.markdown('<div class="panel-title">🧠 Workspace</div>', unsafe_allow_html=True)
    query = st.text_input("Enter your research topic:", label_visibility="collapsed", placeholder="Enter your research topic...")
    
    st.write("") # 提供一定的呼吸感

    # 【功能 2 满足】：Understand 和 Run 的按钮并排，并且左边是 Understand
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        understand_btn = st.button("🔍 Understand Query First", use_container_width=True)
    with btn_col2:
        run_btn = st.button("🚀 Run Search & Analysis", type="primary", use_container_width=True)

    # 【功能 3 满足】：设置变成一个右侧的隐藏/划出侧栏 (通过 expander 完美替代，不挤压主空间)
    with st.expander("⚙️ Settings & Controls (Click to expand/collapse)", expanded=False):
        # 原有的 Cache 控制区域
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("Clear Cache", use_container_width=True):
                clear_all_caches()
                st.success("Cache cleared.")
                st.rerun()
        with c2:
            if st.session_state.last_cache_clear_time:
                st.markdown(f"<div class='cache-note'>Last cache clear: {st.session_state.last_cache_clear_time}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='cache-note'>Cache enabled for preview search, query understanding, retrieval, and ATS analysis.</div>", unsafe_allow_html=True)
        
        # 布局拖动条
        st.session_state.panel_split_ratio = st.slider(
            "Panel width (Left Output %)",
            min_value=20, max_value=80,
            value=st.session_state.panel_split_ratio,
            step=1,
            help="调整左侧分析区和右侧结果区的宽度比例。"
        )

        st.markdown("---")
        
        # 六大检索参数选项区
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            paper_count = st.number_input("Paper count", min_value=3, max_value=500, value=10, step=1)
        with col2:
            sort_mode = st.selectbox("Sort mode", SORT_MODES, index=0)
        with col3:
            prefer_abstracts = st.checkbox("Prefer abstracts", value=True)
        with col4:
            strict_core_only = st.checkbox("Strict core papers only", value=False)
        with col5:
            open_access_only = st.checkbox("Open access only", value=False)
        with col6:
            current_view_index = 0 if st.session_state.display_view_mode == "Compact" else 1
            view_mode = st.selectbox("Paper view", ["Compact", "Detailed"], index=current_view_index)
            st.session_state.display_view_mode = view_mode

        source_filters = st.multiselect("Sources", options=DEFAULT_SOURCES, default=DEFAULT_SOURCES)
        use_year_range = st.checkbox("Use year range filter", value=False)
        if use_year_range:
            year_range = st.slider("Year range", min_value=DEFAULT_MIN_YEAR, max_value=DEFAULT_MAX_YEAR, value=(2018, DEFAULT_MAX_YEAR), step=1)
        else:
            year_range = None
            st.caption("Year range: Any time")

        if strict_core_only:
            st.caption("Strict mode: only core papers are prioritized; adjacent/background papers are not used unless necessary.")
        if open_access_only:
            st.caption("Open access only: only papers with detected OA access will be kept.")

    st.markdown("---")

    # =====================================================================
    # 执行流逻辑 (一行未删)
    # =====================================================================
    if understand_btn:
        if not query.strip():
            st.warning("Please enter a research topic first.")
            st.stop()

        with st.spinner("Understanding your query from real search evidence..."):
            ensure_query_options(query)

    if st.session_state.query_options_data and (st.session_state.query_options_data.get("original_query", "").strip() == query.strip()):
        data = st.session_state.query_options_data
        options = data.get("options", [])
        recommended_index = data.get("recommended_index", 0)

        # 换成可折叠的 expander 容器，取代原来的 st.subheader
        with st.expander("🔍 Query Understanding (Click to expand/collapse)", expanded=True):
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

                # 单选框，加入唯一 key
                selected_option = st.radio("Choose the intended meaning:", radio_labels, index=ui_default_index, key="radio_main_query")

                if selected_option == custom_option_label:
                    custom_query = st.text_input("Enter your corrected academic search query:", value=st.session_state.custom_query_value, key="text_main_query")
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

    stage_inline_container = st.empty()
    render_current_stage_inline(stage_inline_container)
    
    # 【恢复的核心功能】：你遗失的 Agent 实时监测块，现在它终于被挂载在执行区了！
    render_live_agent_activity()

    if run_btn:
        if not query.strip():
            st.warning("Please enter a research topic first.")
            st.stop()
        if not source_filters:
            st.warning("Please select at least one source.")
            st.stop()

        st.session_state.live_workflow_events = []
        st.session_state.live_agent_events = []
        st.session_state.current_run_started_at = time.time()
        st.session_state.last_run_duration_seconds = None
        st.session_state.current_live_stage = "正在准备新的检索流程"
        st.session_state.current_live_agent_label = "System"
        st.session_state.current_live_progress = 2
        render_current_stage_inline(stage_inline_container)

        try:
            update_progress(5, "Understanding query intent...")
            render_current_stage_inline(stage_inline_container)
            final_query, selected_option_payload, _ = get_effective_query_selection(query)

            if not final_query:
                st.warning("Could not prepare a search query.")
                st.stop()

            update_progress(15, "Preparing retrieval settings...")
            render_current_stage_inline(stage_inline_container)
            update_progress(25, "Checking cache and starting pipeline...")
            render_current_stage_inline(stage_inline_container)

            callback = smart_progress_callback(stage_inline_container)

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

            update_progress(95, "Rendering final results...")
            render_current_stage_inline(stage_inline_container)
            update_progress(100, "Done.")
            render_current_stage_inline(stage_inline_container)

            st.session_state.current_live_stage = "检索与分析已完成"
            st.session_state.current_live_agent_label = "System"
            st.session_state.current_live_progress = 100

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

            if st.session_state.current_run_started_at:
                st.session_state.last_run_duration_seconds = max(0, time.time() - float(st.session_state.current_run_started_at))
            st.session_state.current_run_started_at = None
            render_current_stage_inline(stage_inline_container)

            st.success("✅ ATS pipeline finished.")
            st.rerun()

        except Exception as e:
            if st.session_state.current_run_started_at:
                st.session_state.last_run_duration_seconds = max(0, time.time() - float(st.session_state.current_run_started_at))
            st.session_state.current_run_started_at = None
            st.session_state.current_live_stage = f"运行失败：{str(e)}"
            st.session_state.current_live_agent_label = "System"
            st.session_state.current_live_progress = 0
            render_current_stage_inline(stage_inline_container)
            st.error(f"❌ Pipeline failed: {str(e)}")

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
        # =====================================================================
    # 结果展示区块 (接在运行出错的 except 后面，这是整个文件的最末尾)
    # =====================================================================
    if st.session_state.analysis_result:
        result = copy.deepcopy(st.session_state.analysis_result)
        
        # 按照用户在面板中选择的排序模式，重新排版论文列表
        result["papers"] = sort_existing_papers_for_display(
            result.get("papers", []),
            sort_mode=sort_mode
        )

        st.markdown("---")

        # 打印当前使用的检索参数快照，方便比对
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

        # ====== 这是整个 ui.py 的最后一行代码 ======
        # 渲染右侧的最终论文卡片列表
        render_papers_content(
            result,
            view_mode=st.session_state.display_view_mode,
            display_sort_mode=sort_mode
        )

# ================= ui.py 代码到此全部结束 =================