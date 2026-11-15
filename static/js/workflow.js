// PALET 2.0 dashboard. Every action calls /api/v2/*, which runs the same command as the terminal.
// Text that comes from the server is always inserted with textContent, never as HTML.

const $ = (id) => document.getElementById(id);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let currentRun = null;      // run id
let overview = null;        // last /api/v2/runs/<id> answer
let selectedStage = null;   // stage shown in the panel
let jobTimer = null;
let lastJobKey = null;      // step + started_at of the job whose end we have already announced
let jobWasRunning = false;

// ── The robot ────────────────────────────────────────────────────────
// PALET is drawn on a 46x30 pixel scene from text sprites (letters are colours): chunky, dark-outlined,
// lit from the top-left. Original design; no image files. What it does depends on what the tool is doing:
//   sleep  nothing is happening (Zzz; click to wake)      think  short jobs: sits on a chair
//   read   screening: one book every 10 s, piled up        write  assistant, charting, report: notepad
//   cheer  a step ended well (cheeks, arms up)             awake / ask / error  talking to the user

const SCENE_W = 46, SCENE_H = 30, FLOOR_Y = 27, RX = 14, RY = 2;
const PAL = {
    K: "#1a2026", T: "#eef2f5", b: "#cfd6dd", s: "#8f9aa6", h: "#aab4be", f: "#6b7682", v: "#1d2a33", E: "#7ee0a1",
    w: "#ffffff", M: "#7ee0a1", a: "#7ee0a1", c: "#7ee0a1", k: "#f59fb0", C: "#b07a45", D: "#7d5430", n: "#f4f1e4",
    l: "#9aa8a0", p: "#f2c14e", t: "#3a2a1a", e: "#f59fb0", B: "#c8553d", z: "#9fd8ff", o: "#d5dfd8",
};
const BOOK_COLOURS = ["#c8553d", "#3d7fc8", "#d9a441", "#5fae6b", "#8a5fc8", "#c85f9e"];
const LIGHT = { sleep: "#2f5a41", awake: "#7ee0a1", cheer: "#7ee0a1", ask: "#f2c14e", error: "#ff7b72", think: "#f2c14e", read: "#f2c14e", write: "#f2c14e" };

const HEAD_TOP = [
    ".......KaaK.......",
    ".......KaaK.......",
    "........KK........",
    "..KKKKKKKKKKKKKK..",
    ".KTTTTTTTTTTTTTsK.",
    ".KbbbbbbbbbbbbbsK.",
    ".KbvvvvvvvvvvvbsK.",
];
const HEAD_BOTTOM = [
    ".KbvvvvvvvvvvvbsK.",
    ".KbbbbbbbbbbbbbsK.",
    "..KKKKKKKKKKKKKK..",
];
const FACES = {
    awake: ["vEEvvvEEv", "vEwvvvEwv", "vvvMMMvvv"],
    blink: ["vvvvvvvvv", "vEEvvvEEv", "vvvMMMvvv"],
    sleep: ["vvvvvvvvv", "vEEvvvEEv", "vvvvMvvvv"],
    cheer: ["vEEvvvEEv", "kkvvvvvkk", "vvMMMMMvv"],
    ask: ["vEEvvvEEv", "vEwvvvEwv", "vvvvMvvvv"],
    error: ["vEEvvvEEv", "vvvvvvvvv", "vvMMMMMvv"],
    think: ["vvEwvvvEw", "vvEEvvvEE", "vvvMMvvvv"],
    read: ["vvvvvvvvv", "vEEvvvEEv", "vEwvvvEwv"],
    write: ["vvvvvvvvv", "vEEvvvEEv", "vEwvMvEwv"],
};
const BODY_ARMS = [
    "......KKKKKK......",
    "...KKKKKKKKKKKK...",
    ".KhhKbbccccbbsKhhK",
    ".KhhKbbbbbbbbsKhhK",
    ".KhhKbbbbbbbbsKhhK",
    ".KKKKbbbbbbbbsKKKK",
    "....KbbbbbbbbsK...",
    "....KKKKKKKKKKK...",
];
const BODY_NO_ARMS = [
    "......KKKKKK......",
    "...KKKKKKKKKKKK...",
    "....KbbccccbbsK...",
    "....KbbbbbbbbsK...",
    "....KbbbbbbbbsK...",
    "....KbbbbbbbbsK...",
    "....KbbbbbbbbsK...",
    "....KKKKKKKKKKK...",
];
const LEGS_STAND = [".....KffK.KffK....", ".....KffK.KffK....", "....KfffK.KfffK...", "....KKKKK.KKKKK..."];
const LEGS_SIT = [".....KffK.KffK....", "....KfffK.KfffK...", "....KKKKK.KKKKK..."];
const CHAIR = [
    "KKKKKKKKKKKKKKKKKKKK",
    "KCCCCCCCCCCCCCCCCCCK",
    "KCDDDDDDDDDDDDDDDDCK",
    "KCK..............KCK", "KCK..............KCK", "KCK..............KCK",
    "KCK..............KCK", "KCK..............KCK", "KCK..............KCK",
    "KCKKKKKKKKKKKKKKKKCK",
    "KCCCCCCCCCCCCCCCCCCK",
    "KKKKKKKKKKKKKKKKKKKK",
    "KCK..............KCK",
    "KKK..............KKK",
];
const PAD = [
    ["hKKKKKKKKKK...", "hKnnnnnnnnK...", "hKnllnlltpppeh", "hKnlllnnnnK...", ".KnnnnnnnnK...", ".KKKKKKKKKK..."],
    ["hKKKKKKKKKK...", "hKnnnnnnnnK...", "hKnllnllnnK...", "hKnlllnltpppeh", ".KnnnnnnnnK...", ".KKKKKKKKKK..."],
];
const BOOK = [
    ["hKKKKKKKKKKKKh", "hKnnnnnKnnnnKh", "hKnllnnKnllnKh", "hKnnnnnKnnnnKh", ".KBBBBBKBBBBK."],
    ["hKKKKKKKKKKKKh", "hKnnnnnKnnnnKh", "hKnnllnKnnllKh", "hKnllnnKnllnKh", ".KBBBBBKBBBBK."],
];
const ARM_UP_LEFT = ["KKK.", "KhK.", "KhK.", "KhhK", ".KhK", ".KKK"];
const ARM_UP_RIGHT = [".KKK", ".KhK", ".KhK", "KhhK", "KhK.", "KKK."];
const PILE_BOOK = ["KBBBBBnnK", "KKKKKKKKK"];
const Z_SMALL = ["zzz", ".z.", "zzz"];
const Z_BIG = ["zzzz", "..z.", ".z..", "zzzz"];
const DOT = ["oo", "oo"];

