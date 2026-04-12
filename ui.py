import json
import datetime
import html
import re
import copy
import time
import base64
from io import BytesIO
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from search_service import generate_query_options, sort_existing_papers_for_display
from ats_pipeline import run_ats
from deep_read_service import (
    build_brief_highlight_map,
    build_deep_read_report_markdown,
    deep_read_open_access_paper,
    download_open_access_pdf,
    translate_open_access_pdf,
    translate_open_access_pdf_multi,
    renderable_brief_html,
    safe_filename,
    slugify,
)

st.set_page_config(
    page_title="Academic ATS 1.0",
    page_icon="📚",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent
logo_path = BASE_DIR / "Picture" / "LOGO4.png"

#st.caption(f"BASE_DIR = {BASE_DIR}")
#st.caption(f"Trying logo path = {logo_path}")
#st.caption(f"Logo exists = {logo_path.exists()}")

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

        .linked-brief-heading {
            font-size: 1.05rem;
            font-weight: 700;
            margin-top: 0.85rem;
            margin-bottom: 0.35rem;
            color: inherit;
        }

        .linked-brief-paragraph {
            line-height: 1.7;
            color: inherit;
            margin-bottom: 0.55rem;
        }

        .brief-highlight-link {
            display: inline;
            padding: 0;
            margin: 0;
            border-radius: 0;
            background: none;
            color: inherit;
            text-decoration: underline;
            text-underline-offset: 0.15rem;
            font-weight: 600;
            cursor: pointer;
        }

        .brief-highlight-link:hover {
            background: none;
            color: #60a5fa;
        }

        .brief-source-card {
            border: 1px solid rgba(234, 179, 8, 0.22);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.85rem;
            background: rgba(250, 204, 21, 0.06);
        }

        .brief-source-title {
            font-size: 0.98rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
            color: inherit;
        }

        .deep-read-box {
            border: 1px solid rgba(59,130,246,0.16);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            margin: 0.8rem 0 1rem 0;
            background: rgba(59,130,246,0.04);
        }

        .deep-read-mini-title {
            font-size: 0.96rem;
            font-weight: 700;
            margin-bottom: 0.4rem;
            color: inherit;
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
DEFAULT_SOURCES = ["Semantic Scholar", "OpenAlex", "Crossref", "Google Scholar", "arXiv", "PubMed", "ERIC", "DOAJ", "DiGRA"]
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



def build_deep_read_report_pdf_bytes(result: dict, fallback_name: str = "deep_read_report") -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Deep Reading Report",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DeepReadTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=10,
    )
    meta_style = ParagraphStyle(
        "DeepReadMeta",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        spaceAfter=5,
    )
    heading_style = ParagraphStyle(
        "DeepReadHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=15,
        spaceBefore=8,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "DeepReadBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.2,
        leading=14.5,
        spaceAfter=6,
    )

    paper = result.get("paper", {}) or {}
    story = []
    title = paper.get("title", fallback_name) or fallback_name
    story.append(Paragraph(f"Deep Reading Report — {html.escape(str(title))}", title_style))

    meta_lines = [
        f"<b>Authors:</b> {html.escape(str(paper.get('authors', '')))}",
        f"<b>Year:</b> {html.escape(str(paper.get('year', '')))}",
        f"<b>Source:</b> {html.escape(str(paper.get('source', '')))}",
        f"<b>Analysis mode:</b> {html.escape(str(result.get('analysis_mode', 'unknown')))}",
        f"<b>Page count:</b> {html.escape(str(result.get('page_count', 'N/A')))}",
    ]
    for line in meta_lines:
        story.append(Paragraph(line, meta_style))
    story.append(Spacer(1, 6))

    def add_heading(name: str):
        story.append(Paragraph(html.escape(name), heading_style))

    def add_paragraph(value: str):
        safe = html.escape(str(value or "")).replace("\n", "<br/>")
        story.append(Paragraph(safe, body_style))

    if result.get("academic_summary") or result.get("document_summary"):
        add_heading("Academic Summary")
        add_paragraph(result.get("academic_summary") or result.get("document_summary", ""))

    snapshot = result.get("study_snapshot", {}) or {}
    snapshot_rows = [
        ("Research question", snapshot.get("research_question", "")),
        ("Study design", snapshot.get("study_design", "")),
        ("Sample / material", snapshot.get("sample_or_material", "")),
        ("Core claim", snapshot.get("core_claim", "")),
    ]
    if any(v for _, v in snapshot_rows):
        add_heading("Study Snapshot")
        for label, value in snapshot_rows:
            if value:
                add_paragraph(f"<b>{label}:</b> {value}")

    key_findings = result.get("key_findings", []) or []
    if result.get("core_contribution"):
        add_heading("Core Contribution")
        add_paragraph(result.get("core_contribution", ""))

    if result.get("theoretical_or_conceptual_frame"):
        add_heading("Theoretical or Conceptual Frame")
        add_paragraph(result.get("theoretical_or_conceptual_frame", ""))

    if key_findings:
        add_heading("Key Findings")
        for item in key_findings[:4]:
            add_paragraph(f"- {item}")

    evidence_chain = result.get("evidence_chain", []) or []
    if evidence_chain:
        add_heading("Evidence Chain")
        for item in evidence_chain[:5]:
            add_paragraph(f"- {item}")

    if result.get("relevance_to_query"):
        add_heading("Relevance to Your Query")
        add_paragraph(result.get("relevance_to_query", ""))

    high_value = result.get("high_value_paragraphs", []) or []
    if high_value:
        add_heading("Best Passages to Check")
        for item in high_value[:6]:
            add_paragraph(f"Page {item.get('page_number', 'N/A')}")
            if item.get("why_valuable"):
                add_paragraph(f"Why useful: {item.get('why_valuable', '')}")
            add_paragraph(item.get("paragraph", ""))

    section_takeaways = result.get("section_takeaways", []) or []
    if section_takeaways:
        add_heading("Section Takeaways")
        for item in section_takeaways[:6]:
            add_paragraph(f"{item.get('heading', 'Section')} (pp. {item.get('page_start', 'N/A')}-{item.get('page_end', 'N/A')})")
            add_paragraph(item.get("takeaway", ""))

    for title_name, key in [
        ("Methodological Notes", "methodological_notes"),
        ("Practical Implications", "practical_implications"),
        ("Limitations or Cautions", "limitations_or_cautions"),
    ]:
        values = result.get(key, []) or []
        if values:
            add_heading(title_name)
            for item in values[:6]:
                add_paragraph(f"- {item}")

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
if "display_view_mode" not in st.session_state: st.session_state.display_view_mode = "Detailed"
if "live_workflow_events" not in st.session_state: st.session_state.live_workflow_events = []
if "live_agent_events" not in st.session_state: st.session_state.live_agent_events = []
if "current_live_stage" not in st.session_state: st.session_state.current_live_stage = ""
if "current_live_agent_label" not in st.session_state: st.session_state.current_live_agent_label = ""
if "current_live_progress" not in st.session_state: st.session_state.current_live_progress = 0
if "current_run_started_at" not in st.session_state: st.session_state.current_run_started_at = None
if "last_run_duration_seconds" not in st.session_state: st.session_state.last_run_duration_seconds = None
if "deep_read_results" not in st.session_state: st.session_state.deep_read_results = {}
if "deep_read_error_messages" not in st.session_state: st.session_state.deep_read_error_messages = {}
if "original_pdf_results" not in st.session_state: st.session_state.original_pdf_results = {}
if "original_pdf_error_messages" not in st.session_state: st.session_state.original_pdf_error_messages = {}
if "translated_pdf_results" not in st.session_state: st.session_state.translated_pdf_results = {}
if "translated_pdf_error_messages" not in st.session_state: st.session_state.translated_pdf_error_messages = {}
if "deep_read_progress_state" not in st.session_state: st.session_state.deep_read_progress_state = {}
if "translated_pdf_progress_state" not in st.session_state: st.session_state.translated_pdf_progress_state = {}
if "translated_zip_results" not in st.session_state: st.session_state.translated_zip_results = {}
if "translated_zip_error_messages" not in st.session_state: st.session_state.translated_zip_error_messages = {}
if "translated_zip_progress_state" not in st.session_state: st.session_state.translated_zip_progress_state = {}
if "paper_task_queue" not in st.session_state: st.session_state.paper_task_queue = []
if "paper_active_task" not in st.session_state: st.session_state.paper_active_task = None

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


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def cached_deep_read_open_access_paper(paper_json: str, user_query: str):
    paper = json.loads(paper_json) if paper_json else {}
    return deep_read_open_access_paper(paper, user_query=user_query, progress_callback=None)


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def cached_translate_open_access_pdf(paper_json: str, target_language: str):
    paper = json.loads(paper_json) if paper_json else {}
    return translate_open_access_pdf(paper, target_language=target_language, progress_callback=None)



def trigger_auto_download(file_bytes: bytes, file_name: str, mime_type: str, element_key: str):
    if not file_bytes:
        return

    b64 = base64.b64encode(file_bytes).decode("ascii")
    safe_file_name = html.escape(str(file_name), quote=True)
    safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(element_key))
    html_block = f"""
        <a id="{safe_key}" href="data:{mime_type};base64,{b64}" download="{safe_file_name}"></a>
        <script>
        const el = document.getElementById("{safe_key}");
        if (el) el.click();
        </script>
    """

    html_renderer = getattr(st, "html", None)
    if callable(html_renderer):
        try:
            html_renderer(html_block)
            return
        except Exception:
            pass

    components.html(html_block, height=0)


