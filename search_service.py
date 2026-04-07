import json
import os
import re
from datetime import datetime
from urllib.parse import quote

import requests
import streamlit as st
from dotenv import load_dotenv

from llm_service import ask_llm

load_dotenv()

CURRENT_YEAR = datetime.now().year
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "").strip()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "").strip()

REQUEST_TIMEOUT = 20
USER_AGENT = "AcademicATS/1.0 (mailto:{})".format(UNPAYWALL_EMAIL or "no-email@example.com")

SOURCE_LABELS = {
    "Semantic Scholar": "Semantic Scholar",
    "OpenAlex": "OpenAlex",
    "Crossref": "Crossref",
    "Google Scholar": "Google Scholar",
}


def emit_progress(progress_callback, value, message, payload=None):
    if progress_callback:
        try:
            progress_callback(value, message, payload)
        except TypeError:
            progress_callback(value, message)


def parse_openalex_abstract(abstract_inverted_index):
    if not abstract_inverted_index:
        return "No abstract available."

    word_positions = []
    for word, positions in abstract_inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))

    word_positions.sort(key=lambda x: x[0])
    abstract_text = " ".join([word for _, word in word_positions])

    return abstract_text if abstract_text.strip() else "No abstract available."


def safe_json_loads(text: str):
    text = text.strip()
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

    start_arr = text.find("[")
    end_arr = text.rfind("]")
    if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
        candidate = text[start_arr:end_arr + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    raise ValueError("Failed to parse JSON from LLM output.")


def normalize_year(year):
    try:
        y = int(year)
        if 1800 <= y <= CURRENT_YEAR + 1:
            return y
    except Exception:
        pass
    return None


def has_good_abstract(text: str) -> bool:
    if not text:
        return False
    lowered = text.strip().lower()
    if lowered in ["no abstract available.", "no abstract available", "no abstract", ""]:
        return False
    return True


def year_in_range(year, year_range):
    if year_range is None:
        return True

    y = normalize_year(year)
    if y is None:
        return False

    start_year, end_year = year_range
    return start_year <= y <= end_year


def deduplicate_papers(papers):
    seen = set()
    deduped = []

    for p in papers:
        doi = (p.get("doi") or "").strip().lower()
        title_key = (p.get("title") or "").strip().lower()

        key = doi if doi else title_key
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    return deduped


def tokenize_query(query: str):
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return [t for t in tokens if len(t) > 1]


def normalize_intent_profile(intent_profile):
    if not isinstance(intent_profile, dict):
        return {
            "include": [],
            "exclude": [],
            "domain_bias": ""
        }

    include_terms = intent_profile.get("include", []) or []
    exclude_terms = intent_profile.get("exclude", []) or []
    domain_bias = intent_profile.get("domain_bias", "") or ""

    return {
        "include": [str(x).lower() for x in include_terms if str(x).strip()],
        "exclude": [str(x).lower() for x in exclude_terms if str(x).strip()],
        "domain_bias": str(domain_bias).lower().strip()
    }


def truncate_text(text: str, max_chars: int = 900) -> str:
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def normalize_score_0_100(value, fallback=50):
    try:
        v = float(value)
    except Exception:
        return fallback
    return max(0, min(100, v))


def normalize_source_filters(source_filters):
    if not source_filters:
        return list(SOURCE_LABELS.keys())
    normalized = []
    for s in source_filters:
        s = str(s).strip()
        if s in SOURCE_LABELS:
            normalized.append(s)
    return normalized or list(SOURCE_LABELS.keys())


def short_query_core_mode(original_query, retrieval_query, intent_profile):
    q = (original_query or retrieval_query or "").strip().lower()
    tokens = tokenize_query(q)
    intent = normalize_intent_profile(intent_profile)

    if len(tokens) <= 3:
        return True

    if intent.get("domain_bias") in ["entertainment", "education", "clinical"]:
        if len(tokens) <= 4:
            return True

    return False


def core_focus_terms_for_short_query(intent_profile=None):
    intent = normalize_intent_profile(intent_profile)
    domain_bias = intent.get("domain_bias", "")

    if domain_bias == "entertainment":
        return {
            "positive": [
                "game", "games", "gameplay", "player", "players",
                "experience", "engagement", "immersion", "adoption",
                "motivation", "continuance", "design", "guidelines",
                "meaningful", "social", "play", "playing", "presence"
            ],
            "negative": [
                "tourism", "marketing", "destination", "urban", "built environment",
                "heritage", "museum", "rehabilitation", "therapy", "clinical",
                "education", "student", "science-based", "authoring", "registration",
                "architecture", "framework for applications", "industrial", "smart city",
                "teacher", "teachers", "policy", "law", "ethics", "professional development"
            ]
        }

    if domain_bias == "education":
        return {
            "positive": [
                "education", "learning", "teaching", "students", "classroom",
                "pedagogy", "instruction", "educational", "curriculum"
            ],
            "negative": [
                "tourism", "marketing", "destination", "built environment",
                "rehabilitation", "therapy", "clinical", "industrial"
            ]
        }

    if domain_bias == "clinical":
        return {
            "positive": [
                "clinical", "therapy", "rehabilitation", "patients", "treatment",
                "diagnosis", "hospital"
            ],
            "negative": [
                "tourism", "marketing", "destination", "education", "student",
                "game design", "heritage"
            ]
        }

    return {"positive": [], "negative": []}


def clean_doi(doi):
    if not doi:
        return ""
    doi = str(doi).strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "").strip()
    return doi


def choose_best_url(paper):
    return (
        paper.get("oa_url")
        or paper.get("pdf_url")
        or paper.get("url")
        or ""
    )


