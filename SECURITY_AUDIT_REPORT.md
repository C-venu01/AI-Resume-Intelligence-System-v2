# Security Audit Report — AI Resume Intelligence System v2
**Date:** 2026-10-17  
**Auditor:** Senior Software Engineer + Security Engineer  
**Repository:** https://github.com/C-venu01/AI-Resume-Intelligence-System-v2

---

## Executive Summary

This application processes sensitive personal data (resumes containing names, emails, phone numbers, addresses) but currently lacks fundamental security controls. **All API endpoints are publicly accessible without authentication**, allowing anyone to view, export, or delete candidate data. The infrastructure configuration exposes unnecessary ports to the internet, and the upload pipeline lacks validation.

**Critical Risk:** Unauthorized access to personal information, data deletion, and potential abuse.

---

## Critical Security Vulnerabilities (P0 - Fix Immediately)

### 1. **No Authentication or Authorization** ⚠️ CRITICAL
**File:** `backend/main.py`  
**Issue:** All API endpoints are publicly accessible:
- `/api/candidates` — lists ALL candidate personal data (names, emails, phones)
- `/api/candidates/{id}` — retrieves full candidate details
- `/api/export/json` and `/api/export/csv` — exports all data without auth
- `/api/candidates` (DELETE) — deletes ALL candidates without confirmation
- `/api/candidates/{id}` (DELETE) — deletes specific candidates
- `/api/upload` — anyone can upload PDFs
- `/api/job-match` — unrestricted access to matching

**Impact:** Unauthorized parties can access, export, or delete candidate data. This violates GDPR/privacy principles.

**Lines:** 70-265

---

### 2. **Unrestricted CORS Configuration** ⚠️ CRITICAL
**File:** `backend/main.py`  
**Lines:** 40-46
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ← Accepts requests from ANY origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
**Issue:** `allow_origins=["*"]` with `allow_credentials=True` allows any website to make authenticated requests.

**Impact:** Cross-site scripting attacks, credential theft, CSRF.

---

### 3. **SSH Port Exposed to Internet** ⚠️ CRITICAL
**File:** `devops/terraform/main.tf`  
**Lines:** 84-90
```hcl
ingress {
  description = "SSH"
  from_port   = 22
  to_port     = 22
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]  # ← SSH open to the world
}
```
**Issue:** SSH port 22 is accessible from any IP address.

**Impact:** Brute-force attacks, unauthorized server access.

---

### 4. **Monitoring Ports Exposed to Internet** ⚠️ HIGH
**File:** `devops/terraform/main.tf`  
**Lines:** 119-135
```hcl
# Prometheus
ingress {
  from_port   = 9090
  cidr_blocks = ["0.0.0.0/0"]  # ← Public Prometheus
}
# Grafana
ingress {
  from_port   = 3000
  cidr_blocks = ["0.0.0.0/0"]  # ← Public Grafana with default creds
}
```
**Issue:** Prometheus and Grafana exposed publicly. Grafana default credentials in `docker-compose.monitoring.yml` are `admin/admin123`.

**Impact:** Information disclosure, potential credential leaks in metrics.

---

### 5. **Application Port Directly Exposed** ⚠️ MEDIUM
**File:** `devops/terraform/main.tf`  
**Lines:** 110-117
```hcl
ingress {
  description = "App Port"
  from_port   = 8000
  to_port     = 8000
  cidr_blocks = ["0.0.0.0/0"]  # ← FastAPI exposed directly
}
```
**Issue:** Port 8000 bypasses Nginx reverse proxy.

**Impact:** Bypasses security headers, rate limiting, and logging.

---

### 6. **Insufficient PDF Upload Validation** ⚠️ HIGH
**File:** `backend/main.py`  
**Lines:** 70-118

**Current validation:**
- Only checks file extension (`.pdf`)
- No MIME type validation
- No file size limit
- No maximum file count per request
- No page count limit

**Missing checks:**
- PDF file signature/magic bytes
- Encrypted PDFs
- Malformed PDFs
- Resource limits (prevents DoS via large/complex PDFs)

**Impact:** Malicious file uploads, DoS attacks, server resource exhaustion.

---

### 7. **Database Path Not Configurable** ⚠️ MEDIUM
**File:** `backend/database.py`  
**Lines:** 14-15
```python
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume_db.sqlite")
```
**Issue:** Database stored in code directory. On Render's ephemeral filesystem, this means **data is lost on every deploy**.

