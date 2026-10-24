"""Fenêtres du client EVE (Windows uniquement), via l'API Windows (ctypes) :
- lister les fenêtres « EVE - Nom du perso » ;
- savoir laquelle est au premier plan (celle sur laquelle le joueur joue) ;
- capturer la zone client d'une fenêtre, même partiellement recouverte (PrintWindow), avec repli sur une
  capture d'écran classique si le pilote graphique renvoie une image noire.
Aucune interaction : ni clic, ni touche, ni lecture mémoire."""
from __future__ import annotations

import sys


class Backend:
    """Interface commune (implémentée par WinBackend, et par un faux backend dans les tests)."""

    def available(self) -> bool:
        return False

    def list_windows(self) -> list[dict]:
        return []

    def foreground(self) -> int | None:
        return None

    def capture(self, hwnd: int):
        raise RuntimeError("Capture de fenêtre indisponible sur ce système.")


def eve_character(title: str) -> str | None:
    """« EVE - Damien Main » -> « Damien Main » ; « EVE » (écran de connexion) -> None."""
    if title.startswith("EVE - "):
        return title[6:].strip() or None
    return None


def is_eve_title(title: str) -> bool:
    return title == "EVE" or title.startswith("EVE - ")


class WinBackend(Backend):
    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt
        self.ct, self.wt = ctypes, wt
        self.user32 = ctypes.windll.user32
        self.gdi32 = ctypes.windll.gdi32
        # types explicites : sans ça, ctypes tronque les handles 64 bits en int 32 bits
        vp = ctypes.c_void_p
        u, g = self.user32, self.gdi32
        u.GetForegroundWindow.restype = wt.HWND
        u.GetDC.argtypes, u.GetDC.restype = [wt.HWND], vp
        u.ReleaseDC.argtypes = [wt.HWND, vp]
        u.PrintWindow.argtypes, u.PrintWindow.restype = [wt.HWND, vp, wt.UINT], wt.BOOL
        u.IsIconic.argtypes = [wt.HWND]
        u.IsWindowVisible.argtypes = [wt.HWND]
        u.GetWindowTextLengthW.argtypes = [wt.HWND]
        u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        u.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        u.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
        g.CreateCompatibleDC.argtypes, g.CreateCompatibleDC.restype = [vp], vp
        g.CreateCompatibleBitmap.argtypes, g.CreateCompatibleBitmap.restype = [vp, ctypes.c_int, ctypes.c_int], vp
        g.SelectObject.argtypes, g.SelectObject.restype = [vp, vp], vp
        g.DeleteObject.argtypes = [vp]
        g.DeleteDC.argtypes = [vp]
        g.GetDIBits.argtypes = [vp, vp, wt.UINT, wt.UINT, vp, vp, wt.UINT]
        try:   # coordonnées en pixels physiques (écrans à 125 %, 150 %…), cohérentes avec la capture
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                self.user32.SetProcessDPIAware()
            except Exception:
                pass

    def available(self):
        return True

    def _title(self, hwnd):
        n = self.user32.GetWindowTextLengthW(hwnd)
        if not n:
            return ""
        buf = self.ct.create_unicode_buffer(n + 1)
        self.user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def client_rect(self, hwnd):
        rect = self.wt.RECT()
        self.user32.GetClientRect(hwnd, self.ct.byref(rect))
        pt = self.wt.POINT(0, 0)
        self.user32.ClientToScreen(hwnd, self.ct.byref(pt))
        return {"left": pt.x, "top": pt.y, "width": rect.right - rect.left, "height": rect.bottom - rect.top}

    def list_windows(self):
        found = []
        proto = self.ct.WINFUNCTYPE(self.ct.c_bool, self.wt.HWND, self.wt.LPARAM)

        def cb(hwnd, _lp):
            if self.user32.IsWindowVisible(hwnd):   # noqa: SIM102
                t = self._title(hwnd)
                if is_eve_title(t):
                    found.append(int(hwnd))
            return True

        self.user32.EnumWindows(proto(cb), 0)
        fg = self.foreground()
        out = []
        for h in found:
            t = self._title(h)
            out.append({"hwnd": h, "title": t, "character": eve_character(t), "foreground": h == fg,
                        "minimized": bool(self.user32.IsIconic(h)), "rect": self.client_rect(h)})
        return out

    def foreground(self):
        h = self.user32.GetForegroundWindow()
        return int(h) if h else None   # HWND converti en entier (None si aucune fenêtre)

    def capture(self, hwnd):
        import numpy as np
        ct, wt, user32, gdi32 = self.ct, self.wt, self.user32, self.gdi32
        r = self.client_rect(hwnd)
        w, h = r["width"], r["height"]
        if w <= 0 or h <= 0 or user32.IsIconic(hwnd):
            raise RuntimeError("fenêtre réduite")

        class BITMAPINFOHEADER(ct.Structure):
            _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                        ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                        ("biClrImportant", wt.DWORD)]

        hdc = user32.GetDC(hwnd)
        mdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        old = gdi32.SelectObject(mdc, bmp)
        arr = None
        try:
            # 1 = PW_CLIENTONLY, 2 = PW_RENDERFULLCONTENT (fenêtres DirectX, Windows 8.1+)
            if user32.PrintWindow(hwnd, mdc, 3):
                bi = BITMAPINFOHEADER()
                bi.biSize, bi.biWidth, bi.biHeight = ct.sizeof(BITMAPINFOHEADER), w, -h   # -h : de haut en bas
                bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
                buf = ct.create_string_buffer(w * h * 4)
                if gdi32.GetDIBits(mdc, bmp, 0, h, ct.addressof(buf), ct.addressof(bi), 0):
                    arr = np.frombuffer(buf.raw, dtype=np.uint8).reshape(h, w, 4).copy()
        finally:
            gdi32.SelectObject(mdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mdc)
            user32.ReleaseDC(hwnd, hdc)
        if arr is None or int(arr[:, :, :3].max()) < 8:
            # image noire : repli sur une capture d'écran de la zone (la fenêtre doit alors être visible)
            import mss
            with mss.mss() as sct:
                img = sct.grab(r)
                arr = np.frombuffer(img.bgra, dtype=np.uint8).reshape(img.height, img.width, 4).copy()
        return arr


def default_backend() -> Backend:
    if sys.platform == "win32":
        try:
            return WinBackend()
        except Exception:
            return Backend()
    return Backend()
