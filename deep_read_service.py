import html
import io
import json
import re
import zipfile
from collections import Counter
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin

import requests
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from llm_service import ask_llm

REQUEST_TIMEOUT = 45
STREAM_CHUNK_SIZE = 64 * 1024
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARS_FOR_SUMMARY = 24000
MAX_PAGE_CHARS_FOR_TRANSLATION = 3200

REFERENCE_HEADING_RE = re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*)?\s*(references|bibliography)\s*$")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "into",
    "is", "it", "its", "of", "on", "or", "that", "the", "their", "this", "to", "was", "were", "with",
    "we", "our", "can", "may", "using", "use", "used", "based", "study", "paper", "analysis", "results",
    "result", "method", "methods", "data", "approach", "research", "however", "than", "such", "these",
    "those", "also", "show", "shows", "shown", "within", "across", "between", "after", "before", "during",
    "more", "most", "less", "many", "much", "one", "two", "three", "four", "five", "new", "novel",
}
FIXED_NO_TRANSLATE_TERMS = [
    "GEQ", "PAE", "IPAQ-SV", "SD", "F", "p", "η²", "Beat Saber", "Thumper",
    "Northeastern University", "HTC Vive Pro", "Oculus Quest", "AVR", "SVR", "MVPA",
]
TRANSLATION_TERM_LOCKS = {
    "chinese (simplified)": {
        "narrative": "叙事",
        "sedentary": "久坐型",
        "motion sickness": "晕动症",
    },
    "chinese (traditional)": {
        "narrative": "敘事",
        "sedentary": "久坐型",
        "motion sickness": "暈動症",
    },
    "japanese": {
        "narrative": "ナラティブ",
        "sedentary": "座位型",
        "motion sickness": "動揺病",
    },
    "korean": {
        "narrative": "서사",
        "sedentary": "좌식형",
        "motion sickness": "멀미",
    },
}


def _safe_text(value: Any, fallback: str = "") -> str:
    return str(value).strip() if value is not None else fallback


def _safe_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _truncate(text: str, max_chars: int) -> str:
    text = _safe_text(text)
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return text[:80] or "item"



def safe_filename(text: str, suffix: str = ".pdf") -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "_", (text or "paper").strip())
    text = text.strip("._")[:80] or "paper"
    if not text.lower().endswith(suffix.lower()):
        text += suffix
    return text



def compact_whitespace(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()



def split_paragraphs(text: str) -> List[str]:
    text = compact_whitespace(text)
    if not text:
        return []
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]



def _emit_progress(progress_callback, value: int, message: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(int(value), str(message))
    except TypeError:
        try:
            progress_callback(int(value), str(message), {"type": "deep_read_progress"})
        except Exception:
            pass
    except Exception:
        pass



def _extract_json(text: str) -> Dict[str, Any]:
    text = _safe_text(text)
    if not text:
        raise ValueError("Empty response")
    candidates = [
        text,
        re.sub(r"^```json", "", text, flags=re.I).strip(),
        re.sub(r"^```|```$", "", text, flags=re.M).strip(),
    ]
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            pass
    start_obj = text.find("{")
    end_obj = text.rfind("}")
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        return json.loads(text[start_obj:end_obj + 1])
    raise ValueError("No JSON found")



def _ask_llm_with_fallback(prompt: str, *, provider: str = "openai", model: str = "gpt-5.4-mini", max_tokens: int = 1800) -> str:
    try:
        return ask_llm(prompt=prompt, provider=provider, model=model, max_tokens=max_tokens)
    except Exception:
        backup_provider = "claude" if provider == "openai" else "openai"
        backup_model = "claude-sonnet-4-6" if backup_provider == "claude" else "gpt-5.4-mini"
        return ask_llm(prompt=prompt, provider=backup_provider, model=backup_model, max_tokens=max_tokens)



def _register_cjk_fonts() -> None:
    for font_name in ["STSong-Light", "HeiseiMin-W3", "HYGoThic-Medium"]:
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(font_name))
        except Exception:
            pass



def _font_for_language(target_language: str) -> str:
    lang = (target_language or "").strip().lower()
    if "chinese" in lang:
        return "STSong-Light"
    if "japanese" in lang:
        return "HeiseiMin-W3"
    if "korean" in lang:
        return "HYGoThic-Medium"
    return "Helvetica"