def render_progress_state_widget(bar_placeholder, label_placeholder, state: dict, prefix_percent: bool = False):
    state = state or {}
    value = clamp_progress(state.get("value", 0))
    text = str(state.get("text", "") or "").strip()
    if text:
        bar_placeholder.progress(value)
        label_placeholder.caption(f"{value}% · {text}" if prefix_percent else text)
    else:
        bar_placeholder.empty()
        label_placeholder.empty()

def get_paper_state_key(paper: dict, index: int) -> str:
    doi = str(paper.get("doi", "") or "").strip().lower()
    if doi:
        return slugify(doi)
    title = str(paper.get("title", "") or "").strip()
    if title:
        return slugify(title)
    return f"paper-{index}"

def _serialize_task_payload(task: dict) -> str:
    try:
        return json.dumps(task, sort_keys=True, ensure_ascii=False)
    except Exception:
        return str(task)


def _task_matches(task_a: dict, task_b: dict) -> bool:
    if not isinstance(task_a, dict) or not isinstance(task_b, dict):
        return False
    return _serialize_task_payload(task_a) == _serialize_task_payload(task_b)


def enqueue_paper_task(task: dict):
    task = copy.deepcopy(task or {})
    if not task:
        return
    active = st.session_state.paper_active_task
    if isinstance(active, dict) and _task_matches(active, task):
        return
    for existing in st.session_state.paper_task_queue:
        if _task_matches(existing, task):
            return
    st.session_state.paper_task_queue.append(task)


def get_paper_task_status(task_type: str, paper_key: str, languages=None) -> str | None:
    active = st.session_state.paper_active_task
    if isinstance(active, dict) and active.get("task_type") == task_type and active.get("paper_key") == paper_key:
        if task_type == "translated_pdf":
            langs = active.get("languages") or []
            return f"running:{'|'.join(langs)}"
        return "running"

    for queued in st.session_state.paper_task_queue:
        if queued.get("task_type") == task_type and queued.get("paper_key") == paper_key:
            if task_type == "translated_pdf":
                langs = queued.get("languages") or []
                return f"queued:{'|'.join(langs)}"
            return "queued"
    return None


def pop_next_paper_task_for_key(paper_key: str):
    queue = st.session_state.paper_task_queue
    for idx, task in enumerate(queue):
        if task.get("paper_key") == paper_key:
            return queue.pop(idx)
    return None



