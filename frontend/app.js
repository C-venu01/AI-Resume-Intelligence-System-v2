/**
 * AI Resume Intelligence System 2.0 — Frontend Application
 * Handles: API calls, drag-drop upload, candidate display,
 * job matching, search/filter, charts, export, and animations.
 */

// ==================== CONFIG ====================
const API_BASE = window.location.origin + '/api';
let selectedFiles = [];
let allCandidates = [];

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initUploadZone();
    initSearchAndFilters();
    loadDashboard();
});

// ==================== NAVIGATION ====================
function initNavigation() {
    const tabs = document.querySelectorAll('.nav-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Update nav
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    const activeNav = document.querySelector(`.nav-tab[data-tab="${tabName}"]`);
    if (activeNav) activeNav.classList.add('active');

    // Update content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const activeContent = document.getElementById(`tab-${tabName}`);
    if (activeContent) activeContent.classList.add('active');

    // Load data for specific tabs
    if (tabName === 'dashboard') loadDashboard();
    if (tabName === 'candidates') loadCandidates();
    if (tabName === 'analytics') loadAnalytics();
}

// ==================== DASHBOARD ====================
async function loadDashboard() {
    try {
        const stats = await apiGet('/stats');
        animateCounter('stat-total', stats.total_candidates || 0);
        animateCounter('stat-avg-score', Math.round(stats.avg_score || 0));
        animateCounter('stat-top-score', stats.top_score || 0);

        // Top specialization
        const specDist = stats.specialization_distribution || {};
        const topRole = Object.entries(specDist).sort((a, b) => b[1] - a[1])[0];
        const topRoleEl = document.getElementById('stat-top-role');
        if (topRoleEl) {
            topRoleEl.textContent = topRole ? topRole[0] : '—';
            topRoleEl.style.fontSize = '16px';
        }

        // Load top candidates
        const data = await apiGet('/candidates?sort_by=overall_score&sort_order=desc');
        const topCandidates = (data.candidates || []).slice(0, 3);
        const grid = document.getElementById('dashboard-top-candidates');
        const empty = document.getElementById('dashboard-empty');

        if (topCandidates.length > 0) {
            grid.innerHTML = topCandidates.map((c, i) => createCandidateCard(c, i + 1)).join('');
            grid.style.display = 'grid';
            empty.style.display = 'none';
            renderAllScoreGauges(grid);
        } else {
            grid.style.display = 'none';
            empty.style.display = 'block';
        }
    } catch (err) {
        console.error('Dashboard load error:', err);
    }
}

function animateCounter(elementId, target) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const duration = 1000;
    const start = parseInt(el.textContent) || 0;
    const diff = target - start;
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        el.textContent = Math.round(start + diff * eased);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ==================== FILE UPLOAD ====================
function initUploadZone() {
    const zone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('browse-btn');

    // Click to browse
    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
    });
    zone.addEventListener('click', () => fileInput.click());

    // File selection
    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

    // Drag and drop
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        handleFiles(e.dataTransfer.files);
    });
}

function handleFiles(fileList) {
    const pdfs = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));

    if (pdfs.length === 0) {
        showToast('Please select PDF files only', 'error');
        return;
    }

    selectedFiles = pdfs;
    renderFileList();
    document.getElementById('analyze-wrapper').classList.remove('hidden');
    showToast(`${pdfs.length} file(s) selected`, 'info');
}

function renderFileList() {
    const list = document.getElementById('file-list');
    list.innerHTML = selectedFiles.map(f => `
        <div class="file-item">
            <span class="file-item-name">📄 ${f.name}</span>
            <span class="file-item-status">${(f.size / 1024).toFixed(0)} KB</span>
        </div>
    `).join('');
}

