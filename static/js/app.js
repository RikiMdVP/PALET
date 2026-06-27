/* ══════════════════════════════════════════════════════════════════════
   PALET GUI — Frontend logic v2.0
   Enhanced: stepper, sparkline, donut chart, skeletons, responsive
   ══════════════════════════════════════════════════════════════════════ */

const PHASES = ["ARQ", "QSP", "SE", "MAP", "PRISMA", "Synthesis", "Report"];

const PHASE_ICONS = {
    ARQ: '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    QSP: '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    SE: '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
    MAP: '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    PRISMA: '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    Synthesis: '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    Report: '<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
};

// Teal-based palette for charts
const CHART_COLORS = [
    '#1a7a6d', '#2d9d6a', '#4db8a4', '#7accc0', '#a8ddd4',
    '#d48806', '#d94045', '#5c5c66'
];

let pollingInterval = null;
let currentView = "dashboard";
let openPhaseDetails = new Set();
let pipelineStartTime = null;
let timerInterval = null;

// ══════════════════════════════════════════════════════════════════
// Navigation
// ══════════════════════════════════════════════════════════════════

function navigateTo(view) {
    currentView = view;
    closeMobileSidebar();

    document.querySelectorAll(".nav-item").forEach(el => {
        el.classList.toggle("active", el.dataset.view === view);
    });

    document.querySelectorAll(".view").forEach(el => {
        el.classList.toggle("active", el.id === `view-${view}`);
    });

    if (view === "dashboard") loadDashboard();
    if (view === "history") loadHistory();
    if (view === "execution") checkExecutionState();
}

// ══════════════════════════════════════════════════════════════════
// Responsive sidebar
// ══════════════════════════════════════════════════════════════════

function openMobileSidebar() {
    document.getElementById("sidebar").classList.add("open");
    document.getElementById("sidebar-overlay").classList.add("open");
}

function closeMobileSidebar() {
    document.getElementById("sidebar").classList.remove("open");
    document.getElementById("sidebar-overlay").classList.remove("open");
}

// ══════════════════════════════════════════════════════════════════
// Dark Mode
// ══════════════════════════════════════════════════════════════════

function initTheme() {
    const saved = localStorage.getItem("palet-theme");
    if (saved === "dark") document.body.classList.add("dark");
    updateThemeIcon();
}

function toggleTheme() {
    document.body.classList.toggle("dark");
    const isDark = document.body.classList.contains("dark");
    localStorage.setItem("palet-theme", isDark ? "dark" : "light");
    updateThemeIcon();
}

function updateThemeIcon() {
    const isDark = document.body.classList.contains("dark");
    const moon = document.getElementById("theme-icon-moon");
    const sun = document.getElementById("theme-icon-sun");
    if (moon && sun) {
        moon.style.display = isDark ? "none" : "block";
        sun.style.display = isDark ? "block" : "none";
    }
}

// ══════════════════════════════════════════════════════════════════
// Dashboard
// ══════════════════════════════════════════════════════════════════

async function loadDashboard() {
    try {
        const runs = await fetchJSON("/api/history");

        document.getElementById("stat-total-runs").textContent = runs.length;

        const lastRunDetail = document.getElementById("dashboard-last-run");

        if (runs.length > 0) {
            const last = runs[0];
            document.getElementById("stat-last-papers").textContent = last.papers_count || "—";
            document.getElementById("stat-last-rqs").textContent = last.rqs_count || "—";

            if (last.status === "completed") {
                lastRunDetail.innerHTML = renderLastRunCard(last);
                lastRunDetail.style.display = "block";
            } else {
                lastRunDetail.style.display = "none";
            }

            // Sparkline
            renderSparkline(runs);
        } else {
            lastRunDetail.style.display = "none";
            document.getElementById("dashboard-sparkline").style.display = "none";
        }

        renderRunsList(runs.slice(0, 5), "dashboard-recent");
    } catch {
        document.getElementById("dashboard-recent").innerHTML =
            '<p class="empty-state">Aún no hay revisiones. Comienza configurando tu primera revisión sistemática.</p>';
    }
}