def ensure_brief_highlights_for_result(result: dict):
    if not result:
        return
    if result.get("brief_highlights") is not None:
        return
    editor = result.get("editor", "")
    papers = result.get("papers", []) or []
    if not editor or not papers:
        result["brief_highlights"] = []
        return
    try:
        result["brief_highlights"] = build_brief_highlight_map(editor, papers)
    except Exception:
        result["brief_highlights"] = []


def render_deep_read_result(result: dict, paper_key: str):
    if not result:
        return

    paper_meta = result.get("paper", {}) or {}
    expander_title = f"Deep Reading Report — {paper_meta.get('title', 'Untitled')}"

    with st.expander(expander_title, expanded=False):
        st.markdown("<div class='deep-read-box'>", unsafe_allow_html=True)
        st.caption(
            f"mode={result.get('analysis_mode', 'unknown')} | page_count={result.get('page_count', 'N/A')} | "
            f"fallback_outline={result.get('fallback_outline_used', False)}"
        )

        academic_summary = result.get("academic_summary") or result.get("document_summary", "")
        if academic_summary:
            st.markdown("**Academic summary**")
            st.write(academic_summary)

        snapshot = result.get("study_snapshot", {}) or {}
        snapshot_rows = [
            ("Research question", snapshot.get("research_question", "")),
            ("Study design", snapshot.get("study_design", "")),
            ("Sample / material", snapshot.get("sample_or_material", "")),
            ("Core claim", snapshot.get("core_claim", "")),
        ]
        if any(v for _, v in snapshot_rows):
            st.markdown("**Study snapshot**")
            for label, value in snapshot_rows:
                if value:
                    st.write(f"**{label}:** {value}")

        if result.get("core_contribution"):
            st.markdown("**Core contribution**")
            st.write(result.get("core_contribution", ""))

        if result.get("theoretical_or_conceptual_frame"):
            st.markdown("**Theoretical or conceptual frame**")
            st.write(result.get("theoretical_or_conceptual_frame", ""))

        key_findings = result.get("key_findings", []) or []
        if key_findings:
            st.markdown("**Key findings**")
            for item in key_findings[:4]:
                st.write(f"- {item}")

        evidence_chain = result.get("evidence_chain", []) or []
        if evidence_chain:
            st.markdown("**Evidence chain**")
            for item in evidence_chain[:5]:
                st.write(f"- {item}")

        if result.get("relevance_to_query"):
            st.markdown("**Relevance to your query**")
            st.write(result.get("relevance_to_query", ""))

        high_value = result.get("high_value_paragraphs", []) or []
        if high_value:
            with st.expander("Best passages to check", expanded=False):
                for idx, item in enumerate(high_value[:6], start=1):
                    st.write(f"**{idx}. Page {item.get('page_number', 'N/A')}**")
                    if item.get("why_valuable"):
                        st.caption(item.get("why_valuable"))
                    st.write(item.get("paragraph", ""))
                    st.divider()

        section_takeaways = result.get("section_takeaways", []) or []
        if section_takeaways:
            with st.expander("Section takeaways", expanded=False):
                for item in section_takeaways[:6]:
                    st.write(f"**{item.get('heading', 'Section')}** (pp. {item.get('page_start', 'N/A')}-{item.get('page_end', 'N/A')})")
                    st.write(item.get("takeaway", ""))
                    st.divider()

        outline_used = result.get("outline_used", []) or result.get("outline_detected", []) or []
        if outline_used:
            with st.expander("Detected outline", expanded=False):
                for item in outline_used:
                    st.write(f"- {item.get('heading', 'Section')} (start page: {item.get('page_start', 'N/A')})")

        for title, key in [
            ("Methodological notes", "methodological_notes"),
            ("Practical implications", "practical_implications"),
            ("Limitations or cautions", "limitations_or_cautions"),
        ]:
            values = result.get(key, []) or []
            if values:
                with st.expander(title, expanded=False):
                    for item in values[:6]:
                        st.write(f"- {item}")

        report_pdf = build_deep_read_report_pdf_bytes(result, fallback_name=paper_meta.get("title", paper_key))
        st.download_button(
            label="Download deep reading report (PDF)",
            data=report_pdf,
            file_name=safe_filename(f"deep_read_{paper_meta.get('title', paper_key)}", suffix=".pdf"),
            mime="application/pdf",
            key=f"deep_read_report_{paper_key}",
        )
        st.markdown("</div>", unsafe_allow_html=True)


