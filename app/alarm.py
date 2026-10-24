"""Alarme de local et d'intel.

ESI ne donne PAS la liste des pilotes en local. Deux sources sont donc utilisées, au choix :

1. Écran : l'outil photographie une zone de l'écran (la liste du local) et compte les pixels qui ont la couleur
   des icônes de standing que TU as choisies (rouge, orange, neutre…). Si ce nombre augmente, un nouveau pilote
   est arrivé : alarme. L'outil ne clique rien, n'envoie rien au jeu et ne lit pas sa mémoire.
2. Logs d'intel : le jeu écrit chaque canal de chat dans Documents/EVE/logs/Chatlogs. L'outil lit les nouveaux
   messages des canaux choisis et sonne quand un système ou un mot surveillé apparaît.
"""
from __future__ import annotations

import asyncio
import glob
import os
import re
import sys
import threading
import time
from collections import deque

LEVELS = {"rouge": 3, "orange": 2, "neutre": 1, "autre": 1}
LINE = re.compile(r"^\s*\[\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})\s*\]\s*(.+?)\s+>\s?(.*)$")


# ---------------------------------------------------------------------- analyse d'image (fonctions pures, testées)
def count_colors(bgra, colors, tolerance=18):
    """bgra : tableau numpy (h, w, 4). colors : [{"name", "rgb": [r, g, b], "level"}]. -> {nom: nb de pixels}"""
    import numpy as np
    arr = bgra[:, :, :3].astype(np.int16)
    out = {}
    for c in colors:
        r, g, b = c["rgb"]
        target = np.array([b, g, r], dtype=np.int16)
        mask = (np.abs(arr - target) <= tolerance).all(axis=2)
        out[c["name"]] = int(mask.sum())
    return out


def evaluate(counts, baseline, colors, min_pixels):
    """Compare au niveau de référence. Renvoie (alertes, nouveau niveau de référence).
    icon_px (mesuré au clic sur l'icône) = surface d'une icône ; à défaut, min_pixels.
    Une alerte part dès 60 % d'une icône en plus. Le niveau de référence descend quand un pilote part :
    il resonnera s'il revient."""
    alerts, base = [], dict(baseline)
    for c in colors:
        n, ref = counts.get(c["name"], 0), base.get(c["name"], 0)
        icon = max(4, int(c.get("icon_px") or min_pixels))
        if n - ref >= 0.6 * icon:
            est = max(1, round((n - ref) / icon))
            alerts.append({"name": c["name"], "level": c.get("level", "autre"), "pixels": n - ref, "estimate": est})
            base[c["name"]] = n
        elif n < ref:
            base[c["name"]] = n
    return alerts, base


# ---------------------------------------------------------------------- détection automatique des icônes
# Les icônes de standing sont de petits carrés pleins (avec un signe blanc dedans). Le texte, lui, est fait de traits
# fins : on cherche donc des taches de couleur compactes et carrées, et on les classe par teinte.
CATEGORIES = ("rouge", "orange", "neutre", "bleu")


def hsv(bgra):
    import numpy as np
    rgb = bgra[:, :, 2::-1].astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    v = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    d = v - mn
    s = np.where(v > 0, d / np.maximum(v, 1e-6), 0)
    h = np.zeros_like(v)
    nz = d > 1e-6
    rm = nz & (v == r)
    gm = nz & (v == g) & ~rm
    bm = nz & ~rm & ~gm
    h[rm] = (60 * ((g[rm] - b[rm]) / d[rm])) % 360
    h[gm] = 60 * ((b[gm] - r[gm]) / d[gm]) + 120
    h[bm] = 60 * ((r[bm] - g[bm]) / d[bm]) + 240
    return h, s, v


# Familles de couleur des icônes de standing. Les teintes exactes varient d'un client à l'autre (transparence des
# fenêtres, taille d'interface : un neutre relevé à (145,146,146) sur une capture et à (104,108,111) sur une autre).
# La couleur sert donc seulement à CLASSER ; ce qui reconnaît une icône, c'est sa forme (voir find_blobs).
def category_masks(bgra, custom=None, tol=38):
    """Masques par famille de couleur (ou couleur exacte choisie par l'utilisateur)."""
    import numpy as np
    h, s, v = hsv(bgra)
    masks = {
        "rouge": (s > 0.5) & (v > 0.25) & (v < 0.9) & ((h < 15) | (h >= 345)),
        "orange": (s > 0.55) & (v > 0.40) & (h >= 15) & (h < 45),
        "neutre": (s < 0.13) & (v >= 0.28) & (v <= 0.72),
        "bleu": (s > 0.45) & (v > 0.20) & (h >= 195) & (h < 250),
    }
    if custom:
        px = bgra[:, :, :3].astype(np.int16)
        for cat, rgb in custom.items():
            if rgb:
                t = np.array([rgb[2], rgb[1], rgb[0]], dtype=np.int16)
                masks[cat] = (np.abs(px - t) <= tol).all(axis=2)
    return masks


