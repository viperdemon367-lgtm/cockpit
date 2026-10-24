"""Sons d'alarme générés à la volée (WAV mono 16 bits) : pas de fichier à fournir, volume intégré au son.
Le même WAV est joué sur le PC (winsound) ou dans le navigateur (<audio>)."""
from __future__ import annotations

import io
import math
import struct
import wave

RATE = 22050

SOUNDS = {
    "bip": "Bip (3 bips courts)",
    "sonar": "Sonar (ping)",
    "sirene": "Sirène",
    "klaxon": "Klaxon (deux tons)",
    "cloche": "Cloche",
    "radar": "Radar (montée)",
    "alerte": "Alerte rapide (5 bips)",
}


def _tone(freq_fn, dur, shape="sine", env=None, amp=1.0):
    n = int(RATE * dur)
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        f = freq_fn(t)
        phase += 2 * math.pi * f / RATE
        if shape == "square":
            v = 1.0 if math.sin(phase) >= 0 else -1.0
            v *= 0.55
        elif shape == "bell":
            v = math.sin(phase) + 0.45 * math.sin(2 * phase) + 0.2 * math.sin(3.01 * phase)
            v /= 1.65
        else:
            v = math.sin(phase)
        e = env(t, dur) if env else 1.0
        # micro-rampes pour éviter les « clics »
        ramp = min(1.0, t / 0.004, (dur - t) / 0.004)
        out.append(v * e * ramp * amp)
    return out


def _silence(dur):
    return [0.0] * int(RATE * dur)


def _decay(k):
    return lambda t, d: math.exp(-k * t)


def synth(name: str) -> list[float]:
    if name == "sonar":
        return _tone(lambda t: 1250, 0.9, env=_decay(5.5)) + _silence(0.1)
    if name == "sirene":
        return _tone(lambda t: 650 + 650 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 0.8)), 1.6, shape="sine")
    if name == "klaxon":
        s = []
        for f in (980, 720, 980, 720):
            s += _tone(lambda t, f=f: f, 0.22, shape="square") + _silence(0.03)
        return s
    if name == "cloche":
        return _tone(lambda t: 880, 1.6, shape="bell", env=_decay(2.6)) + _silence(0.1)
    if name == "radar":
        s = []
        for _ in range(3):
            s += _tone(lambda t: 700 + 2200 * t, 0.25, env=_decay(3)) + _silence(0.06)
        return s
    if name == "alerte":
        s = []
        for _ in range(5):
            s += _tone(lambda t: 1500, 0.08, shape="square") + _silence(0.06)
        return s
    # bip (défaut)
    s = []
    for _ in range(3):
        s += _tone(lambda t: 1000, 0.13, shape="square") + _silence(0.09)
    return s


_cache: dict[tuple[str, int], bytes] = {}


def wav(name: str, volume: int = 70) -> bytes:
    """WAV du son demandé ; volume de 0 à 100 (courbe quadratique, plus naturelle à l'oreille)."""
    name = name if name in SOUNDS else "bip"
    volume = max(0, min(100, int(volume)))
    key = (name, volume)
    if key in _cache:
        return _cache[key]
    gain = (volume / 100) ** 2 * 0.95
    frames = b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32767 * gain)) for v in synth(name))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    _cache[key] = buf.getvalue()
    return _cache[key]


def play_on_pc(name: str, volume: int = 70) -> bool:
    """Joue le son sur la carte son du PC (Windows). Bloquant : à appeler dans un thread."""
    import sys
    if sys.platform != "win32":
        return False
    try:
        import winsound
        winsound.PlaySound(wav(name, volume), winsound.SND_MEMORY)
        return True
    except Exception:
        return False
