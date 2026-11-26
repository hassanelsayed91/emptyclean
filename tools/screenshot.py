from __future__ import annotations
import ctypes, sys, time
from ctypes import wintypes
from pathlib import Path
from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

def find_window(prefix="EmptyClean"):
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.startswith(prefix) and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None

def capture(hwnd):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = w
    info.bmiHeader.biHeight = -h
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(info), 0)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(hwnd, wdc)
    return img

def main():
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    hwnd = find_window()
    if not hwnd:
        print("EmptyClean window not found - start it first.", file=sys.stderr)
        return 1
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    img = capture(hwnd)
    out = Path(__file__).resolve().parent.parent / "docs" / "screenshot.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"saved {out} ({img.width}x{img.height})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