def bright_mask(bgra):
    """Pixels du signe blanc au centre des icônes (« - », « = », « + »)."""
    import numpy as np
    px = bgra[:, :, :3].astype(np.int16)
    return (px.min(axis=2) >= 185) & ((px.max(axis=2) - px.min(axis=2)) <= 45)


def find_blobs(mask, max_pixels=80_000, bright=None):
    """Icônes dans un masque : taches carrées, pleines jusqu'aux bords, avec un signe clair au centre.
    Le texte (traits fins, coins vides, pas de signe blanc) est rejeté. Renvoie [(x, y, largeur, hauteur)]."""
    import numpy as np
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return []
    if len(ys) > max_pixels:
        raise RuntimeError("zone trop grande ou trop colorée : encadre seulement la liste des pilotes du local")
    todo = set(zip(ys.tolist(), xs.tolist()))
    blobs = []
    while todo:
        start = todo.pop()
        stack, pts = [start], [start]
        while stack:
            y, x = stack.pop()
            for n in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if n in todo:
                    todo.remove(n)
                    stack.append(n)
                    pts.append(n)
        if len(pts) < 20:
            continue
        yy = [p[0] for p in pts]
        xx = [p[1] for p in pts]
        x0, x1, y0, y1 = min(xx), max(xx), min(yy), max(yy)
        w, hgt = x1 - x0 + 1, y1 - y0 + 1
        if not (6 <= w <= 40 and 6 <= hgt <= 40 and 0.75 <= w / hgt <= 1.34):
            continue
        sub = mask[y0:y1 + 1, x0:x1 + 1]
        # carré plein : coins et bords colorés (le texte a des coins vides)
        ring = np.concatenate([sub[0, :], sub[-1, :], sub[1:-1, 0], sub[1:-1, -1]])
        if ring.mean() < 0.7:
            continue
        if bright is not None:
            # le centre doit contenir le signe clair ou être entièrement de la couleur de l'icône
            cy0, cy1, cx0, cx1 = y0 + hgt // 4, y1 - hgt // 4 + 1, x0 + w // 4, x1 - w // 4 + 1
            centre_bright = int(bright[cy0:cy1, cx0:cx1].sum())
            centre_fill = float(mask[cy0:cy1, cx0:cx1].mean())
            if centre_bright < 2 and centre_fill < 0.95:
                continue
            # surface : couleur de l'icône + signe clair ≈ tout le carré
            filled = (sub | bright[y0:y1 + 1, x0:x1 + 1]).mean()
            if filled < 0.8:
                continue
        elif sub.mean() < 0.6:
            continue
        blobs.append((x0, y0, w, hgt))
    return blobs


def count_icons(bgra, custom=None, tol=38):
    """{catégorie: nombre d'icônes}, et la position de chaque icône (pour l'afficher à l'utilisateur)."""
    masks = category_masks(bgra, custom, tol)
    bright = bright_mask(bgra)
    boxes = {c: find_blobs(m, bright=bright) for c, m in masks.items()}
    return {c: len(b) for c, b in boxes.items()}, boxes


def evaluate_icons(counts, baseline, watch):
    """Nouveaux arrivants par catégorie surveillée. Renvoie (alertes, nouvelle référence)."""
    alerts, base = [], dict(baseline)
    for cat in watch:
        n, ref = counts.get(cat, 0), base.get(cat, 0)
        if n > ref:
            alerts.append({"name": cat, "level": cat, "estimate": n - ref})
        base[cat] = n          # suit aussi les départs : un pilote qui revient resonne
    for cat in counts:
        base.setdefault(cat, counts[cat])
    return alerts, base


# ---------------------------------------------------------------------- logs de chat (fonctions pures, testées)
def chatlog_dirs():
    home = os.path.expanduser("~")
    cands = [os.path.join(home, "Documents", "EVE", "logs", "Chatlogs"),
             os.path.join(home, "OneDrive", "Documents", "EVE", "logs", "Chatlogs"),
             os.path.join(home, "OneDrive", "Documents", "EVE", "logs", "ChatLogs")]
    return [d for d in cands if os.path.isdir(d)]