async function analyzeFiles() {
    if (selectedFiles.length === 0) {
        showToast('No files selected', 'error');
        return;
    }

    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    progressContainer.classList.add('visible');

    showLoading('Uploading and analyzing resumes...');

    try {
        const formData = new FormData();
        selectedFiles.forEach(f => formData.append('files', f));

        progressBar.style.width = '30%';
        progressText.textContent = 'Uploading files...';

        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData,
        });

        progressBar.style.width = '70%';
        progressText.textContent = 'Analyzing with AI...';

        const result = await response.json();

        progressBar.style.width = '100%';
        progressText.textContent = `✅ Done! ${result.success} analyzed, ${result.failed} failed`;

        hideLoading();

        if (result.success > 0) {
            showToast(`${result.success} resume(s) analyzed successfully!`, 'success');

            // Update file list with status
            const list = document.getElementById('file-list');
            list.innerHTML = selectedFiles.map(f => {
                const analyzed = result.candidates.find(c => c.filename === f.name);
                const errored = result.errors.find(e => e.filename === f.name);
                const status = analyzed ? 'success' : (errored ? 'error' : 'processing');
                const label = analyzed ? `Score: ${analyzed.overall_score}` : (errored ? errored.error : 'Pending');
                return `
                    <div class="file-item">
                        <span class="file-item-name">📄 ${f.name}</span>
                        <span class="file-item-status ${status}">${label}</span>
                    </div>
                `;
            }).join('');

            // Auto-switch to candidates after delay
            setTimeout(() => switchTab('candidates'), 1500);
        } else {
            showToast('Could not analyze any resumes.', 'error');
        }

        selectedFiles = [];
        document.getElementById('analyze-wrapper').classList.add('hidden');

    } catch (err) {
        hideLoading();
        showToast('Upload failed: ' + err.message, 'error');
        progressText.textContent = '❌ Error occurred';
    }
}

// ==================== CANDIDATES ====================
function initSearchAndFilters() {
    const searchInput = document.getElementById('search-input');
    const filterLevel = document.getElementById('filter-level');
    const sortBy = document.getElementById('sort-by');

    let debounceTimer;
    searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(loadCandidates, 300);
    });
    filterLevel.addEventListener('change', loadCandidates);
    sortBy.addEventListener('change', loadCandidates);
}

async function loadCandidates() {
    const search = document.getElementById('search-input').value;
    const level = document.getElementById('filter-level').value;
    const sortBy = document.getElementById('sort-by').value;

    try {
        const params = new URLSearchParams({
            search, sort_by: sortBy, sort_order: 'desc', experience_level: level,
        });
        const data = await apiGet(`/candidates?${params}`);
        allCandidates = data.candidates || [];

        const grid = document.getElementById('candidates-grid');
        const empty = document.getElementById('candidates-empty');
        const countEl = document.getElementById('candidates-count');

        countEl.textContent = allCandidates.length;

        if (allCandidates.length > 0) {
            grid.innerHTML = allCandidates.map((c, i) => createCandidateCard(c, i + 1)).join('');
            grid.style.display = 'grid';
            empty.style.display = 'none';
            renderAllScoreGauges(grid);
        } else {
            grid.style.display = 'none';
            empty.style.display = 'block';
        }
    } catch (err) {
        console.error('Load candidates error:', err);
    }
}

function createCandidateCard(c, rank) {
    const scoreColor = c.overall_score >= 80 ? '#48bb78' : c.overall_score >= 60 ? '#667eea' : c.overall_score >= 40 ? '#ed8936' : '#fc5c65';
    const techs = (c.technologies || []).slice(0, 5);
    const certs = (c.certifications || []).slice(0, 2);

    return `
        <div class="candidate-card" id="card-${c.id}">
            <div class="candidate-rank">${rank}</div>
            <div class="candidate-card-header">
                <div class="candidate-info">
                    <div class="candidate-name">${escapeHtml(c.candidate_name)}</div>
                    <div class="candidate-role">${escapeHtml(c.specialization || 'Software Developer')}</div>
                </div>
                <div class="candidate-score-gauge">
                    <canvas id="gauge-${c.id}" width="120" height="120" data-score="${c.overall_score}" data-color="${scoreColor}"></canvas>
                    <div class="candidate-score-value" style="color:${scoreColor}">${c.overall_score}</div>
                </div>
            </div>

            <div class="candidate-details">
                <div class="candidate-detail">
                    <span class="candidate-detail-icon">💼</span>
                    ${c.experience_years} yr(s) • ${c.experience_level}
                </div>
                <div class="candidate-detail">
                    <span class="candidate-detail-icon">🎓</span>
                    ${escapeHtml(c.education || 'N/A')}
                </div>
                <div class="candidate-detail">
                    <span class="candidate-detail-icon">📧</span>
                    ${escapeHtml(c.email || 'N/A')}
                </div>
                <div class="candidate-detail">
                    <span class="candidate-detail-icon">📱</span>
                    ${escapeHtml(c.phone || 'N/A')}
                </div>
            </div>

            <div class="candidate-techs">
                ${techs.map(t => `<span class="tech-badge">${escapeHtml(t)}</span>`).join('')}
                ${techs.length < (c.technologies || []).length ? `<span class="tech-badge">+${(c.technologies || []).length - techs.length}</span>` : ''}
                ${certs.map(t => `<span class="tech-badge cert">${escapeHtml(t)}</span>`).join('')}
            </div>

            <div class="candidate-actions">
                <button class="btn btn-secondary btn-sm" onclick="viewCandidate(${c.id})" id="view-${c.id}">👁️ Details</button>
                <button class="btn btn-danger btn-sm" onclick="deleteCandidate(${c.id})" id="delete-${c.id}">🗑️</button>
            </div>

            ${c.job_match_score != null ? `
                <div style="margin-top:12px; padding-top:12px; border-top:1px solid rgba(255,255,255,0.05);">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:13px; color:var(--text-secondary);">Job Match</span>
                        <span class="match-score-badge ${getMatchClass(c.job_match_score)}">${c.job_match_score}% — ${c.match_level}</span>
                    </div>
                    ${c.skill_gaps && c.skill_gaps.length > 0 ? `
                        <div class="skill-gaps-list">
                            ${c.skill_gaps.slice(0, 4).map(g => `<span class="gap-badge">${escapeHtml(g)}</span>`).join('')}
                        </div>
                    ` : ''}
                </div>
            ` : ''}
        </div>
    `;
}