function renderLastRunCard(run) {
    const date = formatTimestamp(run.timestamp);
    const duration = run.started_at && run.finished_at
        ? formatDuration((new Date(run.finished_at) - new Date(run.started_at)) / 1000)
        : "—";
    const prompt = (run.seed_prompt_preview || "").substring(0, 200);

    let html = `
        <div class="last-run-card">
            <div class="last-run-header">
                <span class="last-run-title">Última ejecución completada</span>
                <span class="last-run-date">${date}</span>
            </div>
            <div class="last-run-prompt">${escapeHtml(prompt)}${prompt.length >= 200 ? '…' : ''}</div>
            <div class="last-run-stats">
                <div class="last-run-stat">
                    <span class="last-run-stat-value">${run.papers_count || 0}</span>
                    <span class="last-run-stat-label">papers</span>
                </div>
                <div class="last-run-stat">
                    <span class="last-run-stat-value">${run.rqs_count || 0}</span>
                    <span class="last-run-stat-label">RQs</span>
                </div>
                <div class="last-run-stat">
                    <span class="last-run-stat-value">${duration}</span>
                    <span class="last-run-stat-label">duración</span>
                </div>
            </div>`;

    if (run.params) {
        const p = run.params;
        const tags = [];
        if (p.database) tags.push(p.database.toUpperCase());
        if (p.max_results) tags.push(`máx. ${p.max_results} papers`);
        if (p.min_year && p.max_year) tags.push(`${p.min_year}–${p.max_year}`);
        if (p.doc_types) tags.push(p.doc_types.join(", "));

        if (tags.length) {
            html += `<div class="last-run-tags">${tags.map(t => `<span class="detail-tag">${escapeHtml(t)}</span>`).join("")}</div>`;
        }
    }

    html += `</div>`;
    return html;
}

// ══════════════════════════════════════════════════════════════════
// Sparkline Chart
// ══════════════════════════════════════════════════════════════════

function renderSparkline(runs) {
    const container = document.getElementById("dashboard-sparkline");
    const chart = document.getElementById("sparkline-chart");

    // Get up to 10 most recent completed runs
    const completed = runs
        .filter(r => r.status === "completed" && r.papers_count > 0)
        .slice(0, 10)
        .reverse();

    if (completed.length < 2) {
        container.style.display = "none";
        return;
    }

    container.style.display = "block";

    const values = completed.map(r => r.papers_count || 0);
    const max = Math.max(...values);
    const w = 100;
    const h = 60;
    const padding = 4;
    const innerW = w - padding * 2;
    const innerH = h - padding * 2;

    const points = values.map((v, i) => {
        const x = padding + (i / (values.length - 1)) * innerW;
        const y = padding + innerH - (v / max) * innerH;
        return [x, y];
    });

    const linePoints = points.map(p => p.join(",")).join(" ");

    // Area (closed path to bottom)
    const areaPath = `M ${points[0][0]},${h - padding} L ${points.map(p => p.join(",")).join(" L ")} L ${points[points.length - 1][0]},${h - padding} Z`;

    const dots = points.map((p, i) =>
        `<circle class="sparkline-dot" cx="${p[0]}" cy="${p[1]}" r="2" opacity="${i === points.length - 1 ? '1' : '0.5'}">
            <title>${values[i]} papers</title>
        </circle>`
    ).join("");

    chart.innerHTML = `
        <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
            <path class="sparkline-area" d="${areaPath}"/>
            <polyline class="sparkline-line" points="${linePoints}"/>
            ${dots}
        </svg>
    `;
}

// ══════════════════════════════════════════════════════════════════
// History
// ══════════════════════════════════════════════════════════════════

async function loadHistory() {
    try {
        const runs = await fetchJSON("/api/history");
        renderRunsList(runs, "history-list");
    } catch {
        document.getElementById("history-list").innerHTML =
            '<p class="empty-state">Aún no hay revisiones registradas.</p>';
    }
}

