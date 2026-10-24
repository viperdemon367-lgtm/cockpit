"use strict";
// ---------------------------------------------------------------- utilitaires
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
function isk(v) {
  if (v == null || !isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return nf2.format(v / 1e9) + " Md";
  if (a >= 1e6) return nf2.format(v / 1e6) + " M";
  if (a >= 1e4) return nf2.format(v / 1e3) + " k";
  return nf2.format(v);
}
const n0 = (v) => (v == null ? "—" : nf.format(v));
const pct = (v) => (v == null || !isFinite(v) ? "—" : nf2.format(v) + " %");
const cls = (v) => (v == null ? "" : v >= 0 ? "pos" : "neg");
function dur(s) {
  if (!s) return "—";
  s = Math.round(s);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return (d ? d + " j " : "") + (h ? h + " h " : "") + (!d ? m + " min" : "");
}
const IMG = "https://images.evetech.net";
// icônes officielles CCP : icon (objets), bp (blueprint original), bpc (copie), render (vaisseaux)
const ico = (tid, extra = "", kind = "icon") => (tid ? `<img class="ico ${extra}" src="${IMG}/types/${tid}/${kind}?size=64" loading="lazy" alt="" onerror="this.style.visibility='hidden'">` : "");
const portrait = (cid, extra = "") => `<img class="portrait ${extra}" src="${IMG}/characters/${cid}/portrait?size=64" alt="" loading="lazy">`;
const withIco = (tid, html, extra = "", kind) => `<div class="with-ico">${ico(tid, extra, kind)}<div>${html}</div></div>`;
const store = {
  get(k, d) { try { const v = localStorage.getItem("indy." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("indy." + k, JSON.stringify(v)); } catch { /* stockage indisponible */ } },
};

const HELP = {
  me: "ME (Material Efficiency) : réduction des matériaux du blueprint, de 0 à 10 %. Un BPO recherché ME 10 consomme 10 % de matériaux en moins.",
  te: "TE (Time Efficiency) : réduction du temps de fabrication du blueprint, de 0 à 20 %.",
  optimize: "Compare pour chaque composant le prix d'achat et le coût de fabrication. S'il est moins cher de l'acheter, l'outil l'achète et retire le job.",
  stock: "Retire de la liste d'achats ce que tu as déjà dans les hangars choisis (onglet Personnages & stock). Les modules montés et les vaisseaux assemblés ne sont jamais comptés.",
  decryptor: "Objet ajouté à l'invention : change la chance de réussite, le nombre de runs et le ME/TE de la copie T2. L'onglet Invention compare tous les décrypteurs.",
  realistic: "Profit qu'un seul slot de fabrication peut rapporter par jour, sans dépasser 10 % de ce qui se vend chaque jour sur le marché (au-delà, tu ferais baisser le prix).",
  slot: "Profit par heure de fabrication pour un slot de production (un job à la fois).",
  index: "Indice de coût du système : plus un système est utilisé pour l'industrie, plus les jobs y coûtent cher. Mis à jour par CCP toutes les heures.",
  critical: "Durée totale si tu lances en parallèle tous les jobs d'une même étape (il faut assez de slots de production).",
  depth: "Choisis jusqu'à quel niveau de l'arbre tu fabriques. Niveau 1 = les composants directs du produit ; tout ce qui est plus profond est acheté. Exemple : « jusqu'au niveau 1 » pour un vaisseau T2 = tu fabriques le vaisseau et ses composants, mais tu achètes les matériaux de réaction.",
  spike: "Le prix actuel dépasse de plus de 25 % la moyenne des 7 derniers jours : la marge risque de fondre avant que tu aies fini de produire.",
};
function bindHelp(root = document) {
  $$("abbr.help[data-help]", root).forEach((a) => { a.title = HELP[a.dataset.help] || ""; a.setAttribute("aria-label", a.title); });
}
const help = (k) => `<abbr class="help" data-help="${k}" title="${esc(HELP[k] || "")}">?</abbr>`;

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (err ? " err" : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.className = ""), err ? 7000 : 3000);
}
async function api(path, opts = {}) {
  const o = { headers: { "Content-Type": "application/json" }, ...opts };
  if (o.body && typeof o.body !== "string") o.body = JSON.stringify(o.body);
  const r = await fetch(path, o);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || `Erreur ${r.status}`);
  return j;
}
async function busy(btn, fn) {
  btn.disabled = true;
  try { return await fn(); } catch (e) { toast(e.message, true); } finally { btn.disabled = false; }
}
// tableau triable générique : cols = [{k, label, num, fmt, cls}]
function table(rows, cols, { onClick, sortKey, desc = true, id } = {}) {
  const st = { k: sortKey, desc };
  const wrap = document.createElement("div");
  wrap.className = "tscroll";
  const draw = () => {
    const r = [...rows];
    if (st.k) r.sort((a, b) => {
      const x = a[st.k], y = b[st.k];
      const c = typeof x === "string" ? x.localeCompare(y) : (x ?? -1e30) - (y ?? -1e30);
      return st.desc ? -c : c;
    });
    wrap.innerHTML = `<table${id ? ` id="${id}"` : ""}><thead><tr>${cols.map((c) =>
      `<th class="sort ${c.num ? "num" : ""}" data-k="${c.k}">${esc(c.label)}${st.k === c.k ? (st.desc ? " ▾" : " ▴") : ""}</th>`).join("")}</tr></thead><tbody>${
      r.map((row, i) => `<tr class="${onClick ? "click" : ""}" data-i="${rows.indexOf(row)}">${cols.map((c) =>
        `<td class="${c.num ? "num" : ""} ${c.cls ? c.cls(row) : ""}">${c.fmt ? c.fmt(row[c.k], row) : esc(row[c.k])}</td>`).join("")}</tr>`).join("")
    }</tbody></table>`;
    $$("th.sort", wrap).forEach((th) => th.onclick = () => { st.desc = st.k === th.dataset.k ? !st.desc : true; st.k = th.dataset.k; draw(); });
    if (onClick) $$("tbody tr", wrap).forEach((tr) => tr.onclick = () => onClick(rows[+tr.dataset.i]));
  };
  draw();
  return wrap;
}
function autocomplete(input, list, endpoint, onPick) {
  let items = [], sel = -1, timer;
  const close = () => list.classList.remove("open");
  const render = () => {
    list.innerHTML = items.map((x, i) => `<div class="${i === sel ? "sel" : ""}" data-i="${i}">${x.type_id ? ico(x.type_id, "s") : x.sec != null ? secBadge(x.sec) + "&nbsp;" : ""}${esc(x.name)}${x.alt ? `<span class="alt">${esc(x.alt)}</span>` : ""}${x.region ? `<span class="alt">${esc(x.region)}</span>` : ""}</div>`).join("");
    list.classList.toggle("open", items.length > 0);
    $$("div", list).forEach((d) => d.onmousedown = (e) => { e.preventDefault(); pick(items[+d.dataset.i]); });
  };
  const pick = (x) => { input.value = x.name; input.dataset.id = x.type_id ?? x.system_id; close(); onPick && onPick(x); };
  input.addEventListener("input", () => {
    input.dataset.id = "";
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (input.value.trim().length < 2) { items = []; return render(); }
      try { items = await api(endpoint + encodeURIComponent(input.value)); } catch (e) { items = []; toast(e.message, true); }
      sel = -1; render();
    }, 160);
  });
  input.addEventListener("keydown", (e) => {
    if (!list.classList.contains("open")) return;
    if (e.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); render(); e.preventDefault(); }
    if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); render(); e.preventDefault(); }
    if (e.key === "Enter" && items[Math.max(sel, 0)]) { pick(items[Math.max(sel, 0)]); e.preventDefault(); }
    if (e.key === "Escape") close();
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
}

// ---------------------------------------------------------------- état global
const G = { settings: null, meta: null, status: null, overrides: {}, lastPlan: null, assets: null, cart: store.get("cart", []) };

async function loadSettings() {
  const r = await api("/api/settings");
  G.settings = r.settings;
  G.meta = r;
}
async function saveSettings(partial) {
  Object.assign(G.settings, partial);
  await api("/api/settings", { method: "POST", body: partial });
}

// ---------------------------------------------------------------- navigation
function route() {
  const v = (location.hash.slice(1).split("?")[0]) || (G.settings && !G.settings.setup_done ? "guide" : "doctrines");
  $$(".view").forEach((s) => (s.hidden = s.id !== "v-" + v));
  $$(".nav nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === v));
  const q = new URLSearchParams(location.hash.split("?")[1] || "");
  if (v === "personnages") renderCharacters(q.get("ok"));
  if (v === "structures") renderStructures();
  if (v === "reglages") renderSettings();
  if (v === "opportunites") fillScanFilters();
  if (v === "arbitrage") fillArbFilters();
  if (v === "jobs") loadJobs();
  if (v === "demarrage") renderWizard();
  if (v === "aide") renderHelp();
  if (v === "guide") renderGuide();
  if (v === "patch") renderPatch();
  if (v === "alarme") renderAlarm();
  if (v === "carte") initMap();
  if (v === "pi") initPI();
  if (v === "soutenir") renderDonate();
  if (v === "doctrines") loadDoctrines().catch((e) => ($("#d-main").innerHTML = `<div class="warnbox">${esc(e.message)}</div>`));
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    G.status = s;
    const pm = G.meta ? (G.meta.hubs[G.settings.price_market] || (G.settings.custom_markets || []).find((m) => m.id === G.settings.price_market) || {}) : {};
    $("#corp-name").textContent = s.corp_name || "";
    $("#status").innerHTML = `
      <div>Données du jeu : <b>${s.sde_loaded ? esc(s.sde_status || "chargées") : "en cours"}</b></div>
      ${s.sde_loaded ? "" : `<div>${esc(s.sde_status || "")}</div>`}
      <div>Marché : <b>${esc(pm.short || pm.name || "Jita")}</b></div>
      <div>Personnages : <b>${s.characters.length}</b></div>
      ${s.sde_status.startsWith("Erreur") ? '<button class="small" id="sde-btn">Réessayer</button>' : ""}`;
    const b = $("#sde-btn");
    if (b) b.onclick = async () => { await api("/api/sde/update", { method: "POST" }); toast("Téléchargement relancé."); setTimeout(refreshStatus, 1500); };
    if (!s.sde_loaded) setTimeout(refreshStatus, 2500);
    if (location.hash.startsWith("#demarrage")) renderWizard(true);
    renderBanner();
    $("#status").insertAdjacentHTML("beforeend", `<div style="margin-top:6px"><a href="#patch" style="color:var(--muted)">v${esc(s.version)}</a></div>`);
  } catch (e) { $("#status").textContent = "Serveur injoignable"; setTimeout(refreshStatus, 5000); }
}

// ---------------------------------------------------------------- PRODUCTION
function setupProduction() {
  const dec = $("#p-dec");
  dec.innerHTML = `<option value="">Aucun</option>` + G.meta.decryptors.map((d) => `<option>${esc(d)}</option>`).join("");
  autocomplete($("#p-item"), $("#p-item-list"), "/api/search?q=", () => { $("#p-qty").focus(); $("#p-qty").select(); });
  $("#p-stock").checked = store.get("useStock", false);
  $("#p-opt").checked = store.get("optimize", false);
  $("#p-stock").onchange = () => store.set("useStock", $("#p-stock").checked);
  $("#p-run").onclick = () => runPlan();
  $("#p-add").onclick = () => addToCart() && toast("Ajouté. Ajoute d'autres produits ou clique « Calculer le plan ».");
  $("#p-opt").onchange = () => { store.set("optimize", $("#p-opt").checked); G.overrides = {}; if (G.cart.length) runPlan(); };
  $("#p-qty").addEventListener("keydown", (e) => e.key === "Enter" && runPlan());
  fillDepth(5);
  $("#p-depth").onchange = () => { store.set("maxDepth", $("#p-depth").value); if (G.cart.length) runPlan(); };
  renderCart();
}
function fillDepth(n) {
  const cur = store.get("maxDepth", "all");
  const opts = [["all", "Tout l'arbre"], ["0", "Produit final seulement"]];
  for (let i = 1; i <= Math.max(n, 1); i++) opts.push([String(i), `Jusqu'au niveau ${i}`]);
  $("#p-depth").innerHTML = opts.map(([v, l]) => `<option value="${v}" ${v === String(cur) ? "selected" : ""}>${l}</option>`).join("");
  if (!opts.some(([v]) => v === String(cur))) $("#p-depth").value = "all";
}
function addToCart() {
  const inp = $("#p-item"), id = +inp.dataset.id;
  if (!id) return false;
  const qty = Math.max(1, +$("#p-qty").value || 1);
  const ex = G.cart.find((c) => c.type_id === id);
  if (ex) ex.quantity = qty; else G.cart.push({ type_id: id, name: inp.value, quantity: qty });
  inp.value = ""; inp.dataset.id = ""; $("#p-qty").value = 1;
  store.set("cart", G.cart);
  renderCart();
  return true;
}
function renderCart() {
  const c = $("#p-cart");
  c.innerHTML = G.cart.map((x, i) => `<div class="line" title="${esc(x.name)}">${ico(x.type_id)}<span>${esc(x.name)}</span>
    <input type="number" min="1" value="${x.quantity}" data-i="${i}" aria-label="Quantité"><button data-del="${i}" aria-label="Retirer">×</button></div>`).join("")
    + (G.cart.length > 1 ? `<button class="small" id="p-clear">Vider la liste</button>` : "");
  $$("input", c).forEach((inp) => inp.onchange = () => { G.cart[+inp.dataset.i].quantity = Math.max(1, +inp.value || 1); store.set("cart", G.cart); });
  $$("[data-del]", c).forEach((b) => b.onclick = () => { G.cart.splice(+b.dataset.del, 1); store.set("cart", G.cart); renderCart(); });
  const cl = $("#p-clear");
  if (cl) cl.onclick = () => { G.cart = []; store.set("cart", G.cart); renderCart(); };
}
async function runPlan() {
  if ($("#p-item").dataset.id) addToCart();
  if (!G.cart.length) return toast("Choisis un produit dans la liste déroulante.", true);
  const body = {
    items: G.cart.map((c) => ({ type_id: c.type_id, quantity: c.quantity })), optimize: $("#p-opt").checked,
    overrides: G.overrides, use_stock: $("#p-stock").checked, stock_sources: G.settings.stock_sources,
    decryptor: $("#p-dec-wrap").hidden ? "__default__" : $("#p-dec").value,
    max_depth: $("#p-depth").value,
  };
  $("#p-out").innerHTML = `<div class="empty">Calcul en cours… (la première fois, la récupération des prix prend quelques secondes)</div>`;
  await busy($("#p-run"), async () => {
    const r = await api("/api/plan", { method: "POST", body });
    G.lastPlan = r;
    fillDepth(r.full_depth);
    const isT2 = r.inventions.length > 0;
    if (isT2 && $("#p-dec-wrap").hidden) $("#p-dec").value = G.settings.default_decryptor || "";
    $("#p-dec-wrap").hidden = !isT2;
    renderPlan(r);
  });
}
function renderPlan(r) {
  const s = r.summary;
  const out = $("#p-out");
  const virtual = r.jobs.some((j) => j.structure_virtual);
  const noPrice = r.targets.filter((t) => t.no_market_price);
  out.innerHTML = `
    ${virtual ? `<div class="warnbox">Aucune structure configurée pour certains jobs : calcul sans bonus. <a href="#structures">Déclare tes structures</a> pour des chiffres justes.</div>` : ""}
    ${noPrice.length ? `<div class="warnbox">Pas de prix de vente sur ${esc(r.price_market)} pour : ${noPrice.map((t) => esc(t.name)).join(", ")}. Le revenu affiché est donc incomplet.</div>` : ""}
    ${r.compare_error ? `<div class="warnbox">Comparaison de marché impossible : ${esc(r.compare_error)}</div>` : ""}
    ${$("#p-stock").checked && !r.stock_loaded ? `<div class="warnbox">« Déduire mon stock » est coché mais aucun stock n'est chargé. <a href="#personnages">Connecte un personnage</a>.</div>` : ""}
    <div class="kpis">
      <div class="kpi"><span>Coût total</span><b>${isk(s.total_cost)}</b></div>
      <div class="kpi"><span>Revenu net (${esc(r.price_market)})</span><b>${isk(s.revenue_net)}</b></div>
      <div class="kpi"><span>Profit</span><b class="${cls(s.profit)}">${isk(s.profit)}</b></div>
      <div class="kpi"><span>Marge</span><b class="${cls(s.margin_pct)}">${pct(s.margin_pct)}</b></div>
      ${s.multi ? "" : `<div class="kpi"><span>Coût unitaire</span><b>${isk(s.unit_cost)}</b></div>`}
      <div class="kpi"><span>Durée ${help("critical")}</span><b>${dur(s.critical_path_s)}</b></div>
      <div class="kpi"><span>Volume à transporter</span><b>${n0(s.volume_m3)} m³</b></div>
    </div>
    ${s.multi ? `<div class="card"><h2>Détail par produit</h2><div id="targets"></div></div>` : ""}
    <div class="tree-wrap"><div class="legend">
      <span><i style="background:var(--amber)"></i>Fabriqué</span><span><i style="background:var(--violet)"></i>Réaction</span>
      <span><i style="background:var(--sky)"></i>Acheté</span><span>- - - Invention</span>
      <span>Clique sur un composant pour basculer fabriquer ↔ acheter, ou sur « fabriqué / acheté » en haut d'une colonne pour tout un niveau.</span>
      ${Object.keys(G.overrides).length ? `<button class="small" id="p-reset">Annuler mes choix manuels</button>` : ""}
    </div><div class="tree" id="tree"></div></div>
    <div class="grid2">
      <div class="card"><h2>Jobs à lancer, dans l'ordre <span class="muted" style="font-size:14px">${r.jobs.length} jobs · ${isk(s.job_cost)} de frais</span></h2><div id="jobs"></div></div>
      <div class="card"><h2>Liste d'achats <span><button class="small" id="copy-buy">Copier pour le Multibuy</button></span></h2><div id="buylist"></div></div>
    </div>`;
  if (s.multi) $("#targets").append(table(r.targets, [
    { k: "name", label: "Produit", fmt: (v, x) => withIco(x.type_id, esc(v)) },
    { k: "quantity", label: "Quantité", num: true, fmt: n0 },
    { k: "unit_cost_estimate", label: "Coût unitaire estimé", num: true, fmt: isk },
    { k: "unit_sell_net", label: "Vente nette / u", num: true, fmt: isk },
    { k: "revenue_net", label: "Revenu net", num: true, fmt: isk },
  ], { sortKey: "revenue_net" }));
  const rb = $("#p-reset");
  if (rb) rb.onclick = () => { G.overrides = {}; runPlan(); };
  renderTree(r);
  renderJobs(r);
  renderBuy(r);
  bindHelp(out);
}
function renderTree(r) {
  const tree = $("#tree");
  const maxD = Math.max(...r.nodes.map((n) => n.depth));
  const cols = [];
  for (let d = 0; d <= maxD; d++) cols.push(r.nodes.filter((n) => n.depth === d).sort((a, b) => a.name.localeCompare(b.name)));
  const md = r.max_depth;
  tree.innerHTML = `<svg id="tree-svg"></svg>` + cols.map((c, d) => `<div class="tcol"><h3>${d === 0 ? (c.length > 1 ? "Produits" : "Produit") : "Niveau " + d}
    ${d > 0 ? `<button class="lvl ${md != null && d > md ? "off" : ""}" data-lvl="${d}" title="${md != null && d > md ? "Fabriquer aussi ce niveau" : "Acheter ce niveau et tout ce qui est en dessous"}">${md != null && d > md ? "acheté" : "fabriqué"}</button>` : ""}</h3>${c.map((n) => {
    const kind = n.decision === "buy" ? "buy" : n.activity === "reaction" ? "reaction" : "";
    const fixed = n.depth === 0 || !n.can_build;
    const det = n.decision === "buy"
      ? `${n0(n.needed)} à acheter · ${isk(n.unit_buy)}/u`
      : `${n0(n.needed)} · ${n.runs} run${n.runs > 1 ? "s" : ""}`;
    const tip = `${n.name}${n.in_stock ? " — " + n0(n.in_stock) + " pris dans ton stock" : ""}${fixed ? "" : n.decision === "buy" ? " — clic : le fabriquer" : " — clic : l'acheter"}`;
    return `<div class="node ${kind} ${fixed ? "fixed" : ""}" data-id="${n.type_id}" title="${esc(tip)}" ${fixed ? "" : 'tabindex="0" role="button"'}>
      ${ico(n.type_id)}<div><div class="n">${esc(n.name)}</div><div class="d">${det}${n.in_stock ? " · stock " + n0(n.in_stock) : ""}</div></div></div>`;
  }).join("")}</div>`).join("");
  const toggle = (el) => {
    const id = +el.dataset.id;
    const cur = r.nodes.find((n) => n.type_id === id);
    G.overrides[id] = cur.decision === "build" ? "buy" : "build";
    runPlan();
  };
  $$("button[data-lvl]", tree).forEach((b) => b.onclick = () => {
    const d = +b.dataset.lvl;
    const v = md != null && d > md ? String(Math.max(d, md + 1)) : String(d - 1);
    $("#p-depth").value = v; store.set("maxDepth", v); runPlan();
  });
  $$(".node:not(.fixed)", tree).forEach((el) => {
    el.onclick = () => toggle(el);
    el.onkeydown = (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), toggle(el));
  });
  requestAnimationFrame(() => drawEdges(r));
  $$("img", tree).forEach((img) => img.addEventListener("load", () => drawEdges(r), { once: true }));
}
function drawEdges(r) {
  const tree = $("#tree"), svg = $("#tree-svg");
  if (!tree || !svg) return;
  const base = tree.getBoundingClientRect();
  svg.setAttribute("width", tree.scrollWidth);
  svg.setAttribute("height", tree.scrollHeight);
  const pos = {};
  $$(".node", tree).forEach((el) => { pos[el.dataset.id] = el.getBoundingClientRect(); });
  const seen = new Set();
  let paths = "";
  for (const e of r.edges) {
    const k = e.from + ">" + e.to;
    if (seen.has(k)) continue;
    seen.add(k);
    const a = pos[e.from], b = pos[e.to];
    if (!a || !b) continue;
    const x1 = a.right - base.left, y1 = a.top + a.height / 2 - base.top;
    const x2 = b.left - base.left, y2 = b.top + b.height / 2 - base.top;
    const mx = (x1 + x2) / 2;
    const node = r.nodes.find((n) => n.type_id === e.to);
    const col = e.invention ? "#8796ab" : node && node.decision === "buy" ? "#6aa9e0" : node && node.activity === "reaction" ? "#a58be0" : "#e2a542";
    paths += `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" fill="none" stroke="${col}" stroke-opacity=".45" stroke-width="1.3" ${e.invention ? 'stroke-dasharray="4 3"' : ""}/>`;
  }
  svg.innerHTML = paths;
}
window.addEventListener("resize", () => G.lastPlan && drawEdges(G.lastPlan));

function renderJobs(r) {
  const byDepth = {};
  r.jobs.forEach((j) => (byDepth[j.depth] = byDepth[j.depth] || []).push(j));
  const depths = Object.keys(byDepth).map(Number).sort((a, b) => b - a);
  let step = 0, html = "";
  if (r.inventions.length) {
    step++;
    html += `<tr class="step"><td colspan="5">Étape ${step} · Inventions (copie du BPC T1 puis invention)</td></tr>`;
    html += r.inventions.map((v) => `<tr><td>${withIco(v.t1_blueprint_id, `${esc(v.name)}<div class="muted">${esc(v.t1_blueprint)} · décrypteur ${esc(v.decryptor)} · ${pct(v.probability * 100)} de réussite · ${v.runs_per_bpc} runs/copie</div>`, "", "bpc")}</td>
      <td class="num">${v.attempts} essais</td><td>${esc(v.structure)}</td><td class="num">${dur(v.duration_s)}</td><td class="num">${isk(v.job_cost_total)}</td></tr>`).join("");
  }
  for (const d of depths) {
    step++;
    html += `<tr class="step"><td colspan="5">Étape ${step} · ${d === 0 ? "Produit final" : "Niveau " + d} ${step > 1 ? '<span class="muted" style="font-weight:400">— quand l’étape précédente est terminée</span>' : ""}</td></tr>`;
    html += byDepth[d].map((j) => `<tr><td>${withIco(j.type_id, `${esc(j.name)}<div class="muted">ME ${j.me} / TE ${j.te}${j.activity === "reaction" ? " · réaction" : ""}</div>`)}</td>
      <td class="num">${j.runs} run${j.runs > 1 ? "s" : ""}<div class="muted">→ ${n0(j.output)}</div></td><td>${esc(j.structure)}</td><td class="num">${dur(j.duration_s)}</td><td class="num">${isk(j.job_cost)}</td></tr>`).join("");
  }
  $("#jobs").innerHTML = `<div class="tscroll"><table><thead><tr><th>Job</th><th class="num">Runs</th><th>Structure</th><th class="num">Durée</th><th class="num">Frais</th></tr></thead><tbody>${html}</tbody></table></div>`;
}
function renderBuy(r) {
  const cmp = r.compare_market;
  const per = r.transport_isk_per_m3 || 0;
  const rows = r.buy.map((b) => {
    const row = { ...b };
    if (cmp) {
      const vol = b.to_buy ? b.volume_m3 / b.to_buy : 0;
      row.main_landed = b.unit_price + vol * per;
      row.best = b.compare_price && b.compare_price < row.main_landed ? cmp : r.price_market;
    }
    return row;
  });
  const cols = [
    { k: "name", label: "Objet", fmt: (v, x) => withIco(x.type_id, esc(v), "s") },
    { k: "to_buy", label: "À acheter", num: true, fmt: (v, x) => n0(v) + (x.in_stock ? `<div class="muted">déjà ${n0(x.in_stock)} en stock</div>` : "") },
    { k: "unit_price", label: `Prix ${r.price_market}`, num: true, fmt: (v, x) => isk(v) + (cmp && per ? `<div class="muted">rendu ${isk(x.main_landed)}</div>` : ""), cls: (x) => (cmp && x.best === r.price_market ? "cheaper" : "") },
  ];
  if (cmp) cols.push({ k: "compare_price", label: `Prix ${cmp}`, num: true, fmt: (v, x) => (v ? isk(v) + `<div class="muted">${n0(x.compare_stock)} dispo</div>` : "—"), cls: (x) => (x.best === cmp ? "cheaper" : "") });
  cols.push({ k: "total", label: "Total", num: true, fmt: isk }, { k: "volume_m3", label: "m³", num: true, fmt: n0 });
  $("#buylist").innerHTML = "";
  if (cmp) $("#buylist").insertAdjacentHTML("beforeend", `<p class="hint" style="padding:8px 14px 0;margin:0">En vert : le marché le moins cher pour cet objet${per ? `, transport (${n0(per)} ISK/m³) inclus pour ${esc(r.price_market)}` : ""}.</p>`);
  $("#buylist").append(table(rows, cols, { sortKey: "total" }));
  $("#copy-buy").onclick = async () => {
    const txt = r.buy.filter((b) => b.to_buy > 0).map((b) => `${b.name}\t${b.to_buy}`).join("\n");
    try { await navigator.clipboard.writeText(txt); toast("Copié. En jeu : Marché → Multibuy → colle (Ctrl+V)."); }
    catch { toast("Copie bloquée par le navigateur : sélectionne la liste à la main.", true); }
  };
}