def _localized_label(key: str, target_language: str) -> str:
    lang = (target_language or "").strip().lower()
    labels = {
        "page": {
            "chinese (simplified)": "第", "chinese (traditional)": "第", "japanese": "ページ", "korean": "페이지"
        },
        "translated_pdf": {
            "chinese (simplified)": "译文 PDF", "chinese (traditional)": "譯文 PDF", "japanese": "翻訳PDF", "korean": "번역 PDF"
        },
        "target_language": {
            "chinese (simplified)": "目标语言", "chinese (traditional)": "目標語言", "japanese": "対象言語", "korean": "대상 언어"
        },
        "layout_note": {
            "chinese (simplified)": "说明", "chinese (traditional)": "說明", "japanese": "注記", "korean": "안내"
        },
        "layout_note_body": {
            "chinese (simplified)": "为保证稳定性，译文采用纯文本分页排版。",
            "chinese (traditional)": "為保證穩定性，譯文採用純文字分頁排版。",
            "japanese": "安定性のため、翻訳版はプレーンテキスト中心のページ構成です。",
            "korean": "안정성을 위해 번역본은 순수 텍스트 중심의 페이지 구성으로 출력됩니다。",
        },
    }
    return labels.get(key, {}).get(lang, key.replace("_", " ").title())



def _translated_pdf_filename(title: str, target_language: str) -> str:
    return safe_filename(f"translated_{slugify(title)}_{slugify(target_language)}", suffix=".pdf")



def _zip_filename(title: str) -> str:
    return safe_filename(f"translated_{slugify(title)}", suffix=".zip")



def sniff_pdf_response(response: requests.Response) -> Tuple[bool, bytes]:
    content_type = (response.headers.get("Content-Type") or "").lower()
    first_chunk = b""
    try:
        first_chunk = next(response.iter_content(chunk_size=2048), b"")
    except Exception:
        first_chunk = b""
    return ("application/pdf" in content_type or first_chunk.startswith(b"%PDF"), first_chunk)