function renderRunsList(runs, containerId) {
    const container = document.getElementById(containerId);

    if (!runs || runs.length === 0) {
        container.innerHTML = '<p class="empty-state">Aún no hay revisiones. Comienza tu primera revisión sistemática.</p>';
        return;
    }

    container.innerHTML = runs.map(run => {
        const date = formatTimestamp(run.timestamp);
        const preview = (run.seed_prompt_preview || "").substring(0, 80);
        const status = run.status || "unknown";
        return `
            <div class="run-item status-${status}">
                <span class="run-date">${date}</span>
                <span class="run-prompt" title="${escapeHtml(run.seed_prompt_preview || "")}">${escapeHtml(preview)}${preview.length >= 80 ? "…" : ""}</span>
                <span class="run-papers">${run.papers_count || 0} papers</span>
                <span class="run-status ${status}">${status}</span>
            </div>
        `;
    }).join("");
}

// ══════════════════════════════════════════════════════════════════
// Cost Estimation
// ══════════════════════════════════════════════════════════════════

let costDebounce = null;

function setupCostEstimation() {
    const textarea = document.getElementById("seed-prompt");
    const maxResults = document.getElementById("max-results");
    const charCount = document.getElementById("char-count");

    const update = () => {
        charCount.textContent = `${textarea.value.length} caracteres`;
        clearTimeout(costDebounce);
        costDebounce = setTimeout(() => updateCostEstimate(), 400);
    };

    textarea.addEventListener("input", update);
    maxResults.addEventListener("input", update);
}

async function updateCostEstimate() {
    const prompt = document.getElementById("seed-prompt").value;
    const maxResults = parseInt(document.getElementById("max-results").value) || 20;
    const card = document.getElementById("cost-estimate");

    if (prompt.length < 20) {
        card.style.display = "none";
        return;
    }

    try {
        const data = await fetchJSON("/api/estimate-cost", {
            method: "POST",
            body: JSON.stringify({ seed_prompt: prompt, max_results: maxResults }),
        });

        document.getElementById("cost-usd").textContent = `$${data.total_cost_usd.toFixed(3)}`;
        document.getElementById("cost-eur").textContent = `€${data.total_cost_eur.toFixed(3)}`;
        document.getElementById("cost-tokens").textContent = formatNumber(data.total_input_tokens + data.total_output_tokens);
        card.style.display = "block";
    } catch (err) {
        console.error("Cost estimation error:", err);
    }
}

// ══════════════════════════════════════════════════════════════════
// Seed Prompt Modal
// ══════════════════════════════════════════════════════════════════

async function showSeedPrompts() {
    const modal = document.getElementById("modal-seeds");
    const list = document.getElementById("seeds-list");
    modal.classList.add("open");

    try {
        const seeds = await fetchJSON("/api/prompts");
        if (seeds.length === 0) {
            list.innerHTML = '<p class="empty-state">No se encontraron seed prompts en prompts/.</p>';
            return;
        }

        list.innerHTML = seeds.map(s => `
            <div class="seed-option" onclick="selectSeed('${s.filename}')">
                <div class="seed-name">${s.filename}</div>
                <div class="seed-preview">${escapeHtml(s.preview)}</div>
            </div>
        `).join("");
    } catch {
        list.innerHTML = '<p class="empty-state">Error cargando prompts.</p>';
    }
}

async function selectSeed(filename) {
    try {
        const res = await fetch(`/api/download/prompts/${filename}`);
        const text = await res.text();
        document.getElementById("seed-prompt").value = text;
        document.getElementById("char-count").textContent = `${text.length} caracteres`;
        closeSeedModal();
        updateCostEstimate();
    } catch (err) {
        console.error("Error loading seed:", err);
    }
}

function closeSeedModal(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById("modal-seeds").classList.remove("open");
}

// ══════════════════════════════════════════════════════════════════
// Launch Pipeline
// ══════════════════════════════════════════════════════════════════