def compute_relevance_features(query: str, paper: dict, intent_profile=None):
    title = paper.get("title", "") or ""
    abstract = paper.get("summary", "") or ""
    intent = normalize_intent_profile(intent_profile)

    title_l = title.lower()
    abstract_l = abstract.lower()
    query_l = query.lower()
    tokens = tokenize_query(query)

    title_hits = sum(1 for t in tokens if t in title_l)
    abstract_hits = sum(1 for t in tokens if t in abstract_l)

    exact_phrase_bonus = 0
    if query_l in title_l:
        exact_phrase_bonus += 5
    if query_l in abstract_l:
        exact_phrase_bonus += 3

    abstract_bonus = 2 if has_good_abstract(abstract) else 0

    include_hits = 0
    for term in intent["include"]:
        if term in title_l:
            include_hits += 2
        elif term in abstract_l:
            include_hits += 1

    exclude_hits = 0
    for term in intent["exclude"]:
        if term in title_l:
            exclude_hits += 2
        elif term in abstract_l:
            exclude_hits += 1

    domain_bias_bonus = 0

    if intent["domain_bias"] == "entertainment":
        entertainment_terms = [
            "player experience", "immersion", "presence", "game design",
            "video game", "video games", "gaming", "gameplay", "play", "players",
            "engagement", "motivation", "continuance", "meaningful", "multiplayer"
        ]
        off_terms = [
            "rehabilitation", "therapy", "clinical", "stroke", "elderly",
            "patient", "patients", "diagnosis", "education", "learning",
            "tourism", "urban planning", "built environment", "marketing",
            "destination", "student", "science-based", "authoring",
            "teacher", "teachers", "policy", "law", "ethics", "professional development"
        ]
        for term in entertainment_terms:
            if term in title_l:
                domain_bias_bonus += 2.2
            elif term in abstract_l:
                domain_bias_bonus += 1.1
        for term in off_terms:
            if term in title_l:
                domain_bias_bonus -= 4.5
            elif term in abstract_l:
                domain_bias_bonus -= 2.1

    broad_review_bonus = 0
    broad_review_penalty = 0
    title_summary = f"{title_l} {abstract_l}"

    review_terms = [
        "systematic review", "literature review", "review", "survey",
        "mapping study", "scoping review", "meta-analysis"
    ]
    if any(term in title_summary for term in review_terms):
        if len(tokens) <= 2:
            broad_review_bonus += 1.5
        else:
            broad_review_penalty += 1.0

    generic_theory_terms = [
        "framework", "method", "registration", "architecture", "system",
        "authoring tool", "tool", "prototype", "engine", "conceptual model"
    ]
    generic_theory_hits = sum(1 for term in generic_theory_terms if term in title_summary)

    off_target_penalty = 0
    off_target_terms = [
        "tourism", "heritage", "urban", "built environment", "museum",
        "rehabilitation", "therapy", "clinical", "marketing", "purchase intention",
        "smart city", "industrial", "manufacturing", "destination",
        "student", "science-based", "authoring", "teacher", "teachers",
        "policy", "law", "ethics", "professional development", "sustainability",
        "training", "learning city"
    ]
    for term in off_target_terms:
        if term in title_l:
            off_target_penalty += 3.4
        elif term in abstract_l:
            off_target_penalty += 1.9

    relevance_score = (
        title_hits * 4
        + abstract_hits * 1.5
        + exact_phrase_bonus
        + abstract_bonus
        + include_hits * 3
        - exclude_hits * 4
        + domain_bias_bonus
        + broad_review_bonus
        - broad_review_penalty
        - off_target_penalty
    )

    return {
        "title_hits": title_hits,
        "abstract_hits": abstract_hits,
        "exact_phrase_bonus": exact_phrase_bonus,
        "abstract_bonus": abstract_bonus,
        "relevance_score": relevance_score,
        "include_hits": include_hits,
        "exclude_hits": exclude_hits,
        "domain_bias_bonus": domain_bias_bonus,
        "generic_theory_hits": generic_theory_hits,
        "off_target_penalty": off_target_penalty,
    }


def compute_evidence_strength(query: str, paper: dict, features: dict, sort_mode: str):
    year = normalize_year(paper.get("year"))
    title = (paper.get("title") or "").lower()
    summary = (paper.get("summary") or "").lower()
    query_tokens = tokenize_query(query)

    score = 0

    if features.get("title_hits", 0) >= 3:
        score += 32
    elif features.get("title_hits", 0) == 2:
        score += 24
    elif features.get("title_hits", 0) == 1:
        score += 14

    if features.get("abstract_hits", 0) >= 4:
        score += 20
    elif features.get("abstract_hits", 0) >= 2:
        score += 14
    elif features.get("abstract_hits", 0) >= 1:
        score += 8

    if features.get("exact_phrase_bonus", 0) >= 5:
        score += 14
    elif features.get("exact_phrase_bonus", 0) > 0:
        score += 8

    if has_good_abstract(paper.get("summary", "")):
        score += 10

    if year is not None:
        if year >= CURRENT_YEAR - 2:
            score += 10
        elif year >= CURRENT_YEAR - 5:
            score += 7
        elif year >= CURRENT_YEAR - 10:
            score += 4

    matched_tokens = 0
    for t in query_tokens:
        if t in title or t in summary:
            matched_tokens += 1

    coverage_ratio = (matched_tokens / len(query_tokens)) if query_tokens else 0

    if coverage_ratio >= 0.8:
        score += 12
    elif coverage_ratio >= 0.5:
        score += 7
    elif coverage_ratio >= 0.3:
        score += 3

    score = max(0, min(100, score))

    if score >= 74:
        strength = "Strong"
    elif score >= 48:
        strength = "Moderate"
    else:
        strength = "Limited"

    return strength, score


def build_evidence_breakdown(query: str, paper: dict, features: dict):
    year = normalize_year(paper.get("year"))
    title_hits = features.get("title_hits", 0)
    abstract_hits = features.get("abstract_hits", 0)
    exact_phrase_bonus = features.get("exact_phrase_bonus", 0)

    query_match = min(100, int(title_hits * 28 + abstract_hits * 10 + exact_phrase_bonus * 3))
    abstract_support = 100 if has_good_abstract(paper.get("summary", "")) else 20

    if year is None:
        recency = 25
    elif year >= CURRENT_YEAR - 2:
        recency = 100
    elif year >= CURRENT_YEAR - 5:
        recency = 80
    elif year >= CURRENT_YEAR - 10:
        recency = 55
    else:
        recency = 30

    domain_fit_bonus = features.get("domain_bias_bonus", 0)
    domain_fit = max(0, min(100, int(50 + domain_fit_bonus * 8)))

    open_access = 100 if paper.get("is_oa", False) else 0

    return {
        "query_match": query_match,
        "abstract_support": abstract_support,
        "recency": recency,
        "domain_fit": domain_fit,
        "open_access": open_access,
        "off_target_risk": int(max(0, min(100, paper.get("off_target_risk_score", 40)))),
    }


def explain_keep_reason(paper: dict):
    reasons = []

    if paper.get("research_fit_score", 0) >= 80:
        reasons.append("high research-fit score")
    elif paper.get("research_fit_score", 0) >= 65:
        reasons.append("solid topic fit")

    if paper.get("domain_fit_label") in ["direct", "mostly direct"]:
        reasons.append(f"domain fit is {paper.get('domain_fit_label')}")

    if paper.get("evidence_strength") == "Strong":
        reasons.append("strong evidence strength")

    if paper.get("is_oa"):
        reasons.append("open access available")

    if has_good_abstract(paper.get("summary", "")):
        reasons.append("usable abstract available")

    if not reasons:
        reasons.append("overall ranking signals were stronger than nearby candidates")

    return "Kept because " + ", ".join(reasons[:4]) + "."


def explain_pushdown_reason(paper: dict, open_access_only=False):
    reasons = []

    if paper.get("domain_fit_label") == "adjacent":
        reasons.append("it appears more adjacent than direct")
    elif paper.get("domain_fit_label") == "off-target":
        reasons.append("it looks off-target for the selected interpretation")

    if not has_good_abstract(paper.get("summary", "")):
        reasons.append("abstract support is weak or missing")

    if paper.get("off_target_risk_score", 0) >= 60:
        reasons.append("off-target risk is relatively high")

    if paper.get("research_fit_score", 0) < 60:
        reasons.append("research-fit score is lower than the kept set")

    if open_access_only and not paper.get("is_oa", False):
        reasons.append("it was excluded by the open-access-only setting")

    if not reasons:
        reasons.append("it ranked below stronger nearby candidates after reranking")

    return "Pushed down because " + ", ".join(reasons[:4]) + "."


def build_ranking_reason(sort_mode: str, paper: dict, features: dict, llm_meta=None):
    year = normalize_year(paper.get("year"))
    abstract_flag = "has abstract" if has_good_abstract(paper.get("summary", "")) else "no abstract"

    if llm_meta and llm_meta.get("reason"):
        return f"{llm_meta.get('reason')} Year={year if year else 'unknown'}, {abstract_flag}."

    return f"Ranked using {sort_mode}. Year={year if year else 'unknown'}, {abstract_flag}."


