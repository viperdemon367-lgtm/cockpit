"""Tests de l'alarme : détection de couleurs et lecture des logs de chat (sans écran ni jeu)."""
import os

import numpy as np
import pytest

from app import alarm as A

RED = {"name": "Rouge", "rgb": [200, 20, 20], "level": "rouge"}
ORANGE = {"name": "Orange", "rgb": [230, 120, 20], "level": "orange"}


def img_with(icons):
    """Image BGRA 200x60 avec des carrés de 6x6 aux couleurs demandées."""
    arr = np.zeros((200, 60, 4), dtype=np.uint8)
    arr[:, :] = (40, 30, 25, 255)
    for i, (r, g, b) in enumerate(icons):
        arr[i * 12: i * 12 + 6, 5:11] = (b, g, r, 255)
    return arr


def test_count_and_evaluate():
    base_img = img_with([(200, 20, 20)])
    counts = A.count_colors(base_img, [RED, ORANGE])
    assert counts == {"Rouge": 36, "Orange": 0}
    baseline = counts
    # un rouge et un orange arrivent (couleurs légèrement différentes : tolérance)
    new = A.count_colors(img_with([(200, 20, 20), (205, 25, 15), (225, 118, 25)]), [RED, ORANGE])
    alerts, baseline = A.evaluate(new, baseline, [RED, ORANGE], min_pixels=25)
    assert {a["name"] for a in alerts} == {"Rouge", "Orange"}
    # avec la surface mesurée de l'icône (36 px), l'estimation est exacte
    sized = [dict(RED, icon_px=36), dict(ORANGE, icon_px=36)]
    al2, _ = A.evaluate(new, counts, sized, 25)
    assert {a["name"]: a["estimate"] for a in al2} == {"Rouge": 1, "Orange": 1}
    # pas de nouvelle alerte si rien ne change
    assert A.evaluate(new, baseline, [RED, ORANGE], 25)[0] == []
    # le rouge part puis revient : nouvelle alerte
    gone = A.count_colors(img_with([(200, 20, 20)]), [RED, ORANGE])
    _, baseline = A.evaluate(gone, baseline, [RED, ORANGE], 25)
    back = A.count_colors(img_with([(200, 20, 20), (200, 20, 20)]), [RED, ORANGE])
    assert [a["name"] for a in A.evaluate(back, baseline, [RED, ORANGE], 25)[0]] == ["Rouge"]


def write_log(path, lines, mode="wb"):
    with open(path, mode) as fh:
        if mode == "wb":
            fh.write("\ufeff".encode("utf-16-le"))
        fh.write(("".join(l + "\r\n" for l in lines)).encode("utf-16-le"))


def test_chatlogs(tmp_path):
    d = str(tmp_path)
    write_log(os.path.join(d, "Intel Delve_20261022_180000_123.txt"), ["[ 2026.10.22 18:00:01 ] EVE System > Canal"])
    write_log(os.path.join(d, "Local_20261022_180000_123.txt"), ["x"])
    chans = A.list_channels(d)
    assert set(chans) == {"Intel Delve", "Local"}
    path = A.latest_log(d, "Intel Delve")
    lines, off = A.read_new_lines(path, 0)
    assert len(lines) == 1
    write_log(path, ["[ 2026.10.22 18:05:00 ] Scout Bob > 1DQ1-A 5 reds sur le gate", "[ 2026.10.22 18:06:00 ] Bob > 1DQ1-A clr"], mode="ab")
    lines, off2 = A.read_new_lines(path, off)
    assert len(lines) == 2 and off2 > off
    hit = A.match_intel(lines[0], ["1DQ1-A", "T5ZI-S"], ["cyno"])
    assert hit["speaker"] == "Scout Bob" and hit["hits"] == ["1DQ1-A"]
    assert A.match_intel(lines[1], ["1DQ1-A"], []) is None          # « clr » ignoré
    assert A.match_intel("[ 2026.10.22 18:07:00 ] Bob > cyno up en 8QT", ["1DQ1-A"], ["cyno"])["hits"] == ["cyno"]
    assert A.match_intel("[ 2026.10.22 18:07:00 ] Bob > 1DQ1-AB rien", ["1DQ1-A"], []) is None


async def _noop():
    return None


def test_alarm_events():
    al = A.Alarm(lambda: {"alarm": {"pc_sound": False}})
    al.push("test", "rouge", "essai")
    st = al.status()
    assert st["events"][0]["text"] == "essai" and st["seq"] == 1