const robot = { mood: "awake", frame: 0, books: 0, readSince: null, lastActivity: Date.now(), busy: false };
let mood = "awake";       // kept in step with robot.mood (older code reads it)

function blit(grid, sprite, x, y, swap) {
    sprite.forEach((row, dy) => {
        [...row].forEach((cell, dx) => {
            if (cell === "." || y + dy < 0 || y + dy >= SCENE_H || x + dx < 0 || x + dx >= SCENE_W) return;
            grid[y + dy][x + dx] = (swap && swap[cell]) || PAL[cell];
        });
    });
}

function drawScene() {
    const m = robot.mood;
    const odd = robot.frame % 2;
    const grid = Array.from({ length: SCENE_H }, () => new Array(SCENE_W).fill(null));
    for (let x = 0; x < SCENE_W; x += 1) {           // the floor it stands on
        grid[FLOOR_Y][x] = "#2a3832";
        grid[FLOOR_Y + 1][x] = "#18211d";
        grid[FLOOR_Y + 2][x] = "#18211d";
    }
    const working = m === "think" || m === "read" || m === "write";
    const light = working && odd ? "#23302a" : LIGHT[m];
    const swap = { a: light, c: light };
    if (m === "error") { swap.E = "#ff7b72"; swap.M = "#ff7b72"; }

    // the pile of books already read: right of the robot first, then left
    for (let i = 0; i < Math.min(robot.books, 20); i += 1) {
        const x = i < 10 ? 34 : 2;
        blit(grid, PILE_BOOK, x + (i % 2), FLOOR_Y - 2 * ((i % 10) + 1), { B: BOOK_COLOURS[i % BOOK_COLOURS.length] });
    }

    const sit = m === "think";
    const y = RY + (sit ? 1 : 0);
    if (sit) blit(grid, CHAIR, RX - 1, 13);
    let face = m;
    if (m === "awake" && robot.blink) face = "blink";
    const head = [...HEAD_TOP, ...FACES[face].map((inner) => ".Kbv" + inner + "vbsK."), ...HEAD_BOTTOM];
    const holding = m === "read" || m === "write" || m === "cheer";
    blit(grid, holding ? BODY_NO_ARMS : BODY_ARMS, RX, y + 13, swap);
    blit(grid, sit ? LEGS_SIT : LEGS_STAND, RX, y + 21);
    blit(grid, head, RX, y, swap);
    if (m === "write") blit(grid, PAD[odd], RX + 2, y + 15);
    if (m === "read") blit(grid, BOOK[Math.floor(robot.frame / 3) % 2], RX + 2, y + 15, { B: BOOK_COLOURS[robot.books % BOOK_COLOURS.length] });
    if (m === "cheer") {
        blit(grid, ARM_UP_LEFT, RX, y + 10);
        blit(grid, ARM_UP_RIGHT, RX + 14, y + 10);
    }
    if (m === "sleep") {
        const step = robot.frame % 6;
        if (step >= 1) blit(grid, Z_SMALL, 33, 11);
        if (step >= 3) blit(grid, Z_BIG, 37, 5);
        if (step >= 5) blit(grid, Z_SMALL, 42, 1);
    }
    if (m === "think") {
        const step = robot.frame % 4;
        if (step >= 1) blit(grid, DOT, 33, 8);
        if (step >= 2) blit(grid, DOT, 36, 5);
        if (step >= 3) blit(grid, DOT, 39, 2);
    }

    const parts = [];
    grid.forEach((row, yy) => {
        let x = 0;
        while (x < SCENE_W) {                          // one rect per run of equal pixels
            const colour = row[x];
            let end = x + 1;
            while (end < SCENE_W && row[end] === colour) end += 1;
            if (colour) parts.push(`<rect x="${x}" y="${yy}" width="${end - x}" height="1" fill="${colour}"/>`);
            x = end;
        }
    });
    if (robot.books > 20) parts.push(`<text x="45" y="3.2" text-anchor="end" font-size="3" fill="#7b8a82" font-family="monospace">${robot.books} libros</text>`);
    const svg = $("robot");
    const sparks = svg.querySelector("#sparks");
    svg.innerHTML = parts.join("");                    // built only from the constants above and a number
    if (sparks) svg.appendChild(sparks);
    svg.dataset.mood = m;
}

const MOOD_ALIAS = { idle: "awake", happy: "cheer", working: "think", writing: "write" };

function setMood(next) {
    next = MOOD_ALIAS[next] || next;
    if (next === "read" && robot.mood !== "read") {
        robot.books = 0;
        if (!robot.readSince) robot.readSince = Date.now();
    }
    if (next !== "read") robot.readSince = null;
    if ((next === "think" || next === "write") && robot.mood !== next && !robot.keepPile) robot.books = 0;
    robot.mood = next;
    mood = next;
    robot.lastActivity = Date.now();
    drawScene();
}