**Impact:** Data loss on deployment, no backup strategy.

---

### 8. **Logging of Sensitive Data** ⚠️ MEDIUM
**File:** `backend/main.py`, `backend/resume_analyzer.py`, `backend/embedding_engine.py`

**Issue:** Exception messages with `str(e)` may leak:
- Resume text content
- Personal information
- File paths
- Stack traces with sensitive context

**Lines:** `main.py:111`, `resume_analyzer.py:227`

**Impact:** Personal data leakage in logs.

---

### 9. **No Rate Limiting** ⚠️ HIGH
**File:** `backend/main.py`

**Issue:** No rate limiting on:
- `/api/upload` — can upload unlimited PDFs
- `/api/job-match` — computationally expensive (model inference)
- Authentication endpoints (when added)
- All other endpoints

**Impact:** DoS attacks, resource exhaustion, abuse.

---

### 10. **Hardcoded Secrets in Monitoring Config** ⚠️ MEDIUM
**File:** `devops/monitoring/docker-compose.monitoring.yml`  
**Lines:** 30-32
```yaml
environment:
  - GF_SECURITY_ADMIN_USER=admin
  - GF_SECURITY_ADMIN_PASSWORD=admin123  # ← Hardcoded default password
```
**Impact:** Unauthorized access to monitoring dashboards.

---

## High-Severity Issues (P1 - Fix Before Production)

### 11. **No Input Sanitization in Frontend**
**File:** `frontend/app.js`  
**Lines:** 282, 399, 509

Uses `escapeHtml()` for display, which is good, but candidate names, emails, and other fields are never validated before being sent to the backend.

---

### 12. **No CSRF Protection**
**File:** `backend/main.py`

If cookie-based authentication is added, state-changing operations need CSRF tokens.

---

### 13. **No Security Headers**
**File:** `backend/main.py`

Missing:
- `Strict-Transport-Security` (HSTS)
- `Content-Security-Policy` (CSP)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`

Nginx config (`nginx.conf.j2`) includes some, but FastAPI should also set them.

---

### 14. **GitHub Actions Secrets Not Validated**
**File:** `.github/workflows/ci-cd.yml`

Workflow runs even if required secrets are missing. Should fail early with clear error messages.

---

### 15. **Database Connection Not Pooled**
**File:** `backend/database.py`

Opens a new connection for every request. Under load, this causes connection exhaustion.

---

### 16. **Model Loading Not Thread-Safe**
**File:** `backend/embedding_engine.py`  
**Lines:** 15-25

Global `_model` with lazy loading may cause race conditions under concurrent requests.

---

## Medium-Severity Issues (P2)

### 17. **No Pagination on Candidate List**
**File:** `backend/main.py:123-139`

Returns all candidates in one response. With 1000+ candidates, this becomes slow.

---

### 18. **Frontend API URL Assumption**
**File:** `frontend/app.js:8`
```javascript
const API_BASE = window.location.origin + '/api';
```
**Issue:** Assumes frontend and backend are same-origin. Breaks if deployed separately (e.g., Vercel frontend + Render backend).

---

### 19. **Incomplete Test Coverage**
**File:** `backend/test_edge_cases.py`

Tests exist but don't cover:
- Authentication/authorization
- Rate limiting
- File upload size limits
- Concurrent requests
- Database transactions

---

### 20. **No Health Check for Database**
**File:** `backend/main.py:62-65`

`/api/health` only returns static JSON. Should check database connectivity.

---

## Low-Severity Issues (P3)

### 21. **SpaCy Model Auto-Download in Production**
**File:** `backend/resume_analyzer.py:16-19`

Downloads model on first run if missing. Should be pre-installed in Docker image (already done in Dockerfile).

---

### 22. **Unused Import in Tests**
**File:** `backend/test_edge_cases.py:11`

Comment says removed unused imports, but pytest still imports some unused modules.

---

### 23. **No HTTPS in Terraform**
**File:** `devops/terraform/main.tf`

Only HTTP (port 80) configured. HTTPS requires certificate management (Let's Encrypt + Certbot).

---

## Infrastructure & Deployment Issues

### 24. **Docker Volume Mounts Code Directory**
**File:** `docker-compose.yml:16`
```yaml
volumes:
  - resume_data:/app/backend  # ← Mounts entire backend dir