def test_intel_watch_loop(tmp_path):
    """Boucle réelle : un message arrive dans le canal d'intel -> alerte."""
    import asyncio
    d = str(tmp_path)
    path = os.path.join(d, "Intel Delve_20261022_180000_123.txt")
    write_log(path, ["[ 2026.10.22 18:00:01 ] EVE System > Bienvenue"])
    cfg = {"alarm": {"screen_enabled": False, "logs_enabled": True, "log_dir": d, "channels": ["Intel Delve"],
                     "systems": ["1DQ1-A"], "keywords": ["cyno"], "interval": 0.3, "pc_sound": False}}
    al = A.Alarm(lambda: cfg)

    async def run():
        await al.start()
        await asyncio.sleep(0.8)
        write_log(path, ["[ 2026.10.22 18:05:00 ] Scout > 1DQ1-A neut sur le gate",
                         "[ 2026.10.22 18:05:10 ] Scout > 1DQ1-A clr"], mode="ab")
        await asyncio.sleep(0.9)
        await al.stop()

    asyncio.run(run())
    texts = [e["text"] for e in al.status()["events"]]
    assert texts == ["Intel Delve — Scout : 1DQ1-A neut sur le gate"], texts
    assert al.status()["events"][0]["level"] == "rouge"


def test_window_tracking_and_sounds():
    """Deux clients EVE simulés : seule la fenêtre active est surveillée, avec une référence par fenêtre."""
    import asyncio
    from app.winwin import Backend, eve_character
    from app import sounds

    assert eve_character("EVE - Damien Main") == "Damien Main" and eve_character("EVE") is None
    imgs = {1: img_with([(200, 20, 20)]), 2: img_with([(200, 20, 20), (200, 20, 20), (200, 20, 20)])}
    fg = {"h": 1}

    class Fake(Backend):
        def available(self):
            return True

        def list_windows(self):
            return [{"hwnd": h, "title": f"EVE - Perso{h}", "character": f"Perso{h}", "foreground": fg["h"] == h,
                     "minimized": False, "rect": {}} for h in (1, 2)] + [{"hwnd": 9, "title": "Discord", "character": None,
                                                                        "foreground": fg["h"] == 9, "minimized": False, "rect": {}}][:0]

        def capture(self, hwnd):
            return imgs[hwnd]

    cfg = {"alarm": {"detection": "custom", "screen_enabled": True, "source": "window", "window_mode": "active",
                     "region_rel": {"x": 0, "y": 0, "width": 60, "height": 200}, "output": "browser",
                     "colors": [dict(RED, icon_px=36)], "interval": 0.3}}
    al = A.Alarm(lambda: cfg, backend=Fake())

    async def run():
        await al.start()
        await asyncio.sleep(0.5)
        fg["h"] = 2                      # le joueur passe sur l'autre client (3 rouges déjà là) : pas d'alerte
        await asyncio.sleep(0.5)
        imgs[2] = img_with([(200, 20, 20)] * 4)   # un rouge arrive dans le local du client actif
        await asyncio.sleep(0.5)
        imgs[1] = img_with([(200, 20, 20)] * 5)   # changement sur le client NON actif : ignoré
        await asyncio.sleep(0.5)
        await al.stop()

    asyncio.run(run())
    texts = [e["text"] for e in al.status()["events"]]
    assert texts == ["Local (Perso2) : 1 Rouge vient d'arriver"], texts
    assert al.status()["events"][0]["sound"] == "sirene"
    # sons
    for name in sounds.SOUNDS:
        w = sounds.wav(name, 50)
        assert w[:4] == b"RIFF" and len(w) > 2000
    loud, quiet = sounds.wav("bip", 100), sounds.wav("bip", 10)
    assert max(loud[44:]) >= max(quiet[44:]) and loud != quiet
    assert sounds.wav("inexistant", 50) == sounds.wav("bip", 50)


def test_crop_and_check():
    from app.winwin import Backend
    arr = img_with([(200, 20, 20)])
    assert A.crop(arr, {"x": 0, "y": 0, "width": 30, "height": 30}).shape[:2] == (30, 30)
    with pytest.raises(RuntimeError):
        A.crop(arr, {"x": 500, "y": 0, "width": 10, "height": 10})

    class Fake(Backend):
        def available(self):
            return True

        def list_windows(self):
            return [{"hwnd": 1, "title": "EVE - X", "character": "X", "foreground": True, "minimized": False, "rect": {}}]

        def capture(self, hwnd):
            return img_with([(200, 20, 20), (200, 20, 20)])

    cfg = {"alarm": {"detection": "custom", "source": "window", "region_rel": {"x": 0, "y": 0, "width": 60, "height": 200},
                     "colors": [dict(RED, icon_px=36)]}}
    r = A.Alarm(lambda: cfg, backend=Fake()).check_now()
    assert r["windows"][0]["label"] == "X" and r["windows"][0]["colors"][0]["estimate"] == 2.0