setInterval(() => {
    robot.frame += 1;
    const m = robot.mood;
    if (m === "read" && robot.readSince) {              // one book every 10 seconds; the finished ones pile up
        robot.books = Math.floor((Date.now() - robot.readSince) / 10000);
    }
    const quiet = Date.now() - robot.lastActivity;
    if (!robot.busy) {
        if (m === "cheer" && quiet > 5000) { robot.mood = mood = "awake"; robot.lastActivity = Date.now(); }
        else if ((m === "awake" || m === "ask" || m === "error") && quiet > 30000) robot.mood = mood = "sleep";
    }
    robot.blink = robot.mood === "awake" && !reducedMotion && robot.frame % 8 === 0;
    drawScene();
}, 450);

const WAKE_LINES = ["¿Eh? Estaba repasando la bibliografía. Con los ojos cerrados.", "Despierto. ¿Qué cribamos?",
    "Un momento… ya. Dime.", "No dormía: procesaba en segundo plano."];
const POKE_LINES = ["Estoy despierto, estoy despierto.", "Si me pinchas no cribo más rápido.", "Dime qué paso quieres ver y te lo cuento."];

function pokeRobot() {
    if (robot.busy) return;
    const lines = robot.mood === "sleep" ? WAKE_LINES : POKE_LINES;
    say(lines[Math.floor(Math.random() * lines.length)], "awake");
}

function fireworks() {
    if (reducedMotion) return;
    const svg = $("robot");
    const ns = "http://www.w3.org/2000/svg";
    let layer = svg.querySelector("#sparks");
    if (!layer) {
        layer = document.createElementNS(ns, "g");
        layer.id = "sparks";
        svg.appendChild(layer);
    }
    const bursts = [[8, 7, 0, "#f2c14e"], [38, 6, 450, "#7ee0a1"], [23, 2, 900, "#ff7b72"]];
    for (const [cx, cy, delay, colour] of bursts) {
        setTimeout(() => {
            const sparks = Array.from({ length: 18 }, (_, i) => {
                const rect = document.createElementNS(ns, "rect");
                rect.setAttribute("width", "1");
                rect.setAttribute("height", "1");
                rect.setAttribute("fill", i % 3 ? colour : "#ffffff");
                layer.appendChild(rect);
                const angle = (Math.PI * 2 * i) / 18;
                return { rect, dx: Math.cos(angle), dy: Math.sin(angle), speed: 5 + (i % 3) * 2 };
            });
            const start = performance.now();
            const animate = (now) => {
                const t = (now - start) / 1100;
                for (const spark of sparks) {
                    spark.rect.setAttribute("x", String(Math.round(cx + spark.dx * spark.speed * t)));
                    spark.rect.setAttribute("y", String(Math.round(cy + spark.dy * spark.speed * t + 3 * t * t)));
                    spark.rect.setAttribute("opacity", String(Math.max(0, 1 - t)));
                }
                if (t < 1) requestAnimationFrame(animate); else sparks.forEach((spark) => spark.rect.remove());
            };
            requestAnimationFrame(animate);
        }, delay);
    }
}

let typing = null;
function say(text, nextMood) {
    if (nextMood) setMood(nextMood);
    robot.lastActivity = Date.now();
    const target = $("say");
    clearInterval(typing);
    if (reducedMotion) { target.textContent = text; return; }
    let shown = 0;
    target.textContent = "";
    typing = setInterval(() => {
        shown += 2;
        target.textContent = text.slice(0, shown);
        if (shown >= text.length) clearInterval(typing);
    }, 16);
}

// What PALET says. It is a meticulous librarian: brief, a little dry, never decides for the authors.
const STAGES = {
    protocol: { title: "protocolo", help: "Preguntas de investigación, criterios, listas de revistas y reglas de decisión. Lo fijan los autores antes de empezar; mientras esté en borrador no se criba nada.",
        intro: "El protocolo es vuestro. Yo puedo redactar el borrador, pero lo aprobáis vosotros; después lo aplico al pie de la letra." },
    search: { title: "búsqueda", help: "Fuentes del protocolo: exportaciones importadas a mano y cadenas de búsqueda en OpenAlex. Recontar y descargar no cuesta dinero.",
        intro: "Cada cadena está en el protocolo. Cuenta primero: si salen miles, la cadena es demasiado amplia. Descargo solo las aprobadas." },
    dedup: { title: "duplicados", help: "Une los registros repetidos entre fuentes (por DOI, o por título, autor y año). Los pares dudosos se listan y no se unen. Hay que repetirlo al añadir una fuente.",
        intro: "El mismo artículo suele llegar por tres puertas distintas. Los junto; los dudosos os los dejo anotados." },
    journals: { title: "revistas", help: "Comprueba por ISSN qué registros están en las listas de revistas del protocolo. Los que no están se excluyen en el cribado sin llamar a ningún modelo.",
        intro: "Miro el ISSN de cada revista contra vuestras listas. Es gratis y ahorra muchas llamadas." },
    screen: { title: "cribado", help: "Cada cribador juzga cada registro criterio a criterio y cita el pasaje en que se apoya; el código comprueba la cita y aplica la regla de decisión del protocolo.",
        intro: "Aquí es donde se gasta. Pídeme la estimación primero: no lanzo nada de pago sin tu visto bueno." },
    adjudicate: { title: "decisión humana", help: "Los registros que la regla deja en vuestras manos. Descarga el Excel, decide cada fila y súbelo. Si falta algo, se rechaza entero y no cambia nada.",
        intro: "Estos no los decido yo. Os dejo lo que dijo cada cribador y la cita; la última palabra es vuestra." },
    assign: { title: "asignación", help: "Clasifica cada estudio incluido frente a cada pregunta (principal, parcial o ninguna) con una cita literal, y resume su contribución en una frase.",
        intro: "Leo cada resumen y digo a qué pregunta responde, siempre con la cita delante. Tiene coste: estimación primero." },
    report: { title: "informe", help: "Diagrama PRISMA, lista PRISMA-ScR, apéndice de métodos, excluidos con motivo, evidencia por pregunta, tablas y figuras. Todo sale de los ficheros de la ejecución.",
        intro: "Junto los números y los dejo listos para el capítulo. Ninguna cifra es mía: todas salen de los ficheros." },
};
const START_LINES = {
    search: "Voy a OpenAlex. Vuelvo enseguida.", dedup: "Buscando gemelos…", reparse: "Releyendo los datos en bruto. No descargo nada.",
    journals: "Cotejando ISSN, uno por uno.", screen: "A leer resúmenes. Va para rato: un libro tras otro, y lo guardo todo según llega.",
    adjudicate: "Recibido. Reviso que no falte ninguna fila.", assign: "Leyendo resúmenes y anotando citas.", report: "Montando el informe.",
};
const STEP_MOOD = { search: "think", dedup: "think", reparse: "think", journals: "think", adjudicate: "think",
    screen: "read", assign: "write", report: "write" };
