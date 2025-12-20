import os
import re
from geotext import GeoText
from PyPDF2 import PdfReader
import spacy
from difflib import SequenceMatcher
from typing import Dict, Iterable, Set, Tuple, List
from functools import lru_cache
from spacy.matcher import PhraseMatcher

try:
    from sentence_transformers import SentenceTransformer
    _embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
except Exception:
    _embedder = None

try:
    from App.document_processing import analyze_and_extract as _analyze_and_extract
except ModuleNotFoundError:
    try:
        from document_processing import analyze_and_extract as _analyze_and_extract
    except ModuleNotFoundError:
        _analyze_and_extract = None

@lru_cache(maxsize=1)
def get_nlp():
    return spacy.load("en_core_web_sm")

# -----------------------------
# TEXT EXTRACTION
# -----------------------------
def _basic_extract_text(resume_path):
    """Legacy text extraction fallback when OCR helpers are unavailable."""
    ext = os.path.splitext(resume_path)[1].lower()
    text = ""

    if ext == ".pdf":
        with open(resume_path, "rb") as f:
            reader = PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
    elif ext in [".txt", ".doc", ".docx"]:
        with open(resume_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    return text.strip()


def extract_text_with_metadata(resume_path, original_name=None):
    """
    Extract resume text along with parsing metadata.

    Falls back to the simple extractor when OCR dependencies are missing.
    """
    if _analyze_and_extract:
        try:
            payload = _analyze_and_extract(resume_path, original_name=original_name)
            return payload.get("text") or "", payload
        except Exception:
            pass

    text = _basic_extract_text(resume_path)
    return text, {
        "doc_kind": "unknown",
        "file_mime": None,
        "ocr_used": False,
        "extraction_method": "legacy",
        "extraction_error": None,
        "text_length": len(text),
        "details": {},
    }


def extract_text(resume_path):
    """Backward-compatible helper that only returns text."""
    text, _ = extract_text_with_metadata(resume_path)
    return text


def clean_extracted_text(text):
    """Normalize whitespace and remove junk characters."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x00-\x7F]+", " ", text)  # remove non-ascii
    return text.strip()


# -----------------------------
# BASIC FIELD EXTRACTION
# -----------------------------
def extract_name(doc):
    """Extract probable name using SpaCy's entity recognition."""
    for ent in doc.ents:
        if ent.label_ == "PERSON" and 2 <= len(ent.text.split()) <= 3:
            return ent.text.strip()
    return None


def extract_email(text):
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0).lower().strip() if match else None


def extract_mobile_number(text, custom_regex=None):
    regex = custom_regex or r"(\+?\d[\d\s\-]{7,}\d)"
    match = re.search(regex, text)
    if not match:
        return None
    phone = re.sub(r"[^\d+]", "", match.group(0))
    if phone.startswith("962") and len(phone) > 9:
        phone = "+" + phone
    return phone


def extract_skills(doc, skills_file=None):
    """
    Return dict of hard/soft skills found (raw tokens).

    Uses PhraseMatcher so multi-word skills like "machine learning" are detected.
    """
    base_dir = os.path.dirname(skills_file) if skills_file else os.path.join(os.path.dirname(__file__), "data")
    hard_skills_path = os.path.join(base_dir, "hard_skills.txt")
    soft_skills_path = os.path.join(base_dir, "soft_skills.txt")

    hard_skills = []
    soft_skills = []
    if os.path.exists(hard_skills_path):
        with open(hard_skills_path, "r", encoding="utf-8", errors="ignore") as fh:
            hard_skills = [line.strip() for line in fh.read().splitlines() if line.strip()]
    if os.path.exists(soft_skills_path):
        with open(soft_skills_path, "r", encoding="utf-8", errors="ignore") as fh:
            soft_skills = [line.strip() for line in fh.read().splitlines() if line.strip()]

    found_hard: Set[str] = set()
    found_soft: Set[str] = set()

    matcher_hard = PhraseMatcher(doc.vocab, attr="LOWER")
    matcher_soft = PhraseMatcher(doc.vocab, attr="LOWER")
    nlp = get_nlp()

    hard_patterns = [nlp.make_doc(skill) for skill in hard_skills]
    soft_patterns = [nlp.make_doc(skill) for skill in soft_skills]
    if hard_patterns:
        matcher_hard.add("HARD", hard_patterns)
    if soft_patterns:
        matcher_soft.add("SOFT", soft_patterns)

    for _match_id, start, end in matcher_hard(doc):
        token = normalize_skill_token(doc[start:end].text)
        if token:
            found_hard.add(token)

    for _match_id, start, end in matcher_soft(doc):
        token = normalize_skill_token(doc[start:end].text)
        if token and token not in found_hard:
            found_soft.add(token)

    return {
        "hard": sorted(found_hard),
        "soft": sorted(found_soft),
    }

