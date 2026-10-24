"""Génère le site de présentation de Cockpit (statique, 5 langues) dans site/dist/.

    python site/build.py

Puis publie le dossier site/dist (GitHub Pages, Netlify…). Réglages ci-dessous.
"""
import html
import os
import shutil

# ---------------------------------------------------------------- réglages
DONATE_CHARACTER = "Robapin"
DOWNLOAD_URL = "https://github.com/TON-COMPTE/cockpit/releases/latest"     # page de téléchargement de l'exe
SOURCE_URL = "https://github.com/TON-COMPTE/cockpit"                        # code source
SITE_URL = "https://TON-COMPTE.github.io/cockpit"                           # adresse publique du site
LANGS = ["en", "fr", "es", "de", "ru"]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dist")
C = {}
for f in ("content_en_fr.py", "content_es.py", "content_de.py", "content_ru.py"):
    exec(open(os.path.join(HERE, f), encoding="utf-8").read())
ICONS = {"doctrines": "⚔", "map": "✦", "alarm": "◉", "planetary": "◐", "production": "⚙", "dscan": "◎", "invention": "⚗",
         "opportunities": "▲", "arbitrage": "⇄", "characters": "☰", "jobs": "⏱"}
e = html.escape


def page(lang, path, title, desc, body, depth):
    T = C[lang]
    root = "../" * depth
    alt = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE_URL}/{l}/{path}">' for l in LANGS)
    switch = "".join(f'<a href="{root}{l}/{path}" class="{ "on" if l == lang else ""}" data-setlang="{l}">{l.upper()}</a>' for l in LANGS)
    nav = T["nav"]
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{SITE_URL}/assets/map-sov.png"><meta name="twitter:card" content="summary_large_image">
{alt}<link rel="icon" href="{root}assets/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}assets/site.css"></head>
<body><header class="top"><div class="wrap">
<a class="logo" href="{root}{lang}/index.html"><span class="mark"></span>Cockpit</a>
<nav><a href="{root}{lang}/index.html#features">{e(nav['features'])}</a><a href="{root}{lang}/index.html#faq">{e(nav['faq'])}</a>
<a href="{root}{lang}/donate.html" class="heart">{e(nav['donate'])} ♥</a><a href="{root}{lang}/download.html" class="btn small">{e(nav['download'])}</a></nav>
<div class="langs">{switch}</div></div></header>
<main>{body}</main>
<footer><div class="wrap"><p><b>Cockpit</b> — {e(T['footer_made'])} · <a href="{SOURCE_URL}">GitHub</a> · <a href="{root}{lang}/donate.html">{e(nav['donate'])} ♥</a></p>
<p class="legal">{e(T['footer_legal'])}</p></div></footer>
<script>window.DONATE_CHARACTER = {DONATE_CHARACTER!r}; window.COPIED = {T['copied']!r};</script>
<script src="{root}assets/site.js"></script></body></html>"""


def donate_block(lang, root, full=False):
    T = C[lang]
    steps = "".join(f'<li><b>{e(a)}</b><span>{e(b)}</span></li>' for a, b in T["donate_steps"])
    return f"""<section class="donate {'full' if full else ''}" id="donate"><div class="wrap donate-grid">
<div class="donate-card"><img class="portrait" data-portrait alt="{e(DONATE_CHARACTER)}" src="{root}assets/portrait.svg">
<div class="pname" data-pname>{e(DONATE_CHARACTER)}</div><div class="pcorp" data-pcorp></div>
<button class="btn" data-copy="{e(DONATE_CHARACTER)}">{e(T['copy_name'])}</button></div>
<div><h2>{e(T['donate_title'])}</h2><p class="lead">{e(T['donate_text'])}</p><ol class="steps">{steps}</ol>
<p class="tip">{e(T['donate_in_app'])}</p><p class="small muted">{e(T['donate_note'])}</p></div></div></section>"""


def index(lang):
    T, root = C[lang], "../"
    trust = "".join(f"<li>✓ {e(t)}</li>" for t in T["trust"])
    pillars = "".join(f'<div class="pillar"><h3>{e(a)}</h3><p>{e(b)}</p></div>' for a, b in T["pillars"])
    cards = ""
    for fid in FEATURES_ORDER:
        F = T["F"][fid]
        shot = SHOTS.get(fid)
        media = f'<img src="{root}assets/{shot}" alt="" loading="lazy">' if shot else f'<div class="glyph">{ICONS[fid]}</div>'
        cards += f"""<a class="fcard {CAT[fid]}" href="features/{fid}.html">{media}<div class="fbody"><h3>{e(F['t'])}</h3><p>{e(F['s'])}</p><span class="more">{e(T['learn_more'])} →</span></div></a>"""
    how = "".join(f'<div class="how"><span class="n">{i + 1}</span><h3>{e(a)}</h3><p>{e(b)}</p></div>' for i, (a, b) in enumerate(T["how_steps"]))
    faq = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in T["faq"])
    body = f"""<section class="hero"><div class="wrap hero-grid"><div>