def list_channels(directory, days=7):
    """Canaux présents dans les logs récents : {nom: dernière modification}."""
    out = {}
    limit = time.time() - days * 86400
    for path in glob.glob(os.path.join(directory, "*.txt")):
        try:
            mt = os.path.getmtime(path)
        except OSError:
            continue
        if mt < limit:
            continue
        name = re.sub(r"_\d{8}_\d{6}(_\d+)?\.txt$", "", os.path.basename(path))
        out[name] = max(out.get(name, 0), mt)
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def latest_log(directory, channel):
    files = [p for p in glob.glob(os.path.join(directory, f"{glob.escape(channel)}_*.txt"))
             if re.fullmatch(re.escape(channel) + r"_\d{8}_\d{6}(_\d+)?\.txt", os.path.basename(p))]
    return max(files, key=os.path.getmtime) if files else None


def read_new_lines(path, offset):
    """Lit la suite d'un log (UTF-16 LE, écrit par le jeu). Renvoie (lignes, nouvel offset)."""
    size = os.path.getsize(path)
    if size < offset:      # fichier recréé
        offset = 0
    if size == offset:
        return [], offset
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read(size - offset)
    data = data[: len(data) - (len(data) % 2)]
    text = data.decode("utf-16-le", errors="ignore").lstrip("\ufeff")
    return [l for l in text.replace("\r", "").split("\n") if l.strip()], offset + len(data)


def match_intel(line, systems, keywords, ignore_clear=True):
    m = LINE.match(line)
    if not m:
        return None
    speaker, msg = m.group(2).strip(), m.group(3).strip()
    if speaker == "EVE System":
        return None
    low = msg.lower()
    if ignore_clear and re.search(r"\b(clr|clear|propre|rien)\b", low):
        return None
    hits = [s for s in systems if re.search(r"(?<![\w-])" + re.escape(s.lower()) + r"(?![\w-])", low)]
    hits += [k for k in keywords if k.lower() in low]
    if not hits:
        return None
    return {"speaker": speaker, "message": msg, "hits": hits, "time": m.group(1)}


# ---------------------------------------------------------------------- moteur
def crop(arr, rel):
    """Découpe la zone relative {x, y, width, height} dans l'image de la fenêtre (bornée à sa taille)."""
    h, w = arr.shape[:2]
    x0, y0 = max(0, int(rel["x"])), max(0, int(rel["y"]))
    x1, y1 = min(w, x0 + int(rel["width"])), min(h, y0 + int(rel["height"]))
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError("la zone du local sort de la fenêtre (fenêtre redimensionnée ?) : refais la capture")
    return arr[y0:y1, x0:x1]


def sound_for(kind, level, cfg):
    snd = cfg.get("sounds") or {}
    if kind == "intel":
        return snd.get("intel", "cloche")
    return snd.get(level if level in ("rouge", "orange", "neutre") else "neutre",
                   {"rouge": "sirene", "orange": "klaxon"}.get(level, "bip"))