// ---------------------------------------------------------------- INVENTION
function setupInvention() {
  autocomplete($("#i-item"), $("#i-item-list"), "/api/t2search?q=", (x) => runInvention(x.type_id));
}
async function runInvention(id) {
  $("#i-out").innerHTML = `<div class="empty">Calcul…</div>`;
  try {
    const r = await api("/api/invention/" + id);
    $("#i-out").innerHTML = `
      <div class="kpis">
        <div class="kpi"><span>Blueprint T1 à copier</span><b style="font-size:18px">${withIco(r.t1_blueprint_id, esc(r.t1_blueprint), "", "bp")}</b></div>
        <div class="kpi"><span>Encryption / sciences</span><b>${r.encryption_level} / ${r.science_levels.join(" + ")}</b></div>
        <div class="kpi"><span>Par essai</span><b style="font-size:15px">${r.datacores.map((d) => withIco(d.type_id, `${d.qty} × ${esc(d.name)} <span class="muted">(${isk(d.unit_price)})</span>`, "s")).join("")}</b></div>
      </div>
      <div class="card"><h2>Comparatif des décrypteurs ${help("decryptor")} <button class="small primary" id="i-plan">Planifier avec le meilleur</button></h2><div id="i-table"></div></div>
      <p class="hint">Clique sur une ligne pour planifier la fabrication avec ce décrypteur. Le profit/heure tient compte du TE apporté par le décrypteur ; le temps d'invention n'est pas inclus (slots de science séparés).</p>`;
    $("#i-table").append(table(r.rows, [
      { k: "decryptor_label", label: "Décrypteur", fmt: (v, x) => (x.decryptor_type_id ? withIco(x.decryptor_type_id, esc(v), "s") : esc(v)) },
      { k: "probability", label: "Chance", num: true, fmt: (v) => pct(v * 100) },
      { k: "runs", label: "Runs/BPC", num: true },
      { k: "me", label: "ME", num: true }, { k: "te", label: "TE", num: true },
      { k: "invention_cost_per_unit", label: "Invention / u", num: true, fmt: isk },
      { k: "unit_cost", label: "Coût / u", num: true, fmt: isk },
      { k: "profit_per_unit", label: "Profit / u", num: true, fmt: isk, cls: (x) => cls(x.profit_per_unit) },
      { k: "profit_per_hour", label: "Profit / h", num: true, fmt: isk, cls: (x) => cls(x.profit_per_hour) },
    ], { sortKey: "profit_per_unit", onClick: (row) => openInProduction(id, r.name, row.decryptor === "Aucun" ? "" : row.decryptor) }));
    bindHelp($("#i-out"));
    $("#i-plan").onclick = () => openInProduction(id, r.name, r.rows[0].decryptor === "Aucun" ? "" : r.rows[0].decryptor);
  } catch (e) { $("#i-out").innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; }
}
function openInProduction(id, name, decryptor) {
  location.hash = "production";
  G.cart = [{ type_id: id, name, quantity: 1 }];
  store.set("cart", G.cart);
  renderCart();
  G.overrides = {};
  if (decryptor !== undefined) { $("#p-dec-wrap").hidden = false; $("#p-dec").value = decryptor; }
  runPlan();
}

// ---------------------------------------------------------------- OPPORTUNITES
function fillScanFilters() {
  const s = G.settings.scan;
  $("#o-margin").value = s.min_margin_pct; $("#o-vol").value = s.min_daily_volume; $("#o-maxcost").value = s.max_unit_cost;
  $("#o-t2").checked = s.include_t2; $("#o-react").checked = s.include_reactions; $("#o-cap").checked = s.include_capitals;
}
function setupScan() {
  $("#o-run").onclick = async () => {
    const scan = { ...G.settings.scan, min_margin_pct: +$("#o-margin").value, min_daily_volume: +$("#o-vol").value,
      max_unit_cost: +$("#o-maxcost").value, include_t2: $("#o-t2").checked, include_reactions: $("#o-react").checked, include_capitals: $("#o-cap").checked };
    await saveSettings({ scan });
    await api("/api/scan/start", { method: "POST" });
    pollScan();
  };
  pollScan(true);
}
async function pollScan(once) {
  const s = await api("/api/scan/status");
  $("#o-run").disabled = s.running;
  $("#o-prog").textContent = s.running ? s.progress : s.error ? "Erreur : " + s.error : "";
  if (s.result) renderScan(s.result);
  if (s.running) setTimeout(pollScan, 1200);
}
function renderScan(res) {
  const out = $("#o-out");
  out.innerHTML = `<p class="muted">${n0(res.scanned)} produits analysés sur ${esc(res.market)} · ${new Date(res.time * 1000).toLocaleString("fr-FR")} · clique sur une ligne pour ouvrir le plan de production. ⓘ ${esc(HELP.realistic)}</p>`;
  if (!res.rows.length) { out.innerHTML += `<div class="empty">Aucun résultat avec ces filtres.</div>`; return; }
  const card = document.createElement("div");
  card.className = "card";
  card.append(table(res.rows, [
    { k: "name", label: "Produit", fmt: (v, x) => withIco(x.type_id, esc(v) + (x.price_spike ? ` <span class="tag warn" title="${esc(HELP.spike)}">pic de prix</span>` : "") + `<div class="muted">${esc(x.group)}</div>`) },
    { k: "kind", label: "Type" },
    { k: "unit_cost", label: "Coût / u", num: true, fmt: isk },
    { k: "unit_sell_net", label: "Vente nette / u", num: true, fmt: isk },
    { k: "profit_per_unit", label: "Profit / u", num: true, fmt: isk, cls: (x) => cls(x.profit_per_unit) },
    { k: "margin_pct", label: "Marge", num: true, fmt: pct },
    { k: "profit_per_hour", label: "ISK / h de slot", num: true, fmt: isk },
    { k: "daily_volume", label: "Vendus / jour", num: true, fmt: n0 },
    { k: "isk_per_day_realistic", label: "ISK / jour réaliste ⓘ", num: true, fmt: isk, cls: () => "pos" },
    { k: "structure", label: "Structure" },
  ], { sortKey: "isk_per_day_realistic", onClick: (row) => openInProduction(row.type_id, row.name) }));
  out.append(card);
}

// ---------------------------------------------------------------- ARBITRAGE
function fillArbFilters() {
  const a = G.settings.arbitrage;
  $("#a-hubs").innerHTML = Object.values(G.meta.hubs).map((h) => `<label><input type="checkbox" value="${h.id}" ${a.hubs.includes(h.id) ? "checked" : ""}>${esc(h.short)}</label>`).join("");
  $("#a-minprofit").value = a.min_profit; $("#a-margin").value = a.min_margin_pct; $("#a-instant").checked = a.instant_sell;
}
function setupArb() {
  $("#a-run").onclick = async () => {
    const arbitrage = { ...G.settings.arbitrage, hubs: $$("#a-hubs input:checked").map((i) => i.value),
      min_profit: +$("#a-minprofit").value, min_margin_pct: +$("#a-margin").value, instant_sell: $("#a-instant").checked };
    await saveSettings({ arbitrage });
    await api("/api/arbitrage/start", { method: "POST" });
    pollArb();
  };
  pollArb();
}
async function pollArb() {
  const s = await api("/api/arbitrage/status");
  $("#a-run").disabled = s.running;
  $("#a-prog").textContent = s.running ? s.progress : s.error ? "Erreur : " + s.error : "";
  if (s.result) {
    const out = $("#a-out");
    out.innerHTML = `<p class="muted">${new Date(s.result.time * 1000).toLocaleString("fr-FR")} · « Profit potentiel » = profit unitaire × min(stock dispo, 3 jours de volume à destination).</p>`;
    const card = document.createElement("div");
    card.className = "card";
    card.append(table(s.result.rows, [
      { k: "name", label: "Objet", fmt: (v, x) => withIco(x.type_id, esc(v), "s") }, { k: "from", label: "Acheter à" }, { k: "to", label: "Revendre à" },
      { k: "buy_price", label: "Prix achat", num: true, fmt: isk }, { k: "sell_price", label: "Prix revente", num: true, fmt: isk },
      { k: "unit_profit", label: "Profit / u", num: true, fmt: isk, cls: () => "pos" },
      { k: "margin_pct", label: "Marge", num: true, fmt: pct },
      { k: "qty_available", label: "Dispo", num: true, fmt: n0 },
      { k: "dst_daily_volume", label: "Vol./jour dest.", num: true, fmt: n0 },
      { k: "volume_m3_unit", label: "m³ / u", num: true, fmt: nf2.format },
      { k: "potential_profit", label: "Profit potentiel", num: true, fmt: isk, cls: () => "pos" },
    ], { sortKey: "potential_profit" }));
    out.append(card);
  }
  if (s.running) setTimeout(pollArb, 1500);
}

