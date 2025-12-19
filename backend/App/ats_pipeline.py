"""
ATS pipeline utilities shared between the Streamlit prototype and the FastAPI backend.

This module canonicalizes skill tokens via the synonyms table and computes
weighted JD keyword matches so uploads have consistent scoring regardless of
document type.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Set
import re

# Default weights used when jd_keywords.weight is missing.
IMPORTANCE_WEIGHTS = {
    "critical": 2.0,
    "preferred": 1.0,
    "optional": 0.5,
}


def normalize_skill_token(text: str) -> str:
    """Normalize a skill token for fuzzy comparisons."""
    cleaned = re.sub(r"[^a-z0-9\+#\.\s/\-]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _best_variant_match(
    norm_token: str,
    variant_keys: Sequence[str],
    variant_map: Dict[str, str],
    threshold: float = 0.88,
) -> Optional[str]:
    """Return canonical form for the closest known variant above the threshold."""
    best_key = None
    best_ratio = 0.0
    for key in variant_keys or []:
        ratio = SequenceMatcher(None, norm_token, key).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_key = key
    if best_key and best_ratio >= threshold:
        return variant_map.get(best_key, best_key)
    return None


def canonicalize_token(
    token: str,
    variant_map: Optional[Dict[str, str]] = None,
    variant_keys: Optional[Sequence[str]] = None,
    threshold: float = 0.88,
) -> str:
    """Return the canonical skill token using synonyms + fuzzy fallback."""
    variant_map = variant_map or {}
    norm = normalize_skill_token(token)
    if not norm:
        return ""
    if norm in variant_map:
        return variant_map[norm]
    variant_keys = variant_keys or list(variant_map.keys())
    best = _best_variant_match(norm, variant_keys, variant_map, threshold=threshold)
    return best or norm


def canonicalize_skills(
    skills: Iterable[str],
    variant_map: Optional[Dict[str, str]] = None,
    variant_keys: Optional[Sequence[str]] = None,
    threshold: float = 0.88,
) -> Set[str]:
    """Canonicalize a list of skills into a stable set."""
    canonical = set()
    variant_map = variant_map or {}
    variant_keys = variant_keys or list(variant_map.keys())
    for token in skills or []:
        canonical_token = canonicalize_token(
            token,
            variant_map=variant_map,
            variant_keys=variant_keys,
            threshold=threshold,
        )
        if canonical_token:
            canonical.add(canonical_token)
    return canonical


def _coerce_weight(weight_value, importance_value: Optional[str]) -> float:
    """Return a numeric weight using stored value or the importance fallback."""
    try:
        weight = float(weight_value)
        if weight > 0:
            return weight
    except (TypeError, ValueError):
        weight = None
    importance = (importance_value or "").strip().lower()
    return IMPORTANCE_WEIGHTS.get(importance, 1.0)


def _token_present(
    canonical_keyword: str,
    resume_tokens: Set[str],
    fuzzy_threshold: float = 0.9,
) -> bool:
    """Return True if the canonical keyword exists in the resume token set."""
    if canonical_keyword in resume_tokens:
        return True
    for token in resume_tokens:
        if SequenceMatcher(None, canonical_keyword, token).ratio() >= fuzzy_threshold:
            return True
    return False


def compute_weighted_jd_match(
    resume_skills: Sequence[str],
    jd_keywords: Sequence[Dict[str, str]],
    variant_map: Optional[Dict[str, str]] = None,
    variant_keys: Optional[Sequence[str]] = None,
    *,
    category_map: Optional[Dict[str, str]] = None,
    fuzzy_threshold: float = 0.9,
) -> Optional[Dict[str, object]]:
    """
    Compute a weighted JD match score.

    Args:
        resume_skills: hard/soft skill tokens extracted from the resume.
        jd_keywords: iterable of dict rows with keys (keyword, importance, weight).
        variant_map/variant_keys: synonym canonicalization helpers.
        category_map: optional categories for debug/analytics.
        fuzzy_threshold: ratio threshold for fuzzy token matches.

    Returns:
        dict with score, matched keywords, missing keywords, and weight stats.
    """
    if not resume_skills or not jd_keywords:
        return None

    variant_map = variant_map or {}
    variant_keys = variant_keys or list(variant_map.keys())
    resume_tokens = canonicalize_skills(
        resume_skills, variant_map=variant_map, variant_keys=variant_keys
    )
    if not resume_tokens:
        return None

    matched_keywords: List[str] = []
    missing_keywords: List[str] = []
    matched_weight = 0.0
    total_weight = 0.0

    for row in jd_keywords:
        raw_keyword = (row.get("keyword") or "").strip()
        if not raw_keyword:
            continue
        canonical_kw = canonicalize_token(
            raw_keyword, variant_map=variant_map, variant_keys=variant_keys
        )
        weight = _coerce_weight(row.get("weight"), row.get("importance"))
        total_weight += weight
        if _token_present(canonical_kw, resume_tokens, fuzzy_threshold=fuzzy_threshold):
            matched_keywords.append(raw_keyword)
            matched_weight += weight
        else:
            missing_keywords.append(raw_keyword)

    if total_weight <= 0:
        return None

    score = round((matched_weight / total_weight) * 100, 2)
    return {
        "score": score,
        "matched": matched_keywords,
        "missing": missing_keywords,
        "total": len(matched_keywords) + len(missing_keywords),
        "matched_weight": matched_weight,
        "total_weight": total_weight,
        "coverage": matched_weight / total_weight if total_weight else 0.0,
        "categories": category_map or {},
    }