def extract_pdf_link_from_html(html_text: str, base_url: str) -> str:
    patterns = [
        re.compile(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']', re.I),
        re.compile(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', re.I),
    ]
    for pattern in patterns:
        match = pattern.search(html_text or "")
        if match:
            return urljoin(base_url, match.group(1))
    return ""



def resolve_pdf_bytes_from_candidates(candidate_urls: List[str]) -> Tuple[bytes, str, Dict[str, Any]]:
    session = requests.Session()
    tried: List[str] = []
    queue = [_safe_text(u) for u in candidate_urls if _safe_text(u)]

    while queue:
        url = queue.pop(0)
        if url in tried:
            continue
        tried.append(url)
        response = session.get(url, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True, headers={"User-Agent": "AcademicATS/1.0"})
        if response.status_code >= 400:
            continue

        is_pdf, first_chunk = sniff_pdf_response(response)
        final_url = str(response.url or url)
        if is_pdf:
            buffer = io.BytesIO()
            total = len(first_chunk)
            if first_chunk:
                buffer.write(first_chunk)
            for chunk in response.iter_content(chunk_size=STREAM_CHUNK_SIZE):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    raise ValueError("PDF is too large for in-memory processing.")
                buffer.write(chunk)
            return buffer.getvalue(), final_url, {
                "content_type": response.headers.get("Content-Type", ""),
                "content_length": response.headers.get("Content-Length", ""),
            }

        try:
            html_prefix = first_chunk + response.raw.read(20000, decode_content=True)
            html_text = html_prefix.decode("utf-8", errors="ignore")
        except Exception:
            html_text = ""

        nested = extract_pdf_link_from_html(html_text, final_url)
        if nested and nested not in tried:
            queue.append(nested)

    raise ValueError("Could not resolve a direct PDF stream from the available OA links.")



def extract_page_texts_from_pdf_bytes(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            pass

    pages: List[Dict[str, Any]] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append({"page_number": idx, "text": compact_whitespace(text)})
    return pages



def detect_outline(page_texts: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    outline: List[Dict[str, Any]] = []
    seen = set()
    heading_re = re.compile(r"^(abstract|introduction|background|methods?|results?|discussion|conclusion|limitations|future work)\b", re.I)
    for page in page_texts:
        for raw_line in (page.get("text", "") or "").splitlines()[:25]:
            line = compact_whitespace(raw_line)
            if len(line) < 4 or len(line) > 90:
                continue
            if not heading_re.match(line):
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            outline.append({"heading": line, "page_start": page["page_number"]})
    if outline:
        return outline[:12], False
    return ([
        {"heading": "Abstract / Overview", "page_start": 1},
        {"heading": "Introduction / Problem Framing", "page_start": 1},
        {"heading": "Methods / Approach", "page_start": max(1, len(page_texts) // 3)},
        {"heading": "Results / Findings", "page_start": max(1, len(page_texts) // 2)},
        {"heading": "Discussion / Interpretation", "page_start": max(1, (len(page_texts) * 2) // 3)},
        {"heading": "Conclusion / Implications", "page_start": max(1, len(page_texts) - 1)},
    ], True)



def build_section_map(page_texts: List[Dict[str, Any]], outline: List[Dict[str, Any]], fallback_outline_used: bool) -> List[Dict[str, Any]]:
    if not page_texts:
        return []
    items = sorted([o for o in outline if o.get("page_start")], key=lambda x: int(x["page_start"]))
    if not items:
        items = [{"heading": "Full Paper", "page_start": 1}]

    sections: List[Dict[str, Any]] = []
    last_page = page_texts[-1]["page_number"]
    for idx, item in enumerate(items):
        start_page = int(item["page_start"])
        end_page = int(items[idx + 1]["page_start"]) - 1 if idx + 1 < len(items) else last_page
        pages = [p for p in page_texts if start_page <= p["page_number"] <= end_page]
        if not pages:
            continue
        sections.append({
            "heading": item["heading"],
            "page_start": pages[0]["page_number"],
            "page_end": pages[-1]["page_number"],
            "text": "\n\n".join(p["text"] for p in pages if p.get("text")),
        })
    return sections



def score_paragraph(paragraph: str, page_number: int) -> float:
    text = paragraph.lower()
    score = 0.0
    length = len(paragraph)
    if 180 <= length <= 1200:
        score += 10
    if any(term in text for term in ["we find", "results", "conclusion", "suggest", "evidence", "significant", "limitation"]):
        score += 4
    if any(term in text for term in ["references", "doi", "copyright", "appendix"]):
        score -= 4
    if page_number <= 2:
        score += 1
    return score



def build_high_value_paragraphs(page_texts: List[Dict[str, Any]], max_items: int = 8) -> List[Dict[str, Any]]:
    items = []
    for page in page_texts:
        for para in split_paragraphs(page.get("text", "")):
            if len(para) < 80:
                continue
            items.append({
                "page_number": page["page_number"],
                "text": para,
                "score": score_paragraph(para, page["page_number"]),
            })
    items.sort(key=lambda x: (x["score"], len(x["text"])), reverse=True)
    output = []
    seen = set()
    for item in items:
        key = re.sub(r"\W+", " ", item["text"].lower())[:120]
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "page_number": item["page_number"],
            "why_valuable": "Likely contains a key claim, result, or summary passage.",
            "paragraph": _truncate(item["text"], 900),
        })
        if len(output) >= max_items:
            break
    return output



def summarize_sections_heuristically(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output = []
    for section in sections[:8]:
        paras = split_paragraphs(section.get("text", ""))
        summary = _truncate((paras[0] if paras else section.get("text", "")), 480)
        output.append({
            "heading": section.get("heading", "Section"),
            "page_start": section.get("page_start"),
            "page_end": section.get("page_end"),
            "summary": summary,
        })
    return output



def extract_keywords_from_text(text: str, max_keywords: int = 10) -> List[Dict[str, Any]]:
    tokens = re.findall(r"[A-Za-z][A-Za-z-]{2,}", (text or "").lower())
    filtered = [t for t in tokens if t not in STOPWORDS and len(t) >= 4]
    counts = Counter(filtered)
    return [{"keyword": w, "count": int(c)} for w, c in counts.most_common(max_keywords) if c >= 2][:max_keywords]



def _deep_read_prompt(paper: Dict[str, Any], user_query: str, page_texts: List[Dict[str, Any]], section_takeaways: List[Dict[str, Any]], high_value_paragraphs: List[Dict[str, Any]]) -> str:
    page_block = "\n\n".join(
        f"[Page {p['page_number']}]\n{_truncate(p['text'], 2200)}"
        for p in page_texts[:8]
        if p.get("text")
    )
    section_block = json.dumps(section_takeaways[:6], ensure_ascii=False)
    paragraph_block = json.dumps(high_value_paragraphs[:6], ensure_ascii=False)
    return f"""
You are reading one academic paper and producing a compact, evidence-aware deep reading report.

User query:
{user_query}

Paper metadata:
Title: {paper.get('title', '')}
Authors: {paper.get('authors', '')}
Year: {paper.get('year', '')}
Source: {paper.get('source', '')}

Section takeaways:
{section_block}

High-value paragraphs:
{paragraph_block}

Extracted paper text:
{page_block[:MAX_TEXT_CHARS_FOR_SUMMARY]}

Return JSON only in this format:
{{
  "academic_summary": "1-2 readable paragraphs",
  "study_snapshot": {{
    "research_question": "1 sentence",
    "study_design": "1 sentence",
    "sample_or_material": "1 sentence",
    "core_claim": "1 sentence"
  }},
  "core_contribution": "1-3 sentences",
  "theoretical_or_conceptual_frame": "1-3 sentences",
  "key_findings": ["...", "...", "..."],
  "evidence_chain": ["claim/result + page", "claim/result + page"],
  "relevance_to_query": "1-3 sentences",
  "methodological_notes": ["...", "..."],
  "practical_implications": ["...", "..."],
  "limitations_or_cautions": ["...", "..."]
}}

Rules:
- Use only the supplied paper text.
- Keep claims conservative.
- Mention page numbers when clear.
- Return valid JSON only.
"""



def _heuristic_deep_read_result(paper: Dict[str, Any], user_query: str, page_texts: List[Dict[str, Any]], outline: List[Dict[str, Any]], sections: List[Dict[str, Any]], high_value_paragraphs: List[Dict[str, Any]]) -> Dict[str, Any]:
    section_takeaways = [
        {
            "heading": item["heading"],
            "page_start": item["page_start"],
            "page_end": item["page_end"],
            "takeaway": item["summary"],
        }
        for item in summarize_sections_heuristically(sections)
    ]
    keywords = extract_keywords_from_text("\n\n".join(p.get("text", "") for p in page_texts), max_keywords=10)
    keyword_entries = []
    for item in keywords:
        pages = []
        kw = item["keyword"]
        for page in page_texts:
            if kw in (page.get("text", "").lower()):
                pages.append(page["page_number"])
        keyword_entries.append({"keyword": kw, "reason": "Frequently recurring term in the extracted text.", "pages": pages[:5]})

    summary = " ".join(x["takeaway"] for x in section_takeaways[:3]).strip() or "Compact summary unavailable."
    return {
        "academic_summary": summary,
        "study_snapshot": {
            "research_question": "See abstract/introduction passages in the extracted text.",
            "study_design": "Verify exact design details in the original PDF if this paper is central.",
            "sample_or_material": section_takeaways[1]["takeaway"] if len(section_takeaways) > 1 else "See extracted sections.",
            "core_claim": section_takeaways[0]["takeaway"] if section_takeaways else "See highlighted passages.",
        },
        "core_contribution": "This compact report highlights the paper's likely contribution using extracted text and key passages.",
        "theoretical_or_conceptual_frame": "Use the highlighted sections to verify the paper's theoretical framing.",
        "key_findings": [_truncate(x["takeaway"], 160) for x in section_takeaways[:4]],
        "evidence_chain": [f"See page {x['page_number']} highlighted passage." for x in high_value_paragraphs[:4]],
        "relevance_to_query": "This paper appears relevant to the current query based on the extracted text and retained passages.",
        "document_summary": summary,
        "outline_used": outline,
        "section_takeaways": section_takeaways,
        "keywords": keyword_entries,
        "high_value_paragraphs": high_value_paragraphs[:8],
        "methodological_notes": ["Compact mode was used for deep reading.", "Check the source PDF for fine-grained method details."],
        "practical_implications": ["Useful for quick paper triage and evidence review."],
        "limitations_or_cautions": ["Automatic PDF extraction may miss layout-heavy content like tables or two-column ordering."],
    }



def deep_read_open_access_paper(paper: Dict[str, Any], user_query: str = "", progress_callback=None) -> Dict[str, Any]:
    _emit_progress(progress_callback, 8, "Resolving the open-access PDF...")
    candidate_urls = [paper.get("pdf_url", ""), paper.get("oa_url", ""), paper.get("url", "")]
    pdf_bytes, resolved_pdf_url, response_meta = resolve_pdf_bytes_from_candidates(candidate_urls)

    _emit_progress(progress_callback, 28, "Extracting PDF text...")
    page_texts = extract_page_texts_from_pdf_bytes(pdf_bytes)
    if not any(_safe_text(x.get("text")) for x in page_texts):
        raise ValueError("PDF text extraction succeeded, but no readable text was found.")

    _emit_progress(progress_callback, 45, "Building compact paper structure...")
    outline, fallback_outline_used = detect_outline(page_texts)
    sections = build_section_map(page_texts, outline, fallback_outline_used)
    high_value_paragraphs = build_high_value_paragraphs(page_texts, max_items=8)
    section_takeaways = [
        {
            "heading": item["heading"],
            "page_start": item["page_start"],
            "page_end": item["page_end"],
            "takeaway": item["summary"],
        }
        for item in summarize_sections_heuristically(sections)
    ]

    _emit_progress(progress_callback, 62, "Generating compact deep-reading summary...")
    result_body = _heuristic_deep_read_result(paper, user_query, page_texts, outline, sections, high_value_paragraphs)
    try:
        prompt = _deep_read_prompt(paper, user_query, page_texts, section_takeaways, high_value_paragraphs)
        parsed = _extract_json(_ask_llm_with_fallback(prompt, provider="openai", model="gpt-5.4-mini", max_tokens=1800))
        result_body.update({
            "academic_summary": _safe_text(parsed.get("academic_summary")) or result_body["academic_summary"],
            "study_snapshot": parsed.get("study_snapshot") if isinstance(parsed.get("study_snapshot"), dict) else result_body["study_snapshot"],
            "core_contribution": _safe_text(parsed.get("core_contribution")) or result_body["core_contribution"],
            "theoretical_or_conceptual_frame": _safe_text(parsed.get("theoretical_or_conceptual_frame")) or result_body["theoretical_or_conceptual_frame"],
            "key_findings": _safe_list(parsed.get("key_findings"))[:6] or result_body["key_findings"],
            "evidence_chain": _safe_list(parsed.get("evidence_chain"))[:5] or result_body["evidence_chain"],
            "relevance_to_query": _safe_text(parsed.get("relevance_to_query")) or result_body["relevance_to_query"],
            "methodological_notes": _safe_list(parsed.get("methodological_notes"))[:6] or result_body["methodological_notes"],
            "practical_implications": _safe_list(parsed.get("practical_implications"))[:6] or result_body["practical_implications"],
            "limitations_or_cautions": _safe_list(parsed.get("limitations_or_cautions"))[:6] or result_body["limitations_or_cautions"],
        })
        analysis_mode = "compact_llm"
    except Exception:
        analysis_mode = "compact_heuristic"

    _emit_progress(progress_callback, 100, "Deep-reading report is ready.")
    result = {
        "paper": {
            "title": paper.get("title", "Untitled"),
            "authors": paper.get("authors", ""),
            "year": paper.get("year", ""),
            "source": paper.get("source", ""),
            "resolved_pdf_url": resolved_pdf_url,
        },
        "analysis_mode": analysis_mode,
        "fallback_outline_used": bool(fallback_outline_used),
        "page_count": len(page_texts),
        "outline_detected": outline,
        "outline_used": outline,
        "section_count": len(sections),
        "page_text_excerpt": _truncate("\n\n".join(p.get("text", "") for p in page_texts[:2]), 2000),
        "response_meta": response_meta,
        **result_body,
    }
    return {
        "result": result,
        "pdf_bytes": pdf_bytes,
        "pdf_filename": safe_filename(paper.get("title", "paper"), suffix=".pdf"),
    }



def _protect_non_translate_spans(text: str) -> Tuple[str, Dict[str, str]]:
    protected: Dict[str, str] = {}
    counter = 0

    def reserve(raw: str) -> str:
        nonlocal counter
        key = f"⟪NT{counter}⟫"
        counter += 1
        protected[key] = raw
        return key

    output = text
    for term in sorted(FIXED_NO_TRANSLATE_TERMS, key=len, reverse=True):
        output = re.sub(re.escape(term), lambda m: reserve(m.group(0)), output)
    return output, protected



def _restore_non_translate_spans(text: str, protected: Dict[str, str]) -> str:
    restored = text
    for key, raw in protected.items():
        restored = restored.replace(key, raw)
    return restored



def _translation_term_lock_text(target_language: str) -> str:
    mapping = TRANSLATION_TERM_LOCKS.get((target_language or "").strip().lower(), {})
    if not mapping:
        return ""
    return "\n".join(f"- {src} -> {dst}" for src, dst in mapping.items())



def _split_references_section(text: str) -> Tuple[str, str]:
    if not text:
        return "", ""
    match = REFERENCE_HEADING_RE.search(text)
    if not match:
        return text, ""
    return text[:match.start()].rstrip(), text[match.start():].lstrip()



def _translate_short_text(text: str, target_language: str) -> str:
    text = _safe_text(text)
    if not text:
        return ""
    prompt = f"Translate this title into {target_language}. Return only the translation.\n\n{text}"
    try:
        return _safe_text(_ask_llm_with_fallback(prompt, provider="openai", model="gpt-5.4-mini", max_tokens=200)) or text
    except Exception:
        return text



def _translate_text_chunk(chunk_text: str, target_language: str) -> str:
    protected_source, protected_map = _protect_non_translate_spans(chunk_text)
    source_body, reference_body = _split_references_section(protected_source)
    term_lock_text = _translation_term_lock_text(target_language)
    prompt = f"""
You are a professional academic translator.

Translate the source text into {target_language}.

Rules:
- Preserve paragraph order.
- Preserve citations, numbers, formulas, symbols, and punctuation carefully.
- Do not summarize.
- Do not add notes.
- Return translated text only.
- Keep all placeholder tokens such as ⟪NT0⟫ unchanged.
- Do not translate the references section.
{term_lock_text}

Source text:
{source_body}
"""
    translated = _safe_text(_ask_llm_with_fallback(prompt, provider="openai", model="gpt-5.4-mini", max_tokens=2200))
    translated = _restore_non_translate_spans(translated, protected_map)
    if reference_body:
        translated = f"{translated}\n\n{_restore_non_translate_spans(reference_body, protected_map)}".strip()
    return translated or _restore_non_translate_spans(chunk_text, protected_map)



def build_translated_pdf_bytes(
    paper: Dict[str, Any],
    translated_pages: List[Dict[str, Any]],
    target_language: str,
    translated_title: str | None = None,
    progress_callback=None,
    progress_range: Tuple[int, int] | None = None,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{_localized_label('translated_pdf', target_language)} — {translated_title or paper.get('title', 'Untitled')}",
    )

    _register_cjk_fonts()
    body_font = _font_for_language(target_language)
    bold_font = body_font if body_font != "Helvetica" else "Helvetica-Bold"
    start_progress, end_progress = progress_range or (0, 0)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TranslatedTitle", parent=styles["Title"], fontName=bold_font, fontSize=16, leading=20, spaceAfter=8, wordWrap="CJK" if body_font != "Helvetica" else None)
    meta_style = ParagraphStyle("TranslatedMeta", parent=styles["BodyText"], fontName=body_font, fontSize=9.5, leading=12, spaceAfter=4, wordWrap="CJK" if body_font != "Helvetica" else None)
    page_style = ParagraphStyle("TranslatedPageHeader", parent=styles["Heading2"], fontName=bold_font, fontSize=11.5, leading=14, spaceBefore=4, spaceAfter=6, wordWrap="CJK" if body_font != "Helvetica" else None)
    body_style = ParagraphStyle("TranslatedBody", parent=styles["BodyText"], fontName=body_font, fontSize=9.8, leading=13.2, spaceAfter=5, wordWrap="CJK" if body_font != "Helvetica" else None)

    display_title = translated_title or paper.get("title", "Untitled")
    story = [
        Paragraph(f"{html.escape(_localized_label('translated_pdf', target_language))} — {html.escape(str(display_title))}", title_style),
        Paragraph(f"{html.escape(_localized_label('target_language', target_language))}: {html.escape(target_language)}", meta_style),
        Paragraph(html.escape(_localized_label('layout_note', target_language)) + ": " + html.escape(_localized_label('layout_note_body', target_language)), meta_style),
        Spacer(1, 4),
    ]

    total_pages = max(1, len(translated_pages))
    for idx, page in enumerate(translated_pages, start=1):
        if progress_callback and end_progress > start_progress:
            progress_value = start_progress + int((idx / total_pages) * (end_progress - start_progress))
            _emit_progress(progress_callback, progress_value, f"Building translated PDF: page {idx}/{total_pages} prepared.")
        if idx > 1:
            story.append(PageBreak())
        story.append(Paragraph(f"{_localized_label('page', target_language)} {page.get('page_number', idx)}", page_style))
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", _safe_text(page.get("translated_text"))) if p.strip()]
        if not paragraphs:
            paragraphs = [_safe_text(page.get("translated_text"), "[No translatable text extracted from this page]")]
        for para in paragraphs:
            story.append(Paragraph(html.escape(para).replace("\n", "<br/>"), body_style))

    doc.build(story)
    return buffer.getvalue()



def _translate_single_language_from_pdf_bytes(
    paper: Dict[str, Any],
    pdf_bytes: bytes,
    resolved_pdf_url: str,
    response_meta: Dict[str, Any],
    target_language: str,
    progress_callback=None,
) -> Dict[str, Any]:
    _emit_progress(progress_callback, 12, f"Extracting source PDF for {target_language}...")
    page_texts = extract_page_texts_from_pdf_bytes(pdf_bytes)
    if not any(_safe_text(x.get("text")) for x in page_texts):
        raise ValueError("PDF text extraction succeeded, but no readable text was found for translation.")

    translated_pages: List[Dict[str, Any]] = []
    total_pages = max(1, len(page_texts))
    _emit_progress(progress_callback, 28, f"Translating pages into {target_language}...")
    for idx, page in enumerate(page_texts, start=1):
        source_text = _safe_text(page.get("text"))
        if source_text:
            translated_text = _translate_text_chunk(_truncate(source_text, MAX_PAGE_CHARS_FOR_TRANSLATION), target_language)
        else:
            translated_text = ""
        translated_pages.append({"page_number": page.get("page_number", idx), "translated_text": translated_text})
        _emit_progress(progress_callback, 28 + int((idx / total_pages) * 52), f"Translated page {idx}/{total_pages} ({target_language}).")

    translated_title = _translate_short_text(paper.get("title", "Untitled"), target_language)
    _emit_progress(progress_callback, 84, f"Building translated PDF ({target_language})...")
    translated_pdf_bytes = build_translated_pdf_bytes(
        paper=paper,
        translated_pages=translated_pages,
        target_language=target_language,
        translated_title=translated_title,
        progress_callback=progress_callback,
        progress_range=(84, 98),
    )
    _emit_progress(progress_callback, 100, f"Translated PDF is ready ({target_language}).")
    return {
        "translated_pdf_bytes": translated_pdf_bytes,
        "translated_pdf_filename": _translated_pdf_filename(translated_title or paper.get("title", "paper"), target_language),
        "resolved_pdf_url": resolved_pdf_url,
        "response_meta": response_meta,
        "page_count": len(page_texts),
        "target_language": target_language,
        "translated_title": translated_title,
    }



def _emit_language_progress(progress_callback, language: str, value: int | float, message: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(language, value, message)
    except TypeError:
        try:
            progress_callback(value, f"[{language}] {message}")
        except TypeError:
            pass



def translate_open_access_pdf(paper: Dict[str, Any], target_language: str, progress_callback=None) -> Dict[str, Any]:
    _emit_progress(progress_callback, 5, f"Resolving the open-access PDF ({target_language})...")
    candidate_urls = [paper.get("pdf_url", ""), paper.get("oa_url", ""), paper.get("url", "")]
    pdf_bytes, resolved_pdf_url, response_meta = resolve_pdf_bytes_from_candidates(candidate_urls)
    return _translate_single_language_from_pdf_bytes(paper, pdf_bytes, resolved_pdf_url, response_meta, target_language, progress_callback)



def translate_open_access_pdf_multi(
    paper: Dict[str, Any],
    target_languages: List[str],
    progress_callback=None,
    result_callback=None,
) -> Dict[str, Any]:
    langs = [str(x).strip() for x in (target_languages or []) if str(x).strip()]
    if not langs:
        raise ValueError("No target languages were provided.")

    candidate_urls = [paper.get("pdf_url", ""), paper.get("oa_url", ""), paper.get("url", "")]
    pdf_bytes, resolved_pdf_url, response_meta = resolve_pdf_bytes_from_candidates(candidate_urls)

    results: Dict[str, Dict[str, Any]] = {}
    for idx, lang in enumerate(langs, start=1):
        _emit_language_progress(progress_callback, lang, 0, f"Starting translation for {lang}...")
        payload = _translate_single_language_from_pdf_bytes(
            paper,
            pdf_bytes,
            resolved_pdf_url,
            response_meta,
            lang,
            lambda value, message, worker_lang=lang: _emit_language_progress(progress_callback, worker_lang, value, message),
        )
        results[lang] = payload
        if result_callback:
            try:
                result_callback(lang, payload)
            except Exception:
                pass
        _emit_language_progress(progress_callback, lang, 100, f"Finished {lang} ({idx}/{len(langs)} completed).")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for lang in langs:
            zf.writestr(results[lang]["translated_pdf_filename"], results[lang]["translated_pdf_bytes"])

    return {
        "translated_zip_bytes": zip_buffer.getvalue(),
        "translated_zip_filename": _zip_filename(paper.get("title", "paper")),
        "results": results,
        "target_languages": langs,
    }



def download_open_access_pdf(paper: Dict[str, Any]) -> Dict[str, Any]:
    candidate_urls = [paper.get("pdf_url", ""), paper.get("oa_url", ""), paper.get("url", "")]
    pdf_bytes, resolved_pdf_url, response_meta = resolve_pdf_bytes_from_candidates(candidate_urls)
    return {
        "pdf_bytes": pdf_bytes,
        "pdf_filename": safe_filename(paper.get("title", "paper"), suffix=".pdf"),
        "resolved_pdf_url": resolved_pdf_url,
        "response_meta": response_meta,
    }



def build_deep_read_report_markdown(result: Dict[str, Any]) -> str:
    paper = result.get("paper", {}) or {}
    lines = [
        f"# Deep Reading Report — {paper.get('title', 'Untitled')}",
        "",
        f"- Authors: {paper.get('authors', '')}",
        f"- Year: {paper.get('year', '')}",
        f"- Source: {paper.get('source', '')}",
        f"- Page count: {result.get('page_count', '')}",
        f"- Analysis mode: {result.get('analysis_mode', '')}",
        "",
        "## Academic Summary",
        "",
        _safe_text(result.get("academic_summary") or result.get("document_summary"), "No summary available."),
        "",
    ]
    for title, key in [
        ("Core Contribution", "core_contribution"),
        ("Theoretical or Conceptual Frame", "theoretical_or_conceptual_frame"),
    ]:
        if result.get(key):
            lines.extend([f"## {title}", "", _safe_text(result.get(key)), ""])

    for title, key in [
        ("Key Findings", "key_findings"),
        ("Evidence Chain", "evidence_chain"),
        ("Methodological Notes", "methodological_notes"),
        ("Practical Implications", "practical_implications"),
        ("Limitations or Cautions", "limitations_or_cautions"),
    ]:
        values = result.get(key, []) or []
        if values:
            lines.extend([f"## {title}", ""])
            for item in values:
                lines.append(f"- {item}")
            lines.append("")

    takeaways = result.get("section_takeaways", []) or []
    if takeaways:
        lines.extend(["## Section Takeaways", ""])
        for item in takeaways:
            lines.append(f"### {item.get('heading', 'Section')} (pp. {item.get('page_start', 'N/A')}-{item.get('page_end', 'N/A')})")
            lines.append(_safe_text(item.get("takeaway")))
            lines.append("")

    return "\n".join(lines).strip()



def _citation_label_for_paper(paper: Dict[str, Any]) -> str:
    authors = _safe_text(paper.get("authors"))
    year = _safe_text(paper.get("year"), "Unknown year")
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



def build_brief_citation_map(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output = []
    for idx, paper in enumerate(papers or [], start=1):
        label = _citation_label_for_paper(paper)
        output.append({"label": label, "anchor_id": f"paper-resource-{slugify(label)}-{idx}", "index": idx})
    return output



def build_brief_highlight_map(brief_text: str, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    brief_lower = (brief_text or "").lower()
    output = []
    seen = set()
    for idx, paper in enumerate(papers or [], start=1):
        title = _safe_text(paper.get("title"))
        tokens = [t for t in re.findall(r"[A-Za-z][A-Za-z-]{2,}", title) if t.lower() not in STOPWORDS]
        phrases = []
        if len(tokens) >= 2:
            phrases.extend(" ".join(tokens[i:i + 2]) for i in range(0, min(len(tokens) - 1, 4)))
            phrases.extend(" ".join(tokens[i:i + 3]) for i in range(0, min(len(tokens) - 2, 2)))
        for phrase in phrases:
            phrase_l = phrase.lower()
            if phrase_l in seen or phrase_l not in brief_lower:
                continue
            seen.add(phrase_l)
            output.append({
                "phrase": phrase,
                "why_it_matters": "Phrase overlaps with the paper metadata and the final research brief.",
                "paper_indexes": [idx],
                "anchor_id": f"brief-source-{slugify(phrase)}",
            })
            if len(output) >= 6:
                return output
    return output



def _replace_citations_with_anchors(text: str, citation_map: List[Dict[str, Any]]) -> str:
    rendered = html.escape(text)
    for item in sorted(citation_map or [], key=lambda x: len(x.get("label", "")), reverse=True):
        label = item.get("label", "")
        anchor_id = item.get("anchor_id", "")
        if not label or not anchor_id:
            continue
        for patt in [re.escape(f"({label})"), re.escape(label)]:
            regex = re.compile(patt)
            if regex.search(rendered):
                rendered = regex.sub(lambda m: f"<a class='brief-highlight-link' href='#{anchor_id}' title='点击跳转'>{m.group(0)}</a>", rendered, count=1)
                break
    return rendered



def renderable_brief_html(brief_text: str, papers: List[Dict[str, Any]]) -> str:
    lines = []
    citation_map = build_brief_citation_map(papers)
    headings = {
        "Bottom Line", "What This Literature Actually Covers", "Strongest Signals", "Conceptual Framing",
        "Methodological Reading", "Where the Evidence Is Thin", "Research Gaps", "What This Means for Your Query",
        "Best Next Directions", "Confidence & Scope Note",
    }
    for raw_line in (brief_text or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            lines.append("<div style='height:0.45rem;'></div>")
            continue
        stripped = line.strip().lstrip("#").strip()
        if stripped == "Research Brief":
            continue
        html_line = _replace_citations_with_anchors(line, citation_map)
        if line.startswith("##") or stripped in headings:
            lines.append(f"<div class='linked-brief-heading'>{html.escape(stripped)}</div>")
        else:
            lines.append(f"<div class='linked-brief-paragraph'>{html_line}</div>")
    return "\n".join(lines)