def render_brief_source_locator(result: dict):
    return

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
        "Balanced": "Balances research fit, final score, recency, and open-access availability.",
        "Newest first": "Prioritizes the most recently published papers, then uses research fit and overall score as tie-breakers.",
        "Research fit": "Prioritizes papers that best match the current research question.",
        "Relevance score": "Sorts by the system's overall relevance score.",
        "Evidence strength": "Prioritizes papers with stronger evidence support.",
        "Open access first": "Prioritizes papers with direct open-access availability, then considers quality.",
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
    body = details if details else "The system is processing the current workflow step."

    if agent == "RouterAgent" and action == "start":
        title = "The search workflow has started"
        body = "The system is coordinating multiple agents to handle query understanding, retrieval, screening, verification, and synthesis."
    elif agent == "RouterAgent" and action == "route":
        details_l = details.lower()

        if "next=query_planner_initial" in details_l:
            title = "The system is interpreting your query"
            body = "The next step is to decide the most likely research intent and plan the first retrieval pass."
        elif "next=retrieve" in details_l:
            title = "The system is starting literature retrieval"
            body = "The system is about to collect candidate papers from multiple academic sources and run the first screening pass."
        elif "next=query_planner_review" in details_l:
            title = "The system is reviewing the first retrieval pass"
            body = "The system is checking whether the first batch of results is focused enough or needs refinement."
        elif "next=retrieve_refinement" in details_l:
            title = "The system is running a stricter retrieval pass"
            body = "Because some results still look adjacent or off-target, the system is launching a tighter retrieval round."
        elif "next=researcher" in details_l:
            title = "The system is mapping what this literature covers"
            body = "The Researcher is extracting themes, recurring findings, and overall coverage."
        elif "next=theorist" in details_l:
            title = "The system is extracting conceptual framing"
            body = "The Theorist is identifying core concepts, distinctions, and tensions in the literature."
        elif "next=methodologist" in details_l:
            title = "The system is reading the evidence structure"
            body = "The Methodologist is checking study types, evidence patterns, and methodological gaps."
        elif "next=critic" in details_l:
            title = "The system is stress-testing the evidence"
            body = "The Critic is looking for scope problems, overclaim risks, and weak zones."
        elif "next=gap_analyst" in details_l:
            title = "The system is identifying research gaps"
            body = "The Gap Analyst is checking which important questions remain underexplored."
        elif "next=verifier" in details_l:
            title = "The system is verifying confidence"
            body = "The Verifier is separating strongly supported points from weaker or uncertain ones."
        elif "next=editor" in details_l:
            title = "The system is writing the final Research Brief"
            body = "The Editor is integrating the outputs from the other agents into the final synthesis."
        elif "next=finish" in details_l:
            title = "The workflow is complete"
            body = "This multi-agent run has finished."
        else:
            title = "The system is choosing the next step"
            body = details if details else "The router is deciding which agent should run next."

    elif agent == "QueryPlannerAgent" and action == "plan_initial":
        title = "The initial retrieval plan is ready"
        body = "The system finished the first planning pass and is ready to retrieve candidate papers."
    elif agent == "QueryPlannerAgent" and action == "plan_review":
        title = "The post-retrieval review is complete"
        body = "The system reviewed the first retrieval pass and decided whether another refinement step is needed."
    elif agent == "RetrievalAgent" and action == "retrieve":
        title = "A retrieval pass has finished"
        body = details if details else "Candidate papers were collected, deduplicated, and ranked."
    elif agent == "RetrievalAgent" and action == "retrieve_refined":
        title = "A refined retrieval pass has finished"
        body = details if details else "The refined search reduced adjacent and off-target results."
    elif action == "finish":
        title = "This workflow step is complete"
        body = details if details else "The system has finished this step."

    return title, body

def _humanize_debate_entry(item: dict):
    title = item.get("title", "Untitled")

    selector_decision = str(item.get("selector_decision", "")).strip().lower()
    critic_decision = str(item.get("critic_decision", "")).strip().lower()
    arbiter_decision = str(item.get("arbiter_decision", "")).strip().lower()

    def en_decision(d):
        mapping = {
            "keep": "Keep",
            "reject": "Reject",
            "uncertain": "Review",
        }
        return mapping.get(d, d or "Unknown")

    debate_level = str(item.get("debate_level", "")).strip().lower()
    if debate_level == "high":
        debate_severity = "High disagreement"
    elif debate_level == "medium":
        debate_severity = "Moderate disagreement"
    else:
        debate_severity = "Low disagreement"

    return {
        "title": title,
        "selector_decision": en_decision(selector_decision),
        "critic_decision": en_decision(critic_decision),
        "arbiter_decision": en_decision(arbiter_decision),
        "debate_severity": debate_severity,
        "confidence": float(item.get("confidence", 0.0) or 0.0),
        "selector_reason": item.get("selector_reason", "") or item.get("selector", "") or "No explanation available.",
        "critic_reason": item.get("critic_reason", "") or item.get("critic", "") or "No explanation available.",
        "arbiter_reason": item.get("arbiter_reason", "") or item.get("arbiter", "") or "No explanation available.",
    }

def render_live_agent_activity(container=None):
    return