const DONE_LINES = {
    search: "Hecho. Mira la salida: ahí está el recuento.", dedup: "Listo. Sin duplicados a la vista.", reparse: "Fuentes releídas.",
    journals: "Revistas comprobadas. El detalle está en journal_check.csv.", screen: "Cribado terminado. Lo que no decidí yo os espera en el Excel.",
    adjudicate: "Decisiones cargadas. Gracias: esas eran vuestras.", assign: "Asignación terminada. Cada estudio tiene su pregunta y su cita.",
    report: "Informe generado. Todo lo de abajo se puede descargar.",
};

// ── Helpers ──────────────────────────────────────────────────────────

async function api(path, options) {
    const response = await fetch(path, options);
    let data = null;
    try { data = await response.json(); } catch (e) { /* not JSON */ }
    if (!response.ok) throw new Error((data && data.error) || `Error ${response.status}`);
    return data;
}
const postJson = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const runUrl = (tail = "") => `/api/v2/runs/${encodeURIComponent(currentRun)}${tail}`;
const fileUrl = (name) => `/api/download/runs/${encodeURIComponent(currentRun)}/${name.split("/").map(encodeURIComponent).join("/")}`;

function show(element, text) { element.textContent = text; element.hidden = false; }
function hide(...elements) { for (const element of elements) element.hidden = true; }
function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
}
function fill(select, items, selected) {
    select.replaceChildren();
    for (const item of items) {
        const option = el("option", null, item.label);
        option.value = item.value;
        if (item.value === selected) option.selected = true;
        select.appendChild(option);
    }
}

// ── Runs ─────────────────────────────────────────────────────────────

async function loadRuns(preferred) {
    hide($("page-error"));
    let runs;
    try {
        runs = await api("/api/v2/runs");
    } catch (e) {
        show($("page-error"), e.message);
        return;
    }
    if (!runs.length) {
        fill($("run-select"), [{ value: "", label: "— ninguna —" }], "");
        $("work").hidden = true;
        $("flow").replaceChildren();
        say("No hay ninguna revisión todavía. Pulsa «+ nueva revisión» y empezamos por el protocolo.", "ask");
        return;
    }
    const wanted = preferred || currentRun || localStorage.getItem("palet-run") || runs[0].run_id;
    const selected = runs.some((r) => r.run_id === wanted) ? wanted : runs[0].run_id;
    fill($("run-select"), runs.map((r) => ({ value: r.run_id, label: r.run_id })), selected);
    await loadRun(selected, true);
}

function renderStats(run) {
    const s = run.screening || {};
    const items = [
        [run.records, "registros únicos"], [run.screening ? s.include : null, "incluidos"],
        [run.screening ? s.pending : null, "pendientes"], [run.screening ? s.exclude : null, "excluidos"],
        [run.selection ? run.selection.selected : run.assignments, run.selection ? "en la síntesis" : "asignados"],
        [`${run.spent_usd} $`, "gastado"],
    ];
    $("stats").replaceChildren(...items.map(([value, label]) => {
        const box = el("div", "stat");
        box.append(el("b", null, value === null || value === undefined ? "—" : value), el("span", null, label));
        return box;
    }));
}

function renderFlow(run, job) {
    const running = job && job.running && job.run_id === run.run_id ? stageOfStep(job.step) : null;
    const questions = Object.keys((run.protocol || {}).research_questions || {}).length;
    const first = el("button", "node done");
    first.type = "button";
    const firstHead = el("span", "n");
    firstHead.append(el("span", null, "00"), el("span", "mark", "✓"));
    first.append(firstHead, el("span", "name", "Preguntas"), el("span", "detail", `${questions} preguntas fijadas`));
    first.addEventListener("click", () => selectStage("protocol", true));
    const nodes = run.stages.map((stage, index) => {
        const node = el("button", `node ${stage.status}`);
        node.type = "button";
        node.dataset.stage = stage.id;
        if (stage.id === selectedStage) node.classList.add("selected");
        if (stage.id === running) node.classList.add("running");
        const mark = stage.id === running ? "…" : { done: "✓", current: "▸", skipped: "–", todo: "" }[stage.status];
        const head = el("span", "n");
        head.append(el("span", null, String(index + 1).padStart(2, "0")), el("span", "mark", mark));
        node.append(head, el("span", "name", stage.label), el("span", "detail", stage.detail));
        node.addEventListener("click", () => selectStage(stage.id, true));
        return node;
    });
    // the connector that leads into the running step carries a moving packet
    const runningIndex = run.stages.findIndex((stage) => stage.id === running);
    if (runningIndex > 0) nodes[runningIndex - 1].classList.add("feeding");
    if (runningIndex === 0) first.classList.add("feeding");
    $("flow").replaceChildren(first, ...nodes);
}

function stageOfStep(step) {
    return { reparse: "dedup" }[step] || step;
}