def build_recommendation_reason(sort_mode: str, paper: dict, features: dict, evidence_strength: str, llm_meta=None):
    year = normalize_year(paper.get("year"))
    reasons = []

    if llm_meta:
        if llm_meta.get("research_fit_score", 0) >= 85:
            reasons.append("very strong fit for the current research question")
        elif llm_meta.get("research_fit_score", 0) >= 70:
            reasons.append("good fit for the current research question")

        if llm_meta.get("domain_fit_label"):
            reasons.append(f"domain fit: {llm_meta.get('domain_fit_label')}")

        if llm_meta.get("paper_type_label"):
            reasons.append(f"type: {llm_meta.get('paper_type_label')}")

        if llm_meta.get("reason"):
            reasons.append(llm_meta.get("reason"))

    if paper.get("is_oa"):
        reasons.append("open access available")

    if year is not None:
        reasons.append(f"year: {year}")

    if not reasons:
        reasons.append("overall topical relevance")

    joined = ", ".join(reasons[:3])

    if evidence_strength == "Strong":
        prefix = "High-priority pick"
    elif evidence_strength == "Moderate":
        prefix = "Useful candidate"
    else:
        prefix = "Supplementary candidate"

    return f"{prefix}: {joined}."


def make_headers():
    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


@st.cache_data(ttl=60 * 60, show_spinner=False)
def search_semantic_scholar(query: str, limit: int = 20):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    batch_size = min(100, max(1, limit))
    offset = 0
    papers = []

    while len(papers) < limit:
        params = {
            "query": query,
            "limit": min(batch_size, limit - len(papers)),
            "offset": offset,
            "fields": "title,abstract,year,authors,url,externalIds,openAccessPdf"
        }

        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=make_headers())
        if response.status_code != 200:
            break

        data = response.json()
        items = data.get("data", [])
        if not items:
            break

        for item in items:
            title = item.get("title", "No title")
            abstract = item.get("abstract", "No abstract available.")
            year = item.get("year", "Unknown year")

            authors_data = item.get("authors", [])
            authors = ", ".join([a.get("name", "") for a in authors_data[:5]]) if authors_data else "Unknown authors"

            paper_url = item.get("url", "")
            doi = clean_doi((item.get("externalIds") or {}).get("DOI"))
            pdf_url = ((item.get("openAccessPdf") or {}) or {}).get("url", "")

            papers.append({
                "title": title,
                "summary": abstract if abstract else "No abstract available.",
                "year": year,
                "authors": authors,
                "url": paper_url,
                "source": "Semantic Scholar",
                "doi": doi,
                "pdf_url": pdf_url,
                "oa_url": pdf_url,
                "is_oa": bool(pdf_url),
            })

            if len(papers) >= limit:
                break

        offset += len(items)
        if len(items) < params["limit"]:
            break

    return papers[:limit]


@st.cache_data(ttl=60 * 60, show_spinner=False)
def search_openalex(query: str, limit: int = 20):
    url = "https://api.openalex.org/works"
    per_page = min(200, max(1, limit))
    page = 1
    papers = []

    while len(papers) < limit:
        params = {
            "search": query,
            "per_page": min(per_page, limit - len(papers)),
            "page": page
        }

        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=make_headers())
        if response.status_code != 200:
            break

        data = response.json()
        items = data.get("results", [])
        if not items:
            break

        for item in items:
            title = item.get("title", "No title")
            abstract = parse_openalex_abstract(item.get("abstract_inverted_index", {}))
            year = item.get("publication_year", "Unknown year")
            doi = clean_doi(item.get("doi"))

            authorships = item.get("authorships", [])
            authors = ", ".join(
                [
                    a.get("author", {}).get("display_name", "")
                    for a in authorships[:5]
                    if a.get("author", {}).get("display_name")
                ]
            ) if authorships else "Unknown authors"

            primary_location = item.get("primary_location") or {}
            landing_page_url = primary_location.get("landing_page_url", "") or item.get("id", "")
            pdf_url = primary_location.get("pdf_url", "") or ""
            best_oa = item.get("best_oa_location") or {}
            oa_url = best_oa.get("landing_page_url") or best_oa.get("pdf_url") or pdf_url or ""

            papers.append({
                "title": title,
                "summary": abstract,
                "year": year,
                "authors": authors,
                "url": landing_page_url,
                "source": "OpenAlex",
                "doi": doi,
                "pdf_url": pdf_url,
                "oa_url": oa_url,
                "is_oa": bool(item.get("open_access", {}).get("is_oa", False) or oa_url),
            })

            if len(papers) >= limit:
                break

        page += 1
        if len(items) < params["per_page"]:
            break

    return papers[:limit]


@st.cache_data(ttl=60 * 60, show_spinner=False)
def search_crossref(query: str, limit: int = 20):
    url = "https://api.crossref.org/works"
    rows = min(100, max(1, limit))
    papers = []

    params = {
        "query.bibliographic": query,
        "rows": rows,
        "select": "DOI,title,author,abstract,published-print,published-online,created,URL,container-title,publisher,license"
    }

    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=make_headers())
    if response.status_code != 200:
        return []

    items = response.json().get("message", {}).get("items", [])
    for item in items:
        title = (item.get("title") or ["No title"])[0]
        abstract = item.get("abstract", "No abstract available.") or "No abstract available."
        abstract = re.sub(r"<[^>]+>", " ", abstract).strip() if abstract else "No abstract available."

        authors_data = item.get("author", [])
        authors = ", ".join(
            [
                " ".join(filter(None, [a.get("given", ""), a.get("family", "")])).strip()
                for a in authors_data[:5]
            ]
        ) if authors_data else "Unknown authors"

        year = None
        for key in ["published-print", "published-online", "created"]:
            date_parts = (((item.get(key) or {}).get("date-parts") or [[]])[0] or [])
            if date_parts:
                year = date_parts[0]
                break

        doi = clean_doi(item.get("DOI"))
        url_value = item.get("URL", "")
        license_entries = item.get("license") or []
        oa_url = license_entries[0].get("URL", "") if license_entries else ""

        papers.append({
            "title": title,
            "summary": abstract if abstract else "No abstract available.",
            "year": year or "Unknown year",
            "authors": authors,
            "url": url_value,
            "source": "Crossref",
            "doi": doi,
            "pdf_url": "",
            "oa_url": oa_url,
            "is_oa": bool(oa_url),
        })

    return papers[:limit]


@st.cache_data(ttl=60 * 60, show_spinner=False)
def search_google_scholar_serpapi(query: str, limit: int = 20):
    if not SERPAPI_API_KEY:
        return []

    url = "https://serpapi.com/search"
    params = {
        "engine": "google_scholar",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": min(limit, 20),
    }

    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=make_headers())
    if response.status_code != 200:
        return []

    data = response.json()
    organic = data.get("organic_results", []) or []
    papers = []

    for item in organic[:limit]:
        title = item.get("title", "No title")
        snippet = item.get("snippet", "No abstract available.") or "No abstract available."
        publication_info = item.get("publication_info", {}) or {}
        authors = ", ".join(
            [a.get("name", "") for a in (publication_info.get("authors") or [])[:5]]
        ) if publication_info.get("authors") else "Unknown authors"

        year = None
        summary_text = " ".join(filter(None, [snippet, publication_info.get("summary", "")]))
        year_match = re.search(r"(19|20)\d{2}", summary_text)
        if year_match:
            year = int(year_match.group(0))

        resources = item.get("resources", []) or []
        pdf_url = resources[0].get("link", "") if resources else ""
        url_value = item.get("link", "") or item.get("result_id", "")

        papers.append({
            "title": title,
            "summary": snippet,
            "year": year or "Unknown year",
            "authors": authors,
            "url": url_value,
            "source": "Google Scholar",
            "doi": "",
            "pdf_url": pdf_url,
            "oa_url": pdf_url,
            "is_oa": bool(pdf_url),
        })

    return papers[:limit]