def render_strategy_summary(result: dict):
    with st.container():
        st.markdown(
            "<div class='strategy-box-lite'>"
            "<div class='strategy-title'>🧭 Retrieval Strategy Summary</div>"
            "<div class='panel-subtitle'>This explains how the search was run, how papers were screened, and why some papers were kept while others were pushed down.</div>"
            "</div>",
            unsafe_allow_html=True
        )

        if not result:
            st.info("Run Search & Analysis to see the retrieval strategy summary here.")
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
            f"sources={sources_text}"
        )

    st.markdown(
        f"<div class='sort-note'>Current sort note: {get_sort_note(display_sort_mode)}</div>",
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
        paper_key = get_paper_state_key(p, i)
        paper_anchor = f"paper-resource-{paper_key}"
        paper_view_key = f"paper_view_mode_{paper_key}"

        if paper_view_key not in st.session_state:
            st.session_state[paper_view_key] = "Detailed"

        paper_view_mode = st.session_state.get(paper_view_key, "Detailed")
        deep_result = st.session_state.deep_read_results.get(paper_key)
        deep_error = st.session_state.deep_read_error_messages.get(paper_key, "")
        auto_notice = ""

        st.markdown(f"<div id='{paper_anchor}'></div>", unsafe_allow_html=True)
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

        translation_languages = [
            "Chinese (Simplified)",
            "Chinese (Traditional)",
            "English",
            "Japanese",
            "Korean",
            "Spanish",
            "French",
            "German",
            "Indonesian",
        ]
        selected_translation_languages = st.session_state.get(
            f"translation_langs_{paper_key}",
            ["Chinese (Simplified)"],
        ) or ["Chinese (Simplified)"]
        normalized_langs_preview = [str(x).strip() for x in selected_translation_languages if str(x).strip()]
        normalized_langs_preview = list(dict.fromkeys(normalized_langs_preview)) or ["Chinese (Simplified)"]

        deep_task_status = get_paper_task_status("deep_read", paper_key)
        translated_task_status = get_paper_task_status("translated_pdf", paper_key, normalized_langs_preview)
        any_task_busy_for_paper = bool(deep_task_status or translated_task_status)

        action_col1, action_col2, action_col3, action_col4 = st.columns([1.15, 1.15, 1.35, 1.9])
        with action_col1:
            deep_label = "Deep Read PDF Download"
            if deep_task_status == "queued":
                deep_label = "Deep Read Queued"
            elif deep_task_status == "running":
                deep_label = "Deep Read Running"
            deep_read_clicked = st.button(
                deep_label,
                key=f"deep_read_btn_{paper_key}",
                disabled=(not is_oa) or any_task_busy_for_paper,
                use_container_width=True,
            )
        with action_col2:
            original_download_clicked = st.button(
                "Download Original PDF",
                key=f"original_pdf_btn_{paper_key}",
                disabled=not is_oa,
                use_container_width=True,
            )
        with action_col3:
            translated_label = "Translated PDF Download"
            if translated_task_status and translated_task_status.startswith("queued"):
                translated_label = "Translation Queued"
            elif translated_task_status and translated_task_status.startswith("running"):
                translated_label = "Translation Running"
            translated_download_clicked = st.button(
                translated_label,
                key=f"translated_pdf_btn_{paper_key}",
                disabled=(not is_oa) or any_task_busy_for_paper,
                use_container_width=True,
            )
        with action_col4:
            selected_translation_languages = st.multiselect(
                "Translation languages",
                translation_languages,
                default=["Chinese (Simplified)"],
                key=f"translation_langs_{paper_key}",
                disabled=not is_oa,
            )

        if any_task_busy_for_paper:
            st.caption("Heavy tasks for this paper run serially. Wait for the current job to finish before starting the next one.")

        if is_oa:
            st.caption(
                "Deep Read PDF Download runs the academic deep-reading workflow with a visible progress bar and auto-downloads the deep reading report PDF. "
                "Download Original PDF pushes the source PDF to your device. "
                "Translated PDF Download translates the full paper. Pick one language to download a single translated PDF, or pick multiple languages to build them in parallel and download each translated PDF as a separate file."
            )
        else:
            st.caption("No open-access PDF was detected for this paper in the current metadata.")

        deep_progress_container = st.empty()
        deep_progress_label_container = st.empty()
        translated_progress_parent = st.container()

        deep_progress_state = st.session_state.deep_read_progress_state.get(paper_key, {"value": 0, "text": ""})
        if deep_progress_state.get("text"):
            deep_progress_container.progress(clamp_progress(deep_progress_state.get("value", 0)))
            deep_progress_label_container.caption(deep_progress_state.get("text", ""))

        selected_translation_languages = selected_translation_languages or ["Chinese (Simplified)"]
        normalized_langs = [str(x).strip() for x in selected_translation_languages if str(x).strip()]
        normalized_langs = list(dict.fromkeys(normalized_langs))
        translated_cache_key = f"{paper_key}::{'|'.join(normalized_langs)}"

        translated_progress_widgets = {}
        with translated_progress_parent:
            for lang in normalized_langs:
                st.caption(f"Translation worker — {lang}")
                translated_progress_widgets[lang] = {
                    "bar": st.empty(),
                    "label": st.empty(),
                }
                progress_state_key = f"{translated_cache_key}::{lang}"
                translated_progress_state = st.session_state.translated_pdf_progress_state.get(
                    progress_state_key,
                    {"value": 0, "text": ""},
                )
                if translated_progress_state.get("text"):
                    translated_progress_widgets[lang]["bar"].progress(
                        clamp_progress(translated_progress_state.get("value", 0))
                    )
                    translated_progress_widgets[lang]["label"].caption(
                        translated_progress_state.get("text", "")
                    )

        def _show_deep_task_progress(progress_value, progress_text):
            state = {"value": clamp_progress(progress_value), "text": str(progress_text)}
            st.session_state.deep_read_progress_state[paper_key] = state

        def _show_translated_task_progress(language, progress_value, progress_text):
            language = str(language or (normalized_langs[0] if normalized_langs else "Translation")).strip()
            progress_percent = clamp_progress(progress_value)
            state = {"value": progress_percent, "text": str(progress_text)}
            progress_state_key = f"{translated_cache_key}::{language}"
            st.session_state.translated_pdf_progress_state[progress_state_key] = state

        latest_deep_progress_state = st.session_state.deep_read_progress_state.get(
            paper_key,
            {"value": 0, "text": ""},
        )
        render_progress_state_widget(
            deep_progress_container,
            deep_progress_label_container,
            latest_deep_progress_state,
            prefix_percent=False,
        )

        for lang in normalized_langs:
            progress_state_key = f"{translated_cache_key}::{lang}"
            latest_translated_progress_state = st.session_state.translated_pdf_progress_state.get(
                progress_state_key,
                {"value": 0, "text": ""},
            )
            widgets = translated_progress_widgets.get(lang)
            if widgets:
                render_progress_state_widget(
                    widgets["bar"],
                    widgets["label"],
                    latest_translated_progress_state,
                    prefix_percent=True,
                )

        if deep_read_clicked:
            enqueue_paper_task({
                "task_type": "deep_read",
                "paper_key": paper_key,
                "paper": copy.deepcopy(p),
                "title": title,
                "user_query": result_like.get("original_query", "") or result_like.get("final_search_query", ""),
            })

        if translated_download_clicked:
            enqueue_paper_task({
                "task_type": "translated_pdf",
                "paper_key": paper_key,
                "paper": copy.deepcopy(p),
                "title": title,
                "languages": copy.deepcopy(normalized_langs),
                "cache_key": translated_cache_key,
            })

        next_task = None
        if st.session_state.paper_active_task is None:
            next_task = pop_next_paper_task_for_key(paper_key)
            if next_task:
                st.session_state.paper_active_task = copy.deepcopy(next_task)

        current_task = st.session_state.paper_active_task
        if isinstance(current_task, dict) and current_task.get("paper_key") == paper_key:
            try:
                if current_task.get("task_type") == "deep_read":
                    task_paper = current_task.get("paper", p)
                    task_title = current_task.get("title", title)
                    task_user_query = current_task.get("user_query", result_like.get("original_query", "") or result_like.get("final_search_query", ""))
                    if paper_key in st.session_state.deep_read_results:
                        payload = {"result": st.session_state.deep_read_results[paper_key]}
                        deep_progress_container.progress(100)
                        deep_progress_label_container.caption("Deep-reading report loaded from cache.")
                    else:
                        _show_deep_task_progress(0, "Starting academic deep reading...")
                        payload = deep_read_open_access_paper(
                            task_paper,
                            user_query=task_user_query,
                            progress_callback=_show_deep_task_progress,
                        )
                        st.session_state.deep_read_results[paper_key] = payload["result"]
                        _show_deep_task_progress(100, "Deep-reading report is ready and cached.")

                    st.session_state.deep_read_error_messages[paper_key] = ""
                    deep_result = payload["result"]
                    report_pdf = build_deep_read_report_pdf_bytes(payload["result"], fallback_name=task_title)
                    report_filename = safe_filename(f"deep_read_{task_title}", suffix=".pdf")
                    auto_notice = "Deep reading finished. Use the download button below to save the report PDF."

                elif current_task.get("task_type") == "translated_pdf":
                    task_paper = current_task.get("paper", p)
                    task_title = current_task.get("title", title)
                    task_langs = current_task.get("languages", normalized_langs) or ["Chinese (Simplified)"]
                    task_cache_key = current_task.get("cache_key", translated_cache_key)

                    if len(task_langs) == 1:
                        selected_translation_language = task_langs[0]
                        if task_cache_key in st.session_state.translated_pdf_results:
                            payload = st.session_state.translated_pdf_results[task_cache_key]
                            _show_translated_task_progress(
                                selected_translation_language,
                                100,
                                f"Translated PDF loaded from cache ({selected_translation_language})."
                            )
                        else:
                            _show_translated_task_progress(
                                selected_translation_language,
                                0,
                                f"Starting translated PDF generation in {selected_translation_language}..."
                            )
                            payload = translate_open_access_pdf(
                                task_paper,
                                target_language=selected_translation_language,
                                progress_callback=_show_translated_task_progress,
                            )
                            st.session_state.translated_pdf_results[task_cache_key] = payload
                            _show_translated_task_progress(
                                selected_translation_language,
                                100,
                                f"Translated PDF is ready and cached ({selected_translation_language})."
                            )

                        st.session_state.translated_pdf_error_messages[task_cache_key] = ""
                        auto_notice = (
                            f"Translated PDF is ready. Use the download button below "
                            f"({selected_translation_language})."
                        )
                    else:
                        if task_cache_key in st.session_state.translated_pdf_results:
                            payload = st.session_state.translated_pdf_results[task_cache_key]
                            for cached_lang in task_langs:
                                _show_translated_task_progress(
                                    cached_lang,
                                    100,
                                    f"Translated PDF loaded from cache ({cached_lang})."
                                )
                        else:
                            for lang in task_langs:
                                _show_translated_task_progress(
                                    lang,
                                    0,
                                    f"Queued translation worker for {lang}."
                                )
                            payload = translate_open_access_pdf_multi(
                                task_paper,
                                target_languages=task_langs,
                                progress_callback=_show_translated_task_progress,
                                result_callback=None,
                            )
                            st.session_state.translated_pdf_results[task_cache_key] = payload
                            for lang in task_langs:
                                _show_translated_task_progress(
                                    lang,
                                    100,
                                    f"Translated PDF is ready and cached ({lang})."
                                )

                        st.session_state.translated_pdf_error_messages[task_cache_key] = ""
                        auto_notice = (
                            "Translated PDFs are ready. Use the download buttons below "
                            f"({', '.join(task_langs)})."
                        )
            except Exception as e:
                message = str(e)
                if current_task.get("task_type") == "deep_read":
                    st.session_state.deep_read_error_messages[paper_key] = message
                    deep_error = message
                    _show_deep_task_progress(0, f"Deep reading failed: {message}")
                else:
                    task_cache_key = current_task.get("cache_key", translated_cache_key)
                    task_langs = current_task.get("languages", normalized_langs) or ["Chinese (Simplified)"]
                    st.session_state.translated_pdf_error_messages[task_cache_key] = message
                    st.error(f"Translated PDF generation failed: {message}")
                    for lang in task_langs:
                        _show_translated_task_progress(lang, 0, f"Translated PDF generation failed: {message}")
            finally:
                st.session_state.paper_active_task = None

        if original_download_clicked:
            try:
                with st.spinner("Resolving the OA PDF and preparing a stable Streamlit download..."):
                    payload = download_open_access_pdf(p)
                st.session_state.original_pdf_results[paper_key] = payload
                st.session_state.original_pdf_error_messages[paper_key] = ""
                auto_notice = "Original PDF is ready. Use the download button below."
            except Exception as e:
                message = str(e)
                st.session_state.original_pdf_error_messages[paper_key] = message
                st.error(f"Original PDF download failed: {message}")

        original_pdf_payload = st.session_state.original_pdf_results.get(paper_key)
        original_pdf_error = st.session_state.original_pdf_error_messages.get(paper_key, "")
        if original_pdf_payload:
            st.download_button(
                label="Save original PDF",
                data=original_pdf_payload["pdf_bytes"],
                file_name=original_pdf_payload.get("pdf_filename", safe_filename(title, suffix=".pdf")),
                mime="application/pdf",
                key=f"download_original_pdf_{paper_key}",
                use_container_width=True,
            )
        if original_pdf_error:
            st.caption(f"Original PDF error: {original_pdf_error}")

        deep_result = st.session_state.deep_read_results.get(paper_key)
        if deep_result:
            deep_report_pdf = build_deep_read_report_pdf_bytes(deep_result, fallback_name=title)
            st.download_button(
                label="Save deep reading report PDF",
                data=deep_report_pdf,
                file_name=safe_filename(f"deep_read_{title}", suffix=".pdf"),
                mime="application/pdf",
                key=f"download_deep_read_pdf_{paper_key}",
                use_container_width=True,
            )

        translated_payload = st.session_state.translated_pdf_results.get(translated_cache_key)
        if translated_payload:
            if isinstance(translated_payload, dict) and translated_payload.get("translated_pdf_bytes"):
                st.download_button(
                    label="Save translated PDF",
                    data=translated_payload["translated_pdf_bytes"],
                    file_name=translated_payload.get(
                        "translated_pdf_filename",
                        safe_filename(f"translated_{title}", suffix=".pdf")
                    ),
                    mime="application/pdf",
                    key=f"download_translated_pdf_{paper_key}_{slugify('|'.join(normalized_langs))}",
                    use_container_width=True,
                )
            elif isinstance(translated_payload, dict) and translated_payload.get("results"):
                st.markdown("**Translated PDF downloads**")
                for lang in normalized_langs:
                    lang_payload = (translated_payload.get("results") or {}).get(lang)
                    if not lang_payload:
                        continue
                    st.download_button(
                        label=f"Save translated PDF — {lang}",
                        data=lang_payload["translated_pdf_bytes"],
                        file_name=lang_payload.get(
                            "translated_pdf_filename",
                            safe_filename(f"translated_{title}_{lang}", suffix=".pdf")
                        ),
                        mime="application/pdf",
                        key=f"download_translated_pdf_{paper_key}_{slugify(lang)}",
                        use_container_width=True,
                    )

        translated_error = st.session_state.translated_pdf_error_messages.get(translated_cache_key, "")
        if translated_error:
            st.caption(f"Translated PDF error: {translated_error}")

        if auto_notice:
            st.caption(auto_notice)

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

        with st.expander("Paper view", expanded=False):
            current_view_index = 0 if st.session_state.get(paper_view_key, "Detailed") == "Compact" else 1
            selected_view = st.selectbox(
                f"Paper view mode {i}",
                ["Compact", "Detailed"],
                index=current_view_index,
                key=f"paper_view_select_{paper_key}",
                label_visibility="collapsed",
            )
            st.session_state[paper_view_key] = selected_view
            paper_view_mode = selected_view

        if paper_view_mode == "Compact":
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

        if deep_error:
            st.warning(f"Deep reading unavailable for this paper: {deep_error}")

        if deep_result:
            render_deep_read_result(deep_result, paper_key)

        st.divider()

def render_final_brief(result: dict):
    with st.container():
        st.markdown(
            "<div class='brief-box-lite'>"
            "<div class='brief-title'>📄 Research Brief</div>"
            "<div class='panel-subtitle'>The final Research Brief is shown first by default. Deeper multi-agent traces and retrieval strategy details are available below.</div>"
            "</div>",
            unsafe_allow_html=True
        )

        if not result:
            st.info("Run Search & Analysis to see the final Research Brief here.")
            return

        editor_error = result.get("editor_error", "")

        if result.get("editor"):
            brief_text = result.get("editor", "")
            ensure_brief_highlights_for_result(result)
            linked_brief_html = renderable_brief_html(brief_text, result.get("brief_highlights", []) or [])
            st.markdown(linked_brief_html, unsafe_allow_html=True)

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
            if editor_error:
                st.warning("Final Research Brief was not generated in this run.")
                st.caption(f"Editor error: {editor_error}")
            elif verifier:
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
            "<div class='left-sticky-note'>The structured multi-agent analytical trace is collapsed by default and can be expanded when you want to inspect the reasoning breakdown.</div>"
            "</div>",
            unsafe_allow_html=True
        )

        if not result:
            st.info("Run Search & Analysis to see the multi-agent analytical trace here.")
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
            "<div class='left-sticky-note'>The collaboration trace is collapsed by default and can be expanded when you want to inspect router decisions and refinement steps.</div>"
            "</div>",
            unsafe_allow_html=True
        )

        if not result:
            st.info("Run Search & Analysis to see the collaboration trace here.")
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

    payload_type = str(payload.get("type", "")).strip().lower()
    event_type = str(payload.get("event_type", "")).strip().lower()

    if payload_type in ["workflow", "workflow_trace"] or event_type in ["workflow", "workflow_trace"]:
        workflow_item = payload.get("entry") if isinstance(payload.get("entry"), dict) else {
            "agent": payload.get("agent", "System"),
            "action": payload.get("action", ""),
            "details": payload.get("details", ""),
        }
        _append_unique_limited(st.session_state.live_workflow_events, workflow_item, max_items=50)

    if payload_type in ["adversarial", "adversarial_trace"] or event_type in ["adversarial", "adversarial_trace"]:
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

