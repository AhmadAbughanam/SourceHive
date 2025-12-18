
# AI Resume Analyzer & Interview Screening System

An HR-driven system for **resume parsing, role-based scoring, and AI-assisted interview screening**.  
The system evaluates candidates objectively using **job templates defined by HR**, then validates shortlisted candidates through a **standardized AI quiz per job level**.

This platform provides **structured, explainable insights** to support hiring decisions — it does **not** automate hiring.

---

## 1. Purpose

The system helps HR teams to:
- Parse resumes accurately across formats
- Score candidates based on job-specific requirements
- Rank and shortlist candidates objectively
- Validate skills through an AI-generated interview quiz
- Review CV and quiz scores together in one dashboard

---

## 2. Core Design Principles

- HR defines all scoring rules
- Resume scoring is deterministic and explainable
- AI is used only where it adds value
- Quizzes are standardized per job level
- No autonomous hiring decisions
- No RAG or document memory systems

---

## 3. Phase 0 — Job Template Setup (HR)

Before candidates upload CVs, HR defines a **Job Template** that controls all evaluation logic.

### Job Template Includes
- Job title
- Job level: `Junior | Mid | Senior`
- Required resume sections
- Skills list:
  - Skill name
  - Type: `critical` or `preferred`
  - Weight (total = 100%)
  - Optional minimum years
- Education requirements
- Optional bonuses:
  - Certifications
  - Location match
  - Experience threshold

> HR defines *what matters*.  
> The system only evaluates.

---

## 4. Phase 1 — CV Upload & Parsing

### 4.1 Upload
Applicants upload:
- PDF (text-based or scanned)
- Image (JPG / PNG)
- DOCX (optional)

System actions:
- MIME + extension validation
- Secure file storage
- File hashing to detect duplicates

---

### 4.2 Parsing Pipeline

The system uses a layout-aware parsing approach.

#### Parsing Steps
1. Document type detection
2. OCR for scanned/image CVs
3. Layout detection (sections, columns, headings)
4. Structured data extraction

#### Extracted Information
- Contact information
- Education history
- Work experience (roles, companies, dates)
- Projects
- Skills (raw → hard / soft)
- Certifications
- Total years of experience
- Timeline flags (gaps, overlaps)

All extracted data is stored as a **canonical candidate profile**.

---

## 5. Phase 2 — Resume Scoring

### 5.1 Resume Structure Score
Evaluates CV completeness and formatting:
- Required sections present
- Missing critical sections

Outputs:
- Structure score (0–100)
- Missing section hints

---

### 5.2 Job Match Score (Primary Score)

Each CV is evaluated against the selected Job Template.

#### Scoring Signals
- Skill coverage (critical > preferred)
- Years of experience alignment
- Education fit
- Certifications bonus (if defined)

Scoring is **rule-based and deterministic**.

#### Example Output
```json
{
  "skill_match_score": 75,
  "experience_alignment": 80,
  "education_fit": 100,
  "final_cv_score": 78
}
```

---

## 6. Phase 3 — Ranking & Shortlisting

- Candidates are ranked by `final_cv_score`
- HR defines a cutoff score (e.g. ≥70%)
- Only shortlisted candidates move forward

---

## 7. Phase 4 — AI Interview Quiz Generation

### 7.1 Quiz Rules

- Standardized per job level
- Same difficulty for all candidates at the same level
- No references to CV wording or claimed experience
- Focused on job requirements only

### 7.2 Quiz Inputs

AI receives:

- Job Template
- Job level
- Required skills list

### 7.3 Quiz Structure

- Fixed number of questions
- Skill-based and scenario-based
- Aligned with role expectations

Example questions:

- "Explain how containerization improves deployment reliability."
- "How would you troubleshoot high latency in a production system?"

AI **only generates questions**.

---

## 8. Phase 5 — Quiz Execution

- Timed quiz
- Text-based answers
- Answers stored with metadata and timestamps

---

## 9. Phase 6 — Quiz Evaluation

### Evaluation Criteria

Each answer is evaluated for:

- Correctness
- Depth
- Relevance
- Clarity

AI outputs:

- Per-question score (0–1)
- Explanation
- Risk flags (vague or low-confidence answers)

Final output:

- Quiz score (0–100)
- Confidence level
- Risk indicators

---

## 10. Phase 7 — HR Dashboard

HR reviews both evaluation stages together.

### Candidate View

- CV score
- Quiz score
- Final combined score (HR-weighted)

Example:

```
CV Score:   78
Quiz Score: 72
Final:      75
```

### HR Actions

- Approve for interview
- Reject
- Add comments
- Update candidate status

---

## 11. Security & Operations

- File type validation and hashing
- Secure file storage
- Parameterized database queries
- Rate-limited uploads
- Daily database and file backups
- Parsing error logging and retry mechanisms

---

## 12. Technology Stack

- **Backend:** Python
- **Parsing:** pdfminer, PyMuPDF, PaddleOCR
- **AI:** LLM for quiz generation and evaluation
- **Database:** MySQL
- **UI:** Streamlit
- **API Layer:** FastAPI