function renderAllScoreGauges(container) {
    const canvases = container.querySelectorAll('canvas[data-score]');
    canvases.forEach(canvas => {
        const score = parseInt(canvas.dataset.score) || 0;
        const color = canvas.dataset.color || '#667eea';
        drawScoreGauge(canvas, score, color);
    });
}

function drawScoreGauge(canvas, score, color) {
    const ctx = canvas.getContext('2d');
    const size = 60;
    const center = size / 2;
    const radius = center - 5;
    const lineWidth = 5;

    // Ensure canvas is sized correctly
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';

    // Background arc
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = lineWidth;
    ctx.stroke();

    // Score arc — animate
    const targetAngle = (score / 100) * Math.PI * 2;
    let currentAngle = 0;
    const startAngle = -Math.PI / 2;

    function animate() {
        if (currentAngle >= targetAngle) return;
        currentAngle = Math.min(currentAngle + 0.05, targetAngle);

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // BG
        ctx.beginPath();
        ctx.arc(center, center, radius, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255,255,255,0.06)';
        ctx.lineWidth = lineWidth;
        ctx.stroke();

        // Score
        ctx.beginPath();
        ctx.arc(center, center, radius, startAngle, startAngle + currentAngle);
        ctx.strokeStyle = color;
        ctx.lineWidth = lineWidth;
        ctx.lineCap = 'round';
        ctx.stroke();

        requestAnimationFrame(animate);
    }
    animate();
}

