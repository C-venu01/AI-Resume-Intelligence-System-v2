"""
Resume Analyzer — SpaCy NER + Regex
Parses resumes to extract structured candidate information.
Uses SpaCy for Named Entity Recognition and regex for pattern matching.
"""

import re
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

# ==================== LOAD SPACY MODEL ====================
# We use en_core_web_sm — lightweight but effective for NER
# Falls back to regex-only extraction if SpaCy is unavailable
try:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        print("[Analyzer] SpaCy model not found. Downloading en_core_web_sm...")
        from spacy.cli import download
        download("en_core_web_sm")
        nlp = spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except ImportError:
    nlp = None
    SPACY_AVAILABLE = False
    print("[Analyzer] SpaCy not installed. Using regex-only extraction (name detection may be less accurate).")


# ==================== TECHNOLOGY DATABASE ====================
# 60+ technologies organized by category
TECH_DATABASE = {
    # Programming Languages
    "Python": ["python"],
    "JavaScript": ["javascript", " js ", "es6", "es2015"],
    "TypeScript": ["typescript", " ts "],
    "Java": [" java ", "java,", "java."],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", "c sharp"],
    "Go": [" go ", "golang"],
    "Rust": [" rust "],
    "Ruby": [" ruby "],
    "PHP": [" php "],
    "Swift": [" swift "],
    "Kotlin": ["kotlin"],
    "R": [" r ", "r programming"],
    "Scala": ["scala"],
    "Dart": [" dart "],

    # Frontend
    "React": ["react", "reactjs", "react.js"],
    "Angular": ["angular", "angularjs"],
    "Vue.js": ["vue", "vuejs", "vue.js"],
    "Next.js": ["next.js", "nextjs"],
    "HTML/CSS": ["html", "css"],
    "Tailwind CSS": ["tailwind"],
    "Bootstrap": ["bootstrap"],
    "jQuery": ["jquery"],
    "Svelte": ["svelte"],

    # Backend
    "Node.js": ["node.js", "nodejs", "node js"],
    "Express.js": ["express", "expressjs"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring Boot": ["spring boot", "springboot"],
    "ASP.NET": ["asp.net", "aspnet"],
    "Laravel": ["laravel"],
    "Ruby on Rails": ["rails", "ruby on rails"],

    # Databases
    "SQL": [" sql"],
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "SQLite": ["sqlite"],
    "DynamoDB": ["dynamodb"],
    "Cassandra": ["cassandra"],
    "Elasticsearch": ["elasticsearch", "elastic search"],

    # Cloud & DevOps
    "AWS": [" aws ", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": [" gcp ", "google cloud"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", " k8s"],
    "Terraform": ["terraform"],
    "Ansible": ["ansible"],
    "Jenkins": ["jenkins"],
    "GitHub Actions": ["github actions"],
    "CI/CD": ["ci/cd", "cicd"],
    "Linux": ["linux", "ubuntu", "centos"],
    "Nginx": ["nginx"],

    # AI/ML
    "Machine Learning": ["machine learning", " ml "],
    "Deep Learning": ["deep learning", " dl "],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    "Keras": ["keras"],
    "NLP": [" nlp ", "natural language processing"],
    "Computer Vision": ["computer vision", "opencv"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Hugging Face": ["hugging face", "huggingface", "transformers"],

    # Data Tools
    "Apache Spark": ["apache spark", "pyspark", " spark "],
    "Hadoop": ["hadoop"],
    "Kafka": ["kafka"],
    "Airflow": ["airflow"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],

    # Other
    "REST API": ["rest api", "restful"],
    "GraphQL": ["graphql"],
    "Git": [" git ", "github", "gitlab", "bitbucket"],
    "Microservices": ["microservices", "micro-services"],
    "Agile": ["agile", "scrum", "kanban"],
}

# ==================== CERTIFICATION DATABASE ====================
CERTIFICATIONS = {
    "AWS Certified": ["aws certified", "aws certification", "aws solutions architect",
                      "aws developer", "aws sysops", "aws cloud practitioner"],
    "Azure Certified": ["azure certified", "az-900", "az-104", "az-204", "az-305",
                        "microsoft certified"],
    "Google Cloud Certified": ["google cloud certified", "gcp certified",
                                "associate cloud engineer"],
    "Kubernetes (CKA/CKAD)": ["cka", "ckad", "certified kubernetes"],
    "Docker Certified": ["docker certified", "dca"],
    "Terraform Certified": ["terraform certified", "terraform associate"],
    "PMP": ["pmp", "project management professional"],
    "Scrum Master": ["scrum master", "csm", "psm"],
    "CompTIA": ["comptia", "security+", "network+", "a+"],
    "CISSP": ["cissp"],
    "Data Science Cert": ["data science certification", "ibm data science",
                          "google data analytics"],
}

# ==================== SOFT SKILLS ====================
SOFT_SKILLS = [
    "leadership", "communication", "teamwork", "problem solving",
    "problem-solving", "analytical", "critical thinking", "creative",
    "adaptable", "time management", "collaboration", "mentoring",
    "presentation", "project management", "decision making",
    "strategic planning", "negotiation", "conflict resolution",
]

# ==================== EDUCATION PATTERNS ====================
DEGREE_PATTERNS = [
    (r"(?:ph\.?d|doctorate|doctor of philosophy)", "Ph.D."),
    (r"(?:m\.?tech|master of technology)", "M.Tech"),
    (r"(?:m\.?s\.?|master of science)", "M.S."),
    (r"(?:m\.?e\.?|master of engineering)", "M.E."),
    (r"(?:mba|master of business)", "MBA"),
    (r"(?:m\.?c\.?a|master of computer)", "MCA"),
    (r"(?:b\.?tech|bachelor of technology)", "B.Tech"),
    (r"(?:b\.?s\.?|bachelor of science)", "B.S."),
    (r"(?:b\.?e\.?|bachelor of engineering)", "B.E."),
    (r"(?:b\.?c\.?a|bachelor of computer)", "BCA"),
    (r"(?:b\.?com|bachelor of commerce)", "B.Com"),
    (r"(?:diploma)", "Diploma"),
]


def analyze_resume(text: str, filename: str = "") -> Dict:
    """
    Analyze resume text and extract structured information.
    
    Args:
        text: Raw resume text.
        filename: Original filename for reference.
    
    Returns:
        Dictionary with all extracted candidate information.
    """
    try:
        text_lower = text.lower()
        doc = nlp(text) if SPACY_AVAILABLE else None

        # Extract all fields
        name, name_confidence, name_evidence = _extract_name(doc, text)
        email = _extract_email(text)
        phone = _extract_phone(text)
        linkedin = _extract_linkedin(text)
        experience_years, internship_years, experience_evidence = (
            _extract_experience_years(text, doc)
        )
        experience_level = _determine_experience_level(
            experience_years, text_lower
        )
        technologies = _extract_technologies(text_lower)
        certifications = _extract_certifications(text_lower)
        soft_skills = _extract_soft_skills(text_lower)
        education = _extract_education(text_lower)
        cgpa = _extract_cgpa(text)
        projects_count = _count_projects(text_lower)
        achievements = _extract_achievements(text)
        specialization = _determine_specialization(text_lower, technologies)

        # Calculate score
        score = calculate_candidate_score(
            technologies, experience_years, achievements,
            projects_count, cgpa, certifications, soft_skills
        )

        # Generate summary
        summary = _generate_summary(
            name, experience_level, specialization,
            experience_years, technologies
        )

        return {
            "candidate_name": name,
            "email": email,
            "phone": phone,
            "linkedin": linkedin,
            "experience_years": experience_years,
            "internship_experience_years": internship_years,
            "experience_level": experience_level,
            "name_confidence": name_confidence,
            "name_evidence": name_evidence,
            "experience_evidence": experience_evidence,
            "specialization": specialization,
            "technologies": technologies,
            "certifications": certifications,
            "soft_skills": soft_skills,
            "education": education,
            "cgpa": cgpa,
            "projects_count": projects_count,
            "notable_achievements": achievements[:5],
            "overall_score": score,
            "candidate_summary": summary,
            "filename": filename,
        }

    except Exception as e:
        print(f"[Analyzer] Analysis failed: {type(e).__name__}")
        return _error_result(filename)


# ==================== EXTRACTION FUNCTIONS ====================

_NAME_NOT_DETECTED = "Name not detected"
_NAME_SECTION_HEADERS = {
    "summary", "profile", "objective", "skills", "technical skills",
    "experience", "work experience", "professional experience",
    "employment history", "work history", "education", "projects",
    "certifications", "awards", "publications", "interests", "references",
    "career objective", "professional summary",
}
_NON_NAME_TERMS = {
    "aws", "azure", "gcp", "java", "python", "javascript", "typescript",
    "docker", "kubernetes", "react", "angular", "jupyter", "prometheus",
    "pandas", "numpy", "quick sight", "quicksight", "tableau", "power bi",
    "jenkins", "terraform", "ansible", "linux", "github", "git", "html",
    "css", "sql", "node", "spark", "hadoop", "kafka", "airflow", "flask",
    "django", "fastapi", "machine learning", "data science", "deep learning",
    "software engineer", "software developer", "web developer", "full stack",
    "bachelor", "master", "b tech", "m tech", "b e", "m e", "mba", "bca",
    "mca", "computer science", "information technology", "resume", "curriculum vitae",
    "email", "phone", "mobile", "address", "objective", "summary", "experience",
    "education", "skills", "projects", "profile", "contact", "references",
    "certifications", "internship", "professional experience", "work history",
    "andhra pradesh", "telangana", "karnataka", "tamil nadu", "maharashtra",
    "hyderabad", "bangalore", "chennai", "mumbai", "delhi", "pune", "kolkata",
    "india", "usa", "new york", "california", "london",
}
_NAME_TOKEN_RE = re.compile(r"[^\W\d_]+(?:[.'’\-][^\W\d_]+)*\.?", re.UNICODE)
_NAME_TITLES = {"dr", "mr", "mrs", "ms", "miss", "prof"}
_CONTACT_RE = re.compile(
    r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+?\d[\d\s().-]{7,}\d)|"
    r"https?://\S+|linkedin\.com/\S+)",
    re.IGNORECASE,
)


def _clean_name_candidate(value: str) -> str:
    """Remove common honorifics while preserving initials and name punctuation."""
    tokens = value.strip().split()
    while tokens and tokens[0].rstrip(".").casefold() in _NAME_TITLES:
        tokens.pop(0)
    return " ".join(tokens).strip(" ,;:")


def _is_plausible_name(value: str, ner_confirmed: bool = False) -> bool:
    """Reject headings, role titles, and known technical terms before scoring."""
    candidate = _clean_name_candidate(value)
    tokens = candidate.split()
    if not candidate or len(candidate) > 70 or not 1 <= len(tokens) <= 6:
        return False
    if any(not _NAME_TOKEN_RE.fullmatch(token) for token in tokens):
        return False

    normalized = re.sub(r"[^\w]+", " ", candidate.casefold()).strip()
    words = normalized.split()
    if normalized in _NON_NAME_TERMS or any(
        re.sub(r"[^\w]+", " ", term.casefold()).strip() == normalized
        for term in _NON_NAME_TERMS
    ):
        return False
    if any(word in _NON_NAME_TERMS for word in words):
        return False

    meaningful_tokens = [
        token.rstrip(".").replace("'", "").replace("’", "").replace("-", "")
        for token in tokens
    ]
    if not any(len(token) >= 2 for token in meaningful_tokens):
        return False
    if len(tokens) == 1 and not ner_confirmed:
        return False

    title_words = {
        "engineer", "developer", "analyst", "manager", "architect",
        "consultant", "designer", "scientist", "administrator", "specialist",
        "intern", "student", "graduate", "technician", "director", "lead",
    }
    if any(token.casefold().rstrip(".") in title_words for token in tokens):
        return False
    return True


def _extract_name(doc, text: str) -> Tuple[str, float, Dict]:
    """Score validated name candidates from the resume header and nearby NER."""
    lines = text.splitlines()
    header_lines: List[Tuple[int, str]] = []
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if index > 14 or len(header_lines) >= 10:
            break
        header = re.sub(r"^[\W\d_]+|[\W\d_]+$", "", line.casefold()).strip()
        if header in _NAME_SECTION_HEADERS:
            break
        header_lines.append((index, line))

    header_end = max((line_no for line_no, _ in header_lines), default=-1)
    person_entities = set()
    if doc is not None:
        for entity in doc.ents:
            if entity.label_ == "PERSON":
                entity_line = text.count("\n", 0, entity.start_char)
                if entity_line <= header_end:
                    person_entities.add(
                        re.sub(r"\s+", " ", _clean_name_candidate(entity.text)).casefold()
                    )

    email_or_phone_lines = {
        line_no for line_no, line in header_lines if _CONTACT_RE.search(line)
    }
    candidates: Dict[str, Tuple[float, int, bool, bool]] = {}
    for line_no, line in header_lines:
        fragments = re.split(r"\s*[|•·]\s*", line)
        for fragment in fragments:
            fragment = _CONTACT_RE.sub(" ", fragment).strip()
            if ":" in fragment:
                label, value = fragment.split(":", 1)
                if label.strip().casefold() not in {"name", "candidate", "full name"}:
                    continue
                fragment = value.strip()
            if len(fragment) > 70:
                continue
            candidate = _clean_name_candidate(fragment)
            normalized = re.sub(r"\s+", " ", candidate).casefold()
            ner_confirmed = normalized in person_entities
            if not _is_plausible_name(candidate, ner_confirmed):
                continue

            nearby_contact = any(
                abs(line_no - contact_line) <= 2
                for contact_line in email_or_phone_lines
            )
            words = candidate.split()
            well_cased = all(
                word[0].isupper() or word.isupper()
                for word in words if word and word[0].isalpha()
            )
            confidence = 0.45
            if len(candidates) == 0 and line_no <= 2:
                confidence += 0.25
            if nearby_contact:
                confidence += 0.15
            if well_cased:
                confidence += 0.10
            if ner_confirmed:
                confidence += 0.20
            confidence = min(confidence, 0.99)

            previous = candidates.get(normalized)
            if previous is None or confidence > previous[0]:
                candidates[normalized] = (
                    confidence, line_no, ner_confirmed, nearby_contact
                )

    if not candidates:
        return _NAME_NOT_DETECTED, 0.0, {
            "method": "header_context_and_ner",
            "status": "no_confident_candidate",
            "candidate_count": 0,
        }

    normalized_name, (confidence, line_no, ner_confirmed, nearby_contact) = max(
        candidates.items(), key=lambda item: item[1][0]
    )
    if confidence < 0.68:
        return _NAME_NOT_DETECTED, confidence, {
            "method": "header_context_and_ner",
            "status": "below_confidence_threshold",
            "candidate_count": len(candidates),
            "header_line": line_no,
        }

    original_line = lines[line_no].strip()
    for fragment in re.split(r"\s*[|•·]\s*", original_line):
        cleaned = _clean_name_candidate(_CONTACT_RE.sub(" ", fragment).strip())
        if re.sub(r"\s+", " ", cleaned).casefold() == normalized_name:
            selected_name = cleaned
            break
    else:
        selected_name = " ".join(
            token[0].upper() + token[1:] if token and token[0].islower() else token
            for token in normalized_name.split()
        )

    return selected_name, confidence, {
        "method": "header_context_and_ner",
        "status": "selected",
        "candidate_count": len(candidates),
        "header_line": line_no,
        "near_contact": nearby_contact,
        "ner_confirmed": ner_confirmed,
    }


def _extract_email(text: str) -> str:
    """Extract email address using regex."""
    match = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.\w{2,}', text)
    return match.group() if match else "Not provided"


def _extract_phone(text: str) -> str:
    """Extract phone number using regex."""
    patterns = [
        r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\+?\d{2}[-.\s]?\d{5}[-.\s]?\d{5}',
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group()
    return "Not provided"


def _extract_linkedin(text: str) -> str:
    """Extract LinkedIn URL."""
    match = re.search(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+', text, re.IGNORECASE)
    return match.group() if match else ""


_WORK_HEADERS = {
    "experience", "experience history", "work experience",
    "professional experience", "employment history", "work history",
    "career history", "career experience",
}
_NON_WORK_HEADERS = {
    "education", "academic background", "projects", "personal projects",
    "skills", "technical skills", "certifications", "awards", "publications",
    "interests", "references", "summary", "professional summary",
    "profile", "objective", "career objective",
}
_INTERNSHIP_HEADERS = {"internship", "internships", "internship experience"}
_JOB_TITLE_RE = re.compile(
    r"\b(?:engineering|engineer|developer|analyst|manager|architect|consultant|designer|"
    r"scientist|administrator|specialist|technician|accountant|researcher|"
    r"research\s+assistant|professor|teacher|nurse|attorney|lawyer|"
    r"product\s+owner|project\s+manager|executive|associate|director|"
    r"operations|editor|writer|intern|sales\s+representative|support\s+representative)\b",
    re.IGNORECASE,
)
_EMPLOYER_CUE_RE = re.compile(
    r"\b(?:at|for)\s+[A-Z0-9][\w&.'’ -]{1,50}"
    r"|\b(?:incorporated|corporation|company|technologies|technology|"
    r"systems|solutions|limited|ltd|llc|plc|pvt|private|labs|laboratories)\b",
    re.IGNORECASE,
)
_DATE_TOKEN = (
    r"(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+(?:19|20)\d{2}|"
    r"(?:0?[1-9]|1[0-2])[/\-](?:19|20)\d{2}|"
    r"(?:19|20)\d{2}(?:[/\-](?:0?[1-9]|1[0-2]))?)"
)
_DATE_RANGE_RE = re.compile(
    rf"(?<![\w])(?P<start>{_DATE_TOKEN})(?![\w])\s*"
    rf"(?:-|–|—|to|through|until)\s*"
    rf"(?P<end>present|current|now|{_DATE_TOKEN})(?![\w])",
    re.IGNORECASE,
)


def _date_month_index(value: str, is_end: bool) -> Optional[int]:
    """Convert a resume date into a calendar-month index."""
    value = value.strip()
    if value.casefold() in {"present", "current", "now"}:
        today = date.today()
        return today.year * 12 + today.month

    month_match = re.fullmatch(r"(\d{1,2})[/\-]((?:19|20)\d{2})", value)
    if month_match:
        month, year = int(month_match.group(1)), int(month_match.group(2))
    else:
        year_month_match = re.fullmatch(
            r"((?:19|20)\d{2})[/\-](\d{1,2})", value
        )
        if year_month_match:
            year, month = int(year_month_match.group(1)), int(year_month_match.group(2))
        else:
            named_month_match = re.fullmatch(
                r"([A-Za-z]{3,9})\s+((?:19|20)\d{2})", value
            )
            if named_month_match:
                try:
                    try:
                        parsed = datetime.strptime(value, "%B %Y").date()
                    except ValueError:
                        parsed = datetime.strptime(value, "%b %Y").date()
                except ValueError:
                    return None
                year, month = parsed.year, parsed.month
            else:
                year_match = re.fullmatch(r"((?:19|20)\d{2})", value)
                if not year_match:
                    return None
                year, month = int(year_match.group(1)), 1
                return year * 12 + month - 1

    if month < 1 or month > 12:
        return None
    return year * 12 + month - 1 + (1 if is_end else 0)


def _merged_experience_years(intervals: List[Tuple[int, int]]) -> int:
    """Merge overlapping job intervals before counting complete years."""
    if not intervals:
        return 0
    intervals.sort()
    merged: List[List[int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    total_months = sum(end - start for start, end in merged)
    return min(total_months // 12, 30)


def _extract_experience_years(
    text: str, doc
) -> Tuple[int, int, List[Dict]]:
    """Count only dated employment entries with both a role and employer cue."""
    sections: List[Tuple[int, bool, List[Tuple[int, str]]]] = []
    active_kind: Optional[str] = None
    section_lines: List[Tuple[int, str]] = []

    def save_section() -> None:
        if active_kind and section_lines:
            sections.append((
                1 if active_kind == "internship" else 0,
                active_kind == "internship",
                list(section_lines),
            ))

    for line_no, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        heading = re.sub(r"^[\W\d_]+|[\W\d_]+$", "", line.casefold()).strip()
        if heading in _WORK_HEADERS:
            save_section()
            active_kind = "employment"
            section_lines = []
        elif heading in _INTERNSHIP_HEADERS:
            save_section()
            active_kind = "internship"
            section_lines = []
        elif heading in _NON_WORK_HEADERS:
            save_section()
            active_kind = None
            section_lines = []
        elif active_kind and line:
            section_lines.append((line_no, line))
    save_section()

    org_entities = {
        entity.text.casefold()
        for entity in (doc.ents if doc is not None else [])
        if entity.label_ == "ORG"
    }
    professional_intervals: List[Tuple[int, int]] = []
    internship_intervals: List[Tuple[int, int]] = []
    evidence: List[Dict] = []

    for is_internship, _, section in sections:
        for index, (line_no, line) in enumerate(section):
            for match in _DATE_RANGE_RE.finditer(line):
                start = _date_month_index(match.group("start"), is_end=False)
                end = _date_month_index(match.group("end"), is_end=True)
                if start is None or end is None or start >= end:
                    continue
                current_month = _date_month_index("present", is_end=True)
                if end > current_month:
                    continue

                context = " ".join(
                    context_line
                    for _, context_line in section[max(0, index - 2):index + 3]
                )
                has_title = bool(_JOB_TITLE_RE.search(context))
                has_employer = bool(_EMPLOYER_CUE_RE.search(context)) or any(
                    entity in context.casefold() for entity in org_entities
                )
                if not (has_title and has_employer):
                    continue

                is_intern = (
                    is_internship
                    or "intern" in context.casefold()
                    or "internship" in context.casefold()
                )
                (internship_intervals if is_intern else professional_intervals).append(
                    (start, end)
                )
                evidence.append({
                    "section": "internship" if is_intern else "employment",
                    "line": line_no,
                    "start": match.group("start"),
                    "end": match.group("end"),
                    "role_confirmed": has_title,
                    "employer_confirmed": has_employer,
                })

    return (
        _merged_experience_years(professional_intervals),
        _merged_experience_years(internship_intervals),
        evidence,
    )


def _determine_experience_level(years: int, text_lower: str) -> str:
    """Derive seniority from verified employment duration, not title keywords."""
    if years >= 12:
        return "Principal"
    elif years >= 7:
        return "Senior"
    elif years >= 3:
        return "Mid-level"
    elif years >= 1:
        return "Junior"
    elif any(term in text_lower for term in ("fresher", "entry level", "new graduate", "student")):
        return "Fresher"
    return "Not specified"


def _extract_technologies(text_lower: str) -> List[str]:
    """Extract technologies from resume text."""
    found = []
    for tech, keywords in TECH_DATABASE.items():
        for keyword in keywords:
            if keyword in text_lower:
                found.append(tech)
                break
    return sorted(list(set(found)))


def _extract_certifications(text_lower: str) -> List[str]:
    """Extract certifications."""
    found = []
    for cert, keywords in CERTIFICATIONS.items():
        for keyword in keywords:
            if keyword in text_lower:
                found.append(cert)
                break
    return found


def _extract_soft_skills(text_lower: str) -> List[str]:
    """Extract soft skills."""
    return [skill for skill in SOFT_SKILLS if skill in text_lower]


def _extract_education(text_lower: str) -> str:
    """Extract highest education degree."""
    for pattern, degree in DEGREE_PATTERNS:
        if re.search(pattern, text_lower):
            return degree
    return "Not specified"


def _extract_cgpa(text: str) -> Optional[float]:
    """Extract CGPA/GPA."""
    patterns = [
        r'(?:cgpa|gpa|c\.gpa|grade)\s*[:\-=]?\s*(\d+\.?\d*)\s*/?\s*(?:10|4)',
        r'(?:cgpa|gpa)\s*[:\-=]?\s*(\d+\.\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                if 0 < val <= 10:
                    return round(val, 2)
            except ValueError:
                pass
    return None


def _count_projects(text_lower: str) -> int:
    """Count number of projects mentioned."""
    # Count project headings or bullets
    project_patterns = [
        r'project\s*\d',
        r'project\s*[:–—-]',
        r'•\s*\w+.*project',
    ]
    count = sum(len(re.findall(p, text_lower)) for p in project_patterns)
    # Fallback: just count "project" mentions (rough estimate)
    if count == 0:
        count = text_lower.count("project")
    return min(count, 20)


def _extract_achievements(text: str) -> List[str]:
    """Extract notable achievements."""
    keywords = [
        "developed", "implemented", "designed", "built", "created",
        "led", "managed", "achieved", "increased", "improved",
        "reduced", "optimized", "automated", "launched", "deployed",
        "awarded", "published", "contributed", "engineered",
    ]
    achievements = []
    for line in text.split('\n'):
        line = line.strip()
        if len(line) > 25 and any(kw in line.lower() for kw in keywords):
            # Clean up bullet points
            cleaned = re.sub(r'^[\s•\-\*\d\.]+', '', line).strip()
            if cleaned and len(cleaned) > 20:
                achievements.append(cleaned)
                if len(achievements) >= 5:
                    break
    return achievements


def _determine_specialization(text_lower: str, technologies: List[str]) -> str:
    """Determine candidate's specialization."""
    tech_set = set(t.lower() for t in technologies)

    specialization_rules = [
        (["machine learning", "deep learning", "tensorflow", "pytorch", "nlp"],
         "ML/AI Engineer"),
        (["data science", "pandas", "numpy", "tableau", "power bi"],
         "Data Scientist"),
        (["react", "angular", "vue.js", "next.js", "frontend", "html/css"],
         "Frontend Developer"),
        (["node.js", "django", "flask", "fastapi", "spring boot", "backend"],
         "Backend Developer"),
        (["docker", "kubernetes", "terraform", "ansible", "devops", "ci/cd"],
         "DevOps Engineer"),
        (["aws", "azure", "gcp", "cloud"],
         "Cloud Engineer"),
        (["apache spark", "hadoop", "kafka", "airflow", "data engineer"],
         "Data Engineer"),
        (["react", "node.js", "full stack", "fullstack"],
         "Full-Stack Developer"),
        (["ios", "android", "flutter", "react native", "mobile"],
         "Mobile Developer"),
        (["security", "penetration", "cissp", "cybersecurity"],
         "Security Engineer"),
    ]

    for keywords, role in specialization_rules:
        matches = sum(1 for kw in keywords if kw in text_lower or kw in tech_set)
        if matches >= 2:
            return role

    return "Software Developer"


def _calculate_score(
    technologies: List[str],
    experience_years: int,
    achievements: List[str],
    projects_count: int,
    cgpa: Optional[float],
    certifications: List[str],
    soft_skills: List[str],
) -> int:
    """
    Calculate candidate score (0-100).
    
    Scoring weights:
    - Technologies: up to 25 points
    - Experience: up to 20 points
    - Achievements: up to 15 points
    - Projects: up to 10 points
    - Education (CGPA): up to 10 points
    - Certifications: up to 10 points
    - Soft skills: up to 10 points
    """
    score = 0

    # Technologies (max 25)
    score += min(len(technologies) * 2.5, 25)

    # Experience (max 20)
    score += min(experience_years * 3, 20)

    # Achievements (max 15)
    score += min(len(achievements) * 3, 15)

    # Projects (max 10)
    score += min(projects_count * 2, 10)

    # CGPA (max 10)
    if cgpa:
        if cgpa >= 9:
            score += 10
        elif cgpa >= 8:
            score += 8
        elif cgpa >= 7:
            score += 6
        elif cgpa >= 6:
            score += 4

    # Certifications (max 10)
    score += min(len(certifications) * 5, 10)

    # Soft skills (max 10)
    score += min(len(soft_skills) * 2, 10)

    return min(int(score), 100)


def calculate_candidate_score(
    technologies: List[str],
    experience_years: int,
    achievements: List[str],
    projects_count: int,
    cgpa: Optional[float],
    certifications: List[str],
    soft_skills: List[str],
) -> int:
    """Recalculate a score from verified experience and existing parsed fields."""
    return _calculate_score(
        technologies, experience_years, achievements,
        projects_count, cgpa, certifications, soft_skills
    )


def _generate_summary(
    name: str, level: str, specialization: str,
    years: int, technologies: List[str],
) -> str:
    """Generate a human-readable candidate summary."""
    top_tech = ", ".join(technologies[:4]) if technologies else "various technologies"
    experience = (
        f"{years} year(s) of verified professional experience"
        if years
        else "professional experience not specified"
    )
    seniority = f"{level.lower()} " if level != "Not specified" else ""
    return (
        f"{name} is a {seniority}{specialization.lower()} "
        f"with {experience}. Proficient in {top_tech}."
    )


def _error_result(filename: str) -> Dict:
    """Return a default error result."""
    return {
        "candidate_name": _NAME_NOT_DETECTED,
        "email": "N/A",
        "phone": "N/A",
        "linkedin": "",
        "experience_years": 0,
        "internship_experience_years": 0,
        "experience_level": "Not specified",
        "specialization": "Unknown",
        "technologies": [],
        "certifications": [],
        "soft_skills": [],
        "education": "N/A",
        "cgpa": None,
        "projects_count": 0,
        "notable_achievements": [],
        "overall_score": 0,
        "candidate_summary": "Could not process resume.",
        "name_confidence": 0.0,
        "name_evidence": {"status": "analysis_error"},
        "experience_evidence": [],
        "filename": filename,
    }