# ---------------------------------------------------------------------- détection automatique
def local_list(rows):
    """Fausse liste du local : fond sombre, une icône 11x11 avec un signe blanc, puis un « nom » en traits fins
    blancs et gris (comme du texte). rows = liste de couleurs RGB d'icône (None = pas d'icône)."""
    arr = np.zeros((22 * len(rows) + 10, 220, 4), dtype=np.uint8)
    arr[:, :] = (28, 24, 22, 255)                       # fond EVE sombre
    for i, col in enumerate(rows):
        y = 6 + i * 22
        if col:
            r, g, b = col
            arr[y:y + 11, 6:17] = (b, g, r, 255)
            arr[y + 5:y + 6, 8:15] = (240, 240, 240, 255)   # signe « - » blanc dans l'icône
        # « texte » : traits verticaux et horizontaux fins, blancs et gris
        for k in range(14):
            x = 24 + k * 9
            arr[y:y + 11, x:x + 1] = (225, 225, 225, 255)
            arr[y + (k % 3) * 4:y + (k % 3) * 4 + 1, x:x + 6] = (150, 150, 150, 255)
    return arr


RED_EVE, ORANGE_EVE, GREY_EVE, BLUE_EVE = (149, 7, 7), (197, 74, 7), (145, 146, 146), (43, 102, 197)


def test_auto_icon_counting():
    img = local_list([RED_EVE, RED_EVE, ORANGE_EVE, GREY_EVE, BLUE_EVE, BLUE_EVE, BLUE_EVE, None, None])
    counts, boxes = A.count_icons(img)
    assert counts == {"rouge": 2, "orange": 1, "neutre": 1, "bleu": 3}, counts
    assert all(10 <= w <= 12 and 10 <= h <= 12 for w, h in [(b[2], b[3]) for b in boxes["rouge"]])
    # le texte seul ne déclenche rien
    assert A.count_icons(local_list([None] * 8))[0] == {"rouge": 0, "orange": 0, "neutre": 0, "bleu": 0}


def test_auto_icon_variants():
    # teintes un peu différentes (luminosité, transparence légère) : toujours reconnues
    img = local_list([(170, 30, 35), (130, 0, 10), (215, 95, 30), (180, 60, 0)])
    c = A.count_icons(img)[0]
    assert c["rouge"] == 2 and c["orange"] == 2
    # couleur personnalisée pour un thème non standard
    img2 = local_list([(150, 60, 160), (150, 60, 160)])
    assert A.count_icons(img2)[0]["rouge"] == 0
    assert A.count_icons(img2, custom={"rouge": [150, 60, 160]})[0]["rouge"] == 2


def test_evaluate_icons():
    base = {"rouge": 1, "orange": 0, "neutre": 2, "bleu": 5}
    al, base = A.evaluate_icons({"rouge": 2, "orange": 0, "neutre": 2, "bleu": 7}, base, ["rouge", "orange", "neutre"])
    assert al == [{"name": "rouge", "level": "rouge", "estimate": 1}]          # les bleus ne sonnent pas
    al, base = A.evaluate_icons({"rouge": 1, "orange": 0, "neutre": 2, "bleu": 7}, base, ["rouge", "orange", "neutre"])
    assert al == []                                                            # départ : pas d'alerte
    al, _ = A.evaluate_icons({"rouge": 2, "orange": 0, "neutre": 4, "bleu": 7}, base, ["rouge"])
    assert [a["name"] for a in al] == ["rouge"]                                # neutres non surveillés