async function viewCandidate(id) {
    try {
        const c = await apiGet(`/candidates/${id}`);
        const achievements = (c.notable_achievements || []).map(a => `<li style="margin-bottom:6px;font-size:13px;color:var(--text-secondary)">✅ ${escapeHtml(a)}</li>`).join('');
        const softSkills = (c.soft_skills || []).map(s => `<span class="tech-badge">${escapeHtml(s)}</span>`).join('');

        const modal = document.createElement('div');
        modal.className = 'loading-overlay visible';
        modal.style.cursor = 'pointer';
        modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

        modal.innerHTML = `
            <div class="glass-card" style="max-width:600px;width:90%;max-height:80vh;overflow-y:auto;cursor:default;" onclick="event.stopPropagation()">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
                    <h2 style="font-size:20px;font-weight:600;">${escapeHtml(c.candidate_name)}</h2>
                    <button class="btn btn-secondary btn-sm" onclick="this.closest('.loading-overlay').remove()">✕ Close</button>
                </div>
                <p style="color:var(--accent-cyan);font-size:14px;margin-bottom:16px;">${escapeHtml(c.specialization)} • ${c.experience_level} • ${c.experience_years} yr(s)</p>
                <div style="background:var(--bg-glass);padding:16px;border-radius:var(--radius-md);margin-bottom:16px;">
                    <p style="font-size:13px;color:var(--text-secondary);line-height:1.7;">${escapeHtml(c.candidate_summary)}</p>
                </div>
                <div style="margin-bottom:16px;">
                    <strong style="font-size:14px;">📧</strong> ${escapeHtml(c.email)} &nbsp; <strong>📱</strong> ${escapeHtml(c.phone)}
                    ${c.linkedin ? `<br><strong>🔗</strong> <a href="${escapeHtml(c.linkedin)}" target="_blank" style="color:var(--accent-blue);">${escapeHtml(c.linkedin)}</a>` : ''}
                </div>
                <div style="margin-bottom:16px;">
                    <strong style="font-size:14px;">🎓 Education:</strong> ${escapeHtml(c.education)}
                    ${c.cgpa ? ` (CGPA: ${c.cgpa})` : ''}
                </div>
                <div style="margin-bottom:16px;">
                    <strong style="font-size:14px;">🛠️ Technologies</strong>
                    <div class="candidate-techs" style="margin-top:8px;">
                        ${(c.technologies || []).map(t => `<span class="tech-badge">${escapeHtml(t)}</span>`).join('')}
                    </div>
                </div>
                ${(c.certifications || []).length > 0 ? `
                <div style="margin-bottom:16px;">
                    <strong style="font-size:14px;">🏅 Certifications</strong>
                    <div class="candidate-techs" style="margin-top:8px;">
                        ${c.certifications.map(t => `<span class="tech-badge cert">${escapeHtml(t)}</span>`).join('')}
                    </div>
                </div>` : ''}
                ${softSkills ? `
                <div style="margin-bottom:16px;">
                    <strong style="font-size:14px;">💡 Soft Skills</strong>
                    <div class="candidate-techs" style="margin-top:8px;">${softSkills}</div>
                </div>` : ''}
                ${achievements ? `
                <div style="margin-bottom:16px;">
                    <strong style="font-size:14px;">🏆 Achievements</strong>
                    <ul style="margin-top:8px;list-style:none;">${achievements}</ul>
                </div>` : ''}
                <div style="text-align:center;padding-top:16px;border-top:1px solid var(--border-glass);">
                    <span style="font-size:32px;font-weight:800;background:var(--accent-gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">${c.overall_score}/100</span>
                    <p style="color:var(--text-secondary);font-size:13px;margin-top:4px;">Overall Score</p>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    } catch (err) {
        showToast('Error loading candidate details', 'error');
    }
}

async function deleteCandidate(id) {
    if (!confirm('Delete this candidate?')) return;
    try {
        await apiDelete(`/candidates/${id}`);
        showToast('Candidate deleted', 'success');
        loadCandidates();
        loadDashboard();
    } catch (err) {
        showToast('Delete failed', 'error');
    }
}

// ==================== JOB MATCHING ====================
async function runJobMatch() {
    const title = document.getElementById('job-title').value.trim();
    const desc = document.getElementById('job-description').value.trim();

    if (!title || desc.length < 10) {
        showToast('Please enter a job title and description (min 10 chars)', 'error');
        return;
    }

    showLoading('Running AI semantic matching...');

    try {
        const result = await apiPost('/job-match', {
            job_title: title,
            job_description: desc,
        });

        hideLoading();

        const container = document.getElementById('match-results');
        const candidates = result.candidates || [];

        if (candidates.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">⚠️</div>
                    <div class="empty-state-title">No candidates to match</div>
                    <div class="empty-state-text">Upload resumes first</div>
                </div>`;
            return;
        }

        container.innerHTML = candidates.map((c, i) => `
            <div class="match-result-card">
                <div class="match-header">
                    <div>
                        <strong style="font-size:15px;">#${i + 1} ${escapeHtml(c.candidate_name)}</strong>
                        <span style="font-size:12px;color:var(--text-muted);margin-left:8px;">${escapeHtml(c.specialization)}</span>
                    </div>
                    <span class="match-score-badge ${getMatchClass(c.job_match_score)}">
                        ${c.job_match_score}% — ${c.match_level}
                    </span>
                </div>
                <p style="font-size:12px;color:var(--text-secondary);margin-bottom:8px;">
                    Resume Score: ${c.overall_score}/100 • ${c.experience_years} yr(s) exp
                </p>
                ${c.skill_gaps && c.skill_gaps.length > 0 ? `
                    <div>
                        <span style="font-size:12px;color:var(--text-muted);">Missing skills:</span>
                        <div class="skill-gaps-list">
                            ${c.skill_gaps.map(g => `<span class="gap-badge">${escapeHtml(g)}</span>`).join('')}
                        </div>
                    </div>
                ` : '<p style="font-size:12px;color:var(--accent-green);">✅ No skill gaps detected</p>'}
                ${c.suggestions && c.suggestions.length > 0 ? `
                    <div class="suggestions-list">
                        ${c.suggestions.slice(0, 3).map(s => `
                            <div class="suggestion-item">
                                <span class="suggestion-skill">📚 ${escapeHtml(s.skill)}:</span>
                                <span class="suggestion-resource">${escapeHtml(s.resource)}</span>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `).join('');

        showToast(`Matched ${candidates.length} candidates!`, 'success');
    } catch (err) {
        hideLoading();
        showToast('Job matching failed: ' + err.message, 'error');
    }
}

function getMatchClass(score) {
    if (score >= 75) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 40) return 'moderate';
    return 'low';
}