@st.cache_data(ttl=60 * 30, show_spinner=False)
def enrich_unpaywall_by_doi(doi: str):
    doi = clean_doi(doi)
    if not doi or not UNPAYWALL_EMAIL:
        return {}

    url = f"https://api.unpaywall.org/v2/{quote(doi)}"
    params = {"email": UNPAYWALL_EMAIL}

    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=make_headers())
    if response.status_code != 200:
        return {}

    data = response.json()
    best_oa = data.get("best_oa_location") or {}
    oa_url = best_oa.get("url_for_pdf") or best_oa.get("url") or ""
    return {
        "is_oa": bool(data.get("is_oa", False)),
        "oa_url": oa_url,
        "pdf_url": best_oa.get("url_for_pdf", "") or "",
        "doi_url": data.get("doi_url", "") or "",
    }


def enrich_papers_with_unpaywall(papers):
    enriched = []
    for p in papers:
        p_copy = dict(p)
        doi = clean_doi(p_copy.get("doi"))
        if doi and UNPAYWALL_EMAIL:
            try:
                upw = enrich_unpaywall_by_doi(doi)
                if upw:
                    p_copy["is_oa"] = bool(p_copy.get("is_oa", False) or upw.get("is_oa", False))
                    p_copy["oa_url"] = p_copy.get("oa_url") or upw.get("oa_url", "")
                    p_copy["pdf_url"] = p_copy.get("pdf_url") or upw.get("pdf_url", "")
                    if not p_copy.get("url") and upw.get("doi_url"):
                        p_copy["url"] = upw.get("doi_url")
            except Exception:
                pass
        enriched.append(p_copy)
    return enriched


@st.cache_data(ttl=60 * 30, show_spinner=False)
def retrieve_candidate_papers(query: str, candidate_limit: int = 200, source_filters=None):
    all_papers = []
    source_filters = normalize_source_filters(source_filters)

    source_limit = max(20, min(candidate_limit, 250))

    if "Semantic Scholar" in source_filters:
        try:
            all_papers.extend(search_semantic_scholar(query, source_limit))
        except Exception:
            pass

    if "OpenAlex" in source_filters:
        try:
            all_papers.extend(search_openalex(query, source_limit))
        except Exception:
            pass

    if "Crossref" in source_filters:
        try:
            all_papers.extend(search_crossref(query, source_limit))
        except Exception:
            pass

    if "Google Scholar" in source_filters:
        try:
            all_papers.extend(search_google_scholar_serpapi(query, min(source_limit, 20)))
        except Exception:
            pass

    all_papers = deduplicate_papers(all_papers)
    all_papers = enrich_papers_with_unpaywall(all_papers)
    return all_papers


def prepare_rule_scored_candidates(
    query: str,
    papers: list,
    sort_mode: str = "Balanced",
    year_range=None,
    prefer_abstracts: bool = True,
    intent_profile=None,
    open_access_only: bool = False,
):
    filtered = []

    for p in papers:
        if not year_in_range(p.get("year"), year_range):
            continue
        if open_access_only and not p.get("is_oa", False):
            continue
        filtered.append(p)

    rescored = []
    for p in filtered:
        features = compute_relevance_features(query, p, intent_profile=intent_profile)

        abstract_penalty = -10 if (prefer_abstracts and not has_good_abstract(p.get("summary", ""))) else 0
        year_val = normalize_year(p.get("year")) or 0
        oa_bonus = 3 if p.get("is_oa") else 0

        if sort_mode == "Newest first":
            final_score = year_val * 10 + features["relevance_score"] + abstract_penalty + oa_bonus
        elif sort_mode == "Relevance score":
            final_score = features["relevance_score"] * 10 + abstract_penalty + oa_bonus
        elif sort_mode == "Research fit":
            final_score = features["relevance_score"] * 8 + abstract_penalty + oa_bonus
        elif sort_mode == "Evidence strength":
            final_score = features["relevance_score"] * 7 + abstract_penalty + oa_bonus
        elif sort_mode == "Open access first":
            final_score = features["relevance_score"] * 8 + abstract_penalty + oa_bonus + (15 if p.get("is_oa") else 0)
        else:
            final_score = features["relevance_score"] * 8 + abstract_penalty + oa_bonus + (year_val / 10)

        evidence_strength, evidence_score = compute_evidence_strength(
            query=query,
            paper=p,
            features=features,
            sort_mode=sort_mode
        )

        p_copy = dict(p)
        p_copy["_rule_features"] = features
        p_copy["_rule_score"] = round(final_score, 2)
        p_copy["_evidence_strength"] = evidence_strength
        p_copy["_evidence_score"] = evidence_score
        p_copy["_intent_match_score"] = (
            features.get("include_hits", 0) * 3
            - features.get("exclude_hits", 0) * 4
            + features.get("domain_bias_bonus", 0)
        )
        rescored.append(p_copy)

    if sort_mode == "Newest first":
        rescored.sort(
            key=lambda x: (
                normalize_year(x.get("year")) or 0,
                x.get("_rule_score", 0),
                x.get("_intent_match_score", 0)
            ),
            reverse=True
        )
    elif sort_mode == "Evidence strength":
        rescored.sort(
            key=lambda x: (
                x.get("_evidence_score", 0),
                x.get("_rule_score", 0),
                normalize_year(x.get("year")) or 0
            ),
            reverse=True
        )
    elif sort_mode == "Open access first":
        rescored.sort(
            key=lambda x: (
                1 if x.get("is_oa", False) else 0,
                x.get("_rule_score", 0),
                normalize_year(x.get("year")) or 0
            ),
            reverse=True
        )
    else:
        rescored.sort(
            key=lambda x: (
                x.get("_intent_match_score", 0),
                x.get("_rule_score", 0),
                normalize_year(x.get("year")) or 0
            ),
            reverse=True
        )

    return rescored


def candidate_pool_size_for_final_count(paper_count: int) -> int:
    return max(120, min(max(paper_count * 3, 120), 300))


def llm_batch_prompt(
    original_query: str,
    retrieval_query: str,
    sort_mode: str,
    intent_profile: dict,
    papers: list,
):
    intent_profile = intent_profile or {}
    formatted = []

    for idx, paper in enumerate(papers, start=1):
        formatted.append(
            f"""
Paper {idx}
Title: {paper.get('title', '')}
Authors: {paper.get('authors', '')}
Year: {paper.get('year', '')}
Source: {paper.get('source', '')}
OpenAccess: {paper.get('is_oa', False)}
Abstract: {truncate_text(paper.get('summary', ''), 1200)}
"""
        )

    papers_block = "\n".join(formatted)

    return f"""
You are ranking academic papers for a research assistant.

Original user topic:
{original_query}

Retrieval query:
{retrieval_query}

Sort mode:
{sort_mode}

Intent profile:
{json.dumps(intent_profile, ensure_ascii=False)}

Task:
Score each paper for how well it fits the user's current research question, not just broad keyword overlap.

For each paper, return:
- paper_index: integer
- research_fit_score: 0-100
- domain_fit_label: one of ["direct", "mostly direct", "adjacent", "off-target"]
- paper_type_label: one of ["empirical study", "review/survey", "framework/tool", "technical method", "application/case", "theory/other"]
- abstract_quality_label: one of ["good", "limited", "missing"]
- off_target_risk_score: 0-100
- reason: short sentence, max 22 words

Return JSON only in this exact format:
{{
  "papers": [
    {{
      "paper_index": 1,
      "research_fit_score": 82,
      "domain_fit_label": "direct",
      "paper_type_label": "empirical study",
      "abstract_quality_label": "good",
      "off_target_risk_score": 12,
      "reason": "Directly studies player motivations in mobile location-based AR games."
    }}
  ]
}}

Papers:
{papers_block}
"""