async function launchPipeline() {
    const seedPrompt = document.getElementById("seed-prompt").value.trim();

    if (!seedPrompt) {
        alert("Escribe un seed prompt antes de iniciar la revisión.");
        return;
    }

    if (seedPrompt.length < 50) {
        if (!confirm("El seed prompt es muy corto. ¿Continuar de todas formas?")) return;
    }

    const docTypes = Array.from(document.querySelectorAll('input[name="doc-type"]:checked')).map(el => el.value);
    const databases = Array.from(document.querySelectorAll('input[name="database"]:checked')).map(el => el.value);
    let database = "openalex";
    if (databases.includes("openalex") && databases.includes("pubmed")) database = "both";
    else if (databases.includes("pubmed")) database = "pubmed";

    const body = {
        seed_prompt: seedPrompt,
        max_results: parseInt(document.getElementById("max-results").value) || 20,
        min_year: parseInt(document.getElementById("min-year").value) || null,
        max_year: parseInt(document.getElementById("max-year").value) || null,
        doc_types: docTypes,
        database: database,
        auto_accept: document.getElementById("auto-accept").checked,
    };

    try {
        const result = await fetchJSON("/api/run", {
            method: "POST",
            body: JSON.stringify(body),
        });

        if (result.error) {
            alert(result.error);
            return;
        }

        pipelineStartTime = Date.now();
        openPhaseDetails.clear();
        navigateTo("execution");
        startPolling();
        startTimer();
    } catch (err) {
        alert("Error iniciando pipeline: " + err.message);
    }
}

// ══════════════════════════════════════════════════════════════════
// Timer
// ══════════════════════════════════════════════════════════════════

function startTimer() {
    stopTimer();
    pipelineStartTime = pipelineStartTime || Date.now();
    timerInterval = setInterval(updateTimer, 1000);
    updateTimer();
}

function stopTimer() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
}

function updateTimer() {
    const el = document.getElementById("exec-timer");
    if (!el || !pipelineStartTime) return;
    const elapsed = Math.floor((Date.now() - pipelineStartTime) / 1000);
    el.textContent = formatDuration(elapsed);
}

function formatDuration(totalSeconds) {
    const s = Math.floor(totalSeconds);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const sec = s % 60;
    if (m < 60) return `${m}m ${sec.toString().padStart(2, '0')}s`;
    const h = Math.floor(m / 60);
    const min = m % 60;
    return `${h}h ${min.toString().padStart(2, '0')}m`;
}

// ══════════════════════════════════════════════════════════════════
// Execution Polling
// ══════════════════════════════════════════════════════════════════