// ==================== ANALYTICS ====================
async function loadAnalytics() {
    try {
        const stats = await apiGet('/stats');
        drawTechChart(stats.top_technologies || {});
        drawExperienceChart(stats.experience_distribution || {});
        drawSpecializationChart(stats.specialization_distribution || {});
        drawScoreHistogram();
    } catch (err) {
        console.error('Analytics error:', err);
    }
}

function drawTechChart(data) {
    const canvas = document.getElementById('chart-technologies');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const entries = Object.entries(data).slice(0, 8);
    if (entries.length === 0) return drawEmptyChart(ctx, canvas, 'No data');

    const width = canvas.parentElement.clientWidth - 48;
    const height = 250;
    canvas.width = width * 2;
    canvas.height = height * 2;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.scale(2, 2);

    const maxVal = Math.max(...entries.map(e => e[1]));
    const barWidth = Math.min(40, (width - 60) / entries.length - 10);
    const colors = ['#667eea', '#764ba2', '#f093fb', '#4fd1c5', '#48bb78', '#ed8936', '#fc5c65', '#667eea'];

    ctx.clearRect(0, 0, width, height);

    entries.forEach(([label, value], i) => {
        const x = 50 + i * (barWidth + 10);
        const barHeight = (value / maxVal) * (height - 60);
        const y = height - 30 - barHeight;

        // Bar
        ctx.fillStyle = colors[i % colors.length];
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, 4);
        ctx.fill();

        // Label
        ctx.fillStyle = '#9898b0';
        ctx.font = '10px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(label.length > 8 ? label.substring(0, 7) + '…' : label, x + barWidth / 2, height - 12);

        // Value
        ctx.fillStyle = '#e8e8f0';
        ctx.fillText(value, x + barWidth / 2, y - 6);
    });
}

function drawExperienceChart(data) {
    const canvas = document.getElementById('chart-experience');
    if (!canvas) return;
    drawPieChart(canvas, data);
}

function drawSpecializationChart(data) {
    const canvas = document.getElementById('chart-specializations');
    if (!canvas) return;
    drawPieChart(canvas, data);
}

function drawPieChart(canvas, data) {
    const ctx = canvas.getContext('2d');
    const entries = Object.entries(data);
    if (entries.length === 0) return drawEmptyChart(ctx, canvas, 'No data');

    const width = canvas.parentElement.clientWidth - 48;
    const height = 250;
    canvas.width = width * 2;
    canvas.height = height * 2;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.scale(2, 2);

    const total = entries.reduce((sum, e) => sum + e[1], 0);
    const centerX = width / 3;
    const centerY = height / 2;
    const radius = Math.min(centerX, centerY) - 20;
    const colors = ['#667eea', '#764ba2', '#f093fb', '#4fd1c5', '#48bb78', '#ed8936', '#fc5c65', '#818cf8'];

    ctx.clearRect(0, 0, width, height);

    let startAngle = -Math.PI / 2;
    entries.forEach(([label, value], i) => {
        const slice = (value / total) * Math.PI * 2;

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, startAngle + slice);
        ctx.fillStyle = colors[i % colors.length];
        ctx.fill();

        startAngle += slice;
    });

    // Inner circle (donut)
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius * 0.55, 0, Math.PI * 2);
    ctx.fillStyle = '#111127';
    ctx.fill();

    // Legend
    const legendX = centerX * 2 + 20;
    entries.forEach(([label, value], i) => {
        const y = 30 + i * 22;
        ctx.fillStyle = colors[i % colors.length];
        ctx.fillRect(legendX, y, 10, 10);
        ctx.fillStyle = '#9898b0';
        ctx.font = '11px Inter';
        ctx.textAlign = 'left';
        const text = label.length > 15 ? label.substring(0, 14) + '…' : label;
        ctx.fillText(`${text} (${value})`, legendX + 16, y + 9);
    });
}

