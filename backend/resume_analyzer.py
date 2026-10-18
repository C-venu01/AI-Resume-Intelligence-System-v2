"""
Resume Analyzer — SpaCy NER + Regex
Parses resumes to extract structured candidate information.
Uses SpaCy for Named Entity Recognition and regex for pattern matching.
"""

import re
from typing import Dict, List, Optional

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
        name = _extract_name(doc, text)
        email = _extract_email(text)
        phone = _extract_phone(text)
        linkedin = _extract_linkedin(text)
        experience_years = _extract_experience_years(text, text_lower)
        experience_level = _determine_experience_level(experience_years, text_lower)
        technologies = _extract_technologies(text_lower)
        certifications = _extract_certifications(text_lower)
        soft_skills = _extract_soft_skills(text_lower)
        education = _extract_education(text_lower)
        cgpa = _extract_cgpa(text)
        projects_count = _count_projects(text_lower)
        achievements = _extract_achievements(text)
        specialization = _determine_specialization(text_lower, technologies)

        # Calculate score
        score = _calculate_score(
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
            "experience_level": experience_level,
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
        print(f"[Analyzer] Error analyzing {filename}: {e}")
        return _error_result(filename)


# ==================== EXTRACTION FUNCTIONS ====================

def _extract_name(doc, text: str) -> str:
    """Extract candidate name using SpaCy NER with validation."""
    
    # Words that SpaCy often misclassifies as PERSON names
    NOT_NAMES = {
        # Tech terms
        "java", "python", "javascript", "html", "css", "sql", "react", "angular",
        "node", "docker", "kubernetes", "aws", "azure", "git", "linux", "email",
        "phone", "mobile", "address", "resume", "cv", "objective", "summary",
        "experience", "education", "skills", "projects", "profile", "contact",
        "references", "interests", "hobbies", "declaration", "certifications",
        # Common locations
        "andhra pradesh", "telangana", "karnataka", "tamil nadu", "maharashtra",
        "hyderabad", "bangalore", "chennai", "mumbai", "delhi", "pune", "kolkata",
        "india", "usa", "new york", "california", "london",
        # Other common false positives
        "bachelor", "master", "b.tech", "m.tech", "b.e", "m.e", "mba", "bca", "mca",
        "computer science", "information technology", "machine learning",
        "data science", "software engineer", "web developer", "full stack",
    }
    
    def is_valid_name(name: str) -> bool:
        """Check if extracted text looks like a real person name."""
        name_clean = name.strip()
        if not name_clean:
            return False
        words = name_clean.split()
        if not (1 <= len(words) <= 4):
            return False
        # Must be alphabetic (allow dots and hyphens in names)
        if not all(c.isalpha() or c in ' .-' for c in name_clean):
            return False
        # Must not be a known non-name
        if name_clean.lower() in NOT_NAMES:
            return False
        # Individual words should not be common non-names
        for word in words:
            if word.lower() in NOT_NAMES:
                return False
        # At least one word should be capitalized (proper noun pattern)
        if not any(w[0].isupper() for w in words if w):
            return False
        # Name should be reasonably short
        if len(name_clean) > 40:
            return False
        return True
    
    # Strategy 1: SpaCy NER — find PERSON entities
    if doc is not None:
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                name = ent.text.strip()
                if is_valid_name(name):
                    return name
    
    # Strategy 2: First few lines — resumes typically start with the name
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:5]:
        # Skip lines that look like section headers or contain special chars
        if any(c in line for c in ['@', ':', '|', '(', ')', '+', '/', '#']):
            continue
        # Skip very long lines (likely paragraphs)
        if len(line) > 40:
            continue
        if is_valid_name(line):
            return line
    
    # Strategy 3: Extract name from email (e.g., "john.doe@gmail.com" -> "John Doe")
    email_match = re.search(r'([\w.+-]+)@', text)
    if email_match:
        prefix = email_match.group(1)
        # Remove trailing numbers
        prefix = re.sub(r'\d+$', '', prefix)
        # Split on dots, underscores, hyphens
        parts = re.split(r'[._-]', prefix)
        parts = [p.capitalize() for p in parts if len(p) > 1 and p.isalpha()]
        if 1 <= len(parts) <= 3:
            name = ' '.join(parts)
            if name.lower() not in NOT_NAMES:
                return name
    
    return "Unknown Candidate"


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


def _extract_experience_years(text: str, text_lower: str) -> int:
    """Estimate years of experience."""
    # Direct mention patterns
    patterns = [
        (r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)', 1),
        (r'experience\s*(?:of)?\s*(\d+)\+?\s*(?:years?|yrs?)', 1),
    ]
    for pattern, group in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return min(int(match.group(group)), 30)

    # Try date-based calculation
    year_ranges = re.findall(r'(20\d{2})\s*[-–—to]+\s*(20\d{2}|present|current)', text_lower)
    if year_ranges:
        total = 0
        for start, end in year_ranges:
            start_yr = int(start)
            end_yr = 2026 if end in ("present", "current") else int(end)
            total += max(0, end_yr - start_yr)
        return min(total, 30)

    # Keyword-based estimates
    if "fresher" in text_lower or "entry level" in text_lower:
        return 0
    elif "intern" in text_lower:
        return 0

    return 0


def _determine_experience_level(years: int, text_lower: str) -> str:
    """Determine experience level from years and keywords."""
    if "principal" in text_lower or "architect" in text_lower or years >= 12:
        return "Principal"
    elif "senior" in text_lower or "lead" in text_lower or "staff" in text_lower or years >= 7:
        return "Senior"
    elif "mid" in text_lower or years >= 3:
        return "Mid-level"
    elif years >= 1:
        return "Junior"
    else:
        return "Fresher"


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


def _generate_summary(
    name: str, level: str, specialization: str,
    years: int, technologies: List[str],
) -> str:
    """Generate a human-readable candidate summary."""
    top_tech = ", ".join(technologies[:4]) if technologies else "various technologies"
    return (
        f"{name} is a {level.lower()} {specialization.lower()} "
        f"with {years} year(s) of experience. "
        f"Proficient in {top_tech}."
    )


def _error_result(filename: str) -> Dict:
    """Return a default error result."""
    return {
        "candidate_name": "Analysis Error",
        "email": "N/A",
        "phone": "N/A",
        "linkedin": "",
        "experience_years": 0,
        "experience_level": "Unknown",
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
        "filename": filename,
    }