function startPolling() {
    if (pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(pollStatus, 1500);
    pollStatus();
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

async function pollStatus() {
    try {
        const state = await fetchJSON("/api/status");
        renderExecution(state);

        // Update sidebar pulse indicator
        const pulse = document.getElementById("sidebar-pulse");
        if (pulse) {
            pulse.classList.toggle("active", state.running);
        }

        if (!state.running && !state.waiting_approval) {
            stopPolling();
            stopTimer();
            if (pulse) pulse.classList.remove("active");
        }
    } catch (err) {
        console.error("Poll error:", err);
    }
}

function checkExecutionState() {
    fetchJSON("/api/status").then(state => {
        if (state.running || state.phase === "Completado" || state.error) {
            renderExecution(state);
            if (state.running) {
                if (!pipelineStartTime) pipelineStartTime = Date.now();
                startPolling();
                startTimer();
            }
        }
    });
}

function renderExecution(state) {
    const idle = document.getElementById("exec-idle");
    const active = document.getElementById("exec-active");

    if (!state.running && !state.phase) {
        idle.style.display = "block";
        active.style.display = "none";
        return;
    }

    idle.style.display = "none";
    active.style.display = "block";

    // Phase stepper
    renderPhaseStepper(state);

    // Status message
    const statusEl = document.getElementById("exec-status");
    const msgEl = document.getElementById("exec-message");

    if (state.running || state.waiting_approval) {
        statusEl.style.display = "flex";
        msgEl.textContent = state.message;
    } else {
        statusEl.style.display = "none";
    }

    // Approval bar
    const approvalBar = document.getElementById("approval-bar");
    approvalBar.style.display = state.waiting_approval ? "flex" : "none";

    // Phases log
    const log = document.getElementById("phases-log");
    log.innerHTML = (state.completed_phases || []).map((p, idx) => `
        <div class="phase-log-item">
            <div class="phase-log-header" onclick="togglePhaseDetails(${idx})">
                <span class="phase-log-badge">${p.phase}</span>
                <span class="phase-log-text">${escapeHtml(p.summary)}</span>
                <span class="phase-log-chevron ${openPhaseDetails.has(idx) ? 'open' : ''}" id="chevron-${idx}">
                    <svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
                </span>
            </div>
            <div class="phase-log-details ${openPhaseDetails.has(idx) ? 'open' : ''}" id="phase-details-${idx}">
                ${renderPhaseDetails(p.phase, p.details)}
            </div>
        </div>
    `).join("");

    // Result card
    const resultCard = document.getElementById("result-card");
    const errorCard = document.getElementById("error-card");

    if (state.phase === "Completado" && state.result) {
        resultCard.style.display = "block";
        errorCard.style.display = "none";

        const finalTime = pipelineStartTime
            ? formatDuration((Date.now() - pipelineStartTime) / 1000)
            : "";
        document.getElementById("result-message").textContent =
            `Reporte generado en: ${state.result.output_dir}` + (finalTime ? ` — Duración: ${finalTime}` : "");

        resultCard.dataset.pdfPath = state.result.pdf_path || "";
    } else if (state.error) {
        resultCard.style.display = "none";
        errorCard.style.display = "block";
        document.getElementById("error-message").textContent = state.error;
    } else {
        resultCard.style.display = "none";
        errorCard.style.display = "none";
    }
}

// ══════════════════════════════════════════════════════════════════
// Phase Stepper
// ══════════════════════════════════════════════════════════════════

function renderPhaseStepper(state) {
    const stepper = document.getElementById("phase-stepper");
    const completedCount = (state.completed_phases || []).length;

    let html = '';
    PHASES.forEach((phase, i) => {
        let stepClass = 'step';
        let circleContent = `<span>${i + 1}</span>`;

        if (state.error && i === state.phase_index) {
            stepClass += ' error';
            circleContent = '<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
        } else if (i < completedCount) {
            stepClass += ' completed';
            circleContent = '<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>';
        } else if (i === state.phase_index && state.running) {
            stepClass += ' active';
        }

        html += `<div class="${stepClass}">
            <div class="step-circle">${circleContent}</div>
            <span class="step-label">${phase}</span>
        </div>`;

        // Connector between steps
        if (i < PHASES.length - 1) {
            const connectorClass = i < completedCount ? 'step-connector completed' : 'step-connector';
            html += `<div class="${connectorClass}"></div>`;
        }
    });

    stepper.innerHTML = html;
}

// ══════════════════════════════════════════════════════════════════
// Approve / Reject
// ══════════════════════════════════════════════════════════════════

async function approvePhase() {
    await fetchJSON("/api/approve", { method: "POST" });
}

async function rejectPhase() {
    if (!confirm("¿Rechazar esta fase? El pipeline se detendrá.")) return;
    await fetchJSON("/api/reject", { method: "POST" });
}

// ══════════════════════════════════════════════════════════════════
// Download
// ══════════════════════════════════════════════════════════════════

function downloadResult() {
    const pdfPath = document.getElementById("result-card").dataset.pdfPath;
    if (pdfPath) {
        window.open(`/api/download/${encodeURIComponent(pdfPath)}`, "_blank");
    }
}

// ══════════════════════════════════════════════════════════════════
// Phase Detail Rendering
// ══════════════════════════════════════════════════════════════════

function togglePhaseDetails(idx) {
    const el = document.getElementById(`phase-details-${idx}`);
    const chevron = document.getElementById(`chevron-${idx}`);

    if (el.classList.contains('open')) {
        el.classList.remove('open');
        chevron.classList.remove('open');
        openPhaseDetails.delete(idx);
    } else {
        el.classList.add('open');
        chevron.classList.add('open');
        openPhaseDetails.add(idx);
    }
}

function renderPhaseDetails(phase, details) {
    if (!details) return '<span class="detail-empty">Sin detalles adicionales</span>';

    switch (phase) {
        case "ARQ": return renderARQDetails(details);
        case "QSP": return renderQSPDetails(details);
        case "SE": return renderSEDetails(details);
        case "MAP": return renderMAPDetails(details);
        case "Synthesis": return renderSynthesisDetails(details);
        default: return '<span class="detail-empty">—</span>';
    }
}

function renderARQDetails(d) {
    let html = '';

    if (d.rqs && d.rqs.length) {
        html += '<div class="detail-section"><div class="detail-title">Research Questions</div>';
        html += d.rqs.map(rq =>
            `<div class="detail-rq"><span class="detail-rq-num">RQ${rq.index}</span>${escapeHtml(rq.text)}</div>`
        ).join("");
        html += '</div>';
    }

    if (d.keywords && d.keywords.length) {
        html += '<div class="detail-section"><div class="detail-title">Keywords</div>';
        html += '<div class="detail-tags">' + d.keywords.map(k =>
            `<span class="detail-tag">${escapeHtml(k)}</span>`
        ).join("") + '</div></div>';
    }

    if (d.inclusion_criteria && d.inclusion_criteria.length) {
        html += '<div class="detail-section"><div class="detail-title">Criterios de inclusión</div>';
        html += d.inclusion_criteria.map(c =>
            `<div class="detail-criterion inclusion">${escapeHtml(c)}</div>`
        ).join("") + '</div>';
    }

    if (d.exclusion_criteria && d.exclusion_criteria.length) {
        html += '<div class="detail-section"><div class="detail-title">Criterios de exclusión</div>';
        html += d.exclusion_criteria.map(c =>
            `<div class="detail-criterion exclusion">${escapeHtml(c)}</div>`
        ).join("") + '</div>';
    }

    return html;
}

function renderQSPDetails(d) {
    let html = '';

    if (d.query) {
        html += '<div class="detail-section"><div class="detail-title">Query booleana</div>';
        html += `<div class="detail-code">${escapeHtml(d.query)}</div></div>`;
    }

    if (d.reasoning) {
        html += '<div class="detail-section"><div class="detail-title">Razonamiento</div>';
        html += `<div class="detail-text">${escapeHtml(d.reasoning)}</div></div>`;
    }

    if (d.alternatives && d.alternatives.length) {
        html += '<div class="detail-section"><div class="detail-title">Queries alternativas</div>';
        html += d.alternatives.map((a, i) =>
            `<div class="detail-code alt">${i + 1}. ${escapeHtml(a)}</div>`
        ).join("") + '</div>';
    }

    return html;
}

function renderSEDetails(d) {
    let html = '<div class="detail-section"><div class="detail-title">Resumen de búsqueda</div>';

    html += '<div class="detail-stats">';
    html += `<div class="detail-stat"><span class="detail-stat-value">${d.total}</span><span class="detail-stat-label">Total papers</span></div>`;
    html += `<div class="detail-stat"><span class="detail-stat-value">${d.with_doi}</span><span class="detail-stat-label">Con DOI</span></div>`;
    html += `<div class="detail-stat"><span class="detail-stat-value">${d.with_abstract}</span><span class="detail-stat-label">Con abstract</span></div>`;
    if (d.year_min && d.year_max) {
        html += `<div class="detail-stat"><span class="detail-stat-value">${d.year_min}–${d.year_max}</span><span class="detail-stat-label">Rango años</span></div>`;
    }
    html += '</div>';

    if (d.by_database) {
        html += '<div class="detail-subsection"><span class="detail-subtitle">Por base de datos</span>';
        html += Object.entries(d.by_database).map(([db, count]) =>
            `<div class="detail-row"><span>${escapeHtml(db)}</span><span class="detail-row-value">${count}</span></div>`
        ).join("") + '</div>';
    }

    if (d.top_sources) {
        html += '<div class="detail-subsection"><span class="detail-subtitle">Top fuentes</span>';
        html += Object.entries(d.top_sources).map(([src, count]) =>
            `<div class="detail-row"><span>${escapeHtml(src)}</span><span class="detail-row-value">${count}</span></div>`
        ).join("") + '</div>';
    }

    html += '</div>';
    return html;
}

function renderMAPDetails(d) {
    let html = '<div class="detail-section"><div class="detail-title">Asignación por Research Question</div>';

    // Donut chart
    if (d.rq_breakdown && d.rq_breakdown.length) {
        html += renderDonutChart(d);
    }

    if (d.rq_breakdown) {
        html += d.rq_breakdown.map(rq =>
            `<div class="detail-rq-row">
                <div class="detail-rq-row-header">
                    <span class="detail-rq-num">${rq.key}</span>
                    <span class="detail-rq-count">${rq.count} paper${rq.count !== 1 ? 's' : ''}</span>
                </div>
                <div class="detail-rq-text">${escapeHtml(rq.text)}</div>
            </div>`
        ).join("");

        html += `<div class="detail-rq-row unmatched">
            <div class="detail-rq-row-header">
                <span class="detail-rq-num dim">No relevante</span>
                <span class="detail-rq-count">${d.unmatched_not_relevant || 0}</span>
            </div>
        </div>`;
        html += `<div class="detail-rq-row unmatched">
            <div class="detail-rq-row-header">
                <span class="detail-rq-num dim">Sin abstract</span>
                <span class="detail-rq-count">${d.unmatched_no_abstract || 0}</span>
            </div>
        </div>`;
    }

    html += '</div>';
    return html;
}

function renderDonutChart(d) {
    const items = d.rq_breakdown.filter(rq => rq.count > 0);
    const unmatched = (d.unmatched_not_relevant || 0) + (d.unmatched_no_abstract || 0);
    if (unmatched > 0) {
        items.push({ key: "Otros", count: unmatched });
    }

    const total = items.reduce((sum, item) => sum + item.count, 0);
    if (total === 0) return '';

    const r = 30;
    const cx = 40;
    const cy = 40;
    const circumference = 2 * Math.PI * r;
    let offset = 0;

    let segments = '';
    let legend = '';

    items.forEach((item, i) => {
        const pct = item.count / total;
        const dashLen = pct * circumference;
        const color = CHART_COLORS[i % CHART_COLORS.length];

        segments += `<circle class="donut-segment" cx="${cx}" cy="${cy}" r="${r}"
            stroke="${color}"
            stroke-dasharray="${dashLen} ${circumference - dashLen}"
            stroke-dashoffset="${-offset}"
        />`;

        offset += dashLen;

        legend += `<div class="donut-legend-item">
            <span class="donut-legend-dot" style="background:${color}"></span>
            <span>${escapeHtml(item.key)}: ${item.count}</span>
        </div>`;
    });

    return `<div class="donut-container">
        <div class="donut-chart">
            <svg viewBox="0 0 80 80">
                ${segments}
            </svg>
        </div>
        <div class="donut-legend">${legend}</div>
    </div>`;
}

function renderSynthesisDetails(d) {
    let html = '';

    if (d.gap_titles && d.gap_titles.length) {
        html += '<div class="detail-section"><div class="detail-title">Gaps de literatura detectados</div>';
        html += d.gap_titles.map((g, i) =>
            `<div class="detail-criterion exclusion">${i + 1}. ${escapeHtml(g)}</div>`
        ).join("") + '</div>';
    }

    return html || '<span class="detail-empty">Síntesis generada correctamente.</span>';
}

// ══════════════════════════════════════════════════════════════════
// Utilities
// ══════════════════════════════════════════════════════════════════

async function fetchJSON(url, options = {}) {
    const res = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    return res.json();
}

function formatTimestamp(ts) {
    if (!ts) return "—";
    const y = ts.slice(0, 4);
    const m = ts.slice(4, 6);
    const d = ts.slice(6, 8);
    const h = ts.slice(9, 11);
    const min = ts.slice(11, 13);
    return `${d}/${m}/${y} ${h}:${min}`;
}

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return (n / 1000).toFixed(1) + "K";
    return n.toString();
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ══════════════════════════════════════════════════════════════════
// Init
// ══════════════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    setupCostEstimation();
    loadDashboard();
});
