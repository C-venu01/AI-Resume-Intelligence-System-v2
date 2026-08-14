# 🤖 AI Resume Intelligence System 2.0 — Cloud-Based Hiring Copilot

An AI-powered resume screening system that analyzes resumes using **NLP + Deep Learning**, matches candidates to job descriptions semantically, identifies skill gaps, ranks candidates, and deploys to **AWS** with a full **DevOps pipeline**.

> **Upgraded from v1.0** — Now with SpaCy NER, sentence-transformers embeddings, FastAPI, Docker, Ansible, Terraform, GitHub Actions, and Prometheus/Grafana monitoring.

---

## 🏗️ Architecture

```
Resume PDF → PyMuPDF → SpaCy NER + Regex → sentence-transformers Embedding
    → Cosine Similarity (Job Match) → Scoring + Skill Gap Analysis
    → SQLite Storage → FastAPI REST API → Web Dashboard
    → Docker → GitHub Actions CI/CD → Terraform (AWS) → Ansible → Nginx
    → Prometheus + Grafana (Monitoring)
```

---

## 🚀 Features

| Feature | Description |
|---|---|
| 📄 **PDF Parsing** | PyMuPDF — fast, multi-column support |
| 🧠 **NLP Analysis** | SpaCy NER + regex — extracts name, skills, experience, education |
| 🔗 **Semantic Matching** | sentence-transformers — AI understands meaning, not just keywords |
| 📊 **Skill Gap Analysis** | Shows missing skills + learning resource suggestions |
| 🏆 **Candidate Ranking** | Weighted scoring (0–100) with auto-ranking |
| 🌐 **Web Dashboard** | Premium dark glassmorphism UI with charts |
| 🗄️ **Persistent Storage** | SQLite — data survives restarts |
| 🐳 **Docker** | Containerized for consistent deployment |
| ⚙️ **Ansible** | Server provisioning + app deployment playbooks |
| 🏗️ **Terraform** | AWS infrastructure as code (EC2 + VPC + SG) |
| 🔄 **GitHub Actions** | CI/CD pipeline (test → build → push → deploy) |
| 📡 **Monitoring** | Prometheus + Grafana dashboards |
| 📤 **Export** | JSON + CSV export |

---

## 📦 Tech Stack

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Core language |
| PyMuPDF | 1.27.1 | PDF extraction |
| SpaCy | 3.8 | NER for resume parsing |
| sentence-transformers | 5.2.3 | Semantic embeddings |
| FastAPI | 0.135.1 | REST API |
| SQLite | built-in | Database |
| Docker | latest | Containerization |
| Ansible | latest | Server config + deployment |
| Terraform | latest | AWS infrastructure |
| GitHub Actions | v4 | CI/CD |
| Nginx | latest | Reverse proxy |
| Prometheus + Grafana | latest | Monitoring |

---

## 🖥️ Quick Start (Local)

### Option 1: One-Click (Windows)
```bash
# Just double-click:
start.bat
```

### Option 2: Manual
```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Download SpaCy NLP model
python -m spacy download en_core_web_sm

# Start the server
python main.py
```

Open: **http://localhost:8000**  
API Docs: **http://localhost:8000/docs**

### Option 3: Docker
```bash
docker-compose up --build
```

---

## ☁️ Deploy to the Cloud (Render)
1. Sign up at https://render.com and connect your GitHub repository.
2. Add the included `render.yaml` (already in project root) or create a new Web Service with:
   * **Environment**: Docker
   * **Dockerfile Path**: `./Dockerfile`
   * **Plan**: Free
   * **Auto Deploy**: Enabled
3. Push to `main` and Render will build & host the app automatically.

Your service will be available at a Render URL (e.g. `https://resume-intelligence.onrender.com`). The API, dashboard, and docs work exactly as locally.

You can still follow the AWS instructions below if you prefer managing infrastructure yourself.

---

## ☁️ Deploy to AWS

### Step 1: Create SSH Key
```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/resume-app-key
```

### Step 2: Provision Infrastructure (Terraform)
```bash
cd devops/terraform
terraform init
terraform plan
terraform apply
# Note the output IP address
```

### Step 3: Setup Server (Ansible)
```bash
cd devops/ansible
# Update inventory.ini with your EC2 IP
ansible-playbook -i inventory.ini playbook-setup.yml
```

### Step 4: Deploy App (Ansible)
```bash
ansible-playbook -i inventory.ini playbook-deploy.yml
```

### Step 5: Setup Monitoring (Optional)
```bash
cd devops/monitoring
docker-compose -f docker-compose.monitoring.yml up -d
# Grafana: http://your-ip:3000 (admin/admin123)
# Prometheus: http://your-ip:9090
```

---

## 📁 Project Structure

The repository is organized for clarity and ease of maintenance:

```
AI Resume Intelligence System 2.0/            # project root
├── backend/                              # Python API & AI logic
│   ├── main.py                           ← FastAPI application
│   ├── resume_analyzer.py                ← SpaCy + regex parsing
│   ├── embedding_engine.py               ← sentence-transformers matching
│   ├── pdf_extractor.py                  ← PyMuPDF text extraction
│   ├── database.py                       ← SQLite persistence & queries
│   ├── models.py                         ← Pydantic request/response types
│   └── requirements.txt                  ← Python dependencies
│
├── frontend/                             # Static dashboard files
│   ├── index.html                        ← Dashboard UI
│   ├── index.css                         ← Dark glassmorphism theme
│   └── app.js                            ← Client-side logic (fetch, charts)
│
├── devops/                               # Infrastructure as Code & scripts
│   ├── ansible/                          ← Server provisioning & deployment playbooks
│   ├── terraform/                        ← AWS infrastructure code
│   └── monitoring/                       ← Prometheus/Grafana config (docker-compose)
│
├── .github/                              # GitHub Actions workflows
│   └── workflows/ci-cd.yml               ← CI/CD pipeline definition
│
├── Dockerfile                            # Application container definition
├── docker-compose.yml                    # Local development orchestration
├── start.bat                             # Windows one‑click startup script
├── render.yaml                           # Render.com deployment config
└── README.md                             # Project documentation (this file)
```

Files such as `implementation_plan.md.resolved` have been removed to keep the
repository focused on runnable code. The structure follows a logical flow: API
code in `backend/`, UI in `frontend/`, infrastructure in `devops/`, with global
configs at the root.


---

## 🔬 What's Novel

1. **Semantic Job Matching** — Uses AI embeddings (not just keyword overlap) to understand that "React.js developer" ≈ "Frontend Engineer"
2. **Skill Gap Analysis + Suggestions** — Identifies missing skills and recommends free learning resources
3. **Full DevOps Pipeline** — Production-ready with Docker, Ansible, Terraform, CI/CD, and monitoring

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/upload` | Upload & analyze resume PDFs |
| GET | `/api/candidates` | List all candidates (search/filter/sort) |
| GET | `/api/candidates/{id}` | Get candidate details |
| DELETE | `/api/candidates/{id}` | Delete a candidate |
| POST | `/api/job-match` | Semantic job matching |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/export/{format}` | Export as JSON or CSV |
| GET | `/api/health` | Health check |

---

## 👨‍💻 Author

**Venu Chillale**  
GitHub: [github.com/C-venu01](https://github.com/C-venu01)

---

## 📄 License

This project is open source and available for educational and non-commercial use.