async function loadRun(runId, announce) {
    currentRun = runId;
    $("wizard").hidden = true;
    localStorage.setItem("palet-run", runId);
    $("bar-run").textContent = runId;
    hide($("page-error"));
    try {
        overview = await api(runUrl());
    } catch (e) {
        $("work").hidden = true;
        show($("page-error"), e.message);
        return;
    }
    $("work").hidden = false;
    renderStats(overview);
    const current = overview.stages.find((stage) => stage.status === "current");
    if (!selectedStage || announce) selectedStage = current ? current.id : "report";
    renderFlow(overview, await api("/api/v2/job").catch(() => null));
    renderStage();
    if (announce) say(current ? `${overview.hint} ${STAGES[current.id].intro}` : overview.hint, "idle");
}

// ── The stage panel ──────────────────────────────────────────────────

function selectStage(stageId, talk) {
    selectedStage = stageId;
    document.querySelectorAll(".node").forEach((node) => node.classList.toggle("selected", node.dataset.stage === stageId));
    renderStage();
    if (talk) say(STAGES[stageId].intro, robot.busy ? null : "awake");
}

function renderStage() {
    const run = overview;
    const info = STAGES[selectedStage];
    $("stage-title").textContent = `palet ${info.title}`;
    $("stage-help").textContent = info.help;
    hide($("stage-error"));
    document.querySelectorAll(".stage").forEach((node) => node.classList.toggle("on", node.dataset.stage === selectedStage));

    // protocol
    const p = run.protocol || {};
    const rules = { adjudicate_all: "toda duda o desacuerdo va a los autores", agreement_or_exclude: "se incluye solo con acuerdo; «uno incluye, otro duda» lo deciden los autores; el resto se excluye" };
    const pairs = [["título", p.title || "—"], ["fichero", p.file || "—"], ["versión", `v${p.version ?? "?"} · ${p.status || "?"}`],
        ["aprobado por", Array.isArray(p.approved_by) ? p.approved_by.join("; ") : (p.approved_by || "—")],
        ["regla de decisión", rules[p.decision_rule] || p.decision_rule || "—"],
        ["listas de revistas", (p.journal_lists || []).join(", ") || "sin filtro de revistas"],
        ["síntesis", p.synthesis_selection === "core_only" ? "solo estudios principales para alguna pregunta" : "todos los incluidos"]];
    $("protocol-kv").replaceChildren(...pairs.flatMap(([k, v]) => [el("dt", null, k), el("dd", null, v)]));
    $("protocol-rqs").replaceChildren(...Object.values(p.research_questions || {}).map((text) => el("li", null, text)));
    const criteria = $("protocol-criteria");
    criteria.replaceChildren();
    for (const criterion of p.criteria || []) {
        const row = criteria.insertRow();
        row.insertCell().textContent = criterion.id;
        const rule = row.insertCell();
        rule.textContent = criterion.rule;
        rule.style.whiteSpace = "normal";
        rule.style.textAlign = "left";
    }
    $("protocol-approve").hidden = p.status === "approved";

    // search
    const table = $("sources");
    table.replaceChildren();
    const head = table.insertRow();
    for (const title of ["fuente", "preguntas", "estado", "registros", ""]) head.appendChild(el("th", null, title));
    for (const source of run.sources) {
        const row = table.insertRow();
        row.insertCell().textContent = source.id.replace(/^openalex_supplementary_/, "openalex · ");
        row.cells[0].title = source.id;
        row.insertCell().textContent = (source.rqs || []).join(", ") || "—";
        const manual = source.type === "manual_import";
        const state = manual ? "importada" : (source.status || "sin estado");
        row.insertCell().appendChild(el("span", `tag ${manual || source.status === "approved" ? "ok" : "wait"}`, state));
        row.insertCell().textContent = source.downloaded ?? "—";
        const actions = row.insertCell();
        if (!manual) {
            const count = el("button", "btn small", "recuento");
            count.type = "button";
            count.addEventListener("click", () => runStep({ step: "search", source: source.id, count_only: true }));
            actions.appendChild(count);
            if (source.status !== "approved") {
                const approve = el("button", "btn small", "aprobar");
                approve.type = "button";
                approve.style.marginLeft = "6px";
                approve.addEventListener("click", () => approveSearch(source.id, approve));
                actions.appendChild(approve);
            }
            if (source.status === "approved") {
                const fetchButton = el("button", "btn small", source.downloaded === null ? "descargar" : "redescargar");
                fetchButton.type = "button";
                fetchButton.style.marginLeft = "6px";
                fetchButton.addEventListener("click", () => runStep({ step: "search", source: source.id }));
                actions.appendChild(fetchButton);
            }
        }
    }

    // journals
    $("journals-download").href = fileUrl("journal_check.csv");
    $("journals-note").textContent = (p.journal_lists || []).length ? `Listas del protocolo: ${p.journal_lists.join(", ")}.` : "Este protocolo no filtra por revista: el paso se omite.";
    document.querySelector('[data-step="journals"]').disabled = !(p.journal_lists || []).length;

    // adjudicate
    const download = $("adjudication-download");
    download.href = fileUrl("adjudication.xlsx");
    download.style.visibility = run.has_adjudication_file ? "visible" : "hidden";

    // report
    $("report-files").replaceChildren(...run.report_files.map((name) => {
        const link = el("a", null, name);
        link.href = fileUrl(`report/${name}`);
        return link;
    }));
}

// ── Screeners ────────────────────────────────────────────────────────

async function loadScreeners() {
    const data = await api("/api/v2/screeners");
    const models = data.models.map((m) => ({ value: m.id, label: `${m.label} · ${m.input_per_mtok}/${m.output_per_mtok} $/M` + (m.status === "current" ? "" : ` (${m.status})`) }));
    fill($("screener-a"), models, data.default[0]);
    fill($("screener-b"), [{ value: "", label: "— sin segundo cribador —" }, ...models], data.default[1] || "");
    fill($("wz-model"), models, data.assistant_default);
    fill($("assign-model"), models, data.assignment_default);
    screenersChanged(false);
}