```
**Issue:** Can hide application code if volume already exists.

**Should be:** `/app/backend/data` or explicit DB path.

---

### 25. **No Backup Strategy Documented**

SQLite database has no backup/restore procedure.

---

### 26. **Ansible Inventory Has Placeholder Values**
**File:** `devops/ansible/inventory.ini:8`
```ini
resume-server ansible_host=YOUR_EC2_PUBLIC_IP
```
Should validate that placeholders are replaced before running.

---

### 27. **CI/CD Deploys on Every Push to Main**
**File:** `.github/workflows/ci-cd.yml:10`

No manual approval gate. Accidental pushes deploy to production.

---

## Privacy & Compliance Gaps

### 28. **No Privacy Policy or Data Retention Policy**

Application stores PII indefinitely with no:
- User consent mechanism
- Data retention limits
- Right to deletion (GDPR Article 17)
- Data export for users (GDPR Article 20)

---

### 29. **Resume Text Stored Unencrypted**
**File:** `backend/database.py:52`

Full resume text stored in plaintext in SQLite.

---

### 30. **No Audit Logging**

No record of:
- Who accessed which candidate
- When data was exported
- When candidates were deleted

---

## Positive Findings ✅

1. **Comprehensive test suite** — `test_edge_cases.py` covers PDF extraction, resume analysis, embedding engine, database, and API endpoints.
2. **Docker health checks** — Both Dockerfile and docker-compose have health checks.
3. **Input validation** — Pydantic models validate API request schemas.
4. **SQL injection protection** — Uses parameterized queries throughout.
5. **Gitignore properly configured** — Excludes secrets, databases, and credentials.
6. **HTML escaping in frontend** — `escapeHtml()` prevents basic XSS.
7. **WAL mode enabled** — SQLite configured with `PRAGMA journal_mode=WAL` for better concurrency.

---

## Summary of Findings by Severity

| Severity | Count | Examples |
|---|---|---|
| **Critical** | 5 | No auth, unrestricted CORS, SSH exposed, monitoring exposed, app port exposed |
| **High** | 4 | Upload validation gaps, no rate limiting, database path |
| **Medium** | 6 | Logging sensitive data, no CSRF, no security headers, etc. |
| **Low** | 3 | Health check, test coverage gaps |
| **Infrastructure** | 4 | Docker volumes, backup strategy, CI/CD gates |
| **Privacy/Compliance** | 3 | No privacy policy, unencrypted storage, no audit logs |

**Total Issues:** 30

---

## Recommended Fix Priority

### Phase 1 (Critical — Before Any Public Deployment)
1. Add authentication to all sensitive endpoints
2. Replace `allow_origins=["*"]` with explicit allowlist
3. Restrict SSH to trusted IPs only (via Terraform variable)
4. Remove Prometheus/Grafana from public internet (use VPN or IP whitelist)
5. Remove direct port 8000 access (force traffic through Nginx)
6. Add PDF upload validation (size, MIME, signature, page count)
7. Make database path configurable via environment variable

### Phase 2 (High — Before Production Load)
1. Add rate limiting (via slowapi or FastAPI middleware)
2. Add pagination to `/api/candidates`
3. Improve error handling (no sensitive data in logs)
4. Add security headers to FastAPI responses
5. Add database health check to `/api/health`
6. Document backup/restore procedures

### Phase 3 (Medium — Harden for Scale)
1. Add CSRF protection if using cookie auth
2. Add automated tests for auth, rate limiting, and security
3. Add proper secret management (GitHub Actions validation, env var checks)
4. Make frontend API URL configurable
5. Add HTTPS support to infrastructure

### Phase 4 (Compliance & Observability)
1. Add privacy policy and consent mechanism
2. Implement data retention and deletion workflows
3. Add audit logging for sensitive operations
4. Encrypt sensitive data at rest (or document why plaintext is acceptable for your use case)

---

## Next Steps

I will now implement the **Phase 1 and Phase 2 fixes** in the following order:

1. Add authentication and authorization system
2. Secure infrastructure (Terraform security groups)
3. Harden upload validation
4. Configure database persistence
5. Add rate limiting
6. Add pagination
7. Update CI/CD and tests
8. Update documentation

**Estimated completion:** All critical and high-priority fixes will be implemented and tested.

---

**End of Audit Report**