# -----------------------------
# SKILL NORMALIZATION
# -----------------------------
def normalize_skill_token(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\+#\.\s/\-]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def canonicalize_skills(
    skills: Iterable[str],
    variant_map: Dict[str, str],
    variant_keys: Iterable[str],
    threshold: float = 0.88
) -> Set[str]:
    """Map skills to canonical form via synonyms + fuzzy."""
    canonical = set()
    for skill in skills or []:
        norm = normalize_skill_token(skill)
        if not norm:
            continue
        if norm in variant_map:
            canonical.add(variant_map[norm])
            continue
        best_key, best_ratio = None, 0.0
        for key in variant_keys:
            ratio = SequenceMatcher(None, norm, key).ratio()
            if ratio > best_ratio:
                best_ratio, best_key = ratio, key
        if best_key and best_ratio >= threshold:
            canonical.add(variant_map[best_key])
        else:
            canonical.add(norm)
    return canonical


def embed_text(text: str):
    """Return embedding vector list for text or None if model missing."""
    if not _embedder or not text:
        return None
    try:
        vec = _embedder.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception:
        return None

# -----------------------------
# DEGREE EXTRACTION (enhanced)
# -----------------------------
def extract_degree(text):
    """Robust detection of academic degrees (Bachelor, Master, PhD, Diploma)."""
    text_clean = re.sub(r"[^A-Za-z\s\.]", " ", text)
    text_clean = re.sub(r"\s+", " ", text_clean)
    matches = []

    # Broad detection patterns (handles BS, B.Sc, Bachelor’s, etc.)
    degree_patterns = [
        r"\b(b[\.\s]?(sc|s|eng|tech|com)|bachelor'?s?)\b.*?(computer|science|engineering|information|technology|ai|cs|it|software|systems)?",
        r"\b(m[\.\s]?(sc|s|eng|tech|com)|master'?s?)\b.*?(computer|science|engineering|information|technology|ai|cs|it|software|systems)?",
        r"\b(ph\.?\s*d|doctorate|doctoral)\b",
        r"\b(associate'?s?\s?degree|diploma)\b"
    ]

    for pattern in degree_patterns:
        for m in re.finditer(pattern, text_clean, re.IGNORECASE):
            degree = m.group().strip()
            degree = re.sub(r"\s+", " ", degree)
            matches.append(degree.title())

    # Normalize common abbreviations to readable full forms
    clean_matches = []
    for degree in matches:
        if re.search(r"\bb[\.\s]?(sc|s|eng|tech|com)|bachelor", degree, re.IGNORECASE):
            degree = re.sub(r"(?i)\b(b[\.\s]?(sc|s|eng|tech|com)|bachelor('?s)?)\b", "Bachelor of Science", degree)
        elif re.search(r"\bm[\.\s]?(sc|s|eng|tech|com)|master", degree, re.IGNORECASE):
            degree = re.sub(r"(?i)\b(m[\.\s]?(sc|s|eng|tech|com)|master('?s)?)\b", "Master of Science", degree)
        elif re.search(r"ph", degree, re.IGNORECASE):
            degree = "Doctor of Philosophy"
        clean_matches.append(degree.strip())

    # Remove noise & duplicates
    unique = list({d for d in clean_matches if len(d) > 5})
    return unique if unique else None


