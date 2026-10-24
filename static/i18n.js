/* Cockpit — traduction de l'interface.
   Le texte source de l'interface est le français. Les dictionnaires (i18n-data.js) donnent, pour chaque texte
   français, sa traduction anglaise (base) et, quand elle existe, espagnole, allemande et russe.
   Une clé peut contenir {n} (nombre) ou {x} (texte quelconque) pour les textes générés.
   Langue par défaut : anglais. Espagnol, allemand, russe : repli sur l'anglais si un texte manque. */
(function () {
  const LANGS = { en: "English", fr: "Français", es: "Español", de: "Deutsch", ru: "Русский" };
  let lang = "en";
  try { lang = localStorage.getItem("cockpit.lang") || "en"; } catch { /* */ }   // anglais par défaut
  if (!LANGS[lang]) lang = "en";
  const D = window.I18N_DATA || { en: {} };
  const norm = (s) => s.replace(/\s+/g, " ").trim();
  const patterns = {};
  function compile(l) {
    if (patterns[l]) return patterns[l];
    const list = [];
    for (const k of Object.keys(D[l] || {})) {
      if (!/\{[nx]\}/.test(k)) continue;
      const parts = k.split(/(\{[nx]\})/);
      const keys = [];
      const rx = parts.map((p) => {
        if (p === "{n}") { keys.push("n"); return "([-+]?[\\d\\s\\u00a0.,]*\\d(?:[.,]\\d+)?\\s?(?:k|M|Md)?)"; }
        if (p === "{x}") { keys.push("x"); return "(.+?)"; }
        return p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      }).join("");
      list.push({ re: new RegExp("^" + rx + "$"), out: D[l][k] });
    }
    return (patterns[l] = list);
  }
  function lookup(l, s) {
    const t = (D[l] || {})[s];
    if (t) return t;
    for (const p of compile(l)) {
      const m = s.match(p.re);
      if (m) { let i = 1; return p.out.replace(/\{[nx]\}/g, () => m[i++]); }
    }
    return null;
  }
  function tr(s) {
    if (lang === "fr" || !s) return s;
    let n = norm(s);
    if (!n || !/[A-Za-zÀ-ÿ]/.test(n)) return s;
    const arrow = n.match(/\s*[▾▴]$/);          // flèche de tri des tableaux
    if (arrow) n = n.slice(0, -arrow[0].length);
    const t = lookup(lang, n) || (lang !== "en" ? lookup("en", n) : null);
    if (!t) return s;
    const lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0];
    return lead + t + (arrow ? arrow[0] : "") + trail;
  }
  const ATTRS = ["placeholder", "title", "aria-label"];
  function translate(root) {
    if (lang === "fr" || !root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.parentNode && /^(SCRIPT|STYLE|TEXTAREA|CODE)$/.test(n.parentNode.nodeName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const n of nodes) {
      if (n.__i18nOut === n.nodeValue) continue;
      const src = n.__i18nSrc && n.__i18nOut === n.nodeValue ? n.__i18nSrc : n.nodeValue;
      const out = tr(src);
      if (out !== n.nodeValue) { n.__i18nSrc = src; n.__i18nOut = out; n.nodeValue = out; }
    }
    const els = root.querySelectorAll ? root.querySelectorAll(ATTRS.map((a) => `[${a}]`).join(",")) : [];
    for (const el of [root, ...els]) {
      if (!el.getAttribute) continue;
      for (const a of ATTRS) {
        const v = el.getAttribute(a);
        if (!v) continue;
        const key = "__i18n_" + a;
        if (el[key] === v) continue;
        const out = tr(v);
        if (out !== v) { el.setAttribute(a, out); el[key] = out; }
      }
    }
  }
  let pending = false;
  const obs = new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; obs.disconnect(); translate(document.body); start(); });
  });
  function start() { obs.observe(document.body, { childList: true, subtree: true, characterData: true }); }
  window.I18N = {
    langs: LANGS, get lang() { return lang; }, tr,
    set(l) { try { localStorage.setItem("cockpit.lang", l); } catch { /* */ } location.reload(); },
  };
  document.documentElement.lang = lang;
  document.addEventListener("DOMContentLoaded", () => { translate(document.body); start(); });
})();
