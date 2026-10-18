# DEPLOYMENT PREPARATION - Credentials and Configuration

## ✅ Step 1: Generated Credentials

Copy these values to your hosting provider's environment variables:

### JWT Secret Key
```
Generate: python backend/generate_credentials.py
OR use: openssl rand -base64 64
```

### Admin Password Hash
```bash
# Generate password hash
python backend/generate_credentials.py

# Or run manually:
python backend/auth.py hash-password "A1zB2@c3#D4@E5% 2025-Oct"
```

## ✅ Step 2: Render.com Backend Deployment

1. Create a new Web Service on Render.com
2. Connect your GitHub repository
3. Configure build settings:
   ```
   Build Command: pip install -r requirements.txt
   Start Command: cd backend && python main.py
   Runtime: Python 3.11+
   ```

4. Set environment variables (Add Environment Variable for each):
   ```
   ENVIRONMENT=production
   JWT_SECRET_KEY=<YOUR_GENERATED_KEY>
   ADMIN_PASSWORD_HASH=<YOUR_GENERATED_HASH>
   CORS_ORIGINS=https://ai-resume-intelligence-system-v2.vercel.app
   DATABASE_PATH=/tmp/resume_db.sqlite
   RATE_LIMIT_ENABLED=true
   MAX_FILE_SIZE_MB=10
   MAX_BATCH_SIZE=20
   ```

5. Advanced: Database persistence
   ```
   Mount volume: /tmp/resume_db.sqlite → persistent storage
   Or set: DATABASE_PATH=/tmp/data/resume_db.sqlite on container startup
   ```

## ✅ Step 3: Vercel Frontend Deployment

1. Create a new project on Vercel
2. Connect to your Git repository
3. Root directory: `/` or select the frontend directory

4. Environment variables:
   ```
   NEXT_PUBLIC_API_URL=<Your Render backend URL>
   NEXT_PUBLIC_API_KEY=<Optional - for additional security>
   ```

5. Build settings:
   ```
   Framework: Next.js (auto-detect)
   Build command: npm run build
   Output directory: .next
   Framework presets: Next.js
   ```

6. Deploy - Vercel will build and deploy automatically

## ✅ Step 4: CORS Configuration Test

Before going to production, verify CORS allows communication:

```bash
# Test from frontend to backend
curl -X OPTIONS https://your-backend-url/api/health \
  -H "Origin: https://your-frontend-url.vercel.app" \
  -H "Access-Control-Request-Method: GET"
```

Expected response:
```
Access-Control-Allow-Origin: https://your-frontend-url.vercel.app
Access-Control-Allow-Credentials: true
```

## ✅ Step 5: API Health Check

After deployment, verify backend is running:

```bash
curl https://your-backend-url/api/health

# Expected response:
# {
#   "status": "healthy",
#   "version": "2.0.0",
#   "timestamp": "2025-10-17T...",
#   "database": {"status": "healthy"}
# }
```

## ✅ Step 6: Login Test

```bash
curl -X POST https://your-backend-url/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "A1zB2@c3#D4@E5%"}'
```

Expected:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {"username": "admin", "role": "admin"}
}
```

## ⚠️ Security Checklist

- [ ] Change admin password from default
- [ ] Generate unique JWT_SECRET_KEY (not in repository)
- [ ] Verify CORS origins only include your frontend
- [ ] Enable GitHub secret rotation
- [ ] Set up proper database backups
- [ ] Configure domain (custom domain on Vercel/Render)
- [ ] Enable HTTPS (automatic on Vercel/Render)

## 📝 Production Directories

Backend:
- Code: `backend/`
- Requirements: `backend/requirements.txt`
- Main entry: `backend/main.py`

Frontend:
- Dashboard: `frontend/index.html`, `frontend/index.css`, `frontend/app.js`

## 🚀 Quick Deployment Flow

1. Generate credentials → Copy to Render environment variables
2. Deploy backend on Render → Wait for URL
3. Deploy frontend on Vercel → Connect to Render backend
4. Test login & resume upload
5. Verify CORS in browser console
6. Go live - add domain, enable CDN

## 🐛 Troubleshooting

**Backend won't start:**
- Check JWT_SECRET_KEY is set
- Check uploads directory exists
- Check database permissions

**Frontend can't reach backend:**
- Verify CORS_ORIGINS includes frontend URL
- Check firewall/rule groups
- Test API directly in browser

**Database persistence issues:**
- Backup/restore database manually
- Mount volume in Render file system
- Use environment variable DATABASE_PATH

**Authentication fails:**
- Re-generate password hash
- Check JWT_SECRET_KEY matches
- Verify token expiration (24 hours)