const chosenScreeners = () => [$("screener-a").value, $("screener-b").value].filter(Boolean);

function screenersChanged(talk = true) {
    const chosen = chosenScreeners();
    const warning = $("screener-warning");
    if (chosen.length === 1) {
        show(warning, "Un solo cribador: sus decisiones serán firmes sin contraste. Solo llegarán a los autores los registros dudosos, con error o sin resumen. El informe lo declara.");
        if (talk) say("¿Yo solo, sin nadie que me lleve la contraria? Puedo, pero lo dejaré escrito en el informe.", "ask");
    } else if (chosen[0] === chosen[1]) {
        show(warning, "Los dos cribadores usan el mismo modelo: su acuerdo mide la consistencia del modelo, no un contraste entre evaluadores distintos.");
        if (talk) say("Dos veces el mismo modelo es preguntarme lo mismo dos veces. Mejor dos modelos distintos.", "ask");
    } else {
        hide(warning);
    }
    resetPaid("screen");
}

// ── Steps ────────────────────────────────────────────────────────────

function resetPaid(step) {
    hide($(`${step}-estimate`), $(`${step}-confirm-row`), $(`${step}-error`));
    $(`${step}-confirm`).checked = false;
    $(`${step}-run-btn`).disabled = true;
}

function paidOptions(step) {
    if (step !== "screen") return { step, model: $("assign-model").value };
    const limit = parseInt($("screen-limit").value, 10);
    return { step, screeners: chosenScreeners(), limit: Number.isInteger(limit) && limit > 0 ? limit : null };
}

async function estimate(step) {
    resetPaid(step);
    show($(`${step}-estimate`), "calculando…");
    say("Haciendo números…", "think");
    try {
        const data = await postJson(runUrl("/estimate"), paidOptions(step));
        show($(`${step}-estimate`), data.output);
        $(`${step}-confirm-row`).hidden = false;
        say("Esta es la cuenta. Si te parece bien, marca la casilla y lo lanzo; si no, no pasa nada.", "ask");
    } catch (e) {
        hide($(`${step}-estimate`));
        show($(`${step}-error`), e.message);
        say("No he podido calcular la estimación. El motivo está en rojo.", "error");
    }
}

async function runStep(body, errorElement = $("stage-error")) {
    hide(errorElement);
    try {
        await postJson(runUrl("/run"), body);
        pollJob();
    } catch (e) {
        show(errorElement, e.message);
        say("Eso no lo puedo lanzar. El motivo está en rojo.", "error");
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
for (const id of ["screener-a", "screener-b"]) $(id).addEventListener("change", () => screenersChanged());
$("screen-limit").addEventListener("input", () => resetPaid("screen"));

document.querySelectorAll("[data-step]").forEach((button) => button.addEventListener("click", () => runStep({ step: button.dataset.step })));

$("report-btn").addEventListener("click", () => {
    const year = parseInt($("partial-year").value, 10);
    runStep({ step: "report", partial_year: Number.isInteger(year) ? year : null });
});

$("adjudication-btn").addEventListener("click", async () => {
    const error = $("adjudication-error");
    hide(error);
    const file = $("adjudication-file").files[0];
    const initials = $("adjudication-initials").value.trim();
    if (!file) return show(error, "Elige el Excel rellenado.");
    if (!/^[A-Za-z]{2,6}$/.test(initials)) return show(error, "Indica tus iniciales (de 2 a 6 letras).");
    try {
        await api(runUrl(`/adjudicate?initials=${encodeURIComponent(initials)}`), { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
        pollJob();
    } catch (e) {
        show(error, e.message);
        say("No he podido recibir el Excel. El motivo está en rojo.", "error");
    }
});

// ── Job output ───────────────────────────────────────────────────────

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
        $("job-command").textContent = job.command || `palet ${job.step}`;
        const state = $("job-state");
        state.className = "state " + (job.running ? "run" : (job.returncode === 0 ? "ok" : "bad"));
        state.textContent = job.running ? "en ejecución…" : (job.returncode === 0 ? "terminado" : `error (código ${job.returncode})`);
        const log = $("job-log");
        log.textContent = job.log.join("\n") || "…";
        log.scrollTop = log.scrollHeight;
    }
    const key = `${job.step}|${job.started_at}`;
    if (job.running) {
        if (!jobWasRunning || key !== lastJobKey) {
            robot.busy = true;
            robot.completeBefore = overview ? overview.stages.every((stage) => stage.status !== "current" && stage.status !== "todo") : true;
            robot.readSince = job.step === "screen" ? (Date.parse(job.started_at) || Date.now()) : null;
            say(START_LINES[job.step] || "En marcha.", STEP_MOOD[job.step] || "think");
            if (job.run_id === currentRun) selectStageQuiet(stageOfStep(job.step));
        }
        jobWasRunning = true;
        lastJobKey = key;
        if (overview && job.run_id === currentRun && $("wizard").hidden) renderFlow(overview, job);
        jobTimer = setTimeout(pollJob, 1200);
    } else if (jobWasRunning) {
        jobWasRunning = false;
        robot.busy = false;
        const finished = stageOfStep(job.step);
        if (currentRun) await loadRun(currentRun, false);
        if (job.returncode === 0) {
            const complete = overview && overview.stages.every((stage) => stage.status !== "current" && stage.status !== "todo");
            robot.keepPile = true;                     // the books read stay beside it while it celebrates
            if (complete && !robot.completeBefore) {
                say("Revisión completa, de la primera pregunta al informe. Esto hay que celebrarlo.", "cheer");
                fireworks();
            } else {
                say(DONE_LINES[job.step] || "Hecho.", "cheer");
            }
            robot.keepPile = false;
            const node = document.querySelector(`.node[data-stage="${finished}"]`);
            if (node) node.classList.add("just-done");
        } else {
            say("Algo ha fallado. No he cambiado nada que no debiera; el motivo está en la salida.", "error");
        }
    }
}

function selectStageQuiet(stageId) {
    if (!STAGES[stageId]) return;
    selectedStage = stageId;
    if (overview) renderStage();
}

// ── New review: questions → advice → draft protocol → run ────────────

const WIZARD_FLOW = [["Preguntas", "contexto y preguntas"], ["Protocolo", "criterios y búsquedas"], ["Búsqueda", ""], ["Duplicados", ""],
    ["Revistas", ""], ["Cribado", ""], ["Decisión humana", ""], ["Asignación", ""], ["Informe", ""]];
let wizard = { step: 1, originals: [], file: null };

function renderWizardFlow(busy) {
    const active = wizard.step === 3 ? 1 : 0;
    $("flow").replaceChildren(...WIZARD_FLOW.map(([label, detail], index) => {
        const status = index < active ? "done" : (index === active ? "current" : "todo");
        const node = el("div", `node ${status}` + (index === active && busy ? " running" : ""));
        const head = el("span", "n");
        head.append(el("span", null, String(index).padStart(2, "0")), el("span", "mark", index < active ? "✓" : (index === active ? (busy ? "…" : "▸") : "")));
        node.append(head, el("span", "name", label), el("span", "detail", detail));
        return node;
    }));
}

function wizardStep(step) {
    wizard.step = step;
    document.querySelectorAll(".wz").forEach((node) => node.classList.toggle("on", Number(node.dataset.wz) === step));
    renderWizardFlow(false);
}

async function openWizard() {
    $("wizard").hidden = false;
    $("work").hidden = true;
    $("stats").replaceChildren();
    $("bar-run").textContent = "nueva";
    for (const id of ["wz-error-1", "wz-error-2", "wz-error-3", "new-error"]) hide($(id));
    wizardStep(1);
    say("Una revisión nueva. Cuéntame de qué va y escribe las preguntas tal como las tengáis: yo las leo con lápiz en mano.", "ask");
    try {
        const protocols = (await api("/api/v2/protocols")).filter((p) => !p.error);
        fill($("new-protocol"), protocols.map((p) => ({ value: p.file, label: `${p.file} · v${p.version} · ${p.status}` })), protocols.length ? protocols[protocols.length - 1].file : "");
    } catch (e) { /* the list is optional */ }
}

function closeWizard() {
    $("wizard").hidden = true;
    setMood("awake");
    loadRuns();
}

const questionLines = () => $("wz-questions").value.split("\n").map((line) => line.trim()).filter(Boolean);

async function withWriting(button, line, action) {
    button.disabled = true;
    renderWizardFlow(true);
    robot.busy = true;
    say(line, "write");
    try {
        return await action();
    } finally {
        robot.busy = false;
        button.disabled = false;
        renderWizardFlow(false);
    }
}

$("wz-file").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (file) $("wz-questions").value = (await file.text()).slice(0, 9000);
});

