import re
import json
import numpy as np
from difflib import SequenceMatcher
from sentence_transformers import SentenceTransformer, util
from App.config import SCORING_RULES


# ------------------------------------------------------
# MODEL INIT (semantic similarity)
# ------------------------------------------------------
# Lightweight but high-quality model for semantic embeddings
try:
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
except Exception:
    model = None
    print("[WARN] Semantic model unavailable — semantic scoring disabled.")


# ------------------------------------------------------
# BASIC HELPERS
# ------------------------------------------------------
def normalize(text):
    """Lowercase and clean text."""
    return re.sub(r"[^a-z0-9\s+]", " ", text.lower()).strip()


def normalize_skill_token(text):
    """Normalize a skill token for consistent comparisons."""
    cleaned = re.sub(r"[^a-z0-9\+#\.\s/\-]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def build_variant_map(synonym_dict):
    """
    Turn a synonym dict into variant→canonical map.
    Expected format: {"ai": ["artificial intelligence"], "ml": ["machine learning", "ml engineer"]}
    """
    variant_map = {}
    if not synonym_dict:
        return variant_map, []

    for base, syns in synonym_dict.items():
        canonical = normalize_skill_token(syns[0] if syns else base)
        base_norm = normalize_skill_token(base)
        if base_norm:
            variant_map[base_norm] = canonical
        if syns:
            for s in syns:
                s_norm = normalize_skill_token(s)
                if s_norm:
                    variant_map[s_norm] = canonical
                    variant_map.setdefault(canonical, canonical)
        if canonical:
            variant_map.setdefault(canonical, canonical)

    return variant_map, list(variant_map.keys())


def canonicalize_skills(skills, variant_map, variant_keys, threshold=0.88):
    """Map skills to their canonical forms using synonyms + fuzzy fallback."""
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


def cover_keywords(resume_set, jd_set, fuzzy_threshold=0.9):
    """Count coverage of JD keywords within resume set with fuzzy tolerance."""
    matched = set()
    for kw in jd_set:
        if kw in resume_set:
            matched.add(kw)
        else:
            if any(SequenceMatcher(None, kw, r).ratio() >= fuzzy_threshold for r in resume_set):
                matched.add(kw)
    ratio = len(matched) / len(jd_set) if jd_set else 0
    return len(matched), round(ratio, 3)


def compute_semantic_similarity(resume_text, jd_text):
    """Compute semantic similarity between resume and JD."""
    if not model:
        return 0.0

    resume_emb = model.encode(resume_text, convert_to_tensor=True)
    jd_emb = model.encode(jd_text, convert_to_tensor=True)
    score = util.cos_sim(resume_emb, jd_emb).item()
    return round(score, 3)


# ------------------------------------------------------
# MAIN MATCHING PIPELINE
# ------------------------------------------------------
def compute_role_suitability(resume_data, jd_data, synonym_dict=None):
    """
    Blend multiple scores:
        - exact keyword coverage
        - synonym coverage
        - semantic similarity
    and produce final suitability score (0–100)
    """

    if not resume_data or not jd_data:
        return {"score": 0, "reason": "Incomplete data"}

    # Extract
    resume_skills = resume_data.get("skills", [])
    resume_text = " ".join(resume_skills)
    jd_text = jd_data.get("description", "")
    jd_critical = jd_data.get("critical_keywords", [])
    jd_preferred = jd_data.get("preferred_keywords", [])

    variant_map, variant_keys = build_variant_map(synonym_dict or {})
    resume_canon = canonicalize_skills(resume_skills, variant_map, variant_keys)
    jd_critical_canon = canonicalize_skills(jd_critical, variant_map, variant_keys)
    jd_preferred_canon = canonicalize_skills(jd_preferred, variant_map, variant_keys)

    # Compute scores
    exact_critical, ratio_critical = cover_keywords(resume_canon, jd_critical_canon)
    exact_preferred, ratio_preferred = cover_keywords(resume_canon, jd_preferred_canon)
    combined_jd = jd_critical_canon.union(jd_preferred_canon)
    syn_ratio = cover_keywords(resume_canon, combined_jd)[1]

    # Semantic similarity (resume text vs JD text)
    semantic_sim = compute_semantic_similarity(resume_text, jd_text)

    # Weighted blend
    w1 = SCORING_RULES["critical_weight"]
    w2 = SCORING_RULES["preferred_weight"]
    w3 = SCORING_RULES["semantic_weight"]

    raw_score = (ratio_critical * w1 + ratio_preferred * w2 + semantic_sim * w3) * 100
    final_score = round(min(raw_score, 100), 2)

    result = {
        "exact_matches": {"critical": exact_critical, "preferred": exact_preferred},
        "ratios": {"critical": ratio_critical, "preferred": ratio_preferred, "semantic": semantic_sim},
        "final_suitability_score": final_score,
        "synonym_ratio": syn_ratio,
    }

    return result


# ------------------------------------------------------
# TEST / DEBUG
# ------------------------------------------------------
if __name__ == "__main__":
    resume_data = {
        "skills": ["python", "machine learning", "deep learning", "flutter", "ai"],
    }

    jd_data = {
        "description": "We are looking for a Python and AI Engineer with experience in machine learning and NLP.",
        "critical_keywords": ["python", "machine learning", "ai"],
        "preferred_keywords": ["nlp", "pytorch", "data science"]
    }

    synonyms = {"ai": ["artificial intelligence"], "ml": ["machine learning"]}

    result = compute_role_suitability(resume_data, jd_data, synonyms)
    print(json.dumps(result, indent=4))