def smart_progress_callback(stage_container=None, live_activity_container=None):
    def _callback(*args):
        progress = None
        stage = "Running..."
        payload = None

        if len(args) >= 1:
            progress = args[0]
        if len(args) >= 2:
            stage = str(args[1])
        if len(args) >= 3:
            payload = args[2]

        st.session_state.current_live_stage = stage
        st.session_state.current_live_agent_label = _guess_agent_label_from_stage(stage)

        is_progress_event = (
            isinstance(payload, dict)
            and str(payload.get("type", "")).strip().lower() == "progress"
        )

        if is_progress_event and progress is not None:
            new_progress = clamp_progress(progress)
            current_progress = int(st.session_state.get("current_live_progress", 0) or 0)
            st.session_state.current_live_progress = max(current_progress, new_progress)

        if payload is not None:
            _update_live_agent_state_from_payload(payload)

        if stage_container is not None:
            render_current_stage_inline(stage_container)
        if live_activity_container is not None:
            render_live_agent_activity(live_activity_container)

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

    target = container.container() if container is not None and hasattr(container, "container") else st.container()

    current_stage_lower = current_stage.strip().lower()
    is_complete = current_progress >= 100 and (
        "completed" in current_stage_lower or current_stage_lower == "done."
    )
    live_marker = '<span style="font-size: 0.95rem;">✓</span>' if is_complete else '<span class="live-dot"></span>'
    live_label = 'SEARCH COMPLETE' if is_complete else 'CURRENTLY RUNNING'

    with target:
        st.markdown(
            f"""
            <div class="live-running-box">
                <div class="live-running-title">
                    {live_marker}
                    <span class="live-blink">{live_label}</span>
                </div>
                <div class="live-running-text">{html.escape(current_agent_label)}: {html.escape(current_stage)}</div>
                <div style="margin-top: 0.85rem;">
                    <div style="width: 100%; height: 10px; background: rgba(37,99,235,0.10); border-radius: 999px; overflow: hidden;">
                        <div style="width: {current_progress}%; height: 100%; background: #2563eb; border-radius: 999px;"></div>
                    </div>
                    <div style="margin-top: 0.45rem; font-size: 0.88rem; color: #8b949e;">Progress: {current_progress}%</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if current_run_started_at:
            timer_id = f"running-time-{int(float(current_run_started_at) * 1000)}"
            start_ms = int(float(current_run_started_at) * 1000)
            components.html(
                f"""
                <div id="{timer_id}" style="font-size: 0.88rem; color: #8b949e; padding-top: 0.05rem;">
                    Running time: 0s
                </div>
                <script>
                    (function() {{
                        const el = document.getElementById("{timer_id}");
                        const startMs = {start_ms};

                        function formatDuration(totalSeconds) {{
                            const seconds = Math.max(0, Math.floor(totalSeconds));
                            const hours = Math.floor(seconds / 3600);
                            const minutes = Math.floor((seconds % 3600) / 60);
                            const secs = seconds % 60;

                            if (hours > 0) return `${{hours}}h ${{minutes}}m ${{secs}}s`;
                            if (minutes > 0) return `${{minutes}}m ${{secs}}s`;
                            return `${{secs}}s`;
                        }}

                        function tick() {{
                            if (!el) return;
                            const elapsedSeconds = (Date.now() - startMs) / 1000;
                            el.textContent = `Running time: ${{formatDuration(elapsedSeconds)}}`;
                        }}

                        tick();
                        const timer = setInterval(tick, 1000);
                        window.addEventListener("beforeunload", function() {{
                            clearInterval(timer);
                        }});
                    }})();
                </script>
                """,
                height=28,
            )
        elif last_run_duration_seconds is not None:
            st.caption(f"Last run time: {format_duration(last_run_duration_seconds)}")

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
    st.session_state.deep_read_results = {}
    st.session_state.original_pdf_results = {}
    st.session_state.original_pdf_error_messages = {}
    st.session_state.translated_pdf_results = {}
    st.session_state.deep_read_error_messages = {}


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
            help="Adjust the width ratio between the left analysis area and the right workspace."
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
            view_mode = st.session_state.display_view_mode

        source_filters = st.multiselect("Sources", options=DEFAULT_SOURCES, default=DEFAULT_SOURCES)
        use_year_range = st.checkbox("Use year range filter", value=False)
        if use_year_range:
            year_range = st.slider("Year range", min_value=DEFAULT_MIN_YEAR, max_value=DEFAULT_MAX_YEAR, value=(2018, DEFAULT_MAX_YEAR), step=1)
        else:
            year_range = None
            st.caption("Year range: Any time")

        if strict_core_only:
            st.caption("Strict mode: only core papers are prioritized; adjacent/background papers are only used when necessary.")
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
                        inherited_intent_profile = {}
                        if options and 0 <= recommended_index < len(options):
                            inherited_intent_profile = (options[recommended_index].get("intent_profile", {}) or {})
                        elif st.session_state.selected_option_payload:
                            inherited_intent_profile = (st.session_state.selected_option_payload.get("intent_profile", {}) or {})

                        st.session_state.selected_option_payload = {
                            "label": "Custom query",
                            "search_query": custom_query.strip(),
                            "reason": "User-entered custom search query.",
                            "confidence": 1.0,
                            "intent_profile": inherited_intent_profile
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

    live_activity_container = st.empty()
    render_live_agent_activity(live_activity_container)

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
        st.session_state.current_live_stage = "Preparing a new search run..."
        st.session_state.current_live_agent_label = "System"
        st.session_state.current_live_progress = 2
        _append_unique_limited(
            st.session_state.live_workflow_events,
            {"agent": "System", "action": "start", "details": "A new search run has started and the workflow is being initialized."},
            max_items=50,
        )
        render_current_stage_inline(stage_inline_container)
        render_live_agent_activity(live_activity_container)

        try:
            update_progress(5, "Understanding query intent...")
            render_current_stage_inline(stage_inline_container)
            render_live_agent_activity(live_activity_container)
            final_query, selected_option_payload, _ = get_effective_query_selection(query)

            if not final_query:
                st.warning("Could not prepare a search query.")
                st.stop()

            update_progress(15, "Preparing retrieval settings...")
            render_current_stage_inline(stage_inline_container)
            render_live_agent_activity(live_activity_container)
            update_progress(25, "Checking cache and starting pipeline...")
            render_current_stage_inline(stage_inline_container)
            render_live_agent_activity(live_activity_container)

            callback = smart_progress_callback(stage_inline_container, live_activity_container)

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
            render_live_agent_activity(live_activity_container)
            update_progress(100, "Search and analysis completed.")
            render_current_stage_inline(stage_inline_container)
            render_live_agent_activity(live_activity_container)

            st.session_state.current_live_stage = "Search and analysis completed."
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
            render_live_agent_activity(live_activity_container)

            st.success("✅ ATS pipeline finished.")
            st.rerun()

        except Exception as e:
            if st.session_state.current_run_started_at:
                st.session_state.last_run_duration_seconds = max(0, time.time() - float(st.session_state.current_run_started_at))
            st.session_state.current_run_started_at = None
            st.session_state.current_live_stage = f"Run failed: {str(e)}"
            st.session_state.current_live_agent_label = "System"
            st.session_state.current_live_progress = 0
            render_current_stage_inline(stage_inline_container)
            render_live_agent_activity(live_activity_container)
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

# ================= ui.py 代码到此全部结束 =================
