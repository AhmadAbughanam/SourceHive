# App/scoring.py
from typing import List
from App.config import SCORING_RULES

def compute_overlap(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    return len(set(a) & set(b)) / len(set(a))

def compute_score(candidate_skills, jd_critical, jd_preferred, semantic_sim=0.0):
    overlap_critical = compute_overlap(candidate_skills, jd_critical)
    overlap_preferred = compute_overlap(candidate_skills, jd_preferred)

    score = (
        overlap_critical * SCORING_RULES["critical_weight"] +
        overlap_preferred * SCORING_RULES["preferred_weight"] +
        semantic_sim * SCORING_RULES["semantic_weight"]
    )
    return round(score * 100, 2)