<p class="kicker">{e(T['hero_kicker'])}</p><h1>{T['hero_title']}</h1><p class="lead">{e(T['hero_sub'])}</p>
<div class="ctas"><a class="btn big" href="download.html">{e(T['cta_download'])}</a><a class="btn ghost big" href="#features">{e(T['cta_features'])}</a></div>
<ul class="trust">{trust}</ul></div>
<div class="hero-shot"><img src="{root}assets/map-sov.png" alt=""><img class="float" src="{root}assets/fit.png" alt=""></div></div></section>
<section class="pillars"><div class="wrap"><h2>{e(T['pillars_title'])}</h2><div class="pillar-grid">{pillars}</div></div></section>
<section id="features"><div class="wrap"><h2>{e(T['features_title'])}</h2><p class="muted center">{e(T['features_sub'])}</p><div class="fgrid">{cards}</div></div></section>
<section class="howto"><div class="wrap"><h2>{e(T['how_title'])}</h2><div class="how-grid">{how}</div>
<p class="center"><a class="btn big" href="download.html">{e(T['cta_download'])}</a></p></div></section>
<section id="faq"><div class="wrap narrow"><h2>{e(T['faq_title'])}</h2>{faq}</div></section>
{donate_block(lang, root)}"""
    return page(lang, "index.html", T["meta_desc"].split(":")[0].strip(), T["meta_desc"], body, 1)


def feature(lang, fid):
    T, root = C[lang], "../../"
    F = T["F"][fid]
    shot = SHOTS.get(fid)
    extra = SHOTS.get("hunt") if fid == "map" else (SHOTS.get("doctrines") and "doctrines.png" if fid == "doctrines" else None)
    media = f'<div class="shot"><img src="{root}assets/{shot}" alt=""></div>' if shot else f'<div class="glyph big">{ICONS[fid]}</div>'
    if extra:
        media += f'<div class="shot"><img src="{root}assets/{extra}" alt="" loading="lazy"></div>'
    bens = "".join(f'<div class="ben"><h3>{e(a)}</h3><p>{e(b)}</p></div>' for a, b in F["b"])
    steps = "".join(f'<li>{e(s)}</li>' for s in F["h"])
    others = "".join(f'<a href="{o}.html">{ICONS[o]} {e(T["F"][o]["t"])}</a>' for o in FEATURES_ORDER if o != fid)
    body = f"""<section class="fhero {CAT[fid]}"><div class="wrap"><a class="back" href="../index.html#features">{e(T['back'])}</a>
<h1><span class="ico">{ICONS[fid]}</span> {e(F['t'])}</h1><p class="lead">{e(F['s'])}</p></div></section>
<section><div class="wrap">{media}<div class="ben-grid">{bens}</div>
<div class="flow"><ol>{steps}</ol></div>
<p class="center"><a class="btn big" href="../download.html">{e(T['feature_cta'])}</a></p>
<div class="others">{others}</div></div></section>
{donate_block(lang, root)}"""
    return page(lang, f"features/{fid}.html", f"{F['t']} — Cockpit", F["s"], body, 2)


def download(lang):
    T, root = C[lang], "../"
    steps = "".join(f'<div class="how"><span class="n">{i + 1}</span><h3>{e(a)}</h3><p>{e(b)}</p></div>' for i, (a, b) in enumerate(T["download_steps"]))
    req = "".join(f"<li>{e(r)}</li>" for r in T["req"])
    body = f"""<section class="fhero"><div class="wrap"><h1>{e(T['download_title'])}</h1><p class="lead">{e(T['download_sub'])}</p>
<p><a class="btn big" href="{DOWNLOAD_URL}">⬇ {e(T['download_btn'])}</a></p><p class="muted"><a href="{SOURCE_URL}">{e(T['download_alt'])}</a></p></div></section>
<section><div class="wrap"><div class="how-grid">{steps}</div><div class="narrow"><h2>{e(T['req_title'])}</h2><ul class="req">{req}</ul></div></div></section>
{donate_block(lang, root)}"""
    return page(lang, "download.html", f"{T['download_title']} — Cockpit", T["download_sub"], body, 1)


def donate(lang):
    T, root = C[lang], "../"
    return page(lang, "donate.html", f"{T['donate_title']} — Cockpit", T["donate_text"], donate_block(lang, root, full=True), 1)


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(HERE, "assets"), os.path.join(OUT, "assets"))
    n = 0
    for lang in LANGS:
        d = os.path.join(OUT, lang, "features")
        os.makedirs(d, exist_ok=True)
        for name, content in (("index.html", index(lang)), ("download.html", download(lang)), ("donate.html", donate(lang))):
            open(os.path.join(OUT, lang, name), "w", encoding="utf-8").write(content)
            n += 1
        for fid in FEATURES_ORDER:
            open(os.path.join(d, f"{fid}.html"), "w", encoding="utf-8").write(feature(lang, fid))
            n += 1
    # racine : anglais par défaut, ou la langue choisie précédemment
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(
        """<!doctype html><meta charset="utf-8"><title>Cockpit</title><meta http-equiv="refresh" content="0; url=en/index.html">
<script>var l="en";try{l=localStorage.getItem("cockpit.site.lang")||"en"}catch(e){}if(["en","fr","es","de","ru"].indexOf(l)<0)l="en";location.replace(l+"/index.html")</script>""")
    print(f"{n} pages générées dans {OUT}")


if __name__ == "__main__":
    build()