$("wz-analyse").addEventListener("click", async () => {
    hide($("wz-error-1"));
    try {
        const data = await withWriting($("wz-analyse"), "Leyendo las preguntas una a una. Apunto lo que no me queda claro.", () =>
            postJson("/api/v2/assistant/questions", { context: $("wz-context").value, questions: questionLines(), model: $("wz-model").value }));
        wizard.originals = data.questions;
        $("wz-overall").textContent = data.analysis.overall;
        const gaps = data.analysis.gaps || [];
        if (gaps.length) show($("wz-gaps"), "El contexto habla de esto y ninguna pregunta lo cubre:\n" + gaps.map((g) => `· ${g}`).join("\n")); else hide($("wz-gaps"));
        $("wz-cards").replaceChildren(...data.analysis.questions.map((advice, index) => {
            const original = data.questions[index];
            const card = el("div", "card");
            const head = el("div", "card-head");
            const labels = { none: "sin cambios", minor: "matiz", major: "cambio de fondo" };
            head.append(el("b", null, advice.id), el("span", `tag ${advice.change === "none" ? "ok" : "wait"}`, labels[advice.change]));
            card.append(head, el("p", "orig", `original: ${original}`));
            if (advice.issues.length) {
                const list = el("ul");
                advice.issues.forEach((issue) => list.appendChild(el("li", null, issue)));
                card.appendChild(list);
            }
            const text = el("textarea");
            text.rows = 3;
            text.maxLength = 800;
            text.dataset.final = "1";
            text.value = advice.change === "none" ? original : advice.suggested;
            if (advice.change !== "none") {
                card.appendChild(el("p", "why", `por qué: ${advice.rationale}`));
                const row = el("div", "row");
                const useSuggested = el("button", "btn small", "usar la sugerencia");
                const keepOriginal = el("button", "btn small", "conservar la original");
                useSuggested.type = keepOriginal.type = "button";
                useSuggested.addEventListener("click", () => { text.value = advice.suggested; });
                keepOriginal.addEventListener("click", () => { text.value = original; });
                row.append(useSuggested, keepOriginal);
                card.appendChild(row);
            }
            card.appendChild(text);
            return card;
        }));
        wizardStep(2);
        const changed = data.analysis.questions.filter((q) => q.change !== "none").length;
        say(changed ? `Tengo sugerencias para ${changed} de ${data.questions.length}. He dejado puesta mi versión; si prefieres la tuya, cámbiala. Coste: ${data.cost_usd} $.`
            : `Las ${data.questions.length} están claras tal como están. No toco nada. Coste: ${data.cost_usd} $.`, "ask");
    } catch (e) {
        show($("wz-error-1"), e.message);
        say("No he podido analizarlas. El motivo está en rojo.", "error");
    }
});

$("wz-back-1").addEventListener("click", () => wizardStep(1));

$("wz-draft").addEventListener("click", async () => {
    hide($("wz-error-2"));
    const finals = [...document.querySelectorAll('#wz-cards textarea[data-final]')].map((t) => t.value.trim());
    try {
        const draft = await withWriting($("wz-draft"), "Redactando criterios y cadenas de búsqueda. Es un borrador: lo firmáis vosotros, no yo.", () =>
            postJson("/api/v2/assistant/protocol", { context: $("wz-context").value, questions: finals, originals: wizard.originals, name: $("wz-name").value, model: $("wz-model").value }));
        wizard.file = draft.file;
        $("wz-file-name").textContent = `config/${draft.file}`;
        const period = draft.year_from || draft.year_to ? `${draft.year_from ?? "…"}–${draft.year_to ?? "…"}` : "sin límite de años";
        $("wz-kv").replaceChildren(...[["título", draft.title], ["periodo", period], ["estado", "borrador, sin aprobar"]].flatMap(([k, v]) => [el("dt", null, k), el("dd", null, v)]));
        const table = $("wz-criteria");
        table.replaceChildren();
        const head = table.insertRow();
        for (const title of ["criterio", "tipo", "regla"]) head.appendChild(el("th", null, title));
        for (const criterion of draft.criteria) {
            const row = table.insertRow();
            row.insertCell().textContent = criterion.id;
            row.insertCell().textContent = criterion.kind === "include" ? "inclusión" : "exclusión";
            const rule = row.insertCell();
            rule.textContent = criterion.rule;
            rule.style.whiteSpace = "normal";
            rule.style.textAlign = "left";
        }
        $("wz-searches").replaceChildren(...draft.searches.map((search) => {
            const block = el("p", "query");
            block.append(el("b", null, `${search.rq} · `), document.createTextNode(search.query));
            return block;
        }));
        if (draft.notes.length) show($("wz-notes"), draft.notes.map((n) => `· ${n}`).join("\n")); else hide($("wz-notes"));
        $("wz-run-id").value = draft.file.replace(/\.yaml$/, "");
        wizardStep(3);
        say(`Borrador listo en config/${draft.file}. Leedlo con calma: los criterios deciden qué entra. Coste: ${draft.cost_usd} $.`, "happy");
    } catch (e) {
        show($("wz-error-2"), e.message);
        say("No he podido redactar el borrador. El motivo está en rojo.", "error");
    }
});

async function createRun(protocol, label, runId, errorElement, button) {
    hide(errorElement);
    button.disabled = true;
    try {
        const created = await postJson("/api/v2/runs", { protocol, label, run_id: runId });
        $("wizard").hidden = true;
        $("job-command").textContent = "python -m palet init";
        $("job-log").textContent = created.output;
        selectedStage = null;
        await loadRuns(created.run_id);
        say("Revisión creada. Siguiente: mirar el recuento de cada búsqueda antes de aprobarla.", "happy");
    } catch (e) {
        show(errorElement, e.message);
        say("No he podido crear la revisión. El motivo está en rojo.", "error");
    } finally {
        button.disabled = false;
    }
}

$("wz-create").addEventListener("click", () => createRun(wizard.file, $("wz-name").value || wizard.file, $("wz-run-id").value, $("wz-error-3"), $("wz-create")));
$("new-create").addEventListener("click", () => createRun($("new-protocol").value, $("wz-name").value || $("new-id").value, $("new-id").value, $("new-error"), $("new-create")));
$("new-btn").addEventListener("click", openWizard);
$("wz-close").addEventListener("click", closeWizard);

// ── Approvals (deliberate acts of the authors) ───────────────────────

$("protocol-approve-btn").addEventListener("click", async () => {
    hide($("stage-error"));
    try {
        await postJson("/api/v2/protocols/approve", { file: overview.protocol.file, by: $("protocol-by").value, confirm: $("protocol-confirm").checked });
        $("protocol-confirm").checked = false;
        await loadRun(currentRun, false);
        say("Protocolo aprobado y fechado. A partir de aquí lo aplico tal cual.", "happy");
    } catch (e) {
        show($("stage-error"), e.message);
        say("No lo doy por aprobado todavía. El motivo está en rojo.", "error");
    }
});

async function approveSearch(sourceId, button) {
    if (button.dataset.armed !== "1") {            // first press arms the button; the second one approves
        button.dataset.armed = "1";
        button.textContent = "¿seguro? confirmar";
        setTimeout(() => { button.dataset.armed = ""; button.textContent = "aprobar"; }, 5000);
        say("Aprobar una cadena es decisión vuestra. ¿Has mirado su recuento? Pulsa otra vez para confirmar.", "ask");
        return;
    }
    hide($("stage-error"));
    try {
        const done = await postJson(runUrl("/approve-search"), { source: sourceId, by: $("approver").value, confirm: true });
        $("job-command").textContent = "python -m palet approve-search";
        $("job-log").textContent = done.output;
        await loadRun(currentRun, false);
        say("Cadena aprobada. Ya se puede descargar.", "happy");
    } catch (e) {
        show($("stage-error"), e.message);
        say("No he podido aprobarla. El motivo está en rojo.", "error");
    }
}

$("run-select").addEventListener("change", (event) => {
    resetPaid("screen");
    resetPaid("assign");
    selectedStage = null;
    if (event.target.value) loadRun(event.target.value, true);
});
$("refresh-btn").addEventListener("click", () => loadRuns());

$("robot").addEventListener("click", pokeRobot);
$("assign-model").addEventListener("change", () => resetPaid("assign"));
setMood("awake");
say("Arrancando…");
loadScreeners().catch((e) => show($("page-error"), e.message));
loadRuns().then(pollJob);