async function drawScoreHistogram() {
    const canvas = document.getElementById('chart-scores');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    try {
        const data = await apiGet('/candidates');
        const candidates = data.candidates || [];

        if (candidates.length === 0) return drawEmptyChart(ctx, canvas, 'No data');

        const width = canvas.parentElement.clientWidth - 48;
        const height = 250;
        canvas.width = width * 2;
        canvas.height = height * 2;
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        ctx.scale(2, 2);
        ctx.clearRect(0, 0, width, height);

        // Buckets: 0-20, 20-40, 40-60, 60-80, 80-100
        const buckets = [0, 0, 0, 0, 0];
        const bucketLabels = ['0-20', '20-40', '40-60', '60-80', '80-100'];
        const bucketColors = ['#fc5c65', '#ed8936', '#ecc94b', '#667eea', '#48bb78'];

        candidates.forEach(c => {
            const s = c.overall_score || 0;
            if (s < 20) buckets[0]++;
            else if (s < 40) buckets[1]++;
            else if (s < 60) buckets[2]++;
            else if (s < 80) buckets[3]++;
            else buckets[4]++;
        });

        const maxVal = Math.max(...buckets, 1);
        const barWidth = (width - 80) / 5 - 10;

        buckets.forEach((count, i) => {
            const x = 50 + i * (barWidth + 10);
            const barHeight = (count / maxVal) * (height - 60);
            const y = height - 30 - barHeight;

            ctx.fillStyle = bucketColors[i];
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, barHeight, 4);
            ctx.fill();

            ctx.fillStyle = '#9898b0';
            ctx.font = '11px Inter';
            ctx.textAlign = 'center';
            ctx.fillText(bucketLabels[i], x + barWidth / 2, height - 12);
            ctx.fillStyle = '#e8e8f0';
            ctx.fillText(count, x + barWidth / 2, y - 6);
        });
    } catch (err) {
        drawEmptyChart(ctx, canvas, 'Error loading');
    }
}

function drawEmptyChart(ctx, canvas, message) {
    const width = canvas.parentElement.clientWidth - 48;
    const height = 250;
    canvas.width = width * 2;
    canvas.height = height * 2;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.scale(2, 2);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#6a6a80';
    ctx.font = '14px Inter';
    ctx.textAlign = 'center';
    ctx.fillText(message, width / 2, height / 2);
}

// ==================== EXPORT ====================
async function exportData(format) {
    try {
        const response = await fetch(`${API_BASE}/export/${format}`);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `candidates_${new Date().toISOString().slice(0, 10)}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
        showToast(`Exported as ${format.toUpperCase()}`, 'success');
    } catch (err) {
        showToast('Export failed', 'error');
    }
}

async function clearAll() {
    if (!confirm('Delete ALL candidates? This cannot be undone.')) return;
    try {
        await apiDelete('/candidates');
        showToast('All candidates deleted', 'success');
        loadDashboard();
        loadCandidates();
    } catch (err) {
        showToast('Clear failed', 'error');
    }
}

// ==================== API HELPERS ====================
async function apiGet(path) {
    const res = await fetch(API_BASE + path);
    if (!res.ok) throw new Error(`API Error: ${res.status}`);
    return res.json();
}

async function apiPost(path, body) {
    const res = await fetch(API_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `API Error: ${res.status}`);
    }
    return res.json();
}

async function apiDelete(path) {
    const res = await fetch(API_BASE + path, { method: 'DELETE' });
    if (!res.ok) throw new Error(`API Error: ${res.status}`);
    return res.json();
}

// ==================== UI HELPERS ====================
function showLoading(text = 'Processing...') {
    const overlay = document.getElementById('loading-overlay');
    const loadingText = document.getElementById('loading-text');
    loadingText.textContent = text;
    overlay.classList.add('visible');
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.remove('visible');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `${icons[type] || 'ℹ️'} ${escapeHtml(message)}`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