# -----------------------------
# ADDRESS EXTRACTION
# -----------------------------
def extract_address(text):
    """Use GeoText to detect city and country names."""
    places = GeoText(text)
    city = places.cities[0] if places.cities else None
    country = places.countries[0] if places.countries else None
    if city or country:
        return f"{city or ''}, {country or ''}".strip(", ")
    return None


def normalize_country_city(address):
    """Normalize capitalization and fix abbreviations."""
    if not address:
        return (None, None)
    city = None
    country = None
    parts = re.split(r"[,/|-]+", address)
    if len(parts) >= 2:
        city, country = parts[0].strip(), parts[-1].strip()
    elif len(parts) == 1:
        city = parts[0].strip()

    if city:
        city = city.title()
    if country:
        country = country.title()

    mapping = {
        "Uae": "United Arab Emirates",
        "Ksa": "Saudi Arabia",
        "Usa": "United States",
        "Uk": "United Kingdom",
        "Jor": "Jordan"
    }
    if country in mapping:
        country = mapping[country]
    if not country and city == "Amman":
        country = "Jordan"

    return (city, country)


# -----------------------------
# EXPERIENCE EXTRACTION
# -----------------------------
def extract_experience_info(text):
    """Extract company names, job titles, and total experience years."""
    experience_info = {
        "companies": [],
        "titles": [],
        "total_years": 0
    }

    # Patterns
    company_patterns = [
        r"at\s+([A-Z][A-Za-z&\s]+)",
        r"for\s+([A-Z][A-Za-z&\s]+)"
    ]
    title_patterns = [
        r"(software engineer|developer|data scientist|ai engineer|intern|manager|researcher|analyst|specialist|technician|consultant)"
    ]
    year_patterns = [
        r"(\d+)\+?\s*(years|yrs)\s*(of)?\s*(experience|exp)?"
    ]

    for pat in company_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            company = m.group(1).strip()
            if len(company.split()) <= 5:
                experience_info["companies"].append(company)

    for pat in title_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            title = m.group(1).title()
            experience_info["titles"].append(title)

    # Extract years of experience
    for pat in year_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                years = int(m.group(1))
                experience_info["total_years"] = max(experience_info["total_years"], years)
            except:
                pass

    # NLP-based fallback (for organization detection)
    doc = get_nlp()(text)
    for ent in doc.ents:
        if ent.label_ == "ORG" and ent.text not in experience_info["companies"]:
            experience_info["companies"].append(ent.text)

    experience_info["companies"] = list(set(experience_info["companies"]))
    experience_info["titles"] = list(set(experience_info["titles"]))
    return experience_info


# -----------------------------
# CERTIFICATIONS & TITLES
# -----------------------------
def extract_certifications(text: str) -> List[str]:
    """Lightweight cert detection using keyword list."""
    cert_patterns = [
        r"\b(AWS\s+Certified\s+(Solutions\s+Architect|Developer|SysOps|Machine\s+Learning))\b",
        r"\b(Azure\s+(Data\s+Engineer|Solutions\s+Architect|Administrator))\b",
        r"\b(GCP\s+(Professional|Associate)\s+[A-Za-z ]+)\b",
        r"\b(PMP|Prince2)\b",
        r"\b(CISSP|CISM|CEH)\b",
        r"\b(CompTIA\s+(Security\+|Network\+|A\+))\b",
        r"\b(ISTQB|Scrum\s+Master|CSM)\b"
    ]
    found = set()
    for pat in cert_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            found.add(re.sub(r"\s+", " ", m.group(0)).strip())
    return sorted(found)


def detect_seniority_level(text: str) -> str:
    """Heuristic seniority detection."""
    text_low = text.lower()
    if re.search(r"\bsenior|lead|staff|principal|head\b", text_low):
        return "senior"
    if re.search(r"\bmid\b", text_low):
        return "mid"
    if re.search(r"\bjunior|jr\.?\b", text_low):
        return "junior"
    return ""


def split_sentences(text: str) -> List[str]:
    if not text:
        return []
    doc = get_nlp()(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]


# -----------------------------
# MISC
# -----------------------------
def get_number_of_pages(resume_path):
    try:
        reader = PdfReader(open(resume_path, "rb"))
        return len(reader.pages)
    except Exception:
        return None