def test_auto_loop_two_windows():
    import asyncio
    from app.winwin import Backend
    imgs = {1: local_list([RED_EVE, BLUE_EVE]), 2: local_list([GREY_EVE])}
    fg = {"h": 1}

    class Fake(Backend):
        def available(self):
            return True

        def list_windows(self):
            return [{"hwnd": h, "title": f"EVE - P{h}", "character": f"P{h}", "foreground": fg["h"] == h,
                     "minimized": False, "rect": {}} for h in (1, 2)]

        def capture(self, hwnd):
            return imgs[hwnd]

    cfg = {"alarm": {"screen_enabled": True, "source": "window", "window_mode": "active", "output": "browser",
                     "region_rel": {"x": 0, "y": 0, "width": 220, "height": 400}, "interval": 0.3}}
    al = A.Alarm(lambda: cfg, backend=Fake())

    async def run():
        await al.start()
        await asyncio.sleep(0.5)
        imgs[1] = local_list([RED_EVE, BLUE_EVE, ORANGE_EVE, GREY_EVE])     # un orange et un neutre arrivent
        await asyncio.sleep(0.5)
        fg["h"] = 2                                                         # changement de client : pas d'alerte
        await asyncio.sleep(0.5)
        imgs[2] = local_list([GREY_EVE, RED_EVE, RED_EVE])                  # deux rouges dans le client actif
        await asyncio.sleep(0.5)
        await al.stop()

    asyncio.run(run())
    texts = sorted(e["text"] for e in al.status()["events"])
    assert texts == ["Local (P1) : 1 neutre vient d'arriver", "Local (P1) : 1 orange vient d'arriver",
                     "Local (P2) : 2 rouges viennent d'arriver"], texts


# ---------------------------------------------------------------------- captures réelles du client EVE
SCREENS = np.load(os.path.join(os.path.dirname(__file__), "data", "eve_screens.npz"))


def shrink(img, size):
    """Redimensionne (plus proche voisin) une icône carrée."""
    h, w = img.shape[:2]
    ys = (np.arange(size) * h / size).astype(int)
    xs = (np.arange(size) * w / size).astype(int)
    return img[ys][:, xs]


def eve_icon(i, size=12):
    """Icône n° i de la capture fournie (0 rouge, 1 orange, 2 neutre, 3 bleu clair, 4 bleu foncé)."""
    x = [2, 28, 54, 80, 106][i]
    return shrink(SCREENS["icons"][5:25, x - 1:x + 19], size)


def test_real_icons_capture():
    counts, _ = A.count_icons(SCREENS["icons"])
    assert counts == {"rouge": 1, "orange": 1, "neutre": 1, "bleu": 2}


def test_real_local_with_red_chat_text():
    # la capture du local contient beaucoup de texte rouge (« EVE System > Channel changed… ») : aucun faux rouge
    counts, _ = A.count_icons(SCREENS["local"])
    assert counts == {"rouge": 0, "orange": 0, "neutre": 0, "bleu": 1}


def test_real_local_arrivals():
    base = SCREENS["local"].copy()
    ref, _ = A.count_icons(base)
    img = base.copy()
    # trois pilotes arrivent dans la colonne des membres : un rouge, un orange, un neutre (icônes réelles, 12 px)
    for k, (i, y) in enumerate([(0, 82), (1, 100), (2, 118)]):
        img[y:y + 12, 170:182] = eve_icon(i, 12)
    counts, boxes = A.count_icons(img)
    assert counts == {"rouge": 1, "orange": 1, "neutre": 1, "bleu": 1}, counts
    alerts, _ = A.evaluate_icons(counts, ref, ["rouge", "orange", "neutre"])
    assert sorted(a["name"] for a in alerts) == ["neutre", "orange", "rouge"]
    # icônes plus petites (interface à 90 %) et plus grandes (125 %)
    for size in (9, 16):
        img2 = base.copy()
        img2[90:90 + size, 170:170 + size] = eve_icon(0, size)
        assert A.count_icons(img2)[0]["rouge"] == 1, size


def test_real_neutral_in_local_full_screen():
    """Capture complète du jeu : un neutre (Drohne-7) dans la fenêtre Local, gris plus foncé que sur l'image
    d'exemple ; du texte rouge partout ; un autre canal avec ses propres neutres."""
    scr = np.load(os.path.join(os.path.dirname(__file__), "data", "eve_screens.npz"))["screen_neutral"]
    local = scr[650:830, 598:910]
    counts, boxes = A.count_icons(local)
    assert counts == {"rouge": 0, "orange": 0, "neutre": 1, "bleu": 1}, counts
    x, y, w, h = boxes["neutre"][0]
    assert 170 <= x <= 185 and 55 <= y <= 70 and 10 <= w <= 14          # l'icône de Drohne-7
    assert A.count_icons(scr[700:945, 405:580])[0]["neutre"] == 5         # liste du canal French
    full = A.count_icons(scr)[0]
    assert full["rouge"] == 0 and full["orange"] == 0                     # décor et textes rouges ignorés
    # le neutre arrive : alerte
    empty = local.copy()
    empty[y:y + h, x:x + w] = local[y - 30:y - 30 + h, x:x + w]          # même zone sans l'icône (fond)
    ref = A.count_icons(empty)[0]
    al, _ = A.evaluate_icons(counts, ref, ["rouge", "orange", "neutre"])
    assert [a["name"] for a in al] == ["neutre"]
