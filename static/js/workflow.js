// Dashboard of the PALET 2.0 review workflow. Every action calls /api/v2/*,
// which runs the same command as the terminal. Text from the server is always
// inserted with textContent, never as HTML.

const $ = (id) => document.getElementById(id);
let currentRun = null;
let jobTimer = null;
let jobWasRunning = false;

if (localStorage.getItem("palet-theme") === "dark") document.body.classList.add("dark");

async function api(path, options) {
    const response = await fetch(path, options);
    let data = null;
    try { data = await response.json(); } catch (e) { /* not JSON */ }
    if (!response.ok) throw new Error((data && data.error) || `Error ${response.status}`);
    return data;
}

function postJson(path, body) {
    return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

function show(element, text) {
    element.textContent = text;
    element.hidden = false;
}

function hide(...elements) {
    for (const element of elements) element.hidden = true;
}

function fill(select, items, selected) {
    select.replaceChildren();
    for (const item of items) {
        const option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.label;
        if (item.value === selected) option.selected = true;
        select.appendChild(option);
    }
}

// ── Runs ─────────────────────────────────────────────────────────────

async function loadRuns() {
    hide($("page-error"));
    try {
        const runs = await api("/api/v2/runs");
        if (!runs.length) {
            fill($("run-select"), [{ value: "", label: "— no hay ejecuciones —" }], "");
            show($("page-error"), "No hay ninguna ejecución en runs/. Crea una desde la terminal:\n" +
                "python -m palet init --protocol config/<protocolo>.yaml --label <nombre>");
            return;
        }
        const wanted = currentRun || localStorage.getItem("palet-run") || runs[0].run_id;
        const selected = runs.some((r) => r.run_id === wanted) ? wanted : runs[0].run_id;
        fill($("run-select"), runs.map((r) => ({ value: r.run_id, label: `${r.run_id} — ${r.label || ""}` })), selected);
        await loadRun(selected);
    } catch (e) {
        show($("page-error"), e.message);
    }
}

function stat(value, label) {
    const box = document.createElement("div");
    box.className = "wf-stat";
    const number = document.createElement("b");
    number.textContent = value === null || value === undefined ? "—" : value;
    const caption = document.createElement("span");
    caption.textContent = label;
    box.append(number, caption);
    return box;
}

async function loadRun(runId) {
    currentRun = runId;
    localStorage.setItem("palet-run", runId);
    hide($("page-error"));
    let run;
    try {
        run = await api(`/api/v2/runs/${encodeURIComponent(runId)}`);
    } catch (e) {
        $("run-area").hidden = true;
        show($("page-error"), e.message);
        return;
    }
    $("run-area").hidden = false;
    $("hint").textContent = run.hint;
    const protocol = run.protocol || {};
    $("run-meta").textContent = `Protocolo ${protocol.file || ""} v${protocol.version ?? "?"} (${protocol.status || "?"}) · ` +
        `gastado hasta ahora ≈ ${run.spent_usd} $`;

    const s = run.screening || {};
    $("stats").replaceChildren(
        stat(run.records, "registros únicos"),
        stat(run.duplicates_removed, "duplicados retirados"),
        stat(run.screening ? s.records : 0, "con decisión de cribado"),
        stat(run.screening ? s.include : null, "incluidos"),
        stat(run.screening ? s.exclude : null, "excluidos"),
        stat(run.screening ? s.pending : null, "pendientes de vosotros"),
        stat(run.assignments, "estudios asignados a RQ"),
    );

    let info = "Todavía no se ha cribado.";
    if (run.last_screen) {
        const models = run.last_screen.screeners.map((x) => `${x.name}: ${x.model}`).join(" · ");
        info = `Último cribado: ${models}` + (run.last_screen.limit ? ` (prueba con ${run.last_screen.limit} registros)` : "") + ".";
        const a = run.agreement;
        if (a && a.records_compared) {
            info += ` Acuerdo entre cribadores: ${a.same_decision}/${a.records_compared} (${a.percent_agreement} %), kappa = ${a.cohen_kappa}.`;
        }
    }
    $("screen-info").textContent = info;

    const table = $("searches");
    table.replaceChildren();
    const head = table.insertRow();
    for (const title of ["Fuente", "Resultados", "Descargados", "Fecha"]) {
        const th = document.createElement("th");
        th.textContent = title;
        head.appendChild(th);
    }
    for (const search of run.searches) {
        const row = table.insertRow();
        const cells = [search.query_id, search.total_hits, search.downloaded + (search.truncated ? " (truncada)" : ""),
            /^\d{4}-\d{2}-\d{2}T/.test(search.executed_at || "") ? search.executed_at.slice(0, 10) : search.executed_at];
        for (const value of cells) row.insertCell().textContent = value ?? "—";
    }

    const download = $("adjudication-download");
    download.href = `/api/download/runs/${encodeURIComponent(runId)}/adjudication.xlsx`;
    download.style.visibility = run.has_adjudication_file ? "visible" : "hidden";

    const files = $("report-files");
    files.replaceChildren();
    for (const name of run.report_files) {
        const link = document.createElement("a");
        link.href = `/api/download/runs/${encodeURIComponent(runId)}/report/${encodeURIComponent(name)}`;
        link.textContent = name;
        files.appendChild(link);
    }
}

// ── Screeners ────────────────────────────────────────────────────────

async function loadScreeners() {
    const data = await api("/api/v2/screeners");
    const models = data.models.map((m) => ({
        value: m.id,
        label: `${m.label} — ${m.input_per_mtok}/${m.output_per_mtok} $ por millón` + (m.status === "current" ? "" : ` (${m.status})`),
    }));
    fill($("screener-a"), models, data.default[0]);
    fill($("screener-b"), [{ value: "", label: "— sin segundo cribador —" }, ...models], data.default[1] || "");
    screenersChanged();
}

function chosenScreeners() {
    return [$("screener-a").value, $("screener-b").value].filter(Boolean);
}

function screenOptions() {
    const limit = parseInt($("screen-limit").value, 10);
    return { step: "screen", screeners: chosenScreeners(), limit: Number.isInteger(limit) && limit > 0 ? limit : null };
}

function screenersChanged() {
    const chosen = chosenScreeners();
    const warning = $("screener-warning");
    if (chosen.length === 1) {
        show(warning, "Un solo cribador: sus decisiones serán firmes sin contraste. Solo llegarán a vuestra revisión " +
            "los registros que marque como dudosos, los que den error y los que no tengan resumen. El informe lo declara.");
    } else if (chosen[0] === chosen[1]) {
        show(warning, "Los dos cribadores usan el mismo modelo: su acuerdo mide la consistencia del modelo, no un " +
            "contraste entre evaluadores distintos, y cuesta el doble que uno solo.");
    } else {
        hide(warning);
    }
    resetPaid("screen");      // a new choice needs a new estimate
}

// ── Steps that cost money: estimate, confirm, run ─────────────────────

function resetPaid(step) {
    hide($(`${step}-estimate`), $(`${step}-confirm-row`), $(`${step}-error`));
    $(`${step}-confirm`).checked = false;
    $(`${step}-run-btn`).disabled = true;
}

function paidOptions(step) {
    return step === "screen" ? screenOptions() : { step: "assign" };
}

async function estimate(step) {
    resetPaid(step);
    show($(`${step}-estimate`), "Calculando…");
    try {
        const data = await postJson(`/api/v2/runs/${encodeURIComponent(currentRun)}/estimate`, paidOptions(step));
        show($(`${step}-estimate`), data.output);
        $(`${step}-confirm-row`).hidden = false;
    } catch (e) {
        hide($(`${step}-estimate`));
        show($(`${step}-error`), e.message);
    }
}

async function runStep(body, errorElement) {
    hide(errorElement);
    try {
        await postJson(`/api/v2/runs/${encodeURIComponent(currentRun)}/run`, body);
        pollJob();
    } catch (e) {
        show(errorElement, e.message);
    }
}

for (const step of ["screen", "assign"]) {
    $(`${step}-estimate-btn`).addEventListener("click", () => estimate(step));
    $(`${step}-confirm`).addEventListener("change", (event) => { $(`${step}-run-btn`).disabled = !event.target.checked; });
    $(`${step}-run-btn`).addEventListener("click", async () => {
        await runStep({ ...paidOptions(step), confirm_cost: $(`${step}-confirm`).checked }, $(`${step}-error`));
        resetPaid(step);
    });
    $(`${step}-replay-btn`).addEventListener("click", () => runStep({ ...paidOptions(step), replay: true }, $(`${step}-error`)));
}

for (const id of ["screener-a", "screener-b"]) $(id).addEventListener("change", screenersChanged);
$("screen-limit").addEventListener("input", () => resetPaid("screen"));

// ── Free steps ───────────────────────────────────────────────────────

document.querySelector('[data-run-step="dedup"]').addEventListener("click", () => runStep({ step: "dedup" }, $("page-error")));

$("report-btn").addEventListener("click", () => {
    const year = parseInt($("partial-year").value, 10);
    runStep({ step: "report", partial_year: Number.isInteger(year) ? year : null }, $("report-error"));
});

$("adjudication-btn").addEventListener("click", async () => {
    const error = $("adjudication-error");
    hide(error);
    const file = $("adjudication-file").files[0];
    const initials = $("adjudication-initials").value.trim();
    if (!file) return show(error, "Elige el Excel rellenado.");
    if (!/^[A-Za-z]{2,6}$/.test(initials)) return show(error, "Indica tus iniciales (de 2 a 6 letras).");
    try {
        await api(`/api/v2/runs/${encodeURIComponent(currentRun)}/adjudicate?initials=${encodeURIComponent(initials)}`,
            { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
        pollJob();
    } catch (e) {
        show(error, e.message);
    }
});

// ── Job output ───────────────────────────────────────────────────────

const STEP_NAMES = { dedup: "Deduplicación", screen: "Cribado", adjudicate: "Decisión de los pendientes",
    assign: "Asignación", report: "Informe" };

async function pollJob() {
    clearTimeout(jobTimer);
    let job;
    try {
        job = await api("/api/v2/job");
    } catch (e) {
        jobTimer = setTimeout(pollJob, 3000);
        return;
    }
    if (job.step) {
        $("job-card").hidden = false;
        const name = STEP_NAMES[job.step] || job.step;
        let state = "en ejecución…";
        if (!job.running) state = job.returncode === 0 ? "terminado" : "terminó con error";
        $("job-title").textContent = `${name} (${job.run_id}): ${state}`;
        const log = $("job-log");
        log.textContent = job.log.join("\n");
        log.scrollTop = log.scrollHeight;
    }
    if (job.running) {
        jobWasRunning = true;
        jobTimer = setTimeout(pollJob, 1500);
    } else if (jobWasRunning) {
        jobWasRunning = false;
        if (currentRun) loadRun(currentRun);
    }
}

$("run-select").addEventListener("change", (event) => {
    resetPaid("screen");
    resetPaid("assign");
    if (event.target.value) loadRun(event.target.value);
});
$("refresh-btn").addEventListener("click", loadRuns);

loadScreeners().catch((e) => show($("page-error"), e.message));
loadRuns();
pollJob();