class Alarm:
    def __init__(self, settings_getter, backend=None):
        from .winwin import default_backend
        self.S = settings_getter
        self.backend = backend or default_backend()
        self.running = False
        self.task = None
        self.baselines = {}      # par fenêtre (ou "screen")
        self.counts = {}
        self.events = deque(maxlen=200)
        self.seq = 0
        self.error = None
        self.note = None
        self.last_check = None
        self.offsets = {}
        self.files = {}
        self.active_hwnd = None
        self.watching = []
        self.intel_last = deque(maxlen=8)

    def cfg(self):
        return self.S().get("alarm") or {}

    # --- capture : écran entier (mode « zone fixe »)
    @staticmethod
    def monitors():
        import mss
        with mss.mss() as sct:
            return [{"index": i, **m} for i, m in enumerate(sct.monitors) if i > 0]

    @staticmethod
    def screenshot_png(index=1):
        import mss
        import mss.tools
        with mss.mss() as sct:
            mon = sct.monitors[index]
            img = sct.grab(mon)
            return mss.tools.to_png(img.rgb, img.size), {"left": mon["left"], "top": mon["top"],
                                                          "width": mon["width"], "height": mon["height"]}

    def grab_region(self):
        import mss
        import numpy as np
        reg = self.cfg().get("region")
        with mss.mss() as sct:
            img = sct.grab({k: int(reg[k]) for k in ("left", "top", "width", "height")})
            return np.frombuffer(img.bgra, dtype=np.uint8).reshape(img.height, img.width, 4)

    # --- capture : fenêtres EVE
    def window_png(self, hwnd):
        import mss.tools
        arr = self.backend.capture(int(hwnd))
        rgb = arr[:, :, [2, 1, 0]].tobytes()
        return mss.tools.to_png(rgb, (arr.shape[1], arr.shape[0]))

    def targets(self, c):
        """Fenêtres EVE à surveiller selon le mode choisi."""
        wins = self.backend.list_windows()
        mode = c.get("window_mode", "active")
        if mode == "all":
            return wins, wins
        if mode == "character":
            name = (c.get("window_character") or "").lower()
            return [w for w in wins if (w.get("character") or "").lower() == name], wins
        # « fenêtre active » : celle au premier plan si c'est EVE, sinon la dernière fenêtre EVE utilisée
        fg = next((w for w in wins if w["foreground"]), None)
        if fg:
            self.active_hwnd = fg["hwnd"]
        cur = next((w for w in wins if w["hwnd"] == self.active_hwnd), None)
        return ([cur] if cur else []), wins

    # --- détection
    def auto(self, c):
        return c.get("detection", "auto") == "auto"

    def measure(self, arr, c):
        if self.auto(c):
            counts, _ = count_icons(arr, c.get("custom_colors"), int(c.get("custom_tol", 38)))
            return counts
        return count_colors(arr, c["colors"], int(c.get("tolerance", 18)))

    def analyze(self, arr, c):
        """Analyse ponctuelle d'une image (photo de réglage) : comptes et position des icônes."""
        counts, boxes = count_icons(arr, c.get("custom_colors"), int(c.get("custom_tol", 38)))
        return {"counts": counts, "boxes": {k: [list(b) for b in v[:200]] for k, v in boxes.items()}}

    def detect(self, c):
        """Une passe de détection. Renvoie [(clé, libellé, comptes)]."""
        out = []
        if c.get("source", "window") == "window":
            if not self.backend.available():
                raise RuntimeError("Le suivi de fenêtre EVE n'existe que sous Windows : choisis « zone fixe de l'écran ».")
            rel = c.get("region_rel")
            if not rel:
                raise RuntimeError("Zone du local non définie : fais l'étape 2.")
            targets, wins = self.targets(c)
            if not wins:
                self.note = "Aucune fenêtre EVE ouverte."
            elif not targets:
                self.note = ("Personnage introuvable parmi les fenêtres EVE." if c.get("window_mode") == "character"
                             else "Clique une fois dans ta fenêtre EVE pour que l'alarme sache laquelle surveiller.")
            else:
                self.note = None
            self.watching = []
            for w in targets:
                label = w.get("character") or w["title"]
                if w.get("minimized"):
                    self.watching.append({"label": label, "state": "réduite (non surveillée)"})
                    continue
                try:
                    arr = crop(self.backend.capture(w["hwnd"]), rel)
                except RuntimeError as e:
                    self.watching.append({"label": label, "state": str(e)})
                    continue
                counts = self.measure(arr, c)
                self.watching.append({"label": label, "state": "surveillée", "counts": counts})
                out.append((f"w{w['hwnd']}", label, counts))
        else:
            if not c.get("region"):
                raise RuntimeError("Zone de l'écran non définie : fais l'étape 2.")
            counts = self.measure(self.grab_region(), c)
            self.watching = [{"label": "Zone de l'écran", "state": "surveillée", "counts": counts}]
            self.note = None
            out.append(("screen", None, counts))
        return out

    def check_now(self):
        """Test ponctuel : combien d'icônes de chaque couleur sont visibles maintenant ?"""
        c = self.cfg()
        if self.auto(c):
            res = [{"label": label or "Zone de l'écran", "icons": counts} for _k, label, counts in self.detect(c)]
            return {"windows": res, "watching": self.watching, "note": self.note, "auto": True}
        if not c.get("colors"):
            raise RuntimeError("Aucune couleur choisie.")
        res = []
        for _key, label, counts in self.detect(c):
            res.append({"label": label or "Zone de l'écran", "colors": [
                {"name": col["name"], "level": col.get("level"), "pixels": counts.get(col["name"], 0),
                 "estimate": round(counts.get(col["name"], 0) / max(4, int(col.get("icon_px") or c.get("min_pixels", 25))), 1)}
                for col in c["colors"]]})
        return {"windows": res, "watching": self.watching, "note": self.note}

    # --- événements et sons
    def push(self, kind, level, text):
        self.seq += 1
        ev = {"id": self.seq, "time": time.time(), "kind": kind, "level": level, "text": text}
        c = self.cfg()
        ev["sound"] = sound_for(kind, level, c)
        self.events.appendleft(ev)
        if c.get("output", "pc") == "pc":
            self.play(ev["sound"])
        return ev

    def play(self, sound):
        from . import sounds
        vol = int(self.cfg().get("volume", 70))
        threading.Thread(target=sounds.play_on_pc, args=(sound, vol), daemon=True).start()

    # --- boucle
    async def start(self):
        if self.running:
            return
        self.running, self.error = True, None
        self.baselines, self.offsets, self.files = {}, {}, {}
        self.task = asyncio.create_task(self._loop())

    async def stop(self):
        self.running = False
        self.counts, self.baselines, self.watching = {}, {}, []
        if self.task:
            self.task.cancel()
            self.task = None

    def rearm(self):
        self.baselines = {}

    async def _loop(self):
        first = True
        while self.running:
            c = self.cfg()
            try:
                if c.get("screen_enabled") and (self.auto(c) or c.get("colors")):
                    results = await asyncio.to_thread(self.detect, c)
                    self.counts = results[0][2] if results else {}
                    watch = [k for k in ("rouge", "orange", "neutre") if (c.get("watch") or {}).get(k, True)]
                    for key, label, counts in results:
                        if key not in self.baselines:
                            self.baselines[key] = dict(counts)   # 1re vue de cette fenêtre : c'est la référence
                            continue
                        if self.auto(c):
                            alerts, self.baselines[key] = evaluate_icons(counts, self.baselines[key], watch)
                        else:
                            alerts, self.baselines[key] = evaluate(counts, self.baselines[key], c["colors"],
                                                                   int(c.get("min_pixels", 25)))
                        for a in alerts:
                            who = f" ({label})" if label else ""
                            n = a["estimate"]
                            nom = {"rouge": "rouge", "orange": "orange", "neutre": "neutre"}.get(a["name"], a["name"])
                            txt = f"1 {nom} vient d'arriver" if n == 1 else f"{n} {nom}s viennent d'arriver"
                            self.push("local", a["level"], f"Local{who} : {txt}")
                if c.get("logs_enabled") and c.get("channels"):
                    await asyncio.to_thread(self._scan_logs, c, first)
                self.error = None
            except Exception as e:
                self.error = f"{e}"
            self.last_check = time.time()
            first = False
            await asyncio.sleep(max(0.3, float(c.get("interval", 1.0))))

    def _scan_logs(self, c, first):
        directory = c.get("log_dir") or (chatlog_dirs() or [None])[0]
        if not directory or not os.path.isdir(directory):
            raise FileNotFoundError("Dossier des logs de chat introuvable : active l'enregistrement du chat dans EVE "
                                    "(étape 1 de l'alarme intel) ou indique le dossier.")
        systems = [s.strip() for s in c.get("systems") or [] if s.strip()]
        keywords = [k.strip() for k in c.get("keywords") or [] if k.strip()]
        for ch in c.get("channels") or []:
            path = latest_log(directory, ch)
            if not path:
                continue
            if self.files.get(ch) != path:      # nouveau fichier (relog) : on part de la fin
                self.files[ch] = path
                self.offsets[path] = os.path.getsize(path)
                continue
            lines, self.offsets[path] = read_new_lines(path, self.offsets.get(path, 0))
            if first:
                continue
            for line in lines:
                m = LINE.match(line)
                if m and m.group(2).strip() != "EVE System":
                    self.intel_last.appendleft({"channel": ch, "time": m.group(1)[-8:], "speaker": m.group(2).strip(),
                                                "message": m.group(3).strip()[:200]})
                hit = match_intel(line, systems, keywords, c.get("ignore_clear", True))
                if hit:
                    self.push("intel", "rouge" if any(h in systems for h in hit["hits"]) else "orange",
                              f"{ch} — {hit['speaker']} : {hit['message']}")

    def status(self):
        return {"running": self.running, "counts": self.counts, "error": self.error, "note": self.note,
                "last_check": self.last_check, "events": list(self.events)[:60], "seq": self.seq,
                "watching": self.watching, "intel_last": list(self.intel_last),
                "window_support": self.backend.available()}