@st.cache_data(ttl=60 * 30, show_spinner=False)
def llm_rerank_batch(
    original_query: str,
    retrieval_query: str,
    sort_mode: str,
    intent_profile_json: str,
    batch_json: str,
):
    try:
        intent_profile = json.loads(intent_profile_json) if intent_profile_json else {}
    except Exception:
        intent_profile = {}

    papers = json.loads(batch_json)
    prompt = llm_batch_prompt(
        original_query=original_query,
        retrieval_query=retrieval_query,
        sort_mode=sort_mode,
        intent_profile=intent_profile,
        papers=papers,
    )

    try:
        raw = ask_llm(prompt)
        parsed = safe_json_loads(raw)
        items = parsed.get("papers", [])
        if not isinstance(items, list):
            return []

        normalized = []
        for item in items:
            idx = item.get("paper_index")
            if not isinstance(idx, int):
                continue

            normalized.append({
                "paper_index": idx,
                "research_fit_score": normalize_score_0_100(item.get("research_fit_score"), fallback=55),
                "domain_fit_label": str(item.get("domain_fit_label", "adjacent")).strip().lower(),
                "paper_type_label": str(item.get("paper_type_label", "theory/other")).strip().lower(),
                "abstract_quality_label": str(item.get("abstract_quality_label", "limited")).strip().lower(),
                "off_target_risk_score": normalize_score_0_100(item.get("off_target_risk_score"), fallback=40),
                "reason": truncate_text(str(item.get("reason", "")).strip(), 180),
            })
        return normalized

    except Exception:
        return []


