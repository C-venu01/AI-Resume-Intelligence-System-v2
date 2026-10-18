# 🤖 AI Resume Intelligence System 2.0 — Cloud-Based Hiring Copilot

An AI-powered resume screening system that analyzes resumes using **NLP + Deep Learning**, matches candidates to job descriptions semantically, identifies skill gaps, ranks candidates, and deploys to **AWS** with a full **DevOps pipeline**.

> **Upgraded from v1.0** — Now with SpaCy NER, sentence-transformers embeddings, FastAPI, Docker, Ansible, Terraform, GitHub Actions, and Prometheus/Grafana monitoring.

---

## 🔒 Security Features

This system includes production-ready security:

| Feature | Description |
|---|---|
| 🔐 **JWT Authentication** | Token-based auth protects all sensitive endpoints |
| 👤 **Private Workspaces** | Publicly registered accounts can access only their own resume and job data |
| 🛡️ **Rate Limiting** | Brute-force and abuse protection on login, signup, uploads, and job matching |
| ✅ **PDF Validation** | Magic bytes, MIME type, size, and page count checks |
| 🔑 **Non-Root Docker** | Container runs as unprivileged user |
| 🔒 **Security Headers** | CSP, X-Frame-Options, HSTS |
| 📝 **Audit Logging** | Privacy-aware logs (no PII) |
| 🌐 **CORS Whitelist** | Explicit origin validation |

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
| 🗄️ **Persistent Storage** | SQLite — persistence depends on the host's durable storage configuration |
| 🐳 **Docker** | Containerized for consistent deployment |
| ⚙️ **Ansible** | Server provisioning + app deployment playbooks |
| 🏗️ **Terraform** | AWS infrastructure as code (EC2 + VPC + SG) |
| 🔄 **GitHub Actions** | CI/CD pipeline (test → build → push) |
| 📡 **Monitoring** | Prometheus + Grafana dashboards |
| 📤 **Export** | JSON + CSV export |

---

## 📦 Tech Stack

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Core language |
| PyMuPDF | 1.25.5 | PDF extraction |
| SpaCy | 3.8 | NER for resume parsing |
| sentence-transformers | 3.4.1 | Semantic embeddings |
| FastAPI | 0.115.12 | REST API |
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

### Option 2: Manual Setup
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
API Docs: **http://localhost:8000/docs** (development only)

For local development, the default login is `admin` / `admin123`. Public users can create a separate account from the sign-in page; each account has an isolated workspace. Change the default admin credentials before deploying.

### Option 3: Docker
```bash
# Copy environment template and configure
cp .env.example .env
# Edit .env and set your secrets (see Security Setup below)

# Start the application
docker compose up --build
```

Open: **http://localhost:8000**

---

## 🔐 Security Setup (Required for Production)

### 1. Generate JWT Secret Key

```bash
# Generate a secure random key
openssl rand -base64 32
```

Set in `.env`:
```bash
JWT_SECRET_KEY=your-generated-key-here
```

### 2. Set Admin Password

Generate a bcrypt hash of your password:

```bash
cd backend
python -c "from auth import hash_password; print(hash_password('YourStrongPassword'))"
```

Set in `.env`:
```bash
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$2b$12$...your-hash-here
```

### 3. Configure CORS

Set allowed origins in `.env`:
```bash
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

### 4. Set Environment

```bash
ENVIRONMENT=production
```

This disables:
- API documentation (`/docs`, `/redoc`)
- Default password fallback
- Development JWT key

### 5. Database Persistence

The database is stored at `/app/backend/data/resume_db.sqlite` inside the container. Mount a volume to persist data:

```yaml
# docker-compose.yml already includes this
volumes:
  - resume_data:/app/backend/data
```

All user accounts, resumes, and job descriptions share this database file, with access scoped to each account. Existing records are assigned to the configured admin workspace when the ownership migration runs. On hosts with ephemeral filesystems (including a Render service without a persistent disk), accounts and uploaded data can be lost on restart or redeploy; attach durable storage or use a managed database before relying on persistence.

---

## ☁️ Deploy to AWS

### Step 0: Configure Security Variables

Create `devops/terraform/terraform.tfvars`:

```hcl
# REQUIRED: Restrict SSH to your IP only
allowed_ssh_cidrs = ["YOUR.IP.ADDRESS/32"]

# OPTIONAL: Restrict monitoring access
allowed_monitoring_cidrs = ["YOUR.IP.ADDRESS/32"]

# EC2 instance type
instance_type = "t3.medium"

# AWS region
region = "us-east-1"
```

**⚠️ Never commit `terraform.tfvars` to git.** It's already in `.gitignore`.

### Step 1: Create SSH Key

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/resume-app-key
```

### Step 2: Provision Infrastructure (Terraform)

```bash
cd devops/terraform
terraform init
terraform plan  # Review changes
terraform apply # Creates EC2, VPC, Security Groups
# Note the output IP address
```

**⚠️ Do NOT run `terraform apply` without reviewing the plan.**

### Step 3: Setup Server (Ansible)

```bash
cd devops/ansible
# Update inventory.ini with your EC2 IP
ansible-playbook -i inventory.ini playbook-setup.yml
```

### Step 4: Deploy App (Ansible)

```bash
# Set environment variables on the server
ansible-playbook -i inventory.ini playbook-deploy.yml \
  -e "JWT_SECRET_KEY=your-key" \
  -e "ADMIN_PASSWORD_HASH=your-hash"
```

### Step 5: Setup Monitoring (Optional)

```bash
cd devops/monitoring

# Create .env with Grafana credentials
echo "GRAFANA_ADMIN_USER=admin" > .env
echo "GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16)" >> .env
echo "GRAFANA_ROOT_URL=https://monitoring.yourdomain.com" >> .env

docker-compose -f docker-compose.monitoring.yml up -d
```

**Access (via SSH tunnel only):**
```bash
# SSH tunnel to access monitoring locally
ssh -L 3000:localhost:3000 -L 9090:localhost:9090 ubuntu@your-ec2-ip

# Then open:
# Grafana: http://localhost:3000
# Prometheus: http://localhost:9090
```

---

## 📁 Project Structure

```
AI Resume Intelligence System 2.0/
├── backend/                          # Python API & AI logic
│   ├── main.py                       ← FastAPI application
│   ├── auth.py                       ← JWT authentication
│   ├── config.py                     ← Environment configuration
│   ├── validators.py                 ← PDF upload validation
│   ├── rate_limiter.py               ← DoS protection
│   ├── logging_config.py             ← Privacy-aware logging
│   ├── resume_analyzer.py            ← SpaCy + regex parsing
│   ├── embedding_engine.py           ← sentence-transformers matching
│   ├── pdf_extractor.py              ← PyMuPDF text extraction
│   ├── database.py                   ← SQLite persistence & queries
│   ├── models.py                     ← Pydantic request/response types
│   ├── test_comprehensive.py         ← Security & functionality tests
│   └── requirements.txt              ← Python dependencies
│
├── frontend/                         # Static dashboard files
│   ├── index.html                    ← Dashboard UI
│   ├── index.css                     ← Dark glassmorphism theme
│   └── app.js                        ← Client-side logic (fetch, charts)
│
├── devops/                           # Infrastructure as Code
│   ├── ansible/                      ← Server provisioning & deployment
│   ├── terraform/                    ← AWS infrastructure code
│   │   ├── variables.tf              ← Security-focused variables
│   │   ├── terraform.tfvars.example  ← Example configuration
│   │   └── user_data.sh              ← EC2 initialization
│   └── monitoring/                   ← Prometheus/Grafana config
│
├── .github/                          # GitHub Actions workflows
│   └── workflows/ci-cd.yml           ← CI/CD pipeline
│
├── Dockerfile                        # Multi-stage, non-root container
├── docker-compose.yml                # Local development orchestration
├── .env.example                      ← Environment template
├── .gitignore                        ← Excludes secrets
├── SECURITY_AUDIT_REPORT.md          ← Security audit findings
├── start.bat                         # Windows one-click startup
├── render.yaml                       # Render.com deployment config
└── README.md                         # Project documentation
```

---

## 📊 API Endpoints

### Public Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Create a private user workspace |
| POST | `/api/auth/login` | Login and get JWT token |
| GET | `/api/health` | Health check |
| GET | `/api/readiness` | Readiness check |

### Protected Endpoints (Require JWT)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/upload` | Upload & analyze resume PDFs |
| GET | `/api/candidates` | List all candidates (search/filter/sort) |
| GET | `/api/candidates/{id}` | Get candidate details |
| DELETE | `/api/candidates/{id}` | Delete a candidate |
| DELETE | `/api/candidates` | Delete all candidates |
| POST | `/api/job-match` | Semantic job matching |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/export/{format}` | Export as JSON or CSV |
| GET | `/api/job-descriptions` | List saved job descriptions in your workspace |
| GET | `/api/auth/me` | Get current user info |

### Authentication

Login to get a JWT token:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

Use the token in subsequent requests:

```bash
curl http://localhost:8000/api/candidates \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## 🧪 Running Tests

```bash
cd backend

# Run all tests
python -m pytest test_comprehensive.py -v

# Run specific test class
python -m pytest test_comprehensive.py::TestAuthentication -v

# Run with coverage
python -m pytest test_comprehensive.py --cov=. --cov-report=html
```

---

## 🔄 GitHub Actions CI/CD

The pipeline runs on every push to `main`:

1. **Lint** — flake8 syntax checking
2. **Test** — Comprehensive test suite including security tests
3. **Build** — Docker image build and push to Docker Hub
4. **Verify** — Container startup and health check

**⚠️ Automatic deployment is disabled for security.** Deploy manually via SSH or create a separate deployment workflow with environment protection rules.

### Required GitHub Secrets

Set these in your repository settings:

| Secret | Description |
|---|---|
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_TOKEN` | Docker Hub access token |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash for admin password (optional, for CI testing) |

---

## 🔬 What's Novel

1. **Semantic Job Matching** — Uses AI embeddings (not just keyword overlap) to understand that "React.js developer" ≈ "Frontend Engineer"
2. **Skill Gap Analysis + Suggestions** — Identifies missing skills and recommends free learning resources
3. **Full DevOps Pipeline** — Production-ready with Docker, Ansible, Terraform, CI/CD, and monitoring
4. **Security-First Design** — JWT auth, rate limiting, input validation, non-root containers, audit logging

---

## 🛡️ Security Best Practices

1. **Never commit `.env` or `terraform.tfvars`** — They contain secrets
2. **Use strong passwords** — Generate with `openssl rand -base64 16`
3. **Restrict SSH access** — Only allow your IP in `allowed_ssh_cidrs`
4. **Use HTTPS in production** — Configure Nginx with Let's Encrypt
5. **Regular backups** — Backup `/app/backend/data/` directory
6. **Monitor logs** — Check for suspicious activity
7. **Update dependencies** — Keep packages patched

---

## 📋 Backup & Recovery

### Backup Database

```bash
# On the server
docker exec resume-intelligence \
  sqlite3 /app/backend/data/resume_db.sqlite ".backup /app/backend/data/backup.db"

# Copy to local machine
scp ubuntu@your-ec2-ip:/opt/resume-intelligence/data/backup.db ./backup_$(date +%Y%m%d).db
```

### Restore Database

```bash
# Copy backup to server
scp ./backup.db ubuntu@your-ec2-ip:/opt/resume-intelligence/data/restore.db

# Stop container and replace database
docker stop resume-intelligence
ssh ubuntu@your-ec2-ip "cp /opt/resume-intelligence/data/restore.db /opt/resume-intelligence/data/resume_db.sqlite"

# Start container
docker start resume-intelligence
```

---

## 👨‍💻 Author

**Venu Chillale**  
GitHub: [github.com/C-venu01](https://github.com/C-venu01)

---

## 📄 License

This project is open source and available for educational and non-commercial use.
