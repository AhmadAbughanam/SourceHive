# App/models.py
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class Candidate:
    id: Optional[int]
    name: str
    email: str
    phone: Optional[str]
    role: Optional[str]
    experience_years: float
    skills_hard: List[str] = field(default_factory=list)
    skills_soft: List[str] = field(default_factory=list)
    resume_score: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class JobDescription:
    id: Optional[int]
    role: str
    critical_skills: List[str]
    preferred_skills: List[str]