def enrich_candidates_with_llm_scores(
    original_query: str,
    retrieval_query: str,
    candidates: list,
    sort_mode: str = "Balanced",
    intent_profile=None,
    progress_callback=None,
    progress_start: float = 42,
    progress_end: float = 72,
):
    if not candidates:
        return []

    intent_profile = normalize_intent_profile(intent_profile)
    batch_size = 6
    scored_map = {}
    total_batches = max(1, (len(candidates) + batch_size - 1) // batch_size)

    for batch_idx, start in enumerate(range(0, len(candidates), batch_size), start=1):
        batch = candidates[start:start + batch_size]

        progress_value = progress_start + ((batch_idx - 1) / total_batches) * (progress_end - progress_start)
        emit_progress(
            progress_callback,
            progress_value,
            f"Second-stage AI screening batch {batch_idx}/{total_batches}..."
        )

        compact_batch = []
        for p in batch:
            compact_batch.append({
                "title": p.get("title", ""),
                "authors": p.get("authors", ""),
                "year": p.get("year", ""),
                "source": p.get("source", ""),
                "summary": p.get("summary", ""),
                "is_oa": p.get("is_oa", False),
            })

        llm_scores = llm_rerank_batch(
            original_query=original_query,
            retrieval_query=retrieval_query,
            sort_mode=sort_mode,
            intent_profile_json=json.dumps(intent_profile, sort_keys=True, ensure_ascii=False),
            batch_json=json.dumps(compact_batch, sort_keys=True, ensure_ascii=False),
        )

        for item in llm_scores:
            paper_index = item.get("paper_index")
            if isinstance(paper_index, int) and 1 <= paper_index <= len(batch):
                global_index = start + paper_index - 1
                scored_map[global_index] = item

    emit_progress(progress_callback, progress_end, "Second-stage AI screening complete.")

    enriched = []
    for i, p in enumerate(candidates):
        p_copy = dict(p)
        llm_meta = scored_map.get(i)

        if llm_meta is None:
            llm_meta = {
                "research_fit_score": 55,
                "domain_fit_label": "adjacent",
                "paper_type_label": "theory/other",
                "abstract_quality_label": "good" if has_good_abstract(p_copy.get("summary", "")) else "missing",
                "off_target_risk_score": 45 if has_good_abstract(p_copy.get("summary", "")) else 68,
                "reason": "Reasonable keyword match, but not strongly confirmed by second-stage screening."
            }

        p_copy["_llm_meta"] = llm_meta
        enriched.append(p_copy)

    return enriched


def combine_rule_and_llm_scores(
    paper: dict,
    sort_mode: str = "Balanced",
    prefer_abstracts: bool = True,
    original_query=None,
    retrieval_query=None,
    intent_profile=None,
):
    rule_score = float(paper.get("_rule_score", 0))
    llm_meta = paper.get("_llm_meta", {}) or {}
    features = paper.get("_rule_features", {}) or {}

    research_fit_score = float(llm_meta.get("research_fit_score", 55))
    off_target_risk_score = float(llm_meta.get("off_target_risk_score", 40))
    abstract_quality_label = str(llm_meta.get("abstract_quality_label", "limited")).lower()
    paper_type_label = str(llm_meta.get("paper_type_label", "theory/other")).lower()
    domain_fit_label = str(llm_meta.get("domain_fit_label", "adjacent")).lower()
    evidence_score = float(paper.get("_evidence_score", 50))
    year_val = normalize_year(paper.get("year")) or 0

    title_l = (paper.get("title") or "").lower()
    abstract_l = (paper.get("summary") or "").lower()
    text_l = f"{title_l} {abstract_l}"

    is_short_core_mode = short_query_core_mode(
        original_query=original_query,
        retrieval_query=retrieval_query or "",
        intent_profile=intent_profile
    )
    core_terms = core_focus_terms_for_short_query(intent_profile=intent_profile)

    type_adjustment = 0
    if paper_type_label == "empirical study":
        type_adjustment += 12
    elif paper_type_label == "review/survey":
        type_adjustment += 8
    elif paper_type_label == "framework/tool":
        type_adjustment -= 6
    elif paper_type_label == "technical method":
        type_adjustment -= 14
    elif paper_type_label == "application/case":
        type_adjustment -= 10

    domain_adjustment = 0
    if domain_fit_label == "direct":
        domain_adjustment += 14
    elif domain_fit_label == "mostly direct":
        domain_adjustment += 7
    elif domain_fit_label == "adjacent":
        domain_adjustment -= 10
    elif domain_fit_label == "off-target":
        domain_adjustment -= 24

    abstract_adjustment = 0
    if prefer_abstracts:
        if abstract_quality_label == "good":
            abstract_adjustment += 4
        elif abstract_quality_label == "limited":
            abstract_adjustment -= 3
        elif abstract_quality_label == "missing":
            abstract_adjustment -= 18

    technical_penalty = 0
    if features.get("generic_theory_hits", 0) >= 2:
        technical_penalty -= 6

    recency_adjustment = year_val / 140.0
    if sort_mode == "Newest first":
        recency_adjustment = year_val / 20.0

    direct_game_bonus = 0
    if "game" in text_l or "games" in text_l or "gameplay" in text_l:
        direct_game_bonus += 4
    if "player" in text_l or "players" in text_l:
        direct_game_bonus += 3
    if "engagement" in text_l or "immersion" in text_l or "motivation" in text_l or "presence" in text_l:
        direct_game_bonus += 3

    oa_bonus = 2 if paper.get("is_oa") else 0
    if sort_mode == "Open access first" and paper.get("is_oa"):
        oa_bonus += 12

    short_query_focus_bonus = 0
    short_query_focus_penalty = 0
    if is_short_core_mode:
        positive_hits = 0
        negative_hits = 0

        for term in core_terms["positive"]:
            if term in title_l:
                positive_hits += 2
            elif term in abstract_l:
                positive_hits += 1

        for term in core_terms["negative"]:
            if term in title_l:
                negative_hits += 3
            elif term in abstract_l:
                negative_hits += 1.5

        short_query_focus_bonus += positive_hits * 1.2
        short_query_focus_penalty += negative_hits * 2.3

    if sort_mode == "Research fit":
        final_score = (
            research_fit_score * 0.90
            + rule_score * 0.10
            - (off_target_risk_score * 0.22)
            + type_adjustment
            + domain_adjustment
            + abstract_adjustment
            + oa_bonus
            + short_query_focus_bonus
            - short_query_focus_penalty
        )
    elif sort_mode == "Evidence strength":
        final_score = (
            evidence_score * 0.82
            + research_fit_score * 0.18
            - (off_target_risk_score * 0.14)
            + type_adjustment
            + domain_adjustment
            + abstract_adjustment
            + oa_bonus
        )
    elif sort_mode == "Relevance score":
        final_score = (
            rule_score * 0.55
            + research_fit_score * 0.45
            - (off_target_risk_score * 0.25)
            + type_adjustment
            + domain_adjustment
            + abstract_adjustment
            + technical_penalty
            + recency_adjustment
            + direct_game_bonus
            + oa_bonus
            + short_query_focus_bonus
            - short_query_focus_penalty
        )
    elif sort_mode == "Newest first":
        final_score = (
            year_val * 1.2
            + research_fit_score * 0.35
            + rule_score * 0.15
            - (off_target_risk_score * 0.10)
            + type_adjustment
            + domain_adjustment
            + abstract_adjustment
            + oa_bonus
        )
    elif sort_mode == "Open access first":
        final_score = (
            rule_score * 0.26
            + research_fit_score * 0.54
            - (off_target_risk_score * 0.22)
            + type_adjustment
            + domain_adjustment
            + abstract_adjustment
            + technical_penalty
            + recency_adjustment
            + direct_game_bonus
            + oa_bonus
            + short_query_focus_bonus
            - short_query_focus_penalty
        )
    else:
        final_score = (
            rule_score * 0.32
            + research_fit_score * 0.68
            - (off_target_risk_score * 0.30)
            + type_adjustment
            + domain_adjustment
            + abstract_adjustment
            + technical_penalty
            + recency_adjustment
            + direct_game_bonus
            + oa_bonus
            + short_query_focus_bonus
            - short_query_focus_penalty
        )

    return round(final_score, 2)


def classify_gate_bucket(paper: dict):
    domain_fit = str(paper.get("domain_fit_label", "adjacent")).lower()
    abstract_quality = str(paper.get("abstract_quality_label", "limited")).lower()
    has_abs = abstract_quality != "missing" and has_good_abstract(paper.get("summary", ""))

    if domain_fit in ["direct", "mostly direct"] and has_abs:
        return "primary"

    if domain_fit == "direct" and not has_abs:
        return "secondary_direct_missing_abstract"

    if domain_fit == "mostly direct" and not has_abs:
        return "secondary_mostly_direct_missing_abstract"

    if domain_fit == "adjacent" and has_abs:
        return "adjacent_with_abstract"

    if domain_fit == "adjacent" and not has_abs:
        return "adjacent_missing_abstract"

    if domain_fit == "off-target" and has_abs:
        return "off_target_with_abstract"

    return "off_target_missing_abstract"


def apply_post_filter_gate(finalized: list, paper_count: int, strict_core_only: bool = False):
    if not finalized:
        return []

    primary = []
    secondary_direct_missing = []
    secondary_mostly_direct_missing = []
    adjacent_with_abstract = []
    adjacent_missing_abstract = []
    off_target_with_abstract = []
    off_target_missing_abstract = []

    for p in finalized:
        bucket = classify_gate_bucket(p)
        if bucket == "primary":
            primary.append(p)
        elif bucket == "secondary_direct_missing_abstract":
            secondary_direct_missing.append(p)
        elif bucket == "secondary_mostly_direct_missing_abstract":
            secondary_mostly_direct_missing.append(p)
        elif bucket == "adjacent_with_abstract":
            adjacent_with_abstract.append(p)
        elif bucket == "adjacent_missing_abstract":
            adjacent_missing_abstract.append(p)
        elif bucket == "off_target_with_abstract":
            off_target_with_abstract.append(p)
        else:
            off_target_missing_abstract.append(p)

    if strict_core_only:
        result = []
        result.extend(primary)

        remaining = paper_count - len(result)
        if remaining > 0:
            result.extend(secondary_direct_missing[:remaining])

        remaining = paper_count - len(result)
        if remaining > 0:
            result.extend(secondary_mostly_direct_missing[:remaining])

        return result[:paper_count]

    if len(primary) >= paper_count:
        return primary[:paper_count]

    result = []
    result.extend(primary)

    remaining = paper_count - len(result)
    if remaining <= 0:
        return result[:paper_count]

    fill_order = [
        secondary_direct_missing,
        secondary_mostly_direct_missing,
        adjacent_with_abstract,
        adjacent_missing_abstract,
        off_target_with_abstract,
        off_target_missing_abstract,
    ]

    for bucket in fill_order:
        if remaining <= 0:
            break
        result.extend(bucket[:remaining])
        remaining = paper_count - len(result)

    return result[:paper_count]


def finalize_ranked_papers(
    candidates: list,
    paper_count: int,
    sort_mode: str = "Balanced",
    prefer_abstracts: bool = True,
    original_query=None,
    retrieval_query=None,
    intent_profile=None,
    strict_core_only: bool = False,
):
    finalized = []

    for p in candidates:
        p_copy = dict(p)
        llm_meta = p_copy.get("_llm_meta", {}) or {}
        features = p_copy.get("_rule_features", {}) or {}

        p_copy["research_fit_score"] = llm_meta.get("research_fit_score", 55)
        p_copy["off_target_risk_score"] = llm_meta.get("off_target_risk_score", 40)

        final_score = combine_rule_and_llm_scores(
            paper=p_copy,
            sort_mode=sort_mode,
            prefer_abstracts=prefer_abstracts,
            original_query=original_query,
            retrieval_query=retrieval_query,
            intent_profile=intent_profile,
        )

        evidence_strength = p_copy.get("_evidence_strength", "Moderate")
        evidence_score = p_copy.get("_evidence_score", 50)

        p_copy["relevance_score"] = final_score
        p_copy["ranking_reason"] = build_ranking_reason(sort_mode, p_copy, features, llm_meta=llm_meta)
        p_copy["recommendation_reason"] = build_recommendation_reason(
            sort_mode,
            p_copy,
            features,
            evidence_strength,
            llm_meta=llm_meta
        )
        p_copy["evidence_strength"] = evidence_strength
        p_copy["evidence_score"] = evidence_score
        p_copy["domain_fit_label"] = llm_meta.get("domain_fit_label", "adjacent")
        p_copy["paper_type_label"] = llm_meta.get("paper_type_label", "theory/other")
        p_copy["abstract_quality_label"] = llm_meta.get("abstract_quality_label", "limited")
        p_copy["url"] = choose_best_url(p_copy)
        p_copy["evidence_breakdown"] = build_evidence_breakdown(
            query=retrieval_query or original_query or "",
            paper=p_copy,
            features=features
        )

        finalized.append(p_copy)

    finalized = sort_existing_papers_for_display(finalized, sort_mode)
    gated = apply_post_filter_gate(
        finalized=finalized,
        paper_count=paper_count,
        strict_core_only=strict_core_only
    )

    for p in gated:
        p["selection_reason"] = explain_keep_reason(p)

    return gated[:paper_count]


def supplement_ranked_papers(final_ranked, rule_ranked, paper_count, sort_mode, strict_core_only=False):
    if strict_core_only or len(final_ranked) >= paper_count:
        return final_ranked[:paper_count]

    seen = set()
    for p in final_ranked:
        key = clean_doi(p.get("doi")) or (p.get("title", "").strip().lower())
        if key:
            seen.add(key)

    supplemented = list(final_ranked)

    for p in rule_ranked:
        key = clean_doi(p.get("doi")) or (p.get("title", "").strip().lower())
        if not key or key in seen:
            continue

        p_copy = dict(p)
        p_copy["relevance_score"] = round(float(p.get("_rule_score", 0)), 2)
        p_copy["ranking_reason"] = f"Supplementary result added to fill the requested paper count. Ranked using {sort_mode}."
        p_copy["recommendation_reason"] = "Supplementary candidate: lower-confidence relevance used to fill the requested paper count."
        p_copy["evidence_strength"] = p.get("_evidence_strength", "Limited")
        p_copy["evidence_score"] = p.get("_evidence_score", 35)
        p_copy["research_fit_score"] = 40
        p_copy["off_target_risk_score"] = 55
        p_copy["domain_fit_label"] = "adjacent"
        p_copy["paper_type_label"] = "theory/other"
        p_copy["abstract_quality_label"] = "good" if has_good_abstract(p_copy.get("summary", "")) else "missing"
        p_copy["url"] = choose_best_url(p_copy)
        p_copy["selection_reason"] = explain_keep_reason(p_copy)
        p_copy["evidence_breakdown"] = {
            "query_match": 40,
            "abstract_support": 100 if has_good_abstract(p_copy.get("summary", "")) else 20,
            "recency": 40,
            "domain_fit": 45,
            "open_access": 100 if p_copy.get("is_oa") else 0,
            "off_target_risk": 55,
        }

        supplemented.append(p_copy)
        seen.add(key)

        if len(supplemented) >= paper_count:
            break

    return sort_existing_papers_for_display(supplemented, sort_mode)[:paper_count]


def sort_existing_papers_for_display(papers, sort_mode="Balanced"):
    sorted_papers = list(papers)

    def year_key(p):
        return normalize_year(p.get("year")) or 0

    def rel_key(p):
        try:
            return float(p.get("relevance_score", 0))
        except Exception:
            return 0

    def fit_key(p):
        try:
            return float(p.get("research_fit_score", 0))
        except Exception:
            return 0

    def ev_key(p):
        try:
            return float(p.get("evidence_score", 0))
        except Exception:
            return 0

    def oa_key(p):
        return 1 if p.get("is_oa", False) else 0

    if sort_mode == "Newest first":
        sorted_papers.sort(
            key=lambda p: (year_key(p), fit_key(p), rel_key(p)),
            reverse=True
        )
    elif sort_mode == "Research fit":
        sorted_papers.sort(
            key=lambda p: (fit_key(p), rel_key(p), year_key(p)),
            reverse=True
        )
    elif sort_mode == "Relevance score":
        sorted_papers.sort(
            key=lambda p: (rel_key(p), fit_key(p), year_key(p)),
            reverse=True
        )
    elif sort_mode == "Evidence strength":
        sorted_papers.sort(
            key=lambda p: (ev_key(p), fit_key(p), rel_key(p)),
            reverse=True
        )
    elif sort_mode == "Open access first":
        sorted_papers.sort(
            key=lambda p: (oa_key(p), fit_key(p), rel_key(p), year_key(p)),
            reverse=True
        )
    else:
        sorted_papers.sort(
            key=lambda p: (rel_key(p), fit_key(p), year_key(p)),
            reverse=True
        )

    return sorted_papers


def search_papers(
    query: str,
    paper_count: int = 5,
    sort_mode: str = "Balanced",
    year_range=None,
    prefer_abstracts: bool = True,
    intent_profile=None,
    original_query=None,
    strict_core_only: bool = False,
    open_access_only: bool = False,
    source_filters=None,
):
    return search_papers_with_diagnostics(
        query=query,
        paper_count=paper_count,
        sort_mode=sort_mode,
        year_range=year_range,
        prefer_abstracts=prefer_abstracts,
        intent_profile=intent_profile,
        original_query=original_query,
        strict_core_only=strict_core_only,
        open_access_only=open_access_only,
        source_filters=source_filters,
    )["papers"]


def search_papers_with_diagnostics_live(
    query: str,
    paper_count: int = 5,
    sort_mode: str = "Balanced",
    year_range=None,
    prefer_abstracts: bool = True,
    intent_profile=None,
    original_query=None,
    strict_core_only: bool = False,
    open_access_only: bool = False,
    source_filters=None,
    progress_callback=None,
):
    source_filters = normalize_source_filters(source_filters)

    emit_progress(progress_callback, 8, "Fetching candidate papers from selected sources...")
    candidate_limit = min(max(paper_count * 12, 200), 4000)
    all_candidates = retrieve_candidate_papers(
        query=query,
        candidate_limit=candidate_limit,
        source_filters=source_filters
    )

    emit_progress(progress_callback, 18, f"Collected {len(all_candidates)} raw candidates. Applying filters...")
    rule_ranked = prepare_rule_scored_candidates(
        query=query,
        papers=all_candidates,
        sort_mode=sort_mode,
        year_range=year_range,
        prefer_abstracts=prefer_abstracts,
        intent_profile=intent_profile,
        open_access_only=open_access_only,
    )

    emit_progress(progress_callback, 30, f"{len(rule_ranked)} candidates remain after filtering and rule-based ranking.")

    stage2_pool_size = min(len(rule_ranked), candidate_pool_size_for_final_count(paper_count))
    stage2_pool = rule_ranked[:stage2_pool_size]
    emit_progress(progress_callback, 38, f"Preparing {len(stage2_pool)} papers for second-stage AI screening...")

    llm_enriched = enrich_candidates_with_llm_scores(
        original_query=original_query or query,
        retrieval_query=query,
        candidates=stage2_pool,
        sort_mode=sort_mode,
        intent_profile=intent_profile,
        progress_callback=progress_callback,
        progress_start=42,
        progress_end=72,
    )

    if open_access_only:
        emit_progress(progress_callback, 74, "Applying open-access-only filter to shortlisted papers...")
        llm_enriched = [p for p in llm_enriched if p.get("is_oa", False)]

    if strict_core_only:
        emit_progress(progress_callback, 78, "Applying strict core-paper prioritization...")
    else:
        emit_progress(progress_callback, 78, "Building final ranked shortlist...")

    final_ranked = finalize_ranked_papers(
        candidates=llm_enriched,
        paper_count=paper_count,
        sort_mode=sort_mode,
        prefer_abstracts=prefer_abstracts,
        original_query=original_query or query,
        retrieval_query=query,
        intent_profile=intent_profile,
        strict_core_only=strict_core_only,
    )

    emit_progress(progress_callback, 84, "Filling any remaining slots from supplementary candidates if needed...")
    final_ranked = supplement_ranked_papers(
        final_ranked=final_ranked,
        rule_ranked=rule_ranked,
        paper_count=paper_count,
        sort_mode=sort_mode,
        strict_core_only=strict_core_only,
    )

    final_keys = set()
    for p in final_ranked:
        key = clean_doi(p.get("doi")) or (p.get("title", "").strip().lower())
        if key:
            final_keys.add(key)

    retained_examples = []
    for p in final_ranked[:5]:
        retained_examples.append({
            "title": p.get("title", "Untitled"),
            "reason": p.get("selection_reason", explain_keep_reason(p))
        })

    pushed_down_examples = []
    for p in llm_enriched:
        key = clean_doi(p.get("doi")) or (p.get("title", "").strip().lower())
        if not key or key in final_keys:
            continue

        tmp = dict(p)
        llm_meta = tmp.get("_llm_meta", {}) or {}
        tmp["research_fit_score"] = llm_meta.get("research_fit_score", 55)
        tmp["off_target_risk_score"] = llm_meta.get("off_target_risk_score", 40)
        tmp["domain_fit_label"] = llm_meta.get("domain_fit_label", "adjacent")
        tmp["paper_type_label"] = llm_meta.get("paper_type_label", "theory/other")
        tmp["abstract_quality_label"] = llm_meta.get("abstract_quality_label", "limited")

        pushed_down_examples.append({
            "title": tmp.get("title", "Untitled"),
            "reason": explain_pushdown_reason(tmp, open_access_only=open_access_only)
        })

        if len(pushed_down_examples) >= 5:
            break

    selection_logic = [
        "Candidates were collected from the selected academic sources and deduplicated.",
        "First-stage ranking combined title/abstract matching, intent-profile matching, recency, and open-access signals.",
        "Second-stage reranking used AI screening to estimate research fit, domain fit, paper type, abstract quality, and off-target risk.",
        "Final selection favored papers with stronger fit, stronger evidence, better abstract support, and lower off-target risk.",
    ]

    if strict_core_only:
        selection_logic.append("Strict core mode further prioritized direct and mostly-direct papers over adjacent background material.")
    if open_access_only:
        selection_logic.append("Open-access-only mode removed papers without detected OA availability.")
    if prefer_abstracts:
        selection_logic.append("Prefer-abstracts mode penalized papers with missing or weak abstracts.")

    diagnostics = {
        "retrieval_funnel": {
            "retrieved_total": len(all_candidates),
            "after_filters": len(rule_ranked),
            "stage2_pool": len(stage2_pool),
            "final_count": len(final_ranked),
        },
        "retained_examples": retained_examples,
        "pushed_down_examples": pushed_down_examples,
        "selection_logic": selection_logic,
    }

    emit_progress(progress_callback, 86, "Retrieval and ranking complete.")

    return {
        "papers": final_ranked[:paper_count],
        "diagnostics": diagnostics
    }


@st.cache_data(ttl=60 * 30, show_spinner=False)
def search_papers_with_diagnostics(
    query: str,
    paper_count: int = 5,
    sort_mode: str = "Balanced",
    year_range=None,
    prefer_abstracts: bool = True,
    intent_profile=None,
    original_query=None,
    strict_core_only: bool = False,
    open_access_only: bool = False,
    source_filters=None,
):
    return search_papers_with_diagnostics_live(
        query=query,
        paper_count=paper_count,
        sort_mode=sort_mode,
        year_range=year_range,
        prefer_abstracts=prefer_abstracts,
        intent_profile=intent_profile,
        original_query=original_query,
        strict_core_only=strict_core_only,
        open_access_only=open_access_only,
        source_filters=source_filters,
        progress_callback=None,
    )


@st.cache_data(ttl=60 * 20, show_spinner=False)
def preview_search_results(raw_query: str, limit_per_source: int = 4):
    previews = []

    try:
        ss_results = search_semantic_scholar(raw_query, limit_per_source)
        for item in ss_results:
            previews.append({
                "source": item["source"],
                "title": item["title"],
                "year": item["year"],
                "summary": item["summary"][:300] if item["summary"] else "No abstract available."
            })
    except Exception:
        pass

    try:
        oa_results = search_openalex(raw_query, limit_per_source)
        for item in oa_results:
            previews.append({
                "source": item["source"],
                "title": item["title"],
                "year": item["year"],
                "summary": item["summary"][:300] if item["summary"] else "No abstract available."
            })
    except Exception:
        pass

    try:
        cr_results = search_crossref(raw_query, limit_per_source)
        for item in cr_results:
            previews.append({
                "source": item["source"],
                "title": item["title"],
                "year": item["year"],
                "summary": item["summary"][:300] if item["summary"] else "No abstract available."
            })
    except Exception:
        pass

    try:
        gs_results = search_google_scholar_serpapi(raw_query, min(limit_per_source, 3))
        for item in gs_results:
            previews.append({
                "source": item["source"],
                "title": item["title"],
                "year": item["year"],
                "summary": item["summary"][:300] if item["summary"] else "No abstract available."
            })
    except Exception:
        pass

    return previews[:10]


def fallback_query_options(user_query: str):
    return {
        "original_query": user_query,
        "needs_disambiguation": False,
        "recommended_index": 0,
        "options": [
            {
                "label": user_query,
                "search_query": user_query,
                "reason": "Fallback: failed to infer candidate meanings.",
                "confidence": 0.5,
                "intent_profile": {
                    "include": [],
                    "exclude": [],
                    "domain_bias": ""
                }
            }
        ]
    }


@st.cache_data(ttl=60 * 20, show_spinner=False)
def generate_query_options(user_query: str):
    previews = preview_search_results(user_query, limit_per_source=4)

    preview_text = "\n\n".join(
        [
            f"Source: {p['source']}\n"
            f"Title: {p['title']}\n"
            f"Year: {p['year']}\n"
            f"Summary: {p['summary']}"
            for p in previews
        ]
    ) if previews else "No preview results available."

    prompt = f"""
You are an academic search query analyst.

User query:
{user_query}

Here are preview search results retrieved using the raw query:
{preview_text}

Task:
Use BOTH the original query and the preview search results to infer the most likely academic meanings.
Then generate 3 to 5 candidate interpretations and search queries.

Return JSON only in this format:
{{
  "original_query": "{user_query}",
  "needs_disambiguation": true,
  "recommended_index": 0,
  "options": [
    {{
      "label": "...",
      "search_query": "...",
      "reason": "...",
      "confidence": 0.0,
      "intent_profile": {{
        "include": ["..."],
        "exclude": ["..."],
        "domain_bias": ""
      }}
    }}
  ]
}}

Rules:
- Rank the options from most likely to least likely
- recommended_index must point to the best option
- confidence must be between 0 and 1
- search_query should be concise and suitable for academic search
- expand abbreviations when appropriate
- intent_profile.include should contain concepts that SHOULD be boosted
- intent_profile.exclude should contain concepts that SHOULD be downweighted
- domain_bias can be values like "entertainment", "clinical", "education", or empty string
- DO NOT invent random interpretations that are not supported by the query or the preview results
- Return valid JSON only
"""

    try:
        result = ask_llm(prompt)
        parsed = safe_json_loads(result)

        if "options" not in parsed or not parsed["options"]:
            return fallback_query_options(user_query)

        for opt in parsed["options"]:
            try:
                opt["confidence"] = float(opt.get("confidence", 0.0))
            except Exception:
                opt["confidence"] = 0.0

            if "intent_profile" not in opt or not isinstance(opt["intent_profile"], dict):
                opt["intent_profile"] = {
                    "include": [],
                    "exclude": [],
                    "domain_bias": ""
                }

        if "recommended_index" not in parsed:
            parsed["recommended_index"] = 0

        return parsed

    except Exception:
        return fallback_query_options(user_query)