// ---------------------------------------------------------------- STRUCTURES
const RIG_PRESETS = { "T1 (ME 2 % / TE 20 %)": [2.0, 20], "T2 (ME 2,4 % / TE 24 %)": [2.4, 24] };
function renderStructures() {
  const list = $("#s-list");
  const sts = G.settings.structures;
  if (!sts.length) list.innerHTML = `<div class="empty">Aucune structure. Ajoute au moins celle où tu fabriques (même une station NPC).</div>`;
  else list.innerHTML = "";
  const kinds = Object.keys(G.meta.structure_kinds);
  const cats = G.meta.rig_categories;
  sts.forEach((st, i) => {
    const el = document.createElement("div");
    el.className = "struct";
    const acts = G.meta.structure_kinds[st.kind] || [];
    el.innerHTML = `
      <div class="top">
        <div class="field"><label>Nom</label><input data-f="name" value="${esc(st.name)}"></div>
        <div class="field"><label>Type</label><select data-f="kind">${kinds.map((k) => `<option ${k === st.kind ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></div>
        <div class="field"><label>Système</label><input data-f="system_name" value="${esc(st.system_name || "")}" placeholder="Jita, C-N4OD…"></div>
        <button class="small" data-a="resolve">Vérifier le système</button>
        <div class="field"><label>Taxe structure (%)</label><input data-f="tax_pct" type="number" step="0.01" value="${st.tax_pct ?? 0}"></div>
        <div class="field"><label>Sécurité</label><select data-f="security">${["high", "low", "null", "wh"].map((x) => `<option ${x === st.security ? "selected" : ""}>${x}</option>`).join("")}</select></div>
        <label class="check"><input type="checkbox" data-f="enabled" ${st.enabled !== false ? "checked" : ""}> Active</label>
        <button class="small danger" data-a="del">Supprimer</button>
      </div>
      <div class="sysinfo">${st.system_id ? `ID ${st.system_id} · sécurité ${st.sec_status ?? "?"} · indices : ${esc(Object.entries(st.indices || {}).filter(([k]) => ["manufacturing", "reaction", "invention"].includes(k)).map(([k, v]) => k + " " + pct(v * 100)).join(", "))}` : "Système non vérifié : l'indice de coût ne sera pas appliqué."}</div>
      <div class="chips">${acts.map((a) => `<label><input type="checkbox" data-act="${a}" ${(st.activities || acts).includes(a) ? "checked" : ""}>${a}</label>`).join("")}</div>
      <div class="rigs">${(st.rigs || []).map((r, j) => `
        <div class="rig" data-r="${j}">
          <select data-rf="applies">${Object.entries(cats).map(([k, v]) => `<option value="${k}" ${k === r.applies ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
          ME % <input type="number" step="0.1" data-rf="me" value="${r.me}" style="width:80px">
          TE % <input type="number" step="1" data-rf="te" value="${r.te}" style="width:80px">
          <button class="small danger" data-a="delrig" data-j="${j}">Retirer</button>
        </div>`).join("")}
        <div class="rig"><select data-a="preset">${Object.keys(RIG_PRESETS).map((p) => `<option>${p}</option>`).join("")}</select><button class="small" data-a="addrig">Ajouter un rig</button>
        <span class="hint">Valeurs de base : le multiplicateur low/null/WH est appliqué automatiquement.</span></div>
      </div>`;
    // liaisons
    $$("[data-f]", el).forEach((inp) => inp.onchange = () => {
      const f = inp.dataset.f;
      st[f] = inp.type === "checkbox" ? inp.checked : inp.type === "number" ? +inp.value : inp.value;
      if (f === "kind") { st.activities = G.meta.structure_kinds[st.kind]; renderStructures(); }
    });
    $$("[data-act]", el).forEach((c) => c.onchange = () => { st.activities = $$("[data-act]:checked", el).map((x) => x.dataset.act); });
    $$(".rig[data-r]", el).forEach((rw) => $$("[data-rf]", rw).forEach((inp) => inp.onchange = () => {
      const r = st.rigs[+rw.dataset.r];
      r[inp.dataset.rf] = inp.dataset.rf === "applies" ? inp.value : +inp.value;
    }));
    $('[data-a="del"]', el).onclick = () => { sts.splice(i, 1); renderStructures(); };
    $('[data-a="addrig"]', el).onclick = () => {
      const [me, te] = RIG_PRESETS[$('[data-a="preset"]', el).value];
      (st.rigs = st.rigs || []).push({ applies: "all", me, te }); renderStructures();
    };
    $$('[data-a="delrig"]', el).forEach((b) => b.onclick = () => { st.rigs.splice(+b.dataset.j, 1); renderStructures(); });
    $('[data-a="resolve"]', el).onclick = (ev) => busy(ev.target, async () => {
      const r = await api("/api/system?name=" + encodeURIComponent(st.system_name || ""));
      Object.assign(st, { system_id: r.system_id, system_name: r.name, sec_status: r.security, security: r.band, indices: r.cost_indices });
      renderStructures();
      toast(`${r.name} trouvé (sécurité ${r.security}).`);
    });
    list.append(el);
  });
}
function setupStructures() {
  $("#s-add").onclick = () => {
    G.settings.structures.push({ id: "s" + Date.now(), name: "Nouvelle structure", kind: "Raitaru", security: "high", tax_pct: 0, rigs: [], enabled: true, activities: G.meta.structure_kinds.Raitaru });
    renderStructures();
  };
  $("#s-save").onclick = (ev) => busy(ev.target, async () => { await saveSettings({ structures: G.settings.structures }); toast("Structures enregistrées."); });
}

// ---------------------------------------------------------------- PERSONNAGES
async function renderCharacters(okName) {
  const out = $("#c-out");
  const s = await api("/api/status");
  G.status = s;
  const chars = await api("/api/characters");
  if (okName) { toast(okName + " connecté. Clique « Rafraîchir depuis le jeu »."); history.replaceState(null, "", "#personnages"); refreshStatus(); }
  const src = G.settings.stock_sources;
  const spfmt = (v) => (v ? nf2.format(v / 1e6) + " M SP" : "");
  out.innerHTML = `
    ${s.esi_configured ? "" : `<div class="warnbox">Pour connecter tes personnages, il faut d'abord une application EVE. <a href="#demarrage">Suis l'étape 5 de l'assistant</a> (3 minutes).</div>`}
    <div class="card"><h2>Personnages connectés (${chars.length})
      <span><a href="/login"><button class="small primary" ${s.esi_configured ? "" : "disabled"}>Ajouter un personnage</button></a>
      <button class="small" id="c-private" ${s.esi_configured ? "" : "disabled"}>Personnage d'un autre compte</button></span></h2>
      <div class="body">${chars.length ? chars.map((c) => `
        <div class="pilot-card"><div class="top">
          <label class="check" style="padding:0">${portrait(c.character_id)}<input type="checkbox" data-char="${c.character_id}" ${src.characters.map(Number).includes(c.character_id) ? "checked" : ""}>
            <span><b>${esc(c.name)}</b> <span class="muted">${spfmt(c.total_sp)}</span><br>
            <span class="muted">${c.corporation_id ? logo("corporations", c.corporation_id) + esc(c.corporation_name || "") : ""}${c.alliance_id ? " · " + logo("alliances", c.alliance_id) + esc(c.alliance_name || "") : ""}</span></span></label>
          <span>${c.broken ? '<span class="threat t-tres">connexion expirée</span> ' : ""}${c.missing_scopes.length ? '<span class="threat t-dang">permissions à mettre à jour</span> ' : '<span class="threat t-faible">OK</span> '}
          ${c.broken || c.missing_scopes.length ? '<a href="/login"><button class="small primary">Reconnecter</button></a>' : ""}
          <button class="small danger" data-del="${c.character_id}">Déconnecter</button></span></div>
          ${c.missing_scopes.length ? `<div class="hint">Permissions manquantes (vérifie qu'elles sont cochées sur ton application EVE, puis reconnecte ce personnage) :</div>${scopeChips(c.missing_scopes, c.missing_scopes)}` : ""}
        </div>`).join("") : '<p class="muted">Aucun personnage. Tu peux en connecter autant que tu veux, sur plusieurs comptes.</p>'}
        <p class="hint">Case cochée = les hangars personnels de ce perso comptent dans ton stock. Tous les persos connectés sont utilisés pour les doctrines et les jobs.<br>
        Même compte : « Ajouter un personnage » et choisis-en un autre sur la page EVE. Autre compte : « Personnage d'un autre compte » copie un lien à ouvrir en navigation privée.</p>
      </div></div>
    <div class="card"><h2>Stock, blueprints et compétences <button class="small" id="c-refresh" ${chars.length ? "" : "disabled"}>Rafraîchir depuis le jeu</button></h2>
      <div class="body" id="c-assets">${s.assets_time ? "Chargement…" : "Pas encore chargé : clique « Rafraîchir depuis le jeu »."}</div></div>`;
  bindCopy(out);
  $("#c-private").onclick = copyPrivateLogin;
  $$("[data-char]", out).forEach((c) => c.onchange = () => saveStock());
  $$("[data-del]", out).forEach((b) => b.onclick = async () => {
    if (!confirm("Déconnecter ce personnage ?")) return;
    await api("/api/characters/" + b.dataset.del, { method: "DELETE" }); renderCharacters(); refreshStatus();
  });
  const rb = $("#c-refresh");
  if (rb) rb.onclick = () => busy(rb, async () => {
    $("#c-assets").textContent = "Lecture des hangars, blueprints et compétences de tous les personnages… (jusqu'à 1 minute)";
    G.assets = await api("/api/assets/refresh", { method: "POST" });
    renderAssetSources(G.assets);
    toast("Données des personnages à jour.");
    renderCharacters();
  });
  if (s.assets_time) { G.assets = await api("/api/assets"); renderAssetSources(G.assets); }
}
function renderAssetSources(r) {
  const src = G.settings.stock_sources;
  const divs = [];
  Object.values(r.divisions || {}).forEach((ds) => ds.forEach((d) => divs.push({ flag: "CorpSAG" + d.division, name: d.name || "Hangar " + d.division })));
  $("#c-assets").innerHTML = `
    ${r.errors && r.errors.length ? `<div class="warnbox">${r.errors.map(esc).join("<br>")}</div>` : ""}
    <p>Dernière lecture : ${r.assets_time ? new Date(r.assets_time * 1000).toLocaleString("fr-FR") : "—"} · ${r.blueprints} blueprints (leur ME/TE réel est utilisé dans les calculs).</p>
    ${divs.length ? `<div class="lbl">Hangars de corporation à compter dans le stock</div>
    <div class="chips" style="margin:6px 0 14px">${divs.map((d) => `<label><input type="checkbox" data-div="${d.flag}" ${src.corp_divisions.includes(d.flag) ? "checked" : ""}>${esc(d.name)}</label>`).join("")}</div>` : ""}
    <div class="lbl">Limiter le stock à certains endroits (rien de coché = partout)</div>
    <div class="chips" style="margin-top:6px">${r.locations.map((l) => `<label><input type="checkbox" data-loc="${l.location_id}" ${src.location_ids.map(Number).includes(l.location_id) ? "checked" : ""}>${esc(l.name)} <span class="muted">(${l.items})</span></label>`).join("")}</div>
    <p class="hint">Exemple : coche seulement ta citadelle de production pour ne pas compter des minerais qui traînent à Jita.</p>`;
  $$("[data-div], [data-loc]", $("#c-assets")).forEach((c) => c.onchange = () => saveStock());
}
async function saveStock() {
  const prev = G.settings.stock_sources;
  const stock_sources = {
    characters: $$("[data-char]:checked").map((c) => +c.dataset.char),
    corp_divisions: $$("[data-div]").length ? $$("[data-div]:checked").map((c) => c.dataset.div) : prev.corp_divisions,
    location_ids: $$("[data-loc]").length ? $$("[data-loc]:checked").map((c) => +c.dataset.loc) : prev.location_ids,
  };
  await saveSettings({ stock_sources });
}

// ---------------------------------------------------------------- JOBS EN COURS
async function loadJobs() {
  const out = $("#j-out");
  $("#j-refresh").onclick = loadJobs;
  if (!(G.status && G.status.characters.length)) { out.innerHTML = `<div class="empty">Connecte un personnage dans <a href="#personnages">Personnages & stock</a> pour voir ses jobs.</div>`; return; }
  out.innerHTML = `<div class="empty">Lecture des jobs…</div>`;
  try {
    const r = await api("/api/jobs");
    $("#j-info").textContent = `${r.jobs.length} jobs · ${r.jobs.filter((j) => j.remaining_s === 0).length} prêts à livrer`;
    out.innerHTML = r.errors.length ? `<div class="warnbox">${r.errors.map(esc).join("<br>")}</div>` : "";
    if (!r.jobs.length) { out.innerHTML += `<div class="empty">Aucun job en cours. Tous tes slots sont libres.</div>`; return; }
    const card = document.createElement("div");
    card.className = "card";
    card.append(table(r.jobs, [
      { k: "name", label: "Produit", fmt: (v, x) => withIco(x.type_id, esc(v)) },
      { k: "activity", label: "Activité" }, { k: "runs", label: "Runs", num: true },
      { k: "character", label: "Personnage", fmt: (v, x) => `<div class="with-ico"><img class="ico s" style="border-radius:50%" src="${IMG}/characters/${x.character_id}/portrait?size=32" alt="">${esc(v)}</div>` },
      { k: "facility_name", label: "Lieu" },
      { k: "remaining_s", label: "Reste", num: true, fmt: (v) => (v ? dur(v) : '<span class="pos">Terminé</span>') },
      { k: "end", label: "Fin", num: true, fmt: (v) => new Date(v).toLocaleString("fr-FR", { weekday: "short", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" }) },
    ], { sortKey: "remaining_s", desc: false }));
    out.append(card);
  } catch (e) { out.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; }
}

function scopeChips(scopes, missing = []) {
  return `<div class="scopes">${scopes.map((sc) => `<span class="scope ${missing.includes(sc) ? "missing" : ""}" data-copy="${esc(sc)}" title="Cliquer pour copier">${esc(sc)}</span>`).join("")}</div>`;
}
function bindCopy(root) {
  $$("[data-copy]", root).forEach((b) => b.onclick = () => copyText(b.dataset.copy, `Copié : ${b.dataset.copy.split("\n")[0]}`));
}
async function copyPrivateLogin() {
  try {
    const r = await api("/api/login_url");
    await copyText(r.url, "Lien copié. Ouvre une fenêtre de navigation privée (Ctrl+Maj+N ou Ctrl+Maj+P), colle-le, connecte-toi avec l'autre compte.");
  } catch (e) { toast(e.message, true); }
}

// ---------------------------------------------------------------- ASSISTANT DE DÉMARRAGE
const LANGS = { fr: "Français", en: "English", de: "Deutsch", ru: "Русский" };
const STRUCT_SIMPLE = { "Station NPC": "Station NPC", Raitaru: "Raitaru", Azbel: "Azbel", Sotiyo: "Sotiyo", Athanor: "Athanor (réactions)", Tatara: "Tatara (réactions)" };
async function renderWizard(soft) {
  const out = $("#w-out");
  if (!out || (soft && $("#v-demarrage").hidden)) return;
  if (soft && out.dataset.ready) {   // rafraîchissement doux : met à jour uniquement l'étape 1
    const st = G.status;
    const s1 = $("#w-s1");
    if (s1) { s1.classList.toggle("done", st.sde_loaded); $("#w-s1 p").textContent = st.sde_loaded ? "Données chargées." : (st.sde_status || "Téléchargement en cours…"); }
    return;
  }
  const st = G.status || await api("/api/status");
  const s = G.settings;
  const wz = s.wizard || {};
  const pre = st.preconfigured;
  out.dataset.ready = "1";
  out.innerHTML = `<div class="steps">
    <div class="wstep ${st.sde_loaded ? "done" : ""}" id="w-s1"><h2>Données du jeu</h2>
      <p>${st.sde_loaded ? "Données chargées." : esc(st.sde_status || "Téléchargement en cours (1 à 3 minutes, une seule fois)…")}</p></div>

    <div class="wstep ${wz.lang ? "done" : ""}"><h2>Langue des noms d'objets</h2>
      <p>Choisis la langue de ton client EVE : la liste d'achats copiée pour le Multibuy doit être dans la même langue que le jeu.</p>
      <div class="wrow"><select id="w-lang">${Object.entries(LANGS).map(([k, v]) => `<option value="${k}" ${k === s.lang ? "selected" : ""}>${v}</option>`).join("")}</select>
      <button class="primary" id="w-lang-ok">Valider</button></div></div>

    <div class="wstep ${wz.market ? "done" : ""}"><h2>Marché et taxes</h2>
      <p>Le marché sert à estimer ce que coûtent tes achats et ce que rapportent tes ventes. Ta taxe de vente s'affiche dans la fenêtre de vente du jeu (elle baisse avec la compétence Accounting).</p>
      <div class="wrow">
        <div class="field"><label>Marché de référence</label><select id="w-market">${Object.values(G.meta.hubs).map((h) => `<option value="${h.id}" ${h.id === s.price_market ? "selected" : ""}>${esc(h.short)}</option>`).join("")}</select></div>
        <div class="field"><label>Taxe de vente (%)</label><input id="w-tax" type="number" step="0.01" value="${s.sales_tax_pct}"></div>
        <div class="field"><label>Frais de courtage (%)</label><input id="w-broker" type="number" step="0.01" value="${s.broker_fee_pct}"></div>
        <button class="primary" id="w-market-ok">Valider</button></div></div>

    <div class="wstep ${st.structures ? "done" : ""}"><h2>Ta structure de production</h2>
      <p>${st.structures ? `${st.structures} structure(s) déclarée(s). Tu peux en ajouter d'autres ici ou dans l'onglet <a href="#structures">Structures</a> (rigs détaillés, plusieurs systèmes).` : "Où fabriques-tu principalement ? Les bonus de la structure et de ses rigs réduisent matériaux et temps."}</p>
      <div class="wrow">
        <div class="field"><label>Type</label><select id="w-kind">${Object.entries(STRUCT_SIMPLE).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
        <div class="field"><label>Système</label><input id="w-sys" placeholder="ex. 1DQ1-A, Jita"></div>
        <div class="field"><label>Rigs</label><select id="w-rigs"><option value="">Aucun</option><option value="t1">Rigs T1</option><option value="t2">Rigs T2</option></select></div>
        <div class="field"><label>Taxe (%)</label><input id="w-stax" type="number" step="0.1" value="0"></div>
        <button class="primary" id="w-struct-ok">Ajouter</button></div></div>

    <div class="wstep ${st.characters.length ? "done" : ""}"><h2>Connecter tes personnages</h2>
      ${pre ? `<p>Cet outil est préconfiguré${st.corp_name ? " par " + esc(st.corp_name) : ""} : il te suffit de te connecter avec ton compte EVE. Tes accès restent sur ton PC.</p>`
      : `<p>Facultatif, mais nécessaire pour compter ton stock, utiliser tes vrais blueprints et compétences, et lire un marché de citadelle. Une seule fois :</p>
      <ol>
        <li>Ouvre <a href="https://developers.eveonline.com/applications" target="_blank" rel="noopener">developers.eveonline.com/applications</a>, connecte-toi avec ton compte EVE, puis « Create application ».</li>
        <li>Nom : ce que tu veux (ex. « Cockpit »). Description : idem.</li>
        <li>Callback URL — copie-colle exactement :
          <div class="copyline"><code>${esc(st.callback_url)}</code><button class="small" data-copy="${esc(st.callback_url)}">Copier</button></div></li>
        <li>Permissions (scopes) : coche ces ${st.scopes.length} cases. Astuce : clique sur une capsule pour copier son nom, puis colle-le dans la recherche de la page EVE.
          ${scopeChips(st.scopes)}</li>
        <li>Valide, puis copie le <b>Client ID</b> affiché et colle-le ici. Le « Secret Key » n'est pas nécessaire.</li>
      </ol>
      <div class="wrow"><div class="field grow"><label>Client ID</label><input id="w-cid" value="${esc(s.esi_client_id)}" placeholder="ex. 3b6f1c…"></div><button id="w-cid-ok">Enregistrer</button></div>`}
      <div class="wrow" style="margin-top:12px">
        <a href="/login"><button class="primary" ${s.esi_client_id ? "" : "disabled"} id="w-login">Connecter un personnage</button></a>
        ${st.characters.map((c) => `<span class="with-ico">${portrait(c.character_id)}${esc(c.name)}</span>`).join("")}
      </div>
      <p class="hint">Plusieurs personnages sur le même compte : reclique sur « Connecter un personnage » et choisis-en un autre. Un personnage d'un <b>autre compte EVE</b> : <button class="small" id="w-private" ${s.esi_client_id ? "" : "disabled"}>Copier le lien pour une fenêtre privée</button></p></div>

    <div class="wstep ${s.setup_done ? "done" : ""}"><h2>C'est prêt</h2>
      <p>Commence par l'onglet <b>Production</b> avec un objet que tu connais, puis lance un scan dans <b>Opportunités</b>. L'onglet <b>Aide & lexique</b> explique chaque terme.</p>
      <button class="primary" id="w-done">Terminer et aller à la production</button></div>
  </div>`;
  const mark = async (k, extra = {}) => { await saveSettings({ ...extra, wizard: { ...(G.settings.wizard || {}), [k]: true } }); out.dataset.ready = ""; renderWizard(); };
  bindCopy(out);
  const pl = $("#w-private");
  if (pl) pl.onclick = copyPrivateLogin;
  $("#w-lang-ok").onclick = () => mark("lang", { lang: $("#w-lang").value });
  $("#w-market-ok").onclick = () => mark("market", { price_market: $("#w-market").value, sales_tax_pct: +$("#w-tax").value, broker_fee_pct: +$("#w-broker").value });
  $("#w-struct-ok").onclick = (ev) => busy(ev.target, async () => {
    const kind = $("#w-kind").value, sys = $("#w-sys").value.trim(), rigs = $("#w-rigs").value;
    if (!sys) return toast("Indique le système.", true);
    const info = await api("/api/system?name=" + encodeURIComponent(sys));
    const isReact = ["Athanor", "Tatara"].includes(kind);
    const st = { id: "s" + Date.now(), name: `${kind} ${info.name}`, kind, system_name: info.name, system_id: info.system_id,
      sec_status: info.security, security: info.band, indices: info.cost_indices, tax_pct: kind === "Station NPC" ? 0.25 : +$("#w-stax").value,
      enabled: true, activities: G.meta.structure_kinds[kind],
      rigs: rigs ? [{ applies: isReact ? "reactions" : "all", me: rigs === "t2" ? 2.4 : 2.0, te: rigs === "t2" ? 24 : 20 }] : [] };
    await saveSettings({ structures: [...G.settings.structures, st] });
    G.status = await api("/api/status");
    toast(`${st.name} ajoutée.`);
    out.dataset.ready = ""; renderWizard();
  });
  const cidOk = $("#w-cid-ok");
  if (cidOk) cidOk.onclick = async () => {
    const v = $("#w-cid").value.trim();
    if (!/^[0-9a-f]{20,40}$/i.test(v)) return toast("Ce Client ID ne ressemble pas à celui du site EVE (32 caractères hexadécimaux).", true);
    await saveSettings({ esi_client_id: v }); toast("Client ID enregistré."); G.status = await api("/api/status"); out.dataset.ready = ""; renderWizard();
  };
  $("#w-done").onclick = async () => { await saveSettings({ setup_done: true }); location.hash = "production"; };
}

// ---------------------------------------------------------------- AIDE
function renderHelp() {
  const out = $("#h-out");
  if (out.dataset.ready) return;
  out.dataset.ready = "1";
  const terms = [
    ["Blueprint (BPO / BPC)", "Le plan de fabrication. Un BPO (original) s'utilise à l'infini ; une BPC (copie) a un nombre de runs limité."],
    ["Run", "Une exécution du blueprint. Un run de Fusion Thruster produit 1 Fusion Thruster ; un run de réaction produit souvent des centaines d'unités."],
    ["ME (Material Efficiency)", HELP.me],
    ["TE (Time Efficiency)", HELP.te],
    ["Invention", "Transforme une copie de blueprint T1 en copie T2 avec des datacores. Ça peut échouer : l'outil compte le nombre moyen d'essais nécessaires."],
    ["Décrypteur", HELP.decryptor],
    ["Réaction", "Fabrication de matériaux avancés à partir de moon materials, uniquement dans une raffinerie (Athanor, Tatara) en lowsec, nullsec ou WH."],
    ["Rig", "Module installé sur une structure qui réduit matériaux (ME) et/ou temps (TE) pour une catégorie de produits. Son effet est multiplié en lowsec (×1,9) et en nullsec/WH (×2,1)."],
    ["Indice de coût du système", HELP.index],
    ["EIV (valeur estimée)", "Valeur de référence calculée par CCP pour fixer le prix d'un job. Elle ne dépend pas du marché où tu achètes."],
    ["Surtaxe SCC", "Taxe fixe ajoutée par CCP à chaque job, en pourcentage de l'EIV."],
    ["Sell order / buy order", "Acheter « sur les sell orders » = immédiat au prix le plus bas affiché. Poser un buy order = moins cher mais il faut attendre qu'un vendeur accepte."],
    ["ISK/jour réaliste", HELP.realistic],
    ["Multibuy", "Fenêtre du marché en jeu qui accepte une liste « nom quantité » collée et achète tout d'un coup."],
  ];
  const faq = [
    ["Les chiffres sont-ils fiables ?", "Les formules sont celles du jeu, mais trois réglages pèsent lourd : ta taxe de vente, les frais de courtage et la surtaxe SCC. Vérifie-les dans Réglages. Pour s'assurer que tout fonctionne, lance verifier.bat."],
    ["Pourquoi un objet est acheté alors que je voulais le fabriquer ?", "Soit il n'a pas de blueprint vendu sur le marché (objets de faction, BPC uniquement), soit « Optimiser la marge » a trouvé qu'il est moins cher à acheter. Clique sur le nœud dans l'arbre pour forcer la fabrication."],
    ["Pourquoi mon stock n'est pas déduit ?", "Il faut connecter le personnage, cliquer « Rafraîchir depuis le jeu », cocher ses hangars, puis cocher « Déduire mon stock » dans Production. Les hangars corpo demandent le rôle Director."],
    ["Mes accès EVE sont-ils en sécurité ?", "Les jetons de connexion sont stockés uniquement sur ton PC (dossier data). L'outil lit tes données et n'écrit qu'une chose : les fits que tu choisis d'envoyer dans ta liste de fittings. Il ne peut ni acheter, ni déplacer, ni lancer quoi que ce soit en jeu. Tu peux révoquer l'accès à tout moment sur community.eveonline.com, rubrique Third Party Applications."],
    ["Les prix sont-ils en temps réel ?", "Les prix de hub sont rafraîchis toutes les 15 minutes, les indices de coût toutes les heures, le volume vendu toutes les 12 heures."],
    ["Un nouveau patch EVE est sorti, que faire ?", "Rien : l'outil vérifie à chaque démarrage si CCP a publié de nouvelles données et les télécharge tout seul."],
    ["Comment ajouter un perso d'un autre compte EVE ?", "Personnages & stock → « Personnage d'un autre compte » : l'outil copie un lien. Ouvre une fenêtre de navigation privée, colle-le, connecte-toi avec l'autre compte. Le personnage apparaît ensuite dans l'outil."],
    ["Pourquoi un perso est marqué « permissions à mettre à jour » ?", "Une nouvelle version utilise des permissions EVE supplémentaires. Vérifie qu'elles sont cochées sur ton application EVE (developers.eveonline.com), puis clique « Reconnecter »."],
    ["L'alarme sonne-t-elle si je joue sur un autre client EVE ?", "Par défaut elle surveille la fenêtre EVE sur laquelle tu joues et la suit quand tu changes de client. Tu peux aussi choisir un personnage fixe ou toutes tes fenêtres (multi-compte)."],
    ["Pourquoi le pilote automatique ne suit pas mon itinéraire ?", "Le jeu ne prend ni les ponts de saut ni les trous de ver : « Destination en jeu » suit les portes. Suis la liste du trajet affichée dans l'outil."],
    ["Comment récupérer les fits de corporation ?", "EVE ne les donne pas aux outils tiers. En jeu, exporte-les en fichier depuis la gestion des fits (onglet Corporation), puis Doctrines & fits → « Importer des fits (fichier) ». Détails dans le README."],
    ["Les doctrines de la corpo ne s'affichent pas", "Elles arrivent par le fichier distribution.json ou par un lien publié par ta corpo. Sinon, demande le fichier d'export et utilise « Importer un fichier » dans Doctrines & fits."],
    ["Comment partager l'outil avec ma corpo ?", "Voir le README, rubrique « Partager avec ta corpo » : une seule application EVE pour tout le monde, chacun lance l'outil sur son PC."],
  ];
  out.innerHTML = `<div class="card"><h2>Lexique</h2><div class="body glossary">${terms.map(([t, d]) => `<dl><dt>${esc(t)}</dt><dd>${esc(d)}</dd></dl>`).join("")}</div></div>
    <div class="card"><h2>Questions fréquentes</h2><div class="body faq">${faq.map(([q, a]) => `<h3>${esc(q)}</h3><p>${esc(a)}</p>`).join("")}</div></div>`;
}

// ---------------------------------------------------------------- REGLAGES
function renderSettings() {
  const s = G.settings;
  const markets = { ...G.meta.hubs };
  (s.custom_markets || []).forEach((m) => (markets[m.id] = m));
  const mopt = (sel, empty) => (empty ? `<option value="">Aucun</option>` : "") + Object.values(markets).map((m) => `<option value="${esc(m.id)}" ${m.id === sel ? "selected" : ""}>${esc(m.short || m.name)}</option>`).join("");
  const num = (path, v, step = "any") => `<input type="number" step="${step}" data-p="${path}" value="${v}">`;
  $("#r-out").innerHTML = `
  <div class="settings-grid">
    <div class="card"><h2>Marchés et prix</h2><div class="body form">
      <label>Langue des noms d'objets</label><select data-p="lang">${Object.entries(LANGS).map(([k, v]) => `<option value="${k}" ${k === s.lang ? "selected" : ""}>${v}</option>`).join("")}</select>
      <label>Marché de référence</label><select data-p="price_market">${mopt(s.price_market)}</select>
      <label>Marché à comparer (liste d'achats)</label><select data-p="compare_market">${mopt(s.compare_market, true)}</select>
      <label>J'achète les matériaux…</label><select data-p="buy_price_mode"><option value="sell" ${s.buy_price_mode === "sell" ? "selected" : ""}>sur les ordres de vente (immédiat)</option><option value="buy" ${s.buy_price_mode === "buy" ? "selected" : ""}>en posant des buy orders</option></select>
      <label>Je revends le produit…</label><select data-p="sell_price_mode"><option value="sell" ${s.sell_price_mode === "sell" ? "selected" : ""}>en posant des sell orders</option><option value="buy" ${s.sell_price_mode === "buy" ? "selected" : ""}>directement aux buy orders</option></select>
      <label>Taxe de vente (%)</label>${num("sales_tax_pct", s.sales_tax_pct)}
      <label>Frais de courtage (%)</label>${num("broker_fee_pct", s.broker_fee_pct)}
      <label>Surtaxe SCC sur les jobs (%)</label>${num("scc_surcharge_pct", s.scc_surcharge_pct)}
      <label>Transport (ISK par m³)</label>${num("transport_isk_per_m3", s.transport_isk_per_m3)}
    </div></div>
    <div class="card"><h2>Compétences par défaut</h2><div class="body form">
      <label>Industry</label>${num("skills.industry", s.skills.industry, 1)}
      <label>Advanced Industry</label>${num("skills.advanced_industry", s.skills.advanced_industry, 1)}
      <label>Reactions</label>${num("skills.reactions", s.skills.reactions, 1)}
      <label>Sciences (invention)</label>${num("skills.science_default", s.skills.science_default, 1)}
      <label>Encryption Methods</label>${num("skills.encryption_default", s.skills.encryption_default, 1)}
      <p class="hint" style="grid-column:1/-1">Remplacées par tes vraies compétences pour l'invention dès qu'un personnage est connecté et rafraîchi.</p>
    </div></div>
    <div class="card"><h2>Blueprints et politique de fabrication</h2><div class="body form">
      <label>ME des BPO T1 par défaut</label>${num("default_bp_me", s.default_bp_me, 1)}
      <label>TE des BPO T1 par défaut</label>${num("default_bp_te", s.default_bp_te, 1)}
      <label>Fabriquer les composants</label><input type="checkbox" data-p="build_policy.build_components" ${s.build_policy.build_components ? "checked" : ""}>
      <label>Faire les réactions</label><input type="checkbox" data-p="build_policy.build_reactions" ${s.build_policy.build_reactions ? "checked" : ""}>
      <label>Inventer les T2</label><input type="checkbox" data-p="build_policy.invent_t2" ${s.build_policy.invent_t2 ? "checked" : ""}>
      <label>Décrypteur par défaut</label><select data-p="default_decryptor"><option value="">Aucun</option>${G.meta.decryptors.map((d) => `<option ${d === s.default_decryptor ? "selected" : ""}>${esc(d)}</option>`).join("")}</select>
    </div></div>
    <div class="card"><h2>Connexion EVE (ESI)</h2><div class="body form">
      <label>Client ID</label><input type="text" data-p="esi_client_id" value="${esc(s.esi_client_id)}">
      <label>Secret (facultatif)</label><input type="password" data-p="esi_client_secret" value="${esc(s.esi_client_secret)}">
      <label>Callback URL</label><input type="text" data-p="callback_url" value="${esc(s.callback_url)}">
      <label>User-Agent (contact)</label><input type="text" data-p="user_agent" value="${esc(s.user_agent)}">
      <p class="hint" style="grid-column:1/-1">L'URL de callback doit être identique à celle déclarée sur developers.eveonline.com.</p>
    </div></div>
    <div class="card"><h2>Marchés de citadelle</h2><div class="body" id="r-cm"></div></div>
    <div class="card"><h2>Données du jeu</h2><div class="body">
      <p>${G.status && G.status.sde_loaded ? "Build " + esc(G.status.sde_build) : "Non chargées"} · ${esc(G.status ? G.status.sde_status : "")}</p>
      <button id="r-sde">Forcer la mise à jour</button>
      <p class="hint">La mise à jour est vérifiée automatiquement à chaque démarrage (nouveaux items après un patch CCP).</p>
    </div></div>
  </div>
  <div class="row-actions" style="margin-top:6px"><button class="primary" id="r-save">Enregistrer les réglages</button></div>`;
  renderCustomMarkets();
  $("#r-sde").onclick = async () => { await api("/api/sde/update", { method: "POST" }); toast("Mise à jour lancée."); setTimeout(refreshStatus, 2000); };
  $("#r-save").onclick = (ev) => busy(ev.target, async () => {
    const upd = JSON.parse(JSON.stringify(G.settings));
    $$("[data-p]", $("#r-out")).forEach((inp) => {
      const path = inp.dataset.p.split(".");
      let o = upd;
      while (path.length > 1) o = o[path.shift()];
      o[path[0]] = inp.type === "checkbox" ? inp.checked : inp.type === "number" ? +inp.value : inp.value;
    });
    G.settings = upd;
    await api("/api/settings", { method: "POST", body: upd });
    toast("Réglages enregistrés. Relance le calcul pour les appliquer.");
    refreshStatus();
  });
}
function renderCustomMarkets() {
  const s = G.settings;
  const chars = (G.status && G.status.characters) || [];
  const box = $("#r-cm");
  box.innerHTML = `${(s.custom_markets || []).map((m, i) => `<div style="display:flex;justify-content:space-between;padding:4px 0"><span>${esc(m.short)} <span class="muted">structure ${m.structure_id}</span></span><button class="small danger" data-i="${i}">Retirer</button></div>`).join("") || '<p class="muted">Aucun.</p>'}
    <div class="form" style="margin-top:10px">
      <label>Nom court</label><input type="text" id="cm-name" placeholder="C-N4OD">
      <label>ID de la structure</label><input type="text" id="cm-id" placeholder="1035466617946">
      <label>Personnage ayant accès</label><select id="cm-char">${chars.map((c) => `<option value="${c.character_id}">${esc(c.name)}</option>`).join("")}</select>
    </div>
    <button class="small" id="cm-add" style="margin-top:10px">Ajouter le marché</button>
    <p class="hint">L'ID de structure s'obtient en glissant la structure dans le chat du jeu puis en survolant le lien, ou via un outil comme EVE Ref.</p>`;
  $$("[data-i]", box).forEach((b) => b.onclick = async () => { s.custom_markets.splice(+b.dataset.i, 1); await saveSettings({ custom_markets: s.custom_markets }); renderSettings(); });
  $("#cm-add").onclick = async () => {
    const name = $("#cm-name").value.trim(), sid = +$("#cm-id").value.trim(), cid = +$("#cm-char").value;
    if (!name || !sid) return toast("Nom et ID de structure requis.", true);
    if (!cid) return toast("Connecte d'abord un personnage qui a accès au marché.", true);
    s.custom_markets.push({ id: "cm" + sid, name, short: name, kind: "structure", structure_id: sid, character_id: cid });
    await saveSettings({ custom_markets: s.custom_markets });
    renderSettings();
  };
}

// ---------------------------------------------------------------- COMMENT ÇA MARCHE
function renderGuide() {
  const out = $("#g-out");
  const corp = (G.status && G.status.corp_name) || "";
  const item = (href, tid, kind, title, text) => `<div class="guide-item"><img src="${IMG}/types/${tid}/${kind}?size=64" alt="" loading="lazy" onerror="this.style.visibility='hidden'"><a href="#${href}"><b>${title}</b><span>${text}</span></a></div>`;
  out.innerHTML = `
    <div class="guide-hero">
      <h1>Cockpit, ton copilote EVE</h1>
      <p>Cockpit réunit en un seul endroit ce qu'il faut à un pilote${corp ? " de " + esc(corp) : ""} pour être prêt au combat et financer sa guerre : les doctrines et fits de la corpo, de l'intel sur les pilotes d'en face, et un planificateur industriel pour gagner des ISK.</p>
      <p>Il lit les infos de tes personnages (compétences, hangars, fits) avec ton autorisation, et les prix du marché. Il ne joue jamais à ta place.</p>
    </div>
    <div class="guide-cols">
      <div class="guide-col pvp"><h2>PvP</h2><p>Être prêt pour les fleets et savoir à qui tu as affaire.</p>
        ${item("doctrines", 626, "render", "Doctrines & fits", "Tous les fits de la corpo au même endroit. Tu vois d'un coup d'œil quels persos peuvent piloter quoi, et combien de temps d'entraînement il manque.")}
        ${item("doctrines", 2048, "icon", "Envoi des fits en jeu", "Un clic et les fits d'une doctrine apparaissent dans ta fenêtre Fitting, sur le perso de ton choix.")}
        ${item("doctrines", 2185, "icon", "Commande de flotte", "« 10 Vexor + 2 logi » : liste d'achats prête pour le Multibuy, moins ce que tu as déjà en hangar.")}
        ${item("carte", 638, "render", "Carte de la galaxie", "Toutes les portes, ponts de saut, Thera/Turnur, kills de la dernière heure, souveraineté et position de tes persos ; itinéraires et liens Dotlan.")}
        ${item("alarme", 12198, "icon", "Alarme local & intel", "Un bip quand un neutre, un orange ou un rouge arrive en local, ou quand ton canal d'intel annonce un système que tu surveilles.")}
        ${item("dscan", 638, "render", "Analyse D-scan", "Colle ton D-scan : composition de la flotte en face, valeur, et alertes bulles, cynos, capitaux, logi.")}
      </div>
      <div class="guide-col indy"><h2>Industrie</h2><p>Gagner des ISK en fabriquant intelligemment.</p>
        ${item("production", 34, "icon", "Production", "Choisis ce que tu veux fabriquer : l'outil déroule tout l'arbre, choisit la meilleure structure, et sort la liste d'achats.")}
        ${item("invention", 20172, "icon", "Invention T2", "Le meilleur décrypteur pour chaque objet T2, et le vrai coût par unité.")}
        ${item("opportunites", 44992, "icon", "Opportunités", "Ce qui rapporte le plus d'ISK par jour en ce moment, en tenant compte de ce qui se vend réellement.")}
        ${item("arbitrage", 648, "render", "Arbitrage hubs", "Acheter à Jita, revendre à Amarr (ou l'inverse) : transport et taxes inclus.")}
        ${item("pi", 2867, "icon", "Planétaire (PI)", "Les planètes et ressources autour de toi, ce que tu peux produire de P1 à P4, et les meilleurs systèmes pour chaque produit.")}
        ${item("jobs", 587, "render", "Mes jobs en cours", "Tous les jobs de tous tes persos, du plus proche de la fin au plus lointain.")}
      </div>
    </div>
    <div class="guide-cols">
      <div class="guide-col"><h2>Par où commencer</h2>
        <ol class="hint" style="font-size:15px;color:#c4cfdb;padding-left:20px">
          <li><b>Démarrage</b> : 5 minutes de configuration guidée (langue, marché, structure).</li>
          <li><b>Connecte tes personnages</b>, autant que tu veux, sur plusieurs comptes.</li>
          <li><b>Personnages & stock → Rafraîchir depuis le jeu</b> pour charger compétences et hangars.</li>
          <li>Ouvre <b>Doctrines & fits</b> pour voir ce que tu peux piloter, règle l'<b>Alarme local</b> avant de partir en roam, ou ouvre <b>Production</b> pour fabriquer.</li>
        </ol>
        <button class="primary" onclick="location.hash='demarrage'">Commencer la configuration</button>
      </div>
      <div class="guide-col"><h2>Tes données</h2>
        <p style="color:#c4cfdb">Tout reste sur ton PC, dans le dossier <b>data</b> à côté de l'application. Les accès EVE servent à <b>lire</b> tes compétences, hangars, blueprints, jobs et fits, et à <b>enregistrer des fits</b> dans ta liste en jeu quand tu le demandes. Rien d'autre : l'outil ne peut ni acheter, ni déplacer, ni lancer quoi que ce soit.</p>
        <p style="color:#c4cfdb">Tu peux retirer l'accès à tout moment sur le site EVE, rubrique Third Party Applications.</p>
        <p class="muted">Version ${esc((G.status && G.status.version) || "")} · <a href="#patch">notes de patch</a></p>
      </div>
    </div>`;
}

// ---------------------------------------------------------------- NOTES DE PATCH
async function renderPatch() {
  const r = await api("/api/version");
  $("#n-out").innerHTML = (r.update ? `<div class="infobox"><span>Le patch ${esc(r.update.version)} est disponible.</span>${r.update.download_url ? `<a href="${esc(r.update.download_url)}" target="_blank" rel="noopener"><button class="small primary">Télécharger</button></a>` : ""}</div>` : "")
    + r.changelog.map((p, i) => `<article class="patch ${i === 0 ? "current" : ""}">
      <h2>Patch ${esc(p.version)} — ${esc(p.title)} ${i === 0 ? '<span class="tag">version installée</span>' : ""}</h2>
      <div class="meta">${new Date(p.date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })} · ${esc(p.highlights)}</div>
      ${p.added.length ? `<h3>Nouveautés</h3><ul>${p.added.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${p.changed.length ? `<h3>Améliorations</h3><ul>${p.changed.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    </article>`).join("");
  if (G.settings.last_seen_version !== r.version) { await saveSettings({ last_seen_version: r.version }); renderBanner(); }
}
function renderBanner() {
  const st = G.status;
  if (!st) return;
  let html = "";
  if (st.update) html += `<div class="infobox"><span>Le patch ${esc(st.update.version)} est disponible${st.update.highlights ? " : " + esc(st.update.highlights) : ""}.</span>${st.update.download_url ? `<a href="${esc(st.update.download_url)}" target="_blank" rel="noopener"><button class="small primary">Télécharger</button></a>` : ""}</div>`;
  const fresh = G.settings.setup_done && G.settings.last_seen_version !== st.version;
  if (fresh) html += `<div class="infobox"><span>Patch ${esc(st.version)} installé. Découvre ce qui a changé.</span><span><button class="small primary" id="bn-see">Voir les nouveautés</button> <button class="small" id="bn-close">Masquer</button></span></div>`;
  const reco = (st.characters || []).filter((c) => c.missing_scopes && c.missing_scopes.length);
  if (reco.length && st.setup_done) html += `<div class="warnbox"><span>${reco.map((c) => esc(c.name)).join(", ")} : reconnexion nécessaire pour activer les nouvelles fonctions (fits, file de compétences).</span><a href="#personnages"><button class="small">Voir</button></a></div>`;
  $("#banner").innerHTML = html;
  $("#patch-badge").hidden = !fresh;
  const see = $("#bn-see");
  if (see) see.onclick = () => (location.hash = "patch");
  const cl = $("#bn-close");
  if (cl) cl.onclick = async () => { await saveSettings({ last_seen_version: st.version }); renderBanner(); };
}

// ---------------------------------------------------------------- DOCTRINES
const D = { data: null, current: null, tab: "fits", fit: null, chars: [] };
const shipImg = (tid, size = 64, extra = "ship") => `<img class="${extra}" src="${IMG}/types/${tid}/render?size=${size}" alt="" loading="lazy" onerror="this.src='${IMG}/types/${tid}/icon?size=64'">`;
const charImg = (cid, size = 32) => `${IMG}/characters/${cid}/portrait?size=${size}`;
async function copyText(txt, msg) {
  try { await navigator.clipboard.writeText(txt); toast(msg || "Copié."); } catch { toast("Copie bloquée par le navigateur.", true); }
}
async function loadDoctrines(keepFit) {
  D.data = await api("/api/doctrines");
  D.chars = (G.status && G.status.characters) || [];
  if (!D.data.doctrines.find((d) => d.id === D.current)) D.current = D.data.doctrines[0] && D.data.doctrines[0].id;
  if (!keepFit) D.fit = null;
  $("#d-corp").hidden = !D.data.corp_url;
  $("#d-info").textContent = D.data.corp_fetched ? `Doctrines corpo à jour du ${new Date(D.data.corp_fetched * 1000).toLocaleString("fr-FR")}` : "";
  renderDocList();
  D.fit ? renderFit(D.fit) : renderDoc();
}
function renderDocList() {
  const l = $("#d-list");
  if (!D.data.doctrines.length) { l.innerHTML = `<p class="muted">Aucune doctrine. Crée la première, ou importe le fichier fourni par ta corpo.</p>`; return; }
  l.innerHTML = D.data.doctrines.map((d) => `<button class="doc-item ${d.id === D.current ? "active" : ""}" data-id="${esc(d.id)}">
    <b>${esc(d.name)} ${d.official ? '<span class="tag corp">Corpo</span>' : ""}</b><span>${d.fits.length} fit${d.fits.length > 1 ? "s" : ""}</span></button>`).join("");
  $$(".doc-item", l).forEach((b) => b.onclick = () => { D.current = b.dataset.id; D.fit = null; D.tab = "fits"; renderDocList(); renderDoc(); });
}
function pilotDots(pilots) {
  return `<div class="pilots-row">${pilots.map((p) => {
    const c = p.unknown ? "" : p.can_fly ? "ok" : p.only_queued ? "queued" : "ko";
    const t = p.unknown ? `${p.name} : compétences non chargées` : p.can_fly ? `${p.name} peut le piloter` : `${p.name} : ${p.missing_count} compétence(s) manquante(s), ${dur(p.train_time_s) || "en file"}`;
    return `<span class="pp ${c}" title="${esc(t)}"><img src="${charImg(p.character_id)}" alt="${esc(p.name)}"></span>`;
  }).join("")}</div>`;
}
function renderDoc() {
  const m = $("#d-main");
  const d = D.data.doctrines.find((x) => x.id === D.current);
  if (!d) { m.innerHTML = `<div class="empty">Crée une doctrine avec « Nouvelle doctrine », puis colle les fits de la corpo.</div>`; return; }
  const ro = d.official;
  m.innerHTML = `
    <div class="card"><div class="body">
      <h2 style="margin:0;font-size:26px">${esc(d.name)} ${ro ? '<span class="tag corp">Doctrine officielle</span>' : ""}</h2>
      ${d.description ? `<p style="margin:4px 0 0;color:#c4cfdb">${esc(d.description)}</p>` : ""}
      <div class="actions">
        ${ro ? "" : '<button class="primary" id="dd-add">Ajouter des fits</button><button id="dd-game">Importer depuis le jeu</button>'}
        <button id="dd-push">Envoyer tous les fits en jeu</button>
        <button id="dd-report">Rapport pour Discord</button>
        <button id="dd-dup">Dupliquer</button>
        ${ro ? "" : '<button id="dd-edit">Renommer</button><button class="danger" id="dd-del">Supprimer</button>'}
      </div>
      <div id="dd-panel"></div>
    </div></div>
    <div class="tabs">${[["fits", "Fits"], ["ready", "Qui peut voler quoi"], ["order", "Commande de flotte"]].map(([k, v]) => `<button data-t="${k}" class="${D.tab === k ? "active" : ""}">${v}</button>`).join("")}</div>
    <div id="dd-tab"></div>`;
  $$(".tabs button", m).forEach((b) => b.onclick = () => { D.tab = b.dataset.t; renderDoc(); });
  const on = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
  on("#dd-add", () => panelAddFits(d));
  on("#dd-game", () => panelGameFits(d));
  on("#dd-push", () => panelPush(d));
  on("#dd-report", async () => { const r = await api(`/api/doctrines/${d.id}/report`); copyText(r.text, "Rapport copié : colle-le sur Discord."); });
  on("#dd-dup", async () => { const r = await api(`/api/doctrines/${d.id}/duplicate`, { method: "POST" }); D.current = r.id; toast("Copie créée : tu peux la modifier."); loadDoctrines(); });
  on("#dd-edit", async () => {
    const name = prompt("Nom de la doctrine", d.name); if (name == null) return;
    const desc = prompt("Description (facultatif)", d.description || ""); 
    await api("/api/doctrines", { method: "POST", body: { id: d.id, name, description: desc || "" } }); loadDoctrines();
  });
  on("#dd-del", async () => { if (!confirm(`Supprimer la doctrine « ${d.name} » et ses ${d.fits.length} fits ?`)) return; await api("/api/doctrines/" + d.id, { method: "DELETE" }); loadDoctrines(); });
  if (D.tab === "fits") tabFits(d); else if (D.tab === "ready") tabReady(d); else tabOrder(d);
}
function tabFits(d) {
  const t = $("#dd-tab");
  if (!d.fits.length) { t.innerHTML = `<div class="empty">Aucun fit. ${d.official ? "" : "Clique « Ajouter des fits » et colle-les au format EFT (en jeu : fenêtre Fitting → Copier dans le presse-papiers)."}</div>`; return; }
  if (d.fits.length && !d.fits[0].skills_known) t.insertAdjacentHTML("beforeend", `<div class="warnbox">Les compétences requises ne sont pas encore connues : mets à jour les données du jeu (Réglages).</div>`);
  const roles = D.data.roles.filter((r) => d.fits.some((f) => f.role === r)).concat([...new Set(d.fits.map((f) => f.role))].filter((r) => !D.data.roles.includes(r)));
  t.innerHTML += roles.map((r) => `<div class="role-title">${esc(r)}</div><div class="fit-grid">${d.fits.filter((f) => f.role === r).map((f) => `
    <button class="fit-card" data-id="${f.id}">${shipImg(f.ship_type_id)}<div><b>${esc(f.name)}</b><span class="sub">${esc(f.ship_name)} · ${esc(f.ship_group)}</span>
    ${f.pilots.length ? pilotDots(f.pilots) : '<div class="sub">Connecte un personnage pour voir qui peut le piloter.</div>'}</div></button>`).join("")}</div>`).join("");
  $$(".fit-card", t).forEach((c) => c.onclick = () => { D.fit = c.dataset.id; renderFit(D.fit); });
}
function tabReady(d) {
  const t = $("#dd-tab");
  const pilots = D.chars;
  if (!pilots.length) { t.innerHTML = `<div class="empty">Connecte tes personnages (Personnages & stock) puis « Rafraîchir depuis le jeu ».</div>`; return; }
  t.innerHTML = `<div class="card"><div class="tscroll"><table class="readiness"><thead><tr><th>Fit</th>${pilots.map((p) => `<th style="text-align:center"><img class="ico s" style="border-radius:50%" src="${charImg(p.character_id)}" alt="">${esc(p.name)}</th>`).join("")}</tr></thead><tbody>
    ${d.fits.map((f) => `<tr class="click" data-id="${f.id}"><td>${withIco(f.ship_type_id, `${esc(f.name)}<div class="muted">${esc(f.ship_name)} · ${esc(f.role)}</div>`)}</td>${pilots.map((p) => {
      const c = f.pilots.find((x) => x.character_id === p.character_id) || { unknown: true };
      if (c.unknown) return `<td class="muted" style="text-align:center">?</td>`;
      if (c.can_fly) return `<td class="ok">✓</td>`;
      if (c.only_queued) return `<td class="q">en file</td>`;
      return `<td class="ko">${dur(c.train_time_s)}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div></div>
    <p class="hint">✓ peut piloter · durée = temps d'entraînement restant (compétences déjà en file non comptées) · « ? » = clique « Rafraîchir depuis le jeu » dans Personnages & stock.</p>`;
  $$("tr[data-id]", t).forEach((tr) => tr.onclick = () => { D.fit = tr.dataset.id; renderFit(D.fit); });
}
function tabOrder(d) {
  const t = $("#dd-tab");
  const q = store.get("order." + d.id, {});
  t.innerHTML = `<div class="card"><h2>Combien d'exemplaires de chaque fit ?</h2><div class="body">
    <div class="fit-grid">${d.fits.map((f) => `<label class="fit-card" style="cursor:default">${shipImg(f.ship_type_id)}<div><b>${esc(f.name)}</b><span class="sub">${esc(f.ship_name)} · ${esc(f.role)}</span>
      <div style="margin-top:6px"><input type="number" min="0" value="${q[f.id] || 0}" data-q="${f.id}" style="width:90px"></div></div></label>`).join("")}</div>
    <div class="actions"><label class="check" style="padding:0"><input type="checkbox" id="or-stock" ${store.get("useStock", false) ? "checked" : ""}> Déduire mon stock</label>
    <button class="primary" id="or-run">Calculer la commande</button></div></div></div><div id="or-out"></div>`;
  $("#or-run").onclick = (ev) => busy(ev.target, async () => {
    const quantities = {};
    $$("[data-q]", t).forEach((i) => (quantities[i.dataset.q] = +i.value || 0));
    store.set("order." + d.id, quantities);
    const r = await api(`/api/doctrines/${d.id}/order`, { method: "POST", body: { quantities, use_stock: $("#or-stock").checked } });
    const out = $("#or-out");
    out.innerHTML = `<div class="kpis"><div class="kpi"><span>Total à ${esc(r.market)}</span><b>${isk(r.total)}</b></div>
      ${r.compare_market ? `<div class="kpi"><span>En prenant le moins cher (${esc(r.market)} / ${esc(r.compare_market)})</span><b>${isk(r.total_best)}</b></div>` : ""}
      <div class="kpi"><span>Objets différents</span><b>${r.rows.length}</b></div></div>
      ${$("#or-stock").checked && !r.stock_loaded ? `<div class="warnbox">Aucun stock chargé : Personnages & stock → Rafraîchir depuis le jeu.</div>` : ""}
      <div class="card"><h2>Liste d'achats <span><button class="small" id="or-copy">Copier pour le Multibuy</button> <button class="small primary" id="or-build">Fabriquer plutôt (vers Production)</button></span></h2><div id="or-table"></div></div>`;
    const cols = [
      { k: "name", label: "Objet", fmt: (v, x) => withIco(x.type_id, esc(v) + (x.buildable ? ' <span class="tag">fabricable</span>' : ""), "s") },
      { k: "needed", label: "Besoin", num: true, fmt: n0 },
      { k: "in_stock", label: "En stock", num: true, fmt: (v) => (v ? n0(v) : "—") },
      { k: "to_buy", label: "À acheter", num: true, fmt: n0 },
      { k: "unit_price", label: `Prix ${r.market}`, num: true, fmt: isk, cls: (x) => (x.compare_price && x.unit_price && x.unit_price <= x.compare_price ? "cheaper" : "") },
    ];
    if (r.compare_market) cols.push({ k: "compare_price", label: `Prix ${r.compare_market}`, num: true, fmt: isk, cls: (x) => (x.compare_price && (!x.unit_price || x.compare_price < x.unit_price) ? "cheaper" : "") });
    cols.push({ k: "total", label: "Total", num: true, fmt: isk });
    $("#or-table").append(table(r.rows, cols, { sortKey: "total" }));
    $("#or-copy").onclick = () => copyText(r.multibuy, "Copié : Marché → Multibuy → Ctrl+V.");
    $("#or-build").onclick = () => {
      const items = r.rows.filter((x) => x.buildable && x.to_buy > 0);
      if (!items.length) return toast("Rien de fabricable dans cette commande.", true);
      G.cart = items.map((x) => ({ type_id: x.type_id, name: x.name, quantity: x.to_buy }));
      store.set("cart", G.cart); renderCart(); location.hash = "production"; runPlan();
    };
  });
}
const IMP = { file: null, content: "" };
function openImportPanel() {
  const p = $("#d-importpanel");
  const own = (D.data ? D.data.doctrines : []).filter((d) => !d.official);
  const cur = own.find((d) => d.id === D.current);
  p.innerHTML = `<div class="card"><h2>Importer des fits <button class="small" id="im-close">Fermer</button></h2><div class="body">
    <div class="dropzone" id="im-drop">Glisse ici le fichier (ou clique pour le choisir)<br><small>XML exporté du jeu ou de Pyfa · texte EFT (.txt) · export de doctrines (.json)</small></div>
    <input type="file" id="im-file" accept=".xml,.txt,.json,.cfg,.eft,text/xml,application/json,text/plain" hidden>
    <p class="hint">Tu peux aussi coller directement le contenu (plusieurs fits EFT à la suite, ou le XML) :</p>
    <textarea id="im-text" rows="4" placeholder="[Vexor, Vexor DPS]&#10;Drone Damage Amplifier II&#10;…"></textarea>
    <div class="radio-list">
      <label><input type="radio" name="im-mode" value="prefix" checked><span><b>Une doctrine par préfixe</b><small>« [Vexor] DPS », « Vexor - Logi » → doctrine « Vexor » avec les fits « DPS » et « Logi ». Les fits sans préfixe vont dans « Autres ».</small></span></label>
      <label><input type="radio" name="im-mode" value="new"><span><b>Tout dans une nouvelle doctrine</b> <input id="im-name" placeholder="nom (par défaut : nom du fichier)" style="margin-left:6px"></span></label>
      <label><input type="radio" name="im-mode" value="existing" ${own.length ? "" : "disabled"}><span><b>Ajouter à une de mes doctrines</b>
        <select id="im-doc" style="margin-left:6px" ${own.length ? "" : "disabled"}>${own.map((d) => `<option value="${esc(d.id)}" ${cur && cur.id === d.id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select></span></label>
    </div>
    <label class="check" style="padding:0"><input type="checkbox" id="im-roles" checked> Deviner le rôle (nom du fit, sinon type de vaisseau : logi, tackle, ewar…)</label>
    <div class="actions"><button id="im-preview">Aperçu</button><button class="primary" id="im-go" disabled>Importer</button><span class="muted" id="im-info"></span></div>
    <div id="im-out"></div></div></div>`;
  IMP.file = null; IMP.content = "";
  $("#im-close").onclick = () => (p.innerHTML = "");
  const drop = $("#im-drop"), inp = $("#im-file");
  drop.onclick = () => inp.click();
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); e.stopPropagation(); drop.classList.remove("over"); $("#v-doctrines").classList.remove("dragging"); if (e.dataTransfer.files[0]) loadImportFile(e.dataTransfer.files[0]); };
  inp.onchange = () => inp.files[0] && loadImportFile(inp.files[0]);
  $("#im-text").oninput = () => { IMP.file = null; IMP.content = $("#im-text").value; $("#im-go").disabled = true; $("#im-info").textContent = ""; };
  $$("input[name=im-mode], #im-roles, #im-doc, #im-name", p).forEach((el) => (el.onchange = () => { $("#im-go").disabled = true; if (IMP.content) importPreview(); }));
  $("#im-preview").onclick = (ev) => busy(ev.target, importPreview);
  $("#im-go").onclick = (ev) => busy(ev.target, importRun);
  p.scrollIntoView({ behavior: "smooth", block: "start" });
}
async function loadImportFile(f) {
  if (f.size > 20 * 1024 * 1024) return toast("Fichier trop gros (20 Mo maximum).", true);
  IMP.file = f.name;
  IMP.content = await f.text();
  $("#im-text").value = "";
  $("#im-drop").innerHTML = `<b>${esc(f.name)}</b> (${n0(f.size / 1024)} Ko)<br><small>clique pour choisir un autre fichier</small>`;
  await importPreview();
}
function importBody(dry) {
  const mode = ($("input[name=im-mode]:checked") || {}).value || "prefix";
  return { filename: IMP.file || "fits collés.txt", content: IMP.content || $("#im-text").value, mode,
    doctrine_id: $("#im-doc") ? $("#im-doc").value : null, doctrine_name: $("#im-name").value.trim(),
    auto_roles: $("#im-roles").checked, dry_run: dry };
}
async function importPreview() {
  const body = importBody(true);
  if (!body.content.trim()) return toast("Choisis un fichier ou colle des fits.", true);
  IMP.content = body.content;
  let r;
  try { r = await api("/api/doctrines/import_file", { method: "POST", body }); }
  catch (e) { $("#im-out").innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; $("#im-go").disabled = true; return; }
  const fmt = { xml: "XML (jeu / Pyfa)", eft: "texte EFT", doctrines: "export de doctrines" }[r.format] || r.format;
  const unknown = r.preview.filter((x) => x.unknown && x.unknown.length);
  $("#im-info").textContent = `Format ${fmt} · ${r.added ?? r.preview.length} fit(s) à importer` + (r.skipped ? ` · ${r.skipped} doublon(s) ignoré(s)` : "") + (r.errors ? ` · ${r.errors} en erreur` : "");
  $("#im-out").innerHTML = `
    ${unknown.length ? `<div class="warnbox">Lignes non reconnues dans ${unknown.length} fit(s) : elles seront ignorées. Vérifie l'orthographe ou mets à jour les données du jeu.<br>${unknown.slice(0, 6).map((x) => `<b>${esc(x.name)}</b> : ${x.unknown.slice(0, 4).map(esc).join(", ")}`).join("<br>")}</div>` : ""}
    <div class="tscroll" style="max-height:420px"><table><thead><tr><th>Doctrine</th><th>Fit</th><th>Vaisseau</th><th>Rôle</th><th class="num">Modules</th><th>État</th></tr></thead><tbody>
    ${r.preview.map((x) => `<tr class="${x.duplicate ? "dup" : x.error ? "err" : ""}"><td>${esc(x.doctrine)}</td><td>${esc(x.name)}</td>
      <td>${x.ship_type_id ? withIco(x.ship_type_id, esc(x.ship_name), "s") : esc(x.ship_name)}</td><td>${esc(x.role)}</td><td class="num">${x.items}</td>
      <td>${x.error ? esc(x.error) : x.duplicate ? "déjà présent" : x.unknown && x.unknown.length ? `${x.unknown.length} ligne(s) ignorée(s)` : '<span class="pos">OK</span>'}</td></tr>`).join("")}
    </tbody></table></div>`;
  $("#im-go").disabled = !((r.added ?? r.preview.length) > 0);
}
async function importRun() {
  const r = await api("/api/doctrines/import_file", { method: "POST", body: importBody(false) });
  const n = r.added ?? r.imported;
  toast(`${n} fit(s) importé(s)` + (r.doctrines ? ` dans : ${r.doctrines.join(", ")}` : "") + (r.skipped ? ` · ${r.skipped} doublon(s) ignoré(s)` : ""));
  $("#d-importpanel").innerHTML = "";
  if (r.doctrine_ids && r.doctrine_ids.length) D.current = r.doctrine_ids[0];
  D.tab = "fits";
  loadDoctrines();
}
function charSelect(id) {
  return `<select id="${id}">${D.chars.map((c) => `<option value="${c.character_id}">${esc(c.name)}</option>`).join("")}</select>`;
}
function panelAddFits(d) {
  $("#dd-panel").innerHTML = `<div class="panel-form" style="margin-top:12px">
    <div class="field"><label>Fits au format EFT (un ou plusieurs à la suite). En jeu : fenêtre Fitting → bouton « Copier dans le presse-papiers ». Pyfa : Ctrl+C sur le fit.</label>
    <textarea id="af-eft" placeholder="[Vexor, Vexor DPS]&#10;Drone Damage Amplifier II&#10;..."></textarea></div>
    <div class="wrow" style="margin-top:10px">
      <div class="field"><label>Rôle</label><select id="af-role">${D.data.roles.map((r) => `<option>${esc(r)}</option>`).join("")}</select></div>
      <div class="field grow"><label>Note (facultatif)</label><input id="af-notes" placeholder="ex. garder le scram, munitions Void en cargo"></div>
      <button class="primary" id="af-ok">Ajouter</button><button id="af-cancel">Annuler</button></div></div>`;
  $("#af-cancel").onclick = () => ($("#dd-panel").innerHTML = "");
  $("#af-ok").onclick = (ev) => busy(ev.target, async () => {
    const r = await api(`/api/doctrines/${d.id}/fits`, { method: "POST", body: { eft: $("#af-eft").value, role: $("#af-role").value, notes: $("#af-notes").value } });
    toast(`${r.added.length} fit(s) ajouté(s)` + (r.warnings.length ? ` — ${r.warnings.length} ligne(s) non reconnue(s)` : ""), !!r.warnings.length);
    if (r.warnings.length) alert("Lignes non reconnues (vérifie l'orthographe ou mets à jour les données du jeu) :\n\n" + r.warnings.join("\n"));
    loadDoctrines();
  });
}
async function panelGameFits(d) {
  const p = $("#dd-panel");
  if (!D.chars.length) { toast("Connecte d'abord un personnage.", true); return; }
  p.innerHTML = `<div class="panel-form" style="margin-top:12px"><div class="wrow"><div class="field"><label>Personnage</label>${charSelect("gf-char")}</div><button id="gf-load">Lire ses fits enregistrés</button></div><div id="gf-list"></div></div>`;
  $("#gf-load").onclick = (ev) => busy(ev.target, async () => {
    const cid = +$("#gf-char").value;
    const fl = await api(`/api/characters/${cid}/fittings`);
    $("#gf-list").innerHTML = fl.length ? `<div style="max-height:320px;overflow:auto;margin:10px 0">${fl.map((f) => `<label class="check" style="padding:3px 0"><input type="checkbox" value="${f.fitting_id}">${ico(f.ship_type_id, "s")}${esc(f.ship_name)} — ${esc(f.name)}</label>`).join("")}</div>
      <div class="wrow"><div class="field"><label>Rôle</label><select id="gf-role">${D.data.roles.map((r) => `<option>${esc(r)}</option>`).join("")}</select></div><button class="primary" id="gf-ok">Importer la sélection</button></div>` : '<p class="muted">Aucun fit enregistré sur ce personnage.</p>';
    const ok = $("#gf-ok");
    if (ok) ok.onclick = () => busy(ok, async () => {
      const ids = $$("#gf-list input:checked").map((i) => +i.value);
      if (!ids.length) return toast("Coche au moins un fit.", true);
      const r = await api(`/api/doctrines/${d.id}/fits_esi`, { method: "POST", body: { character_id: cid, fitting_ids: ids, role: $("#gf-role").value } });
      toast(`${r.added.length} fit(s) importé(s).`); loadDoctrines();
    });
  });
}
function panelPush(d) {
  if (!D.chars.length) { toast("Connecte d'abord un personnage.", true); return; }
  $("#dd-panel").innerHTML = `<div class="panel-form" style="margin-top:12px"><p style="margin:0 0 8px">Les ${d.fits.length} fits de « ${esc(d.name)} » seront ajoutés à la liste de fittings du personnage choisi (fenêtre Fitting → Fits personnels). EVE limite le nombre de fits enregistrés par personnage.</p>
    <div class="wrow"><div class="field"><label>Personnage</label>${charSelect("pa-char")}</div><button class="primary" id="pa-ok">Envoyer</button><button id="pa-cancel">Annuler</button></div></div>`;
  $("#pa-cancel").onclick = () => ($("#dd-panel").innerHTML = "");
  $("#pa-ok").onclick = (ev) => busy(ev.target, async () => {
    const r = await api(`/api/doctrines/${d.id}/push_all`, { method: "POST", body: { character_id: +$("#pa-char").value } });
    toast(`${r.pushed} fit(s) envoyé(s) en jeu.` + (r.errors.length ? " " + r.errors[0] : ""), !!r.errors.length);
    $("#dd-panel").innerHTML = "";
  });
}
async function renderFit(fid) {
  const m = $("#d-main");
  m.innerHTML = `<div class="empty">Chargement du fit…</div>`;
  let f;
  try { f = await api("/api/fits/" + fid); } catch (e) { m.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; return; }
  const ro = f.official;
  const bySlot = {};
  f.items.forEach((it) => (bySlot[it.slot_label] = bySlot[it.slot_label] || []).push(it));
  const order = ["Coque", "Slots hauts", "Slots moyens", "Slots bas", "Rigs", "Sous-systèmes", "Services", "Drones", "Chasseurs", "Munitions chargées", "Soute"];
  m.innerHTML = `
    <button class="small" id="fd-back">← ${esc(f.doctrine)}</button>
    <div class="card" style="margin-top:10px"><div class="body">
      <div class="fit-head">${shipImg(f.ship_type_id, 128, "")}<div>
        <h2>${esc(f.name)}</h2><div class="muted">${esc(f.ship_name)} · ${esc(f.ship_group)} · doctrine ${esc(f.doctrine)}</div>
        <div class="kpis" style="margin:10px 0 0"><div class="kpi"><span>Prix du fit à ${esc(f.market)}</span><b>${isk(f.total)}</b></div>
          ${f.compare_market ? `<div class="kpi"><span>À ${esc(f.compare_market)}</span><b>${isk(f.total_compare)}</b></div>` : ""}
          <div class="kpi"><span>Compétences requises</span><b>${f.skills_known ? f.skills_required : "?"}</b></div></div>
      </div></div>
      <div class="wrow">
        <div class="field"><label>Rôle</label><select id="fd-role" ${ro ? "disabled" : ""}>${D.data.roles.map((r) => `<option ${r === f.role ? "selected" : ""}>${esc(r)}</option>`).join("")}</select></div>
        <div class="field grow"><label>Note</label><input id="fd-notes" value="${esc(f.notes)}" ${ro ? "disabled" : ""}></div>
        ${ro ? "" : '<button id="fd-save">Enregistrer</button>'}
      </div>
      <div class="actions">
        <button id="fd-eft">Copier le fit (EFT, pour Pyfa)</button>
        <button id="fd-eft2">Copier le fit (langue du jeu)</button>
        <button id="fd-mb">Copier pour le Multibuy</button>
        ${D.chars.length ? `${charSelect("fd-char")}<button class="primary" id="fd-push">Envoyer en jeu</button>` : ""}
        ${ro ? "" : '<button class="danger" id="fd-del">Supprimer le fit</button>'}
      </div>
    </div></div>
    <div class="grid2">
      <div class="card"><h2>Contenu du fit</h2><div class="body">${order.filter((k) => bySlot[k]).map((k) => `<div class="slot-title">${k}</div>${bySlot[k].map((it) => `
        <div class="with-ico" style="justify-content:space-between;padding:3px 0"><span class="with-ico">${ico(it.type_id, "s")}${it.qty > 1 ? `<b style="margin-right:6px">${n0(it.qty)}×</b>` : ""}${esc(it.name)}</span><span class="muted">${isk(it.unit_price * it.qty)}</span></div>`).join("")}`).join("")}</div></div>
      <div class="card"><h2>Mes pilotes</h2><div class="body" id="fd-pilots"></div></div>
    </div>`;
  $("#fd-back").onclick = () => { D.fit = null; renderDoc(); };
  $("#fd-eft").onclick = () => copyText(f.eft, "Fit copié (EFT anglais) : importable dans Pyfa et en jeu.");
  $("#fd-eft2").onclick = () => copyText(f.eft_local, "Fit copié dans la langue du jeu.");
  $("#fd-mb").onclick = () => copyText(f.multibuy, "Copié : Marché → Multibuy → Ctrl+V.");
  const push = $("#fd-push");
  if (push) push.onclick = () => busy(push, async () => { await api(`/api/fits/${f.id}/push`, { method: "POST", body: { character_id: +$("#fd-char").value } }); toast("Fit envoyé : il apparaît dans la fenêtre Fitting du personnage."); });
  const sv = $("#fd-save");
  if (sv) sv.onclick = () => busy(sv, async () => { await api("/api/fits/" + f.id, { method: "PUT", body: { role: $("#fd-role").value, notes: $("#fd-notes").value } }); toast("Fit enregistré."); await loadDoctrines(true); });
  const del = $("#fd-del");
  if (del) del.onclick = async () => { if (!confirm("Supprimer ce fit ?")) return; await api("/api/fits/" + f.id, { method: "DELETE" }); D.fit = null; loadDoctrines(); };
  const pl = $("#fd-pilots");
  if (!f.pilots.length) { pl.innerHTML = `<p class="muted">Connecte tes personnages pour savoir lesquels peuvent piloter ce fit.</p>`; return; }
  if (!f.skills_known) { pl.innerHTML = `<p class="muted">Compétences requises inconnues : mets à jour les données du jeu.</p>`; return; }
  pl.innerHTML = f.pilots.map((p, i) => {
    if (p.unknown) return `<div class="pilot-card"><div class="top"><span class="with-ico">${portrait(p.character_id)}<b>${esc(p.name)}</b></span><span class="muted">compétences non chargées</span></div></div>`;
    if (p.can_fly) return `<div class="pilot-card"><div class="top"><span class="with-ico">${portrait(p.character_id)}<b>${esc(p.name)}</b></span><span class="pos">Peut piloter ce fit</span></div></div>`;
    return `<div class="pilot-card"><div class="top"><span class="with-ico">${portrait(p.character_id)}<span><b>${esc(p.name)}</b><br><span class="${p.only_queued ? "" : "neg"}">${p.only_queued ? "Tout est déjà en file d'entraînement" : `${p.missing.length} compétence(s) manquante(s) · ${dur(p.train_time_s)}`}</span></span></span>
      <button class="small" data-plan="${i}">Copier la liste des compétences</button></div>
      <ul>${p.missing.map((m) => `<li>${esc(m.name)} : ${m.have} → <b>${m.need}</b> <span class="muted">${m.queued_until ? "en file, fini le " + new Date(m.queued_until).toLocaleDateString("fr-FR") : dur(m.time_s)}</span></li>`).join("")}</ul></div>`;
  }).join("") + `<p class="hint">Durées calculées avec les attributs actuels du personnage (Oméga). La liste copiée est en anglais, une ligne par niveau, prérequis en premier.</p>`;
  $$("[data-plan]", pl).forEach((b) => b.onclick = () => copyText(f.pilots[+b.dataset.plan].plan, "Liste copiée."));
}
function setupDoctrines() {
  $("#d-new").onclick = async () => {
    const name = prompt("Nom de la nouvelle doctrine (ex. « Vexor », « Kite HAC »)"); if (!name) return;
    const r = await api("/api/doctrines", { method: "POST", body: { name } }); D.current = r.id; D.tab = "fits"; await loadDoctrines(); panelAddFits(D.data.doctrines.find((d) => d.id === r.id));
  };
  $("#d-export").onclick = async () => {
    const r = await api("/api/doctrines/export");
    const blob = new Blob([JSON.stringify(r, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `doctrines-${r.exported}.json`; a.click();
    toast("Fichier téléchargé : partage-le, ou publie-le comme doctrines officielles (voir README).");
  };
  $("#d-import").onclick = () => openImportPanel();
  // glisser-déposer d'un fichier n'importe où sur la page Doctrines
  const zone = $("#v-doctrines");
  let depth = 0;
  zone.addEventListener("dragenter", (e) => { if ([...e.dataTransfer.types].includes("Files")) { depth++; zone.classList.add("dragging"); e.preventDefault(); } });
  zone.addEventListener("dragover", (e) => e.preventDefault());
  zone.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; zone.classList.remove("dragging"); } });
  zone.addEventListener("drop", async (e) => {
    e.preventDefault(); depth = 0; zone.classList.remove("dragging");
    const f = e.dataTransfer.files[0];
    if (f) { openImportPanel(); await loadImportFile(f); }
  });
  $("#d-corp").onclick = (ev) => busy(ev.target, async () => { await api("/api/doctrines/corp/refresh", { method: "POST" }); toast("Doctrines corpo mises à jour."); loadDoctrines(); });
}

// ---------------------------------------------------------------- INTEL
const THREAT_CLS = { "très dangereux": "t-tres", dangereux: "t-dang", moyen: "t-moy", faible: "t-faible", "allié": "t-allie", inconnu: "t-inconnu" };
const STD = { terrible: ["t-tres", "rouge"], bad: ["t-dang", "orange"], neutral: ["t-inconnu", "neutre"], good: ["t-allie", "bleu"], excellent: ["t-allie", "bleu foncé"], member: ["t-allie", "corpo/alliance"] };
const stdBadge = (p) => `<span class="threat ${(STD[p.standing] || STD.neutral)[0]}" title="Standing ${p.standing_value ?? 0}">${(STD[p.standing] || STD.neutral)[1]}</span>`;
const logo = (kind, id) => (id ? `<img class="logo" src="${IMG}/${kind}/${id}/logo?size=32" alt="" loading="lazy">` : "");
function setupIntel() {
  const unlock = () => { $("#in-locked").hidden = true; $("#in-tools").hidden = false; };
  $("#in-unlock").onclick = () => { unlock(); store.set("intelBeta", true); };
  if (store.get("intelBeta", false)) unlock();
  $("#in-text").value = store.get("intelText", "");
  $("#in-run").onclick = (ev) => busy(ev.target, async () => {
    store.set("intelText", $("#in-text").value);
    $("#in-out").innerHTML = `<div class="empty">Identification des pilotes et lecture de zKillboard… (quelques secondes par dizaine de pilotes)</div>`;
    const r = await api("/api/intel/local", { method: "POST", body: { text: $("#in-text").value, zkill_limit: +$("#in-limit").value } });
    renderIntel(r);
  });
  $("#ds-text").value = store.get("dscanText", "");
  $("#ds-run").onclick = (ev) => busy(ev.target, async () => {
    store.set("dscanText", $("#ds-text").value);
    const r = await api("/api/intel/dscan", { method: "POST", body: { text: $("#ds-text").value, grid_km: +$("#ds-grid").value } });
    renderDscan(r);
  });
}
function renderIntel(r) {
  const out = $("#in-out");
  const hostiles = r.pilots.filter((p) => !p.friendly);
  const lvl = {};
  hostiles.forEach((p) => (lvl[p.threat] = (lvl[p.threat] || 0) + 1));
  const max = Math.max(1, ...r.groups.map((g) => g.count));
  const nStd = (k) => r.pilots.filter((p) => p.standing === k).length;
  out.innerHTML = `
    ${r.standings_loaded ? "" : `<div class="warnbox">Standings non chargés : seuls ta corpo et ton alliance sont reconnues. Personnages & stock → « Rafraîchir depuis le jeu » (nouvelle permission contacts, reconnexion peut-être nécessaire).</div>`}
    <div class="kpis"><div class="kpi"><span>Pilotes identifiés</span><b>${r.pilots.length}</b></div>
      <div class="kpi"><span>Rouges</span><b class="neg">${nStd("terrible")}</b></div>
      <div class="kpi"><span>Oranges</span><b style="color:#ffc98a">${nStd("bad")}</b></div>
      <div class="kpi"><span>Neutres</span><b>${nStd("neutral")}</b></div>
      <div class="kpi"><span>Bleus</span><b style="color:#a8d0f5">${r.pilots.length - hostiles.length}</b></div>
      <div class="kpi"><span>Très dangereux</span><b class="neg">${lvl["très dangereux"] || 0}</b></div>
      <div class="kpi"><span>Dangereux</span><b>${lvl["dangereux"] || 0}</b></div>
      <div class="kpi"><span>Groupes</span><b>${r.groups.length}</b></div></div>
    ${r.unknown.length ? `<div class="warnbox">Non trouvés (faute de frappe ou perso supprimé) : ${r.unknown.map(esc).join(", ")}</div>` : ""}
    ${r.zkill_limited ? `<div class="warnbox">Statistiques zKillboard limitées aux premiers pilotes de la liste pour rester rapide.</div>` : ""}
    <div class="groups">${r.groups.map((g) => `<div class="group ${g.friendly ? "friendly" : ""}"><span class="n">${g.count}</span>
      <b>${g.alliance_id ? logo("alliances", g.alliance_id) : logo("corporations", g.corporation_id)}${esc(g.name)}</b>${g.friendly ? ' <span class="threat t-allie">allié</span>' : ""}
      <div class="bar"><i style="width:${(g.count / max) * 100}%"></i></div>
      <div class="corps">${g.corps.map(([c, n]) => `${esc(c)} (${n})`).join(" · ")}</div></div>`).join("")}</div>
    ${r.entities.map((e) => `<div class="card"><h2>${logo(e.kind === "alliance" ? "alliances" : "corporations", e.id)}${esc(e.name)} <a href="https://zkillboard.com/${e.kind}/${e.id}/" target="_blank" rel="noopener" class="small">zKillboard</a></h2>
      <div class="body">${e.stats.found ? `${n0(e.stats.kills)} kills · ${n0(e.stats.losses)} pertes · efficacité ${e.stats.efficiency} % · ${e.stats.kills_7d} kills sur 7 jours · vaisseaux favoris : ${e.stats.top_ships.map((s) => esc(s.name)).join(", ") || "—"}` : "Pas de données zKillboard."}</div></div>`).join("")}
    <div class="card"><h2>Pilotes <button class="small" id="in-copy">Copier le résumé</button></h2><div id="in-table"></div></div>
    <p class="hint">Dangerosité : part des kills dans l'activité (zKillboard) combinée à l'activité des 7 derniers jours. C'est un indice, pas une certitude : un pilote « faible » peut être un cyno ou un éclaireur.</p>`;
  $("#in-table").append(table(r.pilots.map((p) => ({ ...p, kills: p.stats.kills || 0, losses: p.stats.losses || 0, danger: p.stats.danger ?? -1, k7: p.stats.kills_7d || 0, solo: p.stats.solo_pct ?? -1, order: ["très dangereux", "dangereux", "moyen", "faible", "inconnu", "allié"].indexOf(p.threat),
    std_order: ["terrible", "bad", "neutral", "good", "excellent", "member"].indexOf(p.standing) })), [
    { k: "name", label: "Pilote", fmt: (v, x) => `<div class="with-ico"><img class="ico" style="border-radius:50%" src="${charImg(x.character_id)}" alt=""><div><a href="https://zkillboard.com/character/${x.character_id}/" target="_blank" rel="noopener">${esc(v)}</a><div class="muted">${logo("corporations", x.corporation_id)}${esc(x.corporation)}${x.alliance ? " · " + esc(x.alliance) : ""}</div></div></div>` },
    { k: "std_order", label: "Standing", fmt: (v, x) => stdBadge(x) },
    { k: "order", label: "Menace", fmt: (v, x) => `<span class="threat ${THREAT_CLS[x.threat] || ""}">${esc(x.threat)}</span>`, num: false },
    { k: "kills", label: "Kills", num: true, fmt: n0 }, { k: "losses", label: "Pertes", num: true, fmt: n0 },
    { k: "danger", label: "Danger", num: true, fmt: (v) => (v >= 0 ? v + " %" : "—") },
    { k: "solo", label: "Solo", num: true, fmt: (v) => (v >= 0 ? v + " %" : "—") },
    { k: "k7", label: "Kills 7 j", num: true, fmt: n0 },
    { k: "top", label: "Vaisseaux favoris", fmt: (v, x) => (x.stats.top_ships || []).map((s) => `<span title="${esc(s.name)} — ${s.kills} kills">${ico(s.type_id, "s")}</span>`).join("") || "—" },
  ], { sortKey: "std_order", desc: false }));
  $("#in-copy").onclick = () => copyText(`Local : ${r.pilots.length} pilotes — ` + r.groups.slice(0, 6).map((g) => `${g.name} ${g.count}`).join(", ")
    + (hostiles.filter((p) => p.threat === "très dangereux").length ? ` — très dangereux : ${hostiles.filter((p) => p.threat === "très dangereux").map((p) => p.name).join(", ")}` : ""), "Résumé copié pour le chat de fleet.");
}
function renderDscan(r) {
  const out = $("#ds-out");
  const maxc = Math.max(1, ...r.classes.map((c) => c.count));
  out.innerHTML = `
    <div class="kpis"><div class="kpi"><span>Vaisseaux</span><b>${r.total_ships}</b></div>
      ${r.has_distance ? `<div class="kpi"><span>Sur grille</span><b>${r.on_grid}</b></div>` : ""}
      <div class="kpi"><span>Valeur estimée des coques</span><b>${isk(r.estimated_value)}</b></div>
      <div class="kpi"><span>Types différents</span><b>${r.ships.length}</b></div></div>
    ${r.threats.length ? `<div class="alerts">${r.threats.map((t) => `<div class="alert"><b>${t.count}</b>${esc(t.label)}</div>`).join("")}</div>` : ""}
    <div class="grid2">
      <div class="card"><h2>Vaisseaux <button class="small" id="ds-copy">Copier le résumé</button></h2><div id="ds-table"></div></div>
      <div><div class="card"><h2>Par classe</h2><div class="body">${r.classes.map((c) => `<div style="margin-bottom:8px"><div style="display:flex;justify-content:space-between"><span>${esc(c.class)}</span><b>${c.count}</b></div><div class="bar"><i style="width:${(c.count / maxc) * 100}%"></i></div></div>`).join("")}</div></div>
      ${Object.keys(r.other).length ? `<div class="card"><h2>Autres objets</h2><div class="body">${Object.entries(r.other).map(([k, v]) => `<div style="display:flex;justify-content:space-between"><span>${esc(k)}</span><span class="muted">${v}</span></div>`).join("")}</div></div>` : ""}</div>
    </div>
    ${r.has_distance ? "" : '<p class="hint">Pas de distances dans ce scan : « sur grille » indisponible.</p>'}`;
  const cols = [
    { k: "name", label: "Vaisseau", fmt: (v, x) => withIco(x.type_id, esc(v) + (x.threat ? ` <span class="threat t-dang">${esc(x.threat)}</span>` : "") + `<div class="muted">${esc(x.group)}</div>`) },
    { k: "count", label: "Nombre", num: true },
  ];
  if (r.has_distance) cols.push({ k: "on_grid", label: "Sur grille", num: true });
  cols.push({ k: "value", label: "Valeur", num: true, fmt: isk });
  $("#ds-table").append(table(r.ships, cols, { sortKey: "count" }));
  $("#ds-copy").onclick = () => copyText(`D-scan : ${r.total_ships} vaisseaux${r.has_distance ? ` (${r.on_grid} sur grille)` : ""} — `
    + r.ships.slice(0, 8).map((s) => `${s.count} ${s.name}`).join(", ")
    + (r.threats.length ? ` — ALERTES : ${r.threats.map((t) => `${t.label} ×${t.count}`).join(", ")}` : ""), "Résumé copié pour le chat de fleet.");
}

// ---------------------------------------------------------------- ALARME LOCAL & INTEL
const AL = { cfg: null, wins: [], support: false, monitors: [], shot: null, shotSrc: null, mon: null, picking: null,
  lastSeq: store.get("alarmSeq", 0), poll: null, sounds: {} };
const PICK = [["rouge", "Rouge"], ["orange", "Orange"], ["neutre", "Neutre"], ["autre", "Autre"]];
const SOUND_CATS = [["rouge", "Arrivée d'un rouge"], ["orange", "Arrivée d'un orange"], ["neutre", "Arrivée d'un neutre"], ["intel", "Message d'intel"]];
function alarmCfg() { return JSON.parse(JSON.stringify(G.settings.alarm || {})); }
async function saveAlarm(cfg) { AL.cfg = cfg; await saveSettings({ alarm: cfg }); }
function curRel(c = AL.cfg) { return c.source === "screen" ? c.region && c.region.rel : c.region_rel; }
function playSound(name, volume) {
  try { const a = new Audio(`/api/alarm/sound?name=${encodeURIComponent(name)}&volume=${volume}`); a.play().catch(() => {}); } catch { /* */ }
}
function notify(ev) {
  if (!(G.settings.alarm || {}).browser_notif) return;
  try { if (Notification.permission === "granted") new Notification("EVE — alerte", { body: ev.text, silent: true }); } catch { /* */ }
}
async function pollAlarm() {
  let st;
  try { st = await api("/api/alarm/status"); } catch { return; }
  $("#alarm-badge").hidden = !st.running;
  if (st.seq < AL.lastSeq) AL.lastSeq = 0;   // serveur redémarré
  const fresh = st.events.filter((e) => e.id > AL.lastSeq).reverse();
  if (fresh.length) {
    AL.lastSeq = st.seq; store.set("alarmSeq", AL.lastSeq);
    const c = G.settings.alarm || {};
    if (c.output === "browser") playSound(fresh[fresh.length - 1].sound || "bip", c.volume ?? 70);
    fresh.forEach(notify);
    document.body.classList.remove("alarming"); void document.body.offsetWidth; document.body.classList.add("alarming");
    document.title = "🔴 " + fresh[fresh.length - 1].text;
    setTimeout(() => (document.title = "Cockpit"), 8000);
  }
  if (!$("#v-alarme").hidden) renderAlarmState(st);
  clearTimeout(AL.poll);
  AL.poll = setTimeout(pollAlarm, st.running ? 1000 : 5000);
}
function localReady(c) { return !!curRel(c); }
function intelReady(c) { return !!(c.channels || []).length && !!((c.systems || []).length || (c.keywords || []).length); }
function renderAlarmState(st) {
  const box = $("#al-state");
  if (!box) return;
  const watch = (st.watching || []).map((w) => `<li><b>${esc(w.label)}</b> : ${esc(w.state)}${w.counts ? " — " + Object.entries(w.counts).map(([k, v]) => `${esc(k)} ${v} px`).join(", ") : ""}</li>`).join("");
  box.innerHTML = `<div class="al-state"><span class="al-led ${st.error ? "err" : st.running ? "on" : ""}"></span>
      <b>${st.running ? (st.error ? "Problème" : "Surveillance active") : "Arrêtée"}</b>
      <span class="muted">${st.running && st.last_check ? "dernier contrôle " + new Date(st.last_check * 1000).toLocaleTimeString("fr-FR") : ""}</span></div>
    ${st.error ? `<div class="warnbox" style="margin-top:8px">${esc(st.error)}</div>` : ""}
    ${st.running && st.note ? `<div class="infobox" style="margin-top:8px">${esc(st.note)}</div>` : ""}
    ${st.running && watch ? `<ul class="hint" style="margin:8px 0 0;padding-left:18px">${watch}</ul>` : ""}`;
  $("#al-events").innerHTML = st.events.length ? st.events.map((e) => `<div class="ev ${e.level}"><time>${new Date(e.time * 1000).toLocaleTimeString("fr-FR")}</time><span>${esc(e.text)}</span></div>`).join("") : '<p class="muted">Aucune alerte pour l’instant.</p>';
  const il = $("#al-intel-last");
  if (il) il.innerHTML = (st.intel_last || []).length ? st.intel_last.map((m) => `<div class="ev"><time>${esc(m.time)}</time><span><b>${esc(m.channel)}</b> — ${esc(m.speaker)} : ${esc(m.message)}</span></div>`).join("") : '<p class="muted">Rien lu pour l’instant (démarre la surveillance ; seuls les nouveaux messages apparaissent).</p>';
  $("#al-start").hidden = st.running; $("#al-stop").hidden = !st.running; $("#al-rearm").disabled = !st.running;
}
function stepHtml(n, title, done, body) {
  return `<div class="wstep ${done ? "done" : ""}" style="margin-bottom:10px"><h2 style="font-size:18px">${title}</h2>${body}</div>`;
}
async function renderAlarm() {
  const out = $("#al-out");
  AL.cfg = alarmCfg();
  try { AL.sounds = await api("/api/alarm/sounds"); } catch { AL.sounds = { bip: "Bip" }; }
  try { const w = await api("/api/alarm/windows"); AL.support = w.supported; AL.wins = w.windows; } catch { AL.support = false; AL.wins = []; }
  const c = AL.cfg;
  if (!AL.support && c.source !== "screen") { c.source = "screen"; }
  const lr = localReady(c), ir = intelReady(c);
  const vol = c.volume ?? 70;
  const sndSel = (cat) => `<select data-snd="${cat}">${Object.entries(AL.sounds).map(([k, v]) => `<option value="${k}" ${((c.sounds || {})[cat] || "") === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`;
  out.innerHTML = `
    <div class="guide-cols" style="margin-bottom:14px">
      <div class="guide-col"><h2 style="font-size:20px">Alarme local ${lr ? '<span class="threat t-faible">prête</span>' : '<span class="threat t-dang">à configurer</span>'}</h2>
        <p style="color:#c4cfdb;margin:0"><b>À quoi ça sert :</b> tu rattes, tu mines ou tu attends en station sans regarder le local. L'outil le regarde pour toi et sonne dès qu'un pilote <b>rouge, orange ou neutre</b> arrive dans ton système.</p>
        <p class="hint">Comment : il observe les petites icônes de couleur à côté des noms, dans ta fenêtre du local.</p></div>
      <div class="guide-col"><h2 style="font-size:20px">Alarme intel ${ir ? '<span class="threat t-faible">prête</span>' : '<span class="threat t-dang">à configurer</span>'}</h2>
        <p style="color:#c4cfdb;margin:0"><b>À quoi ça sert :</b> dans les canaux d'intel de l'alliance, les éclaireurs écrivent « 3 reds 1DQ1-A ». L'outil lit ces messages et sonne si un système <b>proche de toi</b> est cité, avant que l'ennemi arrive dans ton local.</p>
        <p class="hint">Comment : il lit les fichiers de chat que le jeu enregistre sur ton PC.</p></div>
    </div>
    <div class="grid2">
      <div class="card"><h2>Surveillance</h2><div class="body">
        <div id="al-state"></div>
        <div class="actions"><button class="primary" id="al-start">Démarrer</button><button id="al-stop" hidden>Arrêter</button>
          <button id="al-rearm" title="Les pilotes déjà présents ne sonneront plus ; seuls les nouveaux arrivants sonneront">Réarmer</button></div>
        <p class="hint">Au démarrage, les pilotes déjà présents dans le local sont la référence : seuls les <b>nouveaux arrivants</b> sonnent. Un pilote qui part puis revient sonne de nouveau.</p>
      </div></div>
      <div class="card"><h2>Journal des alertes</h2><div class="body events" id="al-events"></div></div>
    </div>

    <div class="card"><h2>Son</h2><div class="body">
      <div class="wrow">
        <div class="field"><label>Où jouer le son</label><select id="al-out-sel"><option value="pc" ${c.output !== "browser" ? "selected" : ""}>Sur le PC (même navigateur fermé)</option><option value="browser" ${c.output === "browser" ? "selected" : ""}>Dans le navigateur</option></select></div>
        <div class="field grow"><label>Volume : <b id="al-vol-v">${vol} %</b></label><input type="range" id="al-vol" min="0" max="100" value="${vol}" style="width:100%"></div>
        <label class="check"><input type="checkbox" id="al-notif" ${c.browser_notif ? "checked" : ""}> Notification Windows en plus</label>
      </div>
      <div class="wrow" style="margin-top:10px">${SOUND_CATS.map(([k, l]) => `<div class="field"><label>${l}</label><span style="display:flex;gap:4px">${sndSel(k)}<button class="small" data-try="${k}" title="Écouter">▶</button></span></div>`).join("")}</div>
      <p class="hint">▶ joue le son avec le volume choisi, à l'endroit choisi (PC ou navigateur).</p>
    </div></div>

    <div class="card"><h2><label class="check" style="padding:0"><input type="checkbox" id="al-scr" ${c.screen_enabled !== false ? "checked" : ""}> Alarme local — 3 étapes</label></h2><div class="body">
      <div class="sstep ${AL.wins.length || c.source === "screen" ? "ok" : ""}"><span class="sn">1</span><div>
        <b>Lance EVE et ouvre la fenêtre du local</b>, en liste (l'affichage compact, sans portraits, marche le mieux).
        <div class="hint">Pour être prévenu des <b>neutres</b>, ils doivent avoir une icône dans le local : dans les réglages de l'overview, onglet Apparence (étiquettes de couleur), active l'étiquette des pilotes à standing neutre / sans standing. Un pilote sans aucune icône est invisible pour l'alarme.</div>
        <div class="hint">${c.source === "screen" ? "Mode zone fixe de l'écran." : AL.wins.length ? "EVE détecté : " + AL.wins.map((w) => `<b>${esc(w.character || w.title)}</b>${w.minimized ? " (réduite)" : ""}`).join(", ") : "Aucune fenêtre EVE détectée."} <button class="small" id="al-refresh-w">Actualiser</button></div></div></div>
      <div class="sstep ${curRel(c) ? "ok" : ""}"><span class="sn">2</span><div>
        <b>Prends une photo, puis encadre toute la fenêtre du local avec la souris</b>, de la première ligne jusqu'en bas de la fenêtre, <b>partie vide comprise</b> (les nouveaux arrivants s'y ajoutent). C'est la seule chose à faire à la main, une seule fois.
        <div class="actions">${c.source !== "screen" && AL.wins.filter((w) => !w.minimized).length > 1 ? `<select id="al-shot-win">${AL.wins.filter((w) => !w.minimized).map((w) => `<option value="${w.hwnd}" ${w.foreground ? "selected" : ""}>${esc(w.character || w.title)}</option>`).join("")}</select>` : ""}
          ${c.source === "screen" ? `<select id="al-mon"></select>` : ""}
          <button class="primary" id="al-shot">Prendre la photo</button>${curRel(c) ? '<span class="pos">Zone enregistrée ✓</span> <span class="muted">(reprends une photo seulement si tu déplaces le local dans EVE)</span>' : ""}</div>
        <div id="al-shotbox"></div><div id="al-found"></div></div></div>
      <div class="sstep"><span class="sn">3</span><div>
        <b>Choisis ce qui doit sonner, puis démarre.</b>
        <div class="actions">${[["rouge", "Rouges"], ["orange", "Oranges"], ["neutre", "Neutres"]].map(([k, l]) => `<label class="check" style="padding:0"><input type="checkbox" data-watch="${k}" ${(c.watch || {})[k] !== false ? "checked" : ""}> ${l}</label>`).join("")}
          <button class="primary" id="al-start2">Démarrer l'alarme</button></div>
        <p class="hint">Les pilotes déjà là au démarrage ne sonnent pas : seuls les nouveaux arrivants. Les bleus et ta corpo ne sonnent jamais.</p></div></div>
      <details class="howto" style="margin:12px 0 0"><summary>Réglages avancés (seulement si quelque chose ne marche pas)</summary><div class="howto-body">
        <div class="wrow">
          <div class="field"><label>Client EVE surveillé</label><select id="al-wm-sel">
            ${AL.support ? `<option value="active" ${(c.window_mode || "active") === "active" && c.source !== "screen" ? "selected" : ""}>Celui sur lequel je joue</option>
            <option value="character" ${c.window_mode === "character" && c.source !== "screen" ? "selected" : ""}>Toujours le même personnage</option>
            <option value="all" ${c.window_mode === "all" && c.source !== "screen" ? "selected" : ""}>Tous mes clients (multi-compte)</option>` : ""}
            <option value="screen" ${c.source === "screen" ? "selected" : ""}>Une zone fixe de l'écran</option></select></div>
          <div class="field"><label>Personnage (si « toujours le même »)</label><select id="al-char">${AL.wins.filter((w) => w.character).map((w) => `<option ${w.character === c.window_character ? "selected" : ""}>${esc(w.character)}</option>`).join("") || `<option>${esc(c.window_character || "")}</option>`}</select></div>
          <div class="field"><label>Contrôle toutes les (s)</label><input type="number" id="al-int" min="0.3" step="0.1" value="${c.interval ?? 1}"></div>
          <button id="al-save1">Enregistrer</button></div>
        <p style="margin-top:12px"><b>Une couleur n'est pas reconnue</b> (thème d'interface spécial) ? Après la photo, clique sur la couleur concernée puis sur une de ces icônes dans le zoom : l'outil utilisera exactement cette teinte.</p>
        <div id="al-cropbox"></div>
        <div class="wrow"><div class="field"><label>Tolérance des couleurs choisies (0-80)</label><input type="number" id="al-tol" min="0" max="80" value="${c.custom_tol ?? 30}"></div>
          <button id="al-check">Tester la détection maintenant</button></div>
        <div id="al-check-out"></div>
        <input type="hidden" id="al-minpx" value="${c.min_pixels ?? 25}">
      </div></details>
    </div></div>

    <div class="card"><h2><label class="check" style="padding:0"><input type="checkbox" id="al-logs" ${c.logs_enabled ? "checked" : ""}> Configurer l'alarme intel</label></h2><div class="body steps" style="max-width:none">
      ${stepHtml(1, "Fais enregistrer le chat par EVE", false, `
        <p>En jeu : <b>Échap</b> → <b>Paramètres</b> → onglet <b>Chat</b> → coche <b>« Log chat to file »</b> (enregistrer le chat dans un fichier). Puis quitte et rejoins tes canaux d'intel (ou relance le client) pour que l'enregistrement démarre.</p>
        <div class="wrow"><button id="al-chan">Chercher mes canaux</button>
          <div class="field grow"><label>Dossier des logs (vide = automatique)</label><input id="al-dir" value="${esc(c.log_dir || "")}" placeholder="C:\\Users\\…\\Documents\\EVE\\logs\\Chatlogs"></div></div>`)}
      ${stepHtml(2, "Coche tes canaux d'intel", (c.channels || []).length > 0, `<div id="al-chanlist"><p class="muted">Clique « Chercher mes canaux » ci-dessus.</p></div>`)}
      ${stepHtml(3, "Choisis les systèmes qui doivent sonner", (c.systems || []).length > 0, `
        <p>Le plus simple : tous les systèmes à quelques sauts de chez toi.</p>
        <div class="wrow"><div class="field"><label>Autour de</label><div class="ac"><input id="al-near-sys" placeholder="ex. 1DQ1-A" autocomplete="off"><div class="ac-list" id="al-near-list"></div></div></div>
          <div class="field"><label>Sauts</label><select id="al-near-j">${[1, 2, 3, 4, 5, 6, 8, 10].map((n) => `<option ${n === 5 ? "selected" : ""}>${n}</option>`).join("")}</select></div>
          <button id="al-near-add">Ajouter ces systèmes</button></div>
        <div class="wrow" style="margin-top:10px">
          <div class="field grow"><label>Systèmes surveillés (un par ligne) — son « intel », alerte rouge</label><textarea id="al-sys" rows="5">${esc((c.systems || []).join("\n"))}</textarea></div>
          <div class="field grow"><label>Mots-clés en plus (facultatif) — alerte orange</label><textarea id="al-kw" rows="5" placeholder="cyno&#10;bubble&#10;hot drop">${esc((c.keywords || []).join("\n"))}</textarea></div></div>
        <div class="actions"><label class="check" style="padding:0"><input type="checkbox" id="al-clr" ${c.ignore_clear !== false ? "checked" : ""}> Ignorer les messages « clr / clear / propre »</label><button class="primary" id="al-save2">Enregistrer</button></div>`)}
      ${stepHtml(4, "Vérifie que ça marche", false, `<p>Démarre la surveillance : les derniers messages lus dans tes canaux s'affichent ici. S'ils apparaissent, la lecture fonctionne.</p><div class="events" id="al-intel-last"></div>`)}
    </div></div>`;

  // --- son
  const persist = async () => {
    const cfg = AL.cfg;
    const wm = $("#al-wm-sel") ? $("#al-wm-sel").value : null;
    Object.assign(cfg, {
      output: $("#al-out-sel").value, volume: +$("#al-vol").value, browser_notif: $("#al-notif").checked,
      sounds: Object.fromEntries($$("[data-snd]").map((s) => [s.dataset.snd, s.value])),
      screen_enabled: $("#al-scr").checked, logs_enabled: $("#al-logs").checked,
      custom_tol: +$("#al-tol").value, min_pixels: +$("#al-minpx").value, interval: +$("#al-int").value,
      detection: "auto", watch: Object.fromEntries($$("[data-watch]").map((x) => [x.dataset.watch, x.checked])),
      log_dir: $("#al-dir").value.trim(),
      systems: [...new Set($("#al-sys").value.split(/[\n,]/).map((x) => x.trim()).filter(Boolean))],
      keywords: $("#al-kw").value.split("\n").map((x) => x.trim()).filter(Boolean), ignore_clear: $("#al-clr").checked,
    });
    if (wm) { if (wm === "screen") cfg.source = "screen"; else { cfg.source = "window"; cfg.window_mode = wm; } }
    if (!AL.support) cfg.source = "screen";
    if ($("#al-char")) cfg.window_character = $("#al-char").value;
    await saveAlarm(cfg);
  };
  $("#al-vol").oninput = () => ($("#al-vol-v").textContent = $("#al-vol").value + " %");
  ["#al-out-sel", "#al-vol", "#al-scr", "#al-logs", "#al-clr", "#al-char"].forEach((id) => { const el = $(id); if (el) el.onchange = persist; });
  $$("[data-snd]").forEach((s) => (s.onchange = persist));
  $("#al-wm-sel").onchange = async () => { await persist(); renderAlarm(); };
  $$("[data-watch]").forEach((x) => (x.onchange = persist));
  $("#al-start2").onclick = () => $("#al-start").click();
  $("#al-notif").onchange = async () => { if ($("#al-notif").checked && "Notification" in window) await Notification.requestPermission(); persist(); };
  $$("[data-try]").forEach((b) => (b.onclick = async () => {
    await persist();
    const cat = b.dataset.try, name = AL.cfg.sounds[cat];
    if (AL.cfg.output === "browser") playSound(name, AL.cfg.volume);
    else await api("/api/alarm/test", { method: "POST", body: { level: cat } });
  }));
  // --- commandes
  $("#al-start").onclick = (ev) => busy(ev.target, async () => { await persist(); await api("/api/alarm/start", { method: "POST" }); toast("Surveillance démarrée."); pollAlarm(); });
  $("#al-stop").onclick = async () => { await api("/api/alarm/stop", { method: "POST" }); pollAlarm(); };
  $("#al-rearm").onclick = async () => { await api("/api/alarm/rearm", { method: "POST" }); toast("Réarmé : seuls les nouveaux arrivants sonneront."); };
  const rw = $("#al-refresh-w"); if (rw) rw.onclick = () => renderAlarm();
  $("#al-save1").onclick = async () => { await persist(); toast("Réglages enregistrés."); };
  $("#al-save2").onclick = async () => { await persist(); toast("Alarme intel enregistrée."); renderAlarm(); };
  $("#al-chan").onclick = async () => { await persist(); listChannels(); };
  $("#al-check").onclick = (ev) => busy(ev.target, async () => {
    await persist();
    const r = await api("/api/alarm/check", { method: "POST" });
    $("#al-check-out").innerHTML = (r.note ? `<div class="infobox">${esc(r.note)}</div>` : "") + (r.windows.length ? r.windows.map((w) => `<div class="pilot-card"><b>${esc(w.label)}</b> : ${w.icons ? foundText(w.icons) : w.colors.map((x) => `${esc(x.name)} ≈ <b>${x.estimate}</b> icône(s)`).join(" · ")}</div>`).join("")
      : (r.watching || []).map((w) => `<div class="warnbox">${esc(w.label)} : ${esc(w.state)}</div>`).join("") || '<div class="warnbox">Aucune fenêtre surveillée en ce moment.</div>')
      + `<p class="hint">Si le compte est faux : refais la photo en encadrant seulement la liste des noms, ou choisis la couleur à la main ci-dessus.</p>`;
  });
  autocomplete($("#al-near-sys"), $("#al-near-list"), "/api/map/search?q=", () => {});
  $("#al-near-sys").value = (G.settings.map || {}).home || "";
  $("#al-near-add").onclick = (ev) => busy(ev.target, async () => {
    const r = await api(`/api/map/nearby?system=${encodeURIComponent($("#al-near-sys").value)}&jumps=${$("#al-near-j").value}`);
    const cur = $("#al-sys").value.split("\n").map((x) => x.trim()).filter(Boolean);
    $("#al-sys").value = [...new Set(cur.concat(r.map((x) => x.name)))].join("\n");
    await persist(); toast(`${r.length} systèmes ajoutés.`);
  });
  // --- photo
  if (c.source === "screen") {
    try {
      AL.monitors = await api("/api/alarm/monitors");
      $("#al-mon").innerHTML = AL.monitors.map((m) => `<option value="${m.index}" ${m.index === (c.monitor || 1) ? "selected" : ""}>Écran ${m.index} (${m.width}×${m.height})</option>`).join("");
    } catch (e) { $("#al-shotbox").innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; }
  }
  $("#al-shot").onclick = (ev) => busy(ev.target, takeShot);
  if (c.logs_enabled || (c.channels || []).length) listChannels();
  renderColors();
  pollAlarm();
}
async function takeShot() {
  const c = AL.cfg;
  let src;
  if (c.source === "screen") {
    const idx = +$("#al-mon").value || 1;
    AL.mon = AL.monitors.find((m) => m.index === idx);
    src = `/api/alarm/screenshot?monitor=${idx}&t=${Date.now()}`;
  } else {
    const vis = AL.wins.filter((w) => !w.minimized);
    const hwnd = $("#al-shot-win") ? $("#al-shot-win").value : ((vis.find((w) => w.foreground) || vis[0]) || {}).hwnd;
    if (!hwnd) return toast("Aucune fenêtre EVE ouverte (ou elle est réduite) : lance EVE puis clique « Actualiser ».", true);
    AL.shotHwnd = hwnd;
    src = `/api/alarm/window_shot?hwnd=${hwnd}&t=${Date.now()}`;
  }
  const box = $("#al-shotbox");
  box.innerHTML = `<div class="shot-wrap" id="al-wrap"><img id="al-img" alt="Photo"><div class="shot-sel" id="al-sel" hidden></div></div>`;
  const img = $("#al-img");
  await new Promise((ok, ko) => { img.onload = ok; img.onerror = () => ko(new Error("Photo impossible : la fenêtre est peut-être réduite.")); img.src = src; });
  AL.shot = document.createElement("canvas");
  AL.shot.width = img.naturalWidth; AL.shot.height = img.naturalHeight;
  AL.shot.getContext("2d").drawImage(img, 0, 0);
  const wrap = $("#al-wrap"), sel = $("#al-sel");
  wrap.scrollIntoView({ behavior: "instant", block: "center" });
  toast("Glisse la souris sur toute la fenêtre du local, partie vide comprise.");
  let start = null;
  const pt = (e) => { const r = img.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  wrap.onmousedown = (e) => { start = pt(e); sel.hidden = false; Object.assign(sel.style, { left: start.x + "px", top: start.y + "px", width: "0", height: "0" }); e.preventDefault(); };
  wrap.onmousemove = (e) => { if (!start) return; const p = pt(e); Object.assign(sel.style, { left: Math.min(p.x, start.x) + "px", top: Math.min(p.y, start.y) + "px", width: Math.abs(p.x - start.x) + "px", height: Math.abs(p.y - start.y) + "px" }); };
  wrap.onmouseup = async (e) => {
    if (!start) return;
    const p = pt(e), k = img.naturalWidth / img.clientWidth;
    const x = Math.round(Math.min(p.x, start.x) * k), y = Math.round(Math.min(p.y, start.y) * k);
    const w = Math.round(Math.abs(p.x - start.x) * k), h = Math.round(Math.abs(p.y - start.y) * k);
    start = null;
    if (w < 10 || h < 10) return toast("Zone trop petite : glisse la souris sur toute la liste du local.", true);
    if (AL.cfg.source === "screen") { AL.cfg.monitor = AL.mon.index; AL.cfg.region = { left: AL.mon.left + x, top: AL.mon.top + y, width: w, height: h, rel: { x, y } }; }
    else AL.cfg.region_rel = { x, y, width: w, height: h };
    AL.cfg.detection = "auto";
    await saveAlarm(AL.cfg);
    await analyzeZone({ x, y, width: w, height: h });
    renderCrop();
  };
  if (curRel()) renderCrop();
}
function foundText(c) {
  const part = (n, one, many) => `${n} ${n > 1 ? many : one}`;
  return `<span style="color:#ff8f80"><b>${part(c.rouge || 0, "rouge", "rouges")}</b></span> · <span style="color:#ffc98a"><b>${part(c.orange || 0, "orange", "oranges")}</b></span> · <span style="color:#d6dbe2"><b>${part(c.neutre || 0, "neutre", "neutres")}</b></span> · <span class="muted">${part(c.bleu || 0, "bleu", "bleus")} (ignorés)</span>`;
}
async function analyzeZone(rel) {
  const body = AL.cfg.source === "screen" ? { monitor: AL.mon.index, rel } : { hwnd: +AL.shotHwnd, rel };
  const box = $("#al-found");
  try {
    const r = await api("/api/alarm/analyze", { method: "POST", body });
    // cadres autour des icônes trouvées, sur la photo
    const img = $("#al-img"), wrap = $("#al-wrap"), k = img.clientWidth / img.naturalWidth;
    $$(".icon-box", wrap).forEach((e) => e.remove());
    const col = { rouge: "#ff5a4a", orange: "#ffa53a", neutre: "#e8edf3", bleu: "#5aa9ff" };
    Object.entries(r.boxes).forEach(([cat, list]) => list.forEach(([bx, by, bw, bh]) => {
      const d = document.createElement("div");
      d.className = "icon-box";
      Object.assign(d.style, { left: (rel.x + bx - 2) * k + "px", top: (rel.y + by - 2) * k + "px", width: (bw + 4) * k + "px", height: (bh + 4) * k + "px", borderColor: col[cat] });
      wrap.appendChild(d);
    }));
    box.innerHTML = `<div class="infobox" style="display:block;margin-top:10px"><b>Dans ton local, je vois :</b> ${foundText(r.counts)}.<br>
      Ça correspond à ce que tu vois dans EVE ? Alors passe à l'étape 3. Sinon, refais l'encadré sur la seule fenêtre du local (sans l'overview ni d'autres fenêtres).<br>
      <span class="muted">Local très peuplé : agrandis sa fenêtre pour que tout le monde soit visible, sinon les pilotes cachés en bas de liste ne sont pas vus.</span></div>`;
    toast("Zone enregistrée et analysée.");
  } catch (e) { box.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; }
}
function renderCrop() {
  const rel = curRel();
  if (!AL.shot || !rel) return;
  const reg = { x: rel.x, y: rel.y, width: rel.width, height: rel.height };
  const z = Math.max(2, Math.min(4, Math.floor(800 / reg.width) || 2));
  const box = $("#al-cropbox");
  box.innerHTML = `<div class="pickers">${PICK.filter(([k]) => k !== "autre").map(([k, l]) => `<button class="small ${AL.picking === k ? "active" : ""}" data-pick="${k}">${l}</button>`).join("")}<span class="muted">${AL.picking ? "puis clique au centre d'une icône de cette couleur dans le zoom" : "(facultatif) choisis une couleur, puis clique sur une icône"}</span></div>
    <div class="crop-wrap"><div style="max-height:520px;overflow:auto;border-radius:4px"><canvas id="al-crop" width="${reg.width * z}" height="${reg.height * z}"></canvas></div><div class="swatches" id="al-sw"></div></div>`;
  const cv = $("#al-crop"), ctx = cv.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(AL.shot, reg.x, reg.y, reg.width, reg.height, 0, 0, reg.width * z, reg.height * z);
  $$("[data-pick]", box).forEach((b) => b.onclick = () => { AL.picking = b.dataset.pick; renderCrop(); });
  cv.onclick = async (e) => {
    if (!AL.picking) return toast("Clique d'abord sur « Rouge » (ou une autre couleur).", true);
    const r = cv.getBoundingClientRect();
    const px = Math.floor((e.clientX - r.left) * (cv.width / r.width) / z) + reg.x;
    const py = Math.floor((e.clientY - r.top) * (cv.height / r.height) / z) + reg.y;
    const d = AL.shot.getContext("2d").getImageData(px, py, 1, 1).data;
    const label = PICK.find((p) => p[0] === AL.picking)[1];
    const n = (AL.cfg.colors || []).filter((c) => c.level === AL.picking).length;
    const cat = AL.picking === "autre" ? "neutre" : AL.picking;
    AL.cfg.custom_colors = { ...(AL.cfg.custom_colors || {}), [cat]: [d[0], d[1], d[2]] };
    await saveAlarm(AL.cfg);
    toast(`Couleur « ${label} » enregistrée.`);
    renderColors();
    if (curRel()) analyzeZone(curRel());
  };
  renderColors();
}
function iconSize(x0, y0, rgb, tol) {
  const W = 60, img = AL.shot.getContext("2d").getImageData(x0 - W / 2, y0 - W / 2, W, W).data;
  const ok = (x, y) => { const i = (y * W + x) * 4; return Math.abs(img[i] - rgb[0]) <= tol && Math.abs(img[i + 1] - rgb[1]) <= tol && Math.abs(img[i + 2] - rgb[2]) <= tol; };
  const seen = new Uint8Array(W * W), stack = [[W / 2, W / 2]];
  let n = 0;
  while (stack.length) {
    const [x, y] = stack.pop();
    if (x < 0 || y < 0 || x >= W || y >= W || seen[y * W + x] || !ok(x, y)) continue;
    seen[y * W + x] = 1; n++;
    stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
  }
  return Math.max(4, n);
}
function renderColors() {
  let sw = $("#al-sw");
  if (!sw) { const b = $("#al-cropbox"); if (!b) return; b.innerHTML = '<div class="swatches" id="al-sw"></div>'; sw = $("#al-sw"); }
  const cols = Object.entries(AL.cfg.custom_colors || {}).filter(([, v]) => v);
  sw.innerHTML = cols.length ? "<b>Couleurs choisies à la main</b>" + cols.map(([cat, rgb]) => `<div class="swatch"><i style="background:rgb(${rgb.join(",")})"></i><span>${esc(cat)}</span><button class="small danger" data-rm="${cat}">×</button></div>`).join("") : '<span class="muted">Détection automatique des couleurs (aucune couleur choisie à la main).</span>';
  $$("[data-rm]", sw).forEach((b) => b.onclick = async () => { const cc = { ...(AL.cfg.custom_colors || {}) }; delete cc[b.dataset.rm]; AL.cfg.custom_colors = cc; await saveAlarm(AL.cfg); renderColors(); if (curRel()) analyzeZone(curRel()); });
}
async function listChannels() {
  const box = $("#al-chanlist");
  try {
    const r = await api("/api/alarm/channels");
    if (!r.exists) { box.innerHTML = `<div class="warnbox">Dossier des logs introuvable : fais l'étape 1 (enregistrement du chat), ou indique le dossier.</div>`; return; }
    const sel = AL.cfg.channels || [];
    box.innerHTML = `<div class="muted" style="margin-bottom:6px">Canaux actifs ces 7 derniers jours (${esc(r.dir)}) :</div>` + (r.channels.length ? `<div class="chips">${r.channels.map((ch) => `<label><input type="checkbox" value="${esc(ch.name)}" ${sel.includes(ch.name) ? "checked" : ""}>${esc(ch.name)}</label>`).join("")}</div><p class="hint">Coche seulement les canaux d'intel (pas Local, Corp ou Fleet).</p>` : '<p class="muted">Aucun log récent : vérifie l’étape 1 puis rejoins tes canaux en jeu.</p>');
    $$("input", box).forEach((i) => i.onchange = async () => { AL.cfg.channels = $$("input:checked", box).map((x) => x.value); await saveAlarm(AL.cfg); });
  } catch (e) { box.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; }
}

// ---------------------------------------------------------------- CARTE DE LA GALAXIE
const M = { data: null, live: null, byId: {}, adj: null, view: null, sel: null, route: null, hover: null, ready: false, raf: 0 };
const SECC = ["#8d3264", "#722020", "#bb1116", "#ce440f", "#dc6d07", "#f3fd82", "#71e554", "#60dba3", "#4ecef8", "#399aeb", "#2c75e1"];
const secColor = (s) => (s <= 0 ? SECC[0] : SECC[Math.max(1, Math.min(10, Math.round(s * 10)))]);
const ACT_IDX = { kills: 0, pods: 1, jumps: 2, npc: 3 };
const secBadge = (s) => `<span class="secb" style="background:${secColor(s)}">${s.toFixed(1)}</span>`;
const SOV_PALETTE = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c",
  "#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8", "#aaffc3", "#808000", "#ffd8b1", "#00b3ff", "#ff6f91", "#7bd389",
  "#c9a227", "#b5838d", "#6d9dc5", "#ff9f1c"];
function computeSov() {
  const cnt = {}, names = {};
  Object.values((M.live && M.live.sov) || {}).forEach(([name, id]) => { if (!id) return; cnt[id] = (cnt[id] || 0) + 1; names[id] = name; });
  M.sovRank = Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([id, n], i) => ({ id: +id, name: names[id], n, color: i < SOV_PALETTE.length ? SOV_PALETTE[i] : hashColor(String(id)) }));
  M.sovColor = {};
  M.sovRank.forEach((o) => (M.sovColor[o.id] = o.color));
}
function computeActivityMax() {
  M.actMax = [1, 1, 1, 1];
  Object.values((M.live && M.live.activity) || {}).forEach((a) => a.forEach((v, i) => (M.actMax[i] = Math.max(M.actMax[i], v))));
}
function hashColor(str) { let h = 0; for (const ch of str || "") h = (h * 31 + ch.charCodeAt(0)) | 0; return `hsl(${Math.abs(h) % 360} 65% 55%)`; }
async function initMap() {
  if (!M.ready) {
    M.ready = true;
    const cv = $("#m-canvas");
    window.addEventListener("resize", () => { if (!$("#v-carte").hidden) sizeMap(); });
    let drag = null, moved = false;
    cv.addEventListener("mousedown", (e) => { drag = { x: e.clientX, y: e.clientY, tx: M.view.tx, ty: M.view.ty }; moved = false; cv.classList.add("drag"); });
    window.addEventListener("mouseup", (e) => {
      if (!drag) return;
      cv.classList.remove("drag");
      if (!moved) { const s = pickSystem(e); if (s) selectSystem(s[0]); }
      drag = null;
    });
    cv.addEventListener("mousemove", (e) => {
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
        M.view.tx = drag.tx + dx; M.view.ty = drag.ty + dy; drawMap(); return;
      }
      const s = pickSystem(e), tip = $("#m-tip");
      M.hover = s ? s[0] : null;
      if (!s) { tip.hidden = true; return; }
      const a = (M.live && M.live.activity[s[0]]) || [0, 0, 0, 0];
      const sov = M.live && M.live.sov[s[0]];
      tip.innerHTML = `<b>${esc(s[1])}</b> ${secBadge(s[4])} <span class="muted">${esc(M.regionName[s[5]] || "")}</span><br>${a[0]} kills · ${a[1]} capsules · ${a[2]} sauts · ${a[3]} PNJ (1 h)${sov ? "<br>" + esc(sov[0]) : ""}`;
      const r = cv.getBoundingClientRect();
      tip.style.left = Math.min(e.clientX - r.left + 14, r.width - 260) + "px"; tip.style.top = (e.clientY - r.top + 14) + "px"; tip.hidden = false;
    });
    cv.addEventListener("mouseleave", () => ($("#m-tip").hidden = true));
    cv.addEventListener("wheel", (e) => { e.preventDefault(); zoomAt(e.offsetX, e.offsetY, e.deltaY < 0 ? 1.25 : 0.8); }, { passive: false });
    $("#m-zin").onclick = () => zoomAt(cv.clientWidth / 2, cv.clientHeight / 2, 1.5);
    $("#m-zout").onclick = () => zoomAt(cv.clientWidth / 2, cv.clientHeight / 2, 0.67);
    $("#m-fit").onclick = () => { $("#m-region").value = ""; fitMap(); };
    $("#m-me").onclick = () => centerOnMe(true);
    ["#m-layer", "#m-jb", "#m-wh", "#m-chars"].forEach((id) => ($(id).onchange = () => { store.set("map." + id, $(id).type === "checkbox" ? $(id).checked : $(id).value); M.hl = null; drawMap(); legend(); renderHot(); }));
    $("#m-from-sel").addEventListener("change", () => renderHot());
    $("#m-region").onchange = () => fitMap($("#m-region").value ? +$("#m-region").value : null);
    $("#m-refresh").onclick = (ev) => busy(ev.target, async () => { await loadLive(); fillFrom(); drawMap(); renderThera(); toast("Kills, positions et Thera actualisés."); });
    autocomplete($("#m-search"), $("#m-search-list"), "/api/map/search?q=", (x) => { selectSystem(x.system_id, true); $("#m-search").value = ""; });
    autocomplete($("#m-from"), $("#m-from-list"), "/api/map/search?q=", () => {});
    autocomplete($("#m-to"), $("#m-to-list"), "/api/map/search?q=", () => calcRoute());
    autocomplete($("#m-home"), $("#m-home-list"), "/api/map/search?q=", () => {});
    $("#m-to").addEventListener("keydown", (e) => { if (e.key === "Enter" && !$("#m-to-list").classList.contains("open")) calcRoute(); });
    $("#m-from-sel").onchange = () => { $("#m-from-wrap").hidden = $("#m-from-sel").value !== "__other"; };
    $$("#m-mode-seg button").forEach((b) => (b.onclick = () => {
      $$("#m-mode-seg button").forEach((x) => x.classList.toggle("on", x === b));
      $("#m-mode").value = b.dataset.mode; if ($("#m-to").value.trim()) calcRoute();
    }));
    $("#m-route").onclick = (ev) => busy(ev.target, calcRoute);
    $("#m-jbimport").onclick = (ev) => busy(ev.target, async () => {
      const r = await api("/api/map/jump_bridges/import", { method: "POST", body: {} });
      $("#m-jbtext").value = r.text;
      G.settings.map = { ...(G.settings.map || {}), jb_text: r.text };
      $("#m-jbinfo").innerHTML = `${r.found} structure(s) trouvée(s) · ${r.added} pont(s) ajouté(s) · <b>${r.total}</b> au total` + (r.errors.length ? `<br><span class="neg">${r.errors.map(esc).join("<br>")}</span>` : "");
      M.data = null; M.adj = null; await loadMapData(); drawMap();
    });
    $("#m-jbsave").onclick = (ev) => busy(ev.target, async () => {
      const r = await api("/api/map/jump_bridges", { method: "POST", body: { text: $("#m-jbtext").value } });
      G.settings.map = { ...(G.settings.map || {}), jb_text: $("#m-jbtext").value };
      $("#m-jbinfo").textContent = `${r.count} pont(s) enregistré(s)` + (r.bad.length ? ` · ${r.bad.length} ligne(s) ignorée(s) : ${r.bad.slice(0, 3).join(" | ")}` : "");
      M.data = null; M.adj = null; await loadMapData(); drawMap();
    });
    $("#m-homesave").onclick = (ev) => busy(ev.target, async () => {
      await api("/api/map/jump_bridges", { method: "POST", body: { text: $("#m-jbtext").value, home: $("#m-home").value.trim() } });
      G.settings.map = { ...(G.settings.map || {}), home: $("#m-home").value.trim() };
      M.data = null; await loadMapData(); fillFrom(); drawMap(); toast("Système de base enregistré.");
    });
    ["#m-layer"].forEach((id) => { const v = store.get("map." + id, null); if (v) $(id).value = v; });
    ["#m-jb", "#m-wh", "#m-chars"].forEach((id) => { const v = store.get("map." + id, null); if (v !== null) $(id).checked = v; });
  }
  try {
    if (!M.data) await loadMapData();
  } catch (e) { $("#m-wrap").innerHTML = `<div class="warnbox" style="margin:20px">${esc(e.message)}</div>`; return; }
  sizeMap();
  const first = !M.view;
  if (first) fitMap();
  $("#m-home").value = (G.settings.map || {}).home || "";
  $("#m-jbtext").value = (G.settings.map || {}).jb_text || "";
  fillFrom();
  await loadLive();
  fillFrom();
  if (first) centerOnMe(false);
  drawMap(); legend(); renderThera();
}
function myPositions() {
  const out = ((M.live && M.live.characters) || []).filter((c) => M.byId[c.system_id]).map((c) => ({ label: `📍 ${c.name} — ${M.byId[c.system_id][1]}`, system: M.byId[c.system_id][1], id: c.system_id, cid: c.character_id }));
  if (M.data && M.data.home && M.byId[M.data.home]) out.push({ label: `🏠 Ma base — ${M.byId[M.data.home][1]}`, system: M.byId[M.data.home][1], id: M.data.home });
  return out;
}
function fillFrom() {
  const sel = $("#m-from-sel"), cur = sel.value, pos = myPositions();
  sel.innerHTML = pos.map((p, i) => `<option value="${i}">${esc(p.label)}</option>`).join("") + `<option value="__other">✏️ Autre système…</option>`;
  if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
  else if (!pos.length) sel.value = "__other";
  $("#m-from-wrap").hidden = sel.value !== "__other";
}
function fromSystem() {
  const v = $("#m-from-sel").value;
  if (v === "__other") return $("#m-from").value.trim();
  const p = myPositions()[+v];
  return p ? p.system : "";
}
function centerOnMe(toastIfNone) {
  const pos = myPositions();
  if (!pos.length) { if (toastIfNone) toast("Position inconnue : connecte un personnage (permission position) ou définis ta base.", true); return; }
  // cadre le voisinage : tous les systèmes à 6 sauts ou moins
  if (!M.adj) buildAdj();
  const near = Object.keys(jumpsFrom(pos[0].id, 6)).map((id) => M.byId[id]).filter(Boolean);
  const cv = $("#m-canvas"), W = cv.clientWidth, H = cv.clientHeight, me = M.byId[pos[0].id];
  let x0 = me[2], x1 = me[2], y0 = me[3], y1 = me[3];
  near.forEach((s) => { x0 = Math.min(x0, s[2]); x1 = Math.max(x1, s[2]); y0 = Math.min(y0, s[3]); y1 = Math.max(y1, s[3]); });
  const span = Math.max(x1 - x0, y1 - y0, 1e-6);
  const k = Math.min(80, Math.max(M.view.k, Math.min((W - 100) / Math.max(x1 - x0, span * 0.3), (H - 100) / Math.max(y1 - y0, span * 0.3))));
  M.view = { k, tx: W / 2 - k * me[2], ty: H / 2 - k * me[3], region: null };
  $("#m-region").value = "";
  drawMap();
}
async function loadMapData() {
  M.data = await api("/api/map/data");
  M.byId = {}; M.adj = null; M.regionName = {};
  M.data.systems.forEach((s) => (M.byId[s[0]] = s));
  M.order = null; M.orderKey = undefined;
  M.data.regions.forEach((r) => (M.regionName[r.id] = r.name));
  const reg = $("#m-region"), cur = reg.value;
  reg.innerHTML = `<option value="">Tout l'univers</option>` + M.data.regions.map((r) => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
  reg.value = cur;
}
async function loadLive() {
  try { M.live = await api("/api/map/live"); } catch (e) { M.live = { activity: {}, sov: {}, characters: [], wormholes: [], errors: [e.message] }; }
  M.liveStamp = Date.now(); M.orderKey = undefined;
  computeSov(); computeActivityMax();
  if (M.data) renderHot();
}
// ---------------------------------------------------------------- « Où ça ratte / se bat / passe »
function buildAdj() {
  M.adj = {};
  const add = (a, b) => { (M.adj[a] = M.adj[a] || []).push(b); (M.adj[b] = M.adj[b] || []).push(a); };
  M.data.edges.forEach(([a, b]) => add(a, b));
  (M.data.jump_bridges || []).forEach(([a, b]) => add(a, b));
}
function jumpsFrom(start, max) {
  const d = { [start]: 0 }, q = [start];
  while (q.length) { const u = q.shift(); if (d[u] >= max) continue; for (const v of M.adj[u] || []) if (d[v] == null) { d[v] = d[u] + 1; q.push(v); } }
  return d;
}
function renderHot() {
  const box = $("#m-hot"); if (!box || !M.data || !M.live) return;
  if (!M.adj) buildAdj();
  const lay = $("#m-layer").value, idx = ACT_IDX[lay] ?? 3;
  const title = { 0: "Où ça se bat", 1: "Où les capsules tombent", 2: "Où ça passe", 3: "Où ça ratte" }[idx];
  const unit = { 0: "kills", 1: "capsules", 2: "sauts", 3: "PNJ" }[idx];
  const range = $("#m-hot-range") ? $("#m-hot-range").value : store.get("map.hotRange", "10");
  const fromName = fromSystem(), from = M.data.systems.find((x) => x[1].toLowerCase() === (fromName || "").toLowerCase());
  const dist = from ? jumpsFrom(from[0], range === "all" ? 60 : +range) : null;
  const rows = Object.entries(M.live.activity).map(([id, a]) => ({ id: +id, v: a[idx], kills: a[0], s: M.byId[id] }))
    .filter((r) => r.s && r.v > 0 && (range === "all" || !dist || dist[r.id] != null))
    .sort((a, b) => b.v - a.v).slice(0, 15);
  box.innerHTML = `<div class="card"><h2>${title} <span class="muted" style="font-size:13px">dernière heure</span></h2><div class="body">
    <div class="wrow" style="margin-bottom:6px"><div class="field"><label>Autour de ${from ? esc(from[1]) : "moi"}</label><select id="m-hot-range">
      ${[["5", "5 sauts"], ["10", "10 sauts"], ["15", "15 sauts"], ["all", "Toute la galaxie"]].map(([v, l]) => `<option value="${v}" ${v === range ? "selected" : ""}>${l}</option>`).join("")}</select></div></div>
    ${rows.length ? rows.map((r) => `<div class="nbr" data-go="${r.id}"><span>${secBadge(r.s[4])} ${esc(r.s[1])} <span class="muted">${esc(M.regionName[r.s[5]] || "")}</span></span>
      <span><b>${r.v}</b> <span class="muted">${unit}</span>${idx !== 0 && r.kills ? ` <span class="neg">· ${r.kills} kills</span>` : ""}${dist && dist[r.id] != null ? ` <span class="muted">· ${dist[r.id]} saut${dist[r.id] > 1 ? "s" : ""}</span>` : ""}</span></div>`).join("")
      : '<p class="muted">Rien dans ce rayon pour la dernière heure.</p>'}
    <p class="hint">Change « Couleurs » au-dessus de la carte pour passer de ratting à kills ou trafic.</p></div></div>`;
  $("#m-hot-range").onchange = () => { store.set("map.hotRange", $("#m-hot-range").value); renderHot(); };
  $$("[data-go]", box).forEach((el) => (el.onclick = () => selectSystem(+el.dataset.go, true)));
}
function sizeMap() {
  const cv = $("#m-canvas"), dpr = window.devicePixelRatio || 1;
  cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
  if (M.view) drawMap();
}
function fitMap(regionId) {
  const cv = $("#m-canvas");
  const pts = M.data.systems.filter((s) => !regionId || s[5] === regionId);
  if (!pts.length) return;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  pts.forEach((s) => { x0 = Math.min(x0, s[2]); x1 = Math.max(x1, s[2]); y0 = Math.min(y0, s[3]); y1 = Math.max(y1, s[3]); });
  const W = cv.clientWidth, H = cv.clientHeight, pad = regionId ? 60 : 30;
  const k = Math.min((W - pad * 2) / Math.max(1e-6, x1 - x0), (H - pad * 2) / Math.max(1e-6, y1 - y0));
  M.view = { k, tx: W / 2 - k * (x0 + x1) / 2, ty: H / 2 - k * (y0 + y1) / 2, region: regionId || null };
  drawMap(); legend();
}
function zoomAt(x, y, f) {
  const v = M.view;
  v.tx = x - (x - v.tx) * f; v.ty = y - (y - v.ty) * f; v.k *= f;
  drawMap();
}
function pickSystem(e) {
  const r = $("#m-canvas").getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, v = M.view;
  let best = null, bd = 100;
  for (const s of M.data.systems) {
    const dx = s[2] * v.k + v.tx - x, dy = s[3] * v.k + v.ty - y, d = dx * dx + dy * dy;
    if (d < bd) { bd = d; best = s; }
  }
  return best;
}
function sysColor(s) {
  const layer = $("#m-layer").value, a = (M.live && M.live.activity[s[0]]) || [0, 0, 0, 0];
  const mx = M.actMax || [1, 1, 1, 1];
  const heat = (n, ref, col) => (n ? col.replace("A", Math.min(1, 0.45 + 0.55 * Math.sqrt(n / ref)).toFixed(2)) : "#1f2733");
  if (layer === "kills") return heat(a[0], mx[0], "rgba(255,70,50,A)");
  if (layer === "pods") return heat(a[1], mx[1], "rgba(255,150,40,A)");
  if (layer === "jumps") return heat(a[2], mx[2], "rgba(90,170,255,A)");
  if (layer === "npc") return heat(a[3], mx[3], "rgba(120,235,140,A)");
  if (layer === "sov") {
    const o = M.live && M.live.sov[s[0]];
    if (!o || !o[1]) return "#2a3445";
    if (M.hl && M.hl !== o[1]) return "#3a4352";
    return (M.sovColor && M.sovColor[o[1]]) || hashColor(String(o[1]));
  }
  return secColor(s[4]);
}
function drawMap() {
  cancelAnimationFrame(M.raf);
  M.raf = requestAnimationFrame(_draw);
  animateBridges();
}
function animateBridges() {
  if (M.anim) return;
  const tick = () => {
    const on = !$("#v-carte").hidden && $("#m-jb").checked && M.data && (M.data.jump_bridges || []).length && !document.hidden;
    if (!on) { M.anim = null; return; }
    _draw();
    M.anim = setTimeout(() => requestAnimationFrame(tick), 33);   // ~30 images/s
  };
  M.anim = setTimeout(tick, 33);
}
function _draw() {
  const cv = $("#m-canvas"); if (!cv || !M.data || !M.view) return;
  const dpr = window.devicePixelRatio || 1, v = M.view, W = cv.clientWidth, H = cv.clientHeight;
  // la carte (lourde) n'est redessinée que si quelque chose a changé ; seuls les ponts sont animés
  const key = [cv.width, cv.height, v.k, v.tx, v.ty, v.region, $("#m-layer").value, $("#m-jb").checked, $("#m-wh").checked,
    $("#m-chars").checked, M.sel, M.hl, M.liveStamp, M.route ? M.route.path.join(",") : "", M.data.home, (M.data.jump_bridges || []).length].join("|");
  if (!M.base || M.baseKey !== key) {
    M.base = M.base || document.createElement("canvas");
    M.base.width = cv.width; M.base.height = cv.height;
    _drawBase(M.base.getContext("2d"), dpr, v, W, H);
    M.baseKey = key;
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.drawImage(M.base, 0, 0);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  _drawBridges(ctx, v, W, H);
}
function _drawBase(ctx, dpr, v, W, H) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#05080d"; ctx.fillRect(0, 0, W, H);
  const P = (s) => [s[2] * v.k + v.tx, s[3] * v.k + v.ty];
  const inView = (x, y) => x > -50 && y > -50 && x < W + 50 && y < H + 50;
  const reg = v.region;
  // portes
  ctx.lineWidth = 1;
  for (const [a, b] of M.data.edges) {
    const A = M.byId[a], B = M.byId[b]; if (!A || !B) continue;
    const [x1, y1] = P(A), [x2, y2] = P(B);
    if (!inView(x1, y1) && !inView(x2, y2)) continue;
    const dim = reg && A[5] !== reg && B[5] !== reg;
    ctx.strokeStyle = dim ? "rgba(70,85,105,.12)" : A[5] !== B[5] ? "rgba(200,120,200,.35)" : "rgba(110,130,160,.35)";
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }
  // itinéraire
  if (M.route) {
    ctx.strokeStyle = "rgba(226,165,66,.95)"; ctx.lineWidth = 3;
    ctx.beginPath(); let first = true;
    for (const id of M.route.path) { const s = M.byId[id]; if (!s) continue; const [x, y] = P(s); first ? ctx.moveTo(x, y) : ctx.lineTo(x, y); first = false; }
    ctx.stroke();
  }
  // systèmes (les plus actifs dessinés en dernier, donc au-dessus)
  const r = Math.max(1.6, Math.min(6, v.k * 0.9));
  const li = ACT_IDX[$("#m-layer").value];
  const okey = li == null || !M.live ? null : li + ":" + (M.liveStamp || 0);
  if (M.orderKey !== okey) {
    M.orderKey = okey;
    M.order = okey == null ? M.data.systems : M.data.systems.slice().sort((p, q) => ((M.live.activity[p[0]] || [0, 0, 0, 0])[li]) - ((M.live.activity[q[0]] || [0, 0, 0, 0])[li]));
  }
  const order = M.order || M.data.systems;
  for (const s of order) {
    const [x, y] = P(s); if (!inView(x, y)) continue;
    const dim = reg && s[5] !== reg;
    ctx.globalAlpha = dim ? 0.25 : 1;
    ctx.fillStyle = sysColor(s);
    const a = (M.live && M.live.activity[s[0]]) || [0, 0, 0, 0];
    const idx = ACT_IDX[$("#m-layer").value];
    const boost = idx != null && a[idx] ? 1.5 + 9 * Math.sqrt(a[idx] / ((M.actMax || [1, 1, 1, 1])[idx] || 1)) : 0;
    ctx.beginPath(); ctx.arc(x, y, r + boost, 0, Math.PI * 2); ctx.fill();
  }
  ctx.globalAlpha = 1;
  // Thera / Turnur
  if ($("#m-wh").checked && M.live) {
    ctx.strokeStyle = "#c58bff"; ctx.lineWidth = 2;
    for (const w of M.live.wormholes || []) { const s = M.byId[w.system_id]; if (!s) continue; const [x, y] = P(s); ctx.beginPath(); ctx.arc(x, y, r + 4, 0, Math.PI * 2); ctx.stroke(); }
  }
  // noms
  ctx.textBaseline = "middle"; ctx.font = "12px Barlow, system-ui, sans-serif";
  if (v.k < 9 && !reg) {
    ctx.fillStyle = "rgba(200,210,225,.55)"; ctx.textAlign = "center"; ctx.font = "600 12px Barlow, system-ui, sans-serif";
    for (const rg of M.data.regions) { if (rg.n < 3) continue; const x = rg.x * v.k + v.tx, y = rg.y * v.k + v.ty; if (inView(x, y)) ctx.fillText(rg.name, x, y); }
  } else {
    ctx.textAlign = "left"; ctx.fillStyle = "rgba(220,228,238,.85)";
    const minGap = 14; let last = [];
    for (const s of M.data.systems) {
      if (reg && s[5] !== reg && v.k < 40) continue;
      const [x, y] = P(s); if (!inView(x, y)) continue;
      if (last.some(([lx, ly]) => Math.abs(lx - x) < 60 && Math.abs(ly - y) < minGap)) continue;
      ctx.fillText(s[1], x + r + 3, y); last.push([x, y]); if (last.length > 400) break;
    }
  }
  // persos
  if ($("#m-chars").checked && M.live) {
    const byS = {};
    (M.live.characters || []).forEach((c) => (byS[c.system_id] = (byS[c.system_id] || []).concat(c.name)));
    ctx.font = "600 12px Barlow, system-ui, sans-serif"; ctx.textAlign = "left";
    for (const [sid, names] of Object.entries(byS)) {
      const s = M.byId[sid]; if (!s) continue; const [x, y] = P(s);
      ctx.fillStyle = "#4fc1a6"; ctx.beginPath(); ctx.moveTo(x, y - r - 9); ctx.lineTo(x - 6, y - r - 18); ctx.lineTo(x + 6, y - r - 18); ctx.closePath(); ctx.fill();
      ctx.fillText(names.join(", "), x + 8, y - r - 14);
    }
  }
  // base + sélection
  const ring = (id, col, w) => { const s = M.byId[id]; if (!s) return; const [x, y] = P(s); ctx.strokeStyle = col; ctx.lineWidth = w; ctx.beginPath(); ctx.arc(x, y, r + 7, 0, Math.PI * 2); ctx.stroke(); };
  if (M.data.home) ring(M.data.home, "#4fc1a6", 2);
  if (M.sel) ring(M.sel, "#e2a542", 2.5);
}
function _drawBridges(ctx, v, W, H) {
  const P = (s) => [s[2] * v.k + v.tx, s[3] * v.k + v.ty];
  const inView = (x, y) => x > -50 && y > -50 && x < W + 50 && y < H + 50;
  // ponts de saut : traits lumineux et animés (au-dessus de tout)
  if ($("#m-jb").checked && (M.data.jump_bridges || []).length) {
    const t = performance.now() / 1000;
    ctx.save();
    ctx.lineCap = "round";
    for (const [a, b] of M.data.jump_bridges) {
      const A = M.byId[a], B = M.byId[b]; if (!A || !B) continue;
      const [x1, y1] = P(A), [x2, y2] = P(B);
      if (!inView(x1, y1) && !inView(x2, y2)) continue;
      const cx = (x1 + x2) / 2 + (y2 - y1) * 0.15, cy = (y1 + y2) / 2 - (x2 - x1) * 0.15;
      const path = () => { ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo(cx, cy, x2, y2); };
      ctx.shadowColor = "rgba(80,200,255,.9)"; ctx.shadowBlur = 10;
      ctx.strokeStyle = "rgba(60,170,255,.35)"; ctx.lineWidth = 4; ctx.setLineDash([]); path(); ctx.stroke();
      ctx.shadowBlur = 6;
      ctx.strokeStyle = "rgba(140,225,255,.95)"; ctx.lineWidth = 1.8; ctx.setLineDash([8, 7]); ctx.lineDashOffset = -t * 28; path(); ctx.stroke();
      // une étincelle qui voyage le long du pont
      const u = (t * 0.45 + ((a * 7 + b) % 100) / 100) % 1;
      const px = (1 - u) * (1 - u) * x1 + 2 * (1 - u) * u * cx + u * u * x2, py = (1 - u) * (1 - u) * y1 + 2 * (1 - u) * u * cy + u * u * y2;
      ctx.setLineDash([]); ctx.shadowBlur = 14; ctx.fillStyle = "#e8f8ff";
      ctx.beginPath(); ctx.arc(px, py, 2.6, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
}
function legend() {
  const l = $("#m-legend"), lay = $("#m-layer").value;
  setTimeout(() => $$("[data-hl]", l).forEach((el) => (el.onclick = () => { const id = +el.dataset.hl; M.hl = M.hl === id ? null : id; drawMap(); legend(); })), 0);
  const map = {
    sec: `Sécurité<i style="background:${SECC[10]}"></i>1,0<i style="background:${SECC[5]}"></i>0,5<i style="background:${SECC[4]}"></i>0,4<i style="background:${SECC[1]}"></i>0,1<i style="background:${SECC[0]}"></i>null`,
    kills: "Kills de vaisseaux, dernière heure : plus c'est rouge et gros, plus ça se bat", pods: "Capsules détruites, dernière heure",
    jumps: "Sauts, dernière heure : trafic", npc: "PNJ tués, dernière heure : là où ça ratte", sov: "Souveraineté : une couleur par alliance",
  };
  if (lay === "sov") {
    const top = (M.sovRank || []).slice(0, 12);
    map.sov = top.length ? `<b>Souveraineté</b> (${(M.sovRank || []).length} alliances, ${Object.keys((M.live && M.live.sov) || {}).length} systèmes) — clic = mettre en évidence<br>` +
      top.map((o) => `<span class="sov-item ${M.hl === o.id ? "on" : ""}" data-hl="${o.id}"><i style="background:${o.color}"></i>${esc(o.name)} (${o.n})</span>`).join(" ")
      : `<span class="neg">Aucune donnée de souveraineté reçue d'ESI.</span> Clique ↻ ; si ça persiste, CCP a peut-être changé l'API (lance verifier.bat).`;
  }
  if (ACT_IDX[lay] != null) map[lay] += ` — <b>plus le rond est gros, plus il y en a</b> (max : ${(M.actMax || [0, 0, 0, 0])[ACT_IDX[lay]]})`;
  l.innerHTML = map[lay] + `<br><span style="color:#c58bff">◯</span> Thera/Turnur · <span style="color:#8ce1ff">- - -</span> pont de saut (animé) · <span style="color:#4fc1a6">▼</span> tes persos · <span style="color:#e2a542">━</span> itinéraire`;
}
async function selectSystem(id, center) {
  M.sel = id;
  if (center && M.byId[id]) {
    const s = M.byId[id], cv = $("#m-canvas");
    if (M.view.k < 25) M.view.k = 25;
    M.view.tx = cv.clientWidth / 2 - s[2] * M.view.k; M.view.ty = cv.clientHeight / 2 - s[3] * M.view.k;
  }
  drawMap();
  const side = $("#m-sys");
  let d;
  try { d = await api("/api/map/system/" + id); } catch (e) { side.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; return; }
  const a = (M.live && M.live.activity[id]) || [0, 0, 0, 0];
  const sov = M.live && M.live.sov[id];
  const here = ((M.live && M.live.characters) || []).filter((c) => c.system_id === id);
  const chars = (G.status && G.status.characters) || [];
  side.innerHTML = `<div class="card"><div class="body">
    <h2 style="margin:0;font-size:26px">${esc(d.name)} ${secBadge(d.sec)}</h2>
    <div class="muted">${esc(d.region)} · ${esc(d.constellation)}${sov ? " · " + esc(sov[0]) : ""}</div>
    <div class="kpis" style="margin:10px 0"><div class="kpi"><span>Kills (1 h)</span><b class="${a[0] ? "neg" : ""}">${a[0]}</b></div><div class="kpi"><span>Capsules</span><b>${a[1]}</b></div><div class="kpi"><span>Sauts</span><b>${a[2]}</b></div><div class="kpi"><span>PNJ</span><b>${a[3]}</b></div></div>
    ${here.length ? `<p>${here.map((c) => `<span class="with-ico"><img class="ico s" style="border-radius:50%" src="${IMG}/characters/${c.character_id}/portrait?size=32" alt="">${esc(c.name)}${c.ship_type ? " — " + esc(c.ship_type) : ""}</span>`).join("")}</p>` : ""}
    ${d.wormholes.length ? `<div class="infobox">Trou de ver vers <b>${d.wormholes.map((w) => esc(w.hub || "Thera")).join(", ")}</b>${d.wormholes[0].ship_size ? " · taille max " + esc(d.wormholes[0].ship_size) : ""}${d.wormholes[0].remaining_hours ? " · ~" + d.wormholes[0].remaining_hours + " h restantes" : ""}</div>` : ""}
    <div class="big-actions"><button class="primary" id="ms-to">M'y emmener</button>${chars.length ? '<button id="ms-wp">Destination en jeu</button>' : ""}</div>
    ${chars.length > 1 ? `<div class="actions" style="margin-top:0"><span class="muted">Personnage :</span><select id="ms-char">${chars.map((c) => `<option value="${c.character_id}">${esc(c.name)}</option>`).join("")}</select></div>` : chars.length ? `<input type="hidden" id="ms-char" value="${chars[0].character_id}">` : ""}
    <div class="actions"><button class="small" id="ms-from">Partir d'ici</button><button class="small" id="ms-avoid">Éviter ce système</button><button class="small" id="ms-home">C'est ma base</button></div>
    <div class="side-links"><a href="${d.links.dotlan}" target="_blank" rel="noopener"><button class="small">Dotlan (système)</button></a><a href="${d.links.dotlan_region}" target="_blank" rel="noopener"><button class="small">Dotlan (carte région)</button></a><a href="${d.links.zkill}" target="_blank" rel="noopener"><button class="small">zKillboard</button></a></div>
    <div class="slot-title">Accès (${d.neighbors.length})</div>
    ${d.neighbors.map((n) => `<div class="nbr" data-go="${n.system_id}"><span>${secBadge(n.sec)} ${esc(n.name)} ${n.kind === "bridge" ? '<span class="tag" style="background:#17304a;color:#a8d0f5">pont</span>' : ""}</span><span class="muted">${esc(n.region !== d.region ? n.region : "")}</span></div>`).join("")}
  </div></div>`;
  $$("[data-go]", side).forEach((el) => (el.onclick = () => selectSystem(+el.dataset.go, true)));
  $("#ms-from").onclick = () => { $("#m-from-sel").value = "__other"; $("#m-from-wrap").hidden = false; $("#m-from").value = d.name; toast("Départ : " + d.name); };
  $("#ms-to").onclick = () => { $("#m-to").value = d.name; calcRoute(); };
  $("#ms-avoid").onclick = () => { const cur = $("#m-avoid").value.split(",").map((x) => x.trim()).filter(Boolean); if (!cur.includes(d.name)) cur.push(d.name); $("#m-avoid").value = cur.join(", "); toast(d.name + " sera évité."); };
  $("#ms-home").onclick = async () => { $("#m-home").value = d.name; await api("/api/map/jump_bridges", { method: "POST", body: { text: $("#m-jbtext").value, home: d.name } }); G.settings.map = { ...(G.settings.map || {}), home: d.name }; M.data.home = id; fillFrom(); drawMap(); toast(d.name + " est ta base."); };
  const wp = $("#ms-wp");
  if (wp) wp.onclick = () => busy(wp, async () => { await api("/api/map/waypoint", { method: "POST", body: { character_id: +$("#ms-char").value, system_id: id } }); toast("Destination définie en jeu (le personnage doit être connecté)."); });
}
async function calcRoute() {
  const src = fromSystem(), dst = $("#m-to").value.trim();
  if (!dst) return toast("Indique où tu veux aller.", true);
  if (!src) return toast("Choisis un départ (« Autre système… ») ou connecte un personnage.", true);
  const q = new URLSearchParams({ src, dst, mode: $("#m-mode").value,
    avoid: $("#m-avoid").value, jb: $("#m-use-jb").checked, wh: $("#m-use-wh").checked });
  const out = $("#m-route-out");
  let r;
  try { r = await api("/api/map/route?" + q); } catch (e) { out.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; return; }
  M.route = r; drawMap();
  const chars = (G.status && G.status.characters) || [];
  out.innerHTML = `<div class="card"><h2>${esc(r.steps[0].name)} → ${esc(r.steps[r.steps.length - 1].name)} <button class="small" id="mr-close">×</button></h2><div class="body">
    <div class="route-sum"><b>${r.jumps}</b> saut${r.jumps > 1 ? "s" : ""} ·
      <span style="color:${SECC[9]}">${r.counts.high} high</span> / <span style="color:${SECC[3]}">${r.counts.low} low</span> / <span style="color:#d36a9a">${r.counts.null} null</span>
      · <span class="${r.kills ? "neg" : "muted"}">${r.kills} kill${r.kills > 1 ? "s" : ""} (1 h)</span>
      ${r.bridges ? ` · ${r.bridges} pont${r.bridges > 1 ? "s" : ""}` : ""}${r.wormholes ? ` · ${r.wormholes} trou${r.wormholes > 1 ? "s" : ""} de ver` : ""}</div>
    <div class="actions">${chars.length ? `<button class="small primary" id="mr-wp">Destination en jeu</button>${chars.length > 1 ? `<select id="mr-char">${chars.map((c) => `<option value="${c.character_id}">${esc(c.name)}</option>`).join("")}</select>` : `<input type="hidden" id="mr-char" value="${chars[0].character_id}">`}` : ""}
      <a href="${r.dotlan}" target="_blank" rel="noopener"><button class="small">Dotlan</button></a>
      <button class="small" id="mr-copy">Copier</button></div>
    ${r.bridges || r.wormholes ? `<p class="hint">Le pilote automatique du jeu ne prend pas les ponts ni les trous de ver : la destination en jeu suivra les portes. Suis la liste ci-dessous.</p>` : ""}
    <div class="route-list" style="max-height:360px">${r.steps.map((s, i) => `<div class="route-step" data-go="${s.system_id}"><span class="muted">${i}</span>${s.sec_class === "wh" ? '<span class="secb" style="background:#c58bff">W</span>' : secBadge(s.sec)}<span>${esc(s.name)} <span class="muted">${esc(s.region)}</span> ${s.via === "bridge" ? '<span class="via">par pont</span>' : s.via === "wormhole" ? '<span class="via" style="color:#c58bff">par trou de ver</span>' : ""}</span><span class="${s.kills ? "neg" : "muted"}">${s.kills ? s.kills + " kills" : ""}</span></div>`).join("")}</div></div></div>`;
  $("#mr-close").onclick = () => { M.route = null; out.innerHTML = ""; drawMap(); };
  const fromPos = myPositions()[+$("#m-from-sel").value];
  if (fromPos && fromPos.cid && $("#mr-char") && $("#mr-char").tagName === "SELECT") $("#mr-char").value = fromPos.cid;
  const ids = r.path.filter((x) => M.byId[x]);
  if (ids.length) {   // cadrer la carte sur le trajet
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    ids.forEach((x) => { const s = M.byId[x]; x0 = Math.min(x0, s[2]); x1 = Math.max(x1, s[2]); y0 = Math.min(y0, s[3]); y1 = Math.max(y1, s[3]); });
    const cv = $("#m-canvas"), W = cv.clientWidth, H = cv.clientHeight;
    const k = Math.min(60, Math.min((W - 120) / Math.max(1e-6, x1 - x0), (H - 120) / Math.max(1e-6, y1 - y0)));
    M.view = { k, tx: W / 2 - k * (x0 + x1) / 2, ty: H / 2 - k * (y0 + y1) / 2, region: null };
    $("#m-region").value = ""; drawMap();
  }
  $$(".route-step", out).forEach((el) => (el.onclick = () => { const id = +el.dataset.go; if (M.byId[id]) selectSystem(id, true); }));
  $("#mr-copy").onclick = () => copyText(r.steps.map((s) => s.name).join(" > "), "Trajet copié.");
  const wp = $("#mr-wp");
  if (wp) wp.onclick = () => busy(wp, async () => { await api("/api/map/waypoint", { method: "POST", body: { character_id: +$("#mr-char").value, system_id: r.path[r.path.length - 1] } }); toast("Destination définie en jeu."); });
}
function renderThera() {
  const box = $("#m-thera"), w = (M.live && M.live.wormholes) || [];
  if (!w.length) { box.innerHTML = `<p class="muted">Aucune connexion connue (ou EVE-Scout injoignable).</p>`; return; }
  box.innerHTML = `<div class="tscroll" style="max-height:300px"><table><thead><tr><th>Vers</th><th>Système</th><th>Région</th><th>Taille</th><th class="num">Reste</th></tr></thead><tbody>${w.slice().sort((a, b) => (a.region || "").localeCompare(b.region || "")).map((x) => `<tr class="click" data-go="${x.system_id}"><td>${esc(x.hub || "Thera")}</td><td>${M.byId[x.system_id] ? secBadge(M.byId[x.system_id][4]) + " " : ""}${esc(x.system)}</td><td>${esc(x.region)}</td><td>${esc(x.ship_size || "")}</td><td class="num">${x.remaining_hours != null ? x.remaining_hours + " h" : ""}</td></tr>`).join("")}</tbody></table></div>
    <p class="hint">Données EVE-Scout (Signal Cartel), mises à jour par des volontaires. Clique une ligne pour la voir sur la carte.</p>`;
  $$("tr[data-go]", box).forEach((tr) => (tr.onclick = () => { const id = +tr.dataset.go; if (M.byId[id]) selectSystem(id, true); }));
}

// ---------------------------------------------------------------- PLANÉTAIRE (PI)
const PIX = { tab: 4, data: null };
const piIcon = (tid, cls = "s") => ico(tid, cls);
const tierB = (t) => `<span class="tierbadge t${t}">P${t}</span>`;
async function initPI() {
  if (!PIX.ready) {
    PIX.ready = true;
    autocomplete($("#pi-sys"), $("#pi-sys-list"), "/api/map/search?q=", () => {});
    $("#pi-from").onchange = () => ($("#pi-other-wrap").hidden = $("#pi-from").value !== "__other");
    $("#pi-run").onclick = (ev) => busy(ev.target, runPI);
    $("#pi-jumps").value = store.get("pi.jumps", "3");
  }
  // centre : positions des persos (chargées en arrière-plan) + base
  fillPIFrom(M.live);
  if (!M.live && !PIX.liveLoading) {
    PIX.liveLoading = true;
    api("/api/map/live").then((l) => { M.live = M.live || l; fillPIFrom(l); }).catch(() => {}).finally(() => (PIX.liveLoading = false));
  }
}
function fillPIFrom(live) {
  live = live || { characters: [] };
  const opts = (live.characters || []).map((c) => [c.system_id, `📍 ${c.name}`]);
  const home = (G.settings.map || {}).home;
  const sel = $("#pi-from"), cur = sel.value;
  sel.innerHTML = opts.map(([id, l]) => `<option value="id:${id}">${esc(l)}</option>`).join("") + (home ? `<option value="name:${esc(home)}">🏠 ${esc(home)}</option>` : "") + `<option value="__other">✏️ Autre système…</option>`;
  if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur; else if (!opts.length && !home) sel.value = "__other";
  $("#pi-other-wrap").hidden = sel.value !== "__other";
}
async function piCenterName() {
  const v = $("#pi-from").value;
  if (v === "__other") return $("#pi-sys").value.trim();
  if (v.startsWith("name:")) return v.slice(5);
  if (v.startsWith("id:")) { const d = await api("/api/map/system/" + v.slice(3)); return d.name; }
  return "";
}
async function runPI() {
  const center = await piCenterName();
  if (!center) return toast("Choisis un système.", true);
  store.set("pi.jumps", $("#pi-jumps").value);
  $("#pi-out").innerHTML = `<div class="empty">Analyse des planètes…</div>`;
  const r = await api(`/api/pi/area?system=${encodeURIComponent(center)}&jumps=${$("#pi-jumps").value}`);
  PIX.data = r; PIX.center = center;
  renderPI();
}
function renderPI() {
  const r = PIX.data, out = $("#pi-out");
  const kinds = Object.entries(r.kinds);
  const p0ok = r.p0.filter((p) => p.systems > 0).length;
  out.innerHTML = `
    <div class="kpis"><div class="kpi"><span>Systèmes dans le rayon</span><b>${r.systems_in_range}</b></div>
      <div class="kpi"><span>Planètes</span><b>${r.planets}</b></div>
      <div class="kpi"><span>Ressources P0 disponibles</span><b>${p0ok} / ${r.p0.length}</b></div>
      <div class="kpi"><span>Produits faisables à 100 %</span><b>${r.products.filter((p) => p.feasible).length} / ${r.products.length}</b></div></div>
    <div class="card"><h2>Planètes autour de ${esc(r.center_name)}</h2><div class="body"><div class="pi-kinds">${kinds.map(([k, n]) => `
      <div class="pi-kind ${n ? "" : "none"}"><img src="${IMG}/types/${r.kind_types[k] || 11}/icon?size=64" alt="" onerror="this.style.visibility='hidden'"><div><b>${n}</b>${esc(k)}</div></div>`).join("")}</div>
      <div class="slot-title" style="margin-top:10px">Ressources brutes (P0)</div>
      <div>${r.p0.map((p) => `<span class="p0chip ${p.systems ? "ok" : "ko"}" title="${esc(p.planets.join(", "))} · ${p.systems} système(s)">${piIcon(p.type_id)}${esc(p.name)} <span class="muted">${p.systems}</span></span>`).join("")}</div>
      <p class="hint">Le chiffre = nombre de systèmes du rayon qui ont cette ressource. Survole pour voir les types de planètes.</p></div></div>
    <div class="grid2">
      <div class="card"><h2>Ce que tu peux produire</h2><div class="body">
        <div class="tabs" style="margin-top:0">${[4, 3, 2, 1].map((t) => `<button data-tier="${t}" class="${PIX.tab === t ? "active" : ""}">P${t}</button>`).join("")}</div>
        <label class="check" style="padding:0 0 8px"><input type="checkbox" id="pi-only" ${store.get("pi.only", true) ? "checked" : ""}> Seulement ce qui est faisable à 100 % dans le rayon</label>
        <div id="pi-prod"></div></div></div>
      <div id="pi-detail"><div class="card"><div class="body muted">Clique sur un produit pour voir sa chaîne P0 → P4 et les meilleurs systèmes.</div></div></div>
    </div>
    <div class="card"><h2>Systèmes les plus riches du rayon</h2><div id="pi-sys-table"></div></div>`;
  $$("[data-tier]", out).forEach((b) => (b.onclick = () => { PIX.tab = +b.dataset.tier; renderPI(); }));
  $("#pi-only").onchange = () => { store.set("pi.only", $("#pi-only").checked); renderProducts(); };
  renderProducts();
  $("#pi-sys-table").append(table(r.systems, [
    { k: "name", label: "Système", fmt: (v, x) => `${secBadge(x.sec)} ${esc(v)} <span class="muted">${esc(x.region)}</span>` },
    { k: "jumps", label: "Sauts", num: true }, { k: "planets", label: "Planètes", num: true },
    { k: "p0_count", label: "P0 différents", num: true },
    { k: "kinds", label: "Types", fmt: (v) => Object.entries(v).map(([k, n]) => `${n}× ${esc(k)}`).join(", ") },
  ], { sortKey: "p0_count", onClick: (x) => piSystem(x.system_id) }));
}
function renderProducts() {
  const r = PIX.data, only = $("#pi-only").checked;
  const rows = r.products.filter((p) => p.tier === PIX.tab && (!only || p.feasible));
  const box = $("#pi-prod"); box.innerHTML = "";
  if (!rows.length) { box.innerHTML = `<p class="muted">Rien à ce niveau avec les ressources du rayon. Élargis le rayon ou décoche le filtre.</p>`; return; }
  box.append(table(rows, [
    { k: "name", label: "Produit", fmt: (v, x) => withIco(x.type_id, esc(v) + `<div>${x.p0.map((p) => `<span class="p0chip ${p.ok ? "ok" : "ko"}">${esc(p.name)}</span>`).join("")}</div>`, "s") },
    { k: "sell", label: `Prix ${esc(r.market || "")}`, num: true, fmt: isk },
    { k: "margin_hour", label: "Marge / h ⓘ", num: true, fmt: isk, cls: (x) => cls(x.margin_hour) },
    { k: "solo_systems", label: "Systèmes tout-en-un", num: true },
  ], { sortKey: "margin_hour", onClick: (x) => piProduct(x.type_id) }));
  box.insertAdjacentHTML("beforeend", `<p class="hint">ⓘ Marge par heure d'une usine qui achète ses intrants au prix du marché. « Tout-en-un » : systèmes qui fournissent à eux seuls toutes les ressources P0 nécessaires.</p>`);
}
function treeHtml(n) {
  return `<li><div class="row">${tierB(n.tier)}${piIcon(n.type_id)}<b>${n0(n.qty)}</b> ${esc(n.name)}${n.planets ? ` <span class="muted">— ${n.planets.join(", ")}</span>` : ""}</div>${n.children ? `<ul>${n.children.map(treeHtml).join("")}</ul>` : ""}</li>`;
}
async function piProduct(tid) {
  const d = await api(`/api/pi/product/${tid}?system=${encodeURIComponent(PIX.center)}&jumps=${$("#pi-jumps").value}`);
  const box = $("#pi-detail");
  box.innerHTML = `<div class="card"><h2>${withIco(d.type_id, `${tierB(d.tier)} ${esc(d.name)}`)}</h2><div class="body">
    <p class="muted" style="margin-top:0">${d.out_qty} unité(s) toutes les ${Math.round(d.cycle_s / 60)} min à partir de : ${d.inputs.map((i) => `${i.qty} × ${esc(i.name)}`).join(", ")} · prix ${isk(d.price)}</p>
    <div class="slot-title">Chaîne complète pour 1 unité</div>
    <div class="pi-tree"><ul>${treeHtml(d.tree)}</ul></div>
    <div class="slot-title">Ressources P0 et planètes nécessaires</div>
    <div>${d.p0.map((p) => `<span class="p0chip">${piIcon(p.type_id)}${esc(p.name)} <span class="muted">(${p.planets.join(", ")})</span></span>`).join("")}</div>
    <div class="slot-title">Meilleurs systèmes dans le rayon</div><div id="pi-best"></div></div></div>`;
  $("#pi-best").append(table(d.best, [
    { k: "name", label: "Système", fmt: (v, x) => `${secBadge(x.sec)} ${esc(v)} <span class="muted">${x.jumps} saut(s)</span>` },
    { k: "coverage", label: "P0 couverts", num: true, fmt: (v, x) => `<span class="${v === x.needed ? "pos" : ""}">${v} / ${x.needed}</span>` },
    { k: "useful_planets", label: "Planètes utiles", num: true },
    { k: "missing", label: "Manque", fmt: (v) => (v.length ? esc(v.join(", ")) : '<span class="pos">rien</span>') },
  ], { sortKey: "coverage", onClick: (x) => piSystem(x.system_id) }));
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}
async function piSystem(sid) {
  const d = await api("/api/pi/system/" + sid);
  const box = $("#pi-detail");
  box.innerHTML = `<div class="card"><h2>${secBadge(d.sec)} ${esc(d.name)} <span class="muted" style="font-size:14px">${esc(d.region)}</span></h2><div class="body">
    ${d.planets.map((p) => `<div class="pilot-card"><div class="top"><span class="with-ico"><img class="ico" src="${IMG}/types/${p.type_id}/icon?size=64" alt="" style="border-radius:50%"><b>${esc(p.name)}</b> <span class="muted">${esc(p.kind || "fracturée (pas de PI)")}</span></span></div>
      <div style="margin-top:6px">${p.p0.map((x) => `<span class="p0chip">${piIcon(x.type_id)}${esc(x.name)}</span>`).join("")}</div></div>`).join("")}
    <div class="actions"><a href="${d.dotlan}" target="_blank" rel="noopener"><button class="small">Dotlan</button></a><button class="small" id="pi-onmap">Voir sur la carte</button></div></div></div>`;
  $("#pi-onmap").onclick = async () => { location.hash = "carte"; setTimeout(() => selectSystem(sid, true), 600); };
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------- SOUTENIR COCKPIT
async function renderDonate() {
  const out = $("#don-out");
  out.innerHTML = `<div class="empty">…</div>`;
  let d;
  try { d = await api("/api/donate"); } catch { d = { name: "Robapin" }; }
  const chars = (G.status && G.status.characters) || [];
  out.innerHTML = `
    <div class="don-hero">${d.character_id ? `<img src="${IMG}/characters/${d.character_id}/portrait?size=256" alt="${esc(d.name)}">` : `<img alt="">`}
      <div><h1>Soutenir Cockpit</h1>
        <p>Cockpit est gratuit, sans publicité, et le restera. Si l'outil t'a fait gagner du temps, des ISK ou une fleet, un don en ISK au développeur aide à financer les prochaines fonctions.</p>
        <div class="big-name">${esc(d.name)}</div>
        <div class="muted">${esc(d.corporation || "")}${d.alliance ? " · " + esc(d.alliance) : ""}</div>
        <div class="actions"><button class="primary" id="don-copy">Copier le nom</button>
          ${chars.length ? `<select id="don-char">${chars.map((c) => `<option value="${c.character_id}">${esc(c.name)}</option>`).join("")}</select><button id="don-open">Ouvrir sa fiche dans mon jeu</button>` : ""}</div>
      </div></div>
    <h2 style="font-size:22px">Comment faire un don en 30 secondes</h2>
    <div class="don-steps">
      <div class="don-step"><b>Ouvre sa fiche</b>${chars.length ? "Clique « Ouvrir sa fiche dans mon jeu » (ton perso doit être connecté en jeu)" : "En jeu, tape son nom dans la recherche (en haut à gauche) et ouvre sa fiche"}.</div>
      <div class="don-step"><b>Clic droit sur le portrait</b>puis « Donner de l'argent » (Give Money).</div>
      <div class="don-step"><b>Choisis le montant</b>et écris « Cockpit » en motif, pour qu'on sache d'où vient le soutien.</div>
    </div>
    <div class="card" style="margin-top:18px"><h2>À quoi servent les dons ?</h2><div class="body">
      <p style="margin-top:0">Chaque don finance du temps de développement : nouvelles fonctions (statistiques de fit, killboard de corpo, traductions complètes), corrections après les patchs de CCP, et le maintien d'un outil gratuit pour tous. Aucun avantage en jeu n'est vendu : tout le monde a le même Cockpit.</p>
      <p class="hint">Les ISK sont une monnaie de jeu : un don ne peut pas être converti en argent réel, conformément aux règles d'EVE Online.</p></div></div>`;
  $("#don-copy").onclick = () => copyText(d.name, `« ${d.name} » copié : colle-le dans la recherche du jeu.`);
  const op = $("#don-open");
  if (op) op.onclick = () => busy(op, async () => { await api("/api/donate/open", { method: "POST", body: { character_id: +$("#don-char").value } }); toast("Fiche ouverte dans ton jeu : clic droit sur le portrait → Donner de l'argent."); });
}

// ---------------------------------------------------------------- démarrage
function renderLangSwitch() {
  const box = $("#lang-switch");
  if (!box || !window.I18N) return;
  box.innerHTML = Object.entries(I18N.langs).map(([k, v]) => `<button class="${I18N.lang === k ? "on" : ""}" data-lang="${k}" title="${v}">${k.toUpperCase()}</button>`).join("");
  $$("[data-lang]", box).forEach((b) => (b.onclick = () => I18N.set(b.dataset.lang)));
}
(async function init() {
  renderLangSwitch();
  await loadSettings();
  setupProduction(); setupInvention(); setupScan(); setupArb(); setupStructures(); setupDoctrines(); setupIntel();
  bindHelp();
  await refreshStatus();
  route();
  pollAlarm();   // l'alarme sonne quel que soit l'onglet ouvert
})();
