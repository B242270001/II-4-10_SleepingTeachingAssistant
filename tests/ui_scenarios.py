"""UI сценариудыг автоматаар ажиллуулж, screenshot болон үр дүнг хадгална.

Ажиллуулах (macOS / Windows, төслийн үндсэн хавтсанд; Windows дээр Pillow хэрэгтэй):
    python3 tests/ui_scenarios.py S1      # нэг сценари
    python3 tests/ui_scenarios.py all     # бүгд (сценари бүр тусдаа процесс)

Гаралт: tests/screenshots/<ID>.png, <ID>.json

Хэрхэн ажилладаг вэ:
  1. src/ui.py-н Dashboard цонхыг нээнэ.
  2. Сценарийн оролтыг талбаруудад бичнэ.
  3. START / PAUSE / STEP / RESET товчийн үйлдлийг (Dashboard-ийн метод) хугацаатай дуудна.
  4. Тогтоосон мөчид цонхны хэсгийг (macOS: `screencapture`, бусад: Pillow) авч, дэлгэц дээр харагдаж буй
     тоолуурыг (үйлчлүүлсэн, буцсан, дараалал, TA-ийн төлөв) JSON-д бичнэ.
Screenshot авахад macOS-ийн Screen Recording зөвшөөрөл шаардагдаж болно.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
# macOS-ийн BD1 нотолгоог дарж бичихгүйн тулд бусад OS-ийн үр дүнг тусад нь хадгална
OUT = os.path.join(HERE, "screenshots" if sys.platform == "darwin" else f"screenshots_{sys.platform}")

# ID: (сандал, оюутан, ирэх, үйлчилгээ, [(секунд, үйлдэл), ...], төгсгөлийн screenshot-ын секунд)
# Үйлдэл: start | pause | step | reset | probe | shot:<нэр> | shot_sleep:<нэр>
SCENARIOS = {
    "S1":  ("3", "5", "1.0", "1.5", [(0.5, "shot:S1_ready"), (1.0, "start")], 21),
    "S2":  ("1", "10", "0.3", "1.5", [(1.0, "start")], 21),
    "S3":  ("10", "3", "1.5", "0.5", [(1.0, "start")], 21),
    "S4":  ("0", "5", "0.5", "1.0", [(1.0, "start")], 16),
    "S5":  ("1", "1", "2.0", "0.5", [(1.0, "start"), (2.0, "shot_sleep:S5_sleeping")], 21),
    "S6":  ("20", "50", "0.2", "0.5", [(1.0, "start")], 21),
    "S7":  ("3", "5", "1.0", "1.5", [(1.0, "start"), (6.0, "pause"), (6.4, "probe"),
                                     (8.0, "shot:S7_pause"), (10.5, "probe"), (11.0, "start")], 17),
    "S8":  ("3", "5", "1.0", "1.5", [(1.0, "start"), (2.5, "pause"), (3.0, "probe"),
                                     (3.5, "step"), (3.9, "probe"), (4.3, "step"), (4.7, "probe"),
                                     (5.1, "step"), (5.5, "probe"), (5.9, "step"), (6.3, "probe"),
                                     (6.7, "step"), (7.1, "probe")], 8),
    "S9":  ("3", "5", "1.0", "1.5", [(1.0, "start"), (11.0, "shot:S9_before_reset"), (11.3, "reset")], 13),
    "S10": ("25", "5", "1.0", "1.5", [(1.0, "start")], 3),
    "S11": ("abc", "5", "1.0", "1.5", [(1.0, "start")], 3),
}


def _printwindow(hwnd):
    """Windows: цонхыг Win32 PrintWindow-оор зурна. Бусад цонх дээр нь давхарласан
    ч зөв гарна. Дэлгэцээс хуулбал ажиллаж буй Tk canvas заримдаа хар гардаг тул ингэсэн."""
    import ctypes
    from ctypes import wintypes
    from PIL import Image
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    rect = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right, rect.bottom
    hdc = u.GetDC(hwnd)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(mdc, bmp)
    u.PrintWindow(hwnd, mdc, 1 | 2)              # PW_CLIENTONLY | PW_RENDERFULLCONTENT

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(hwnd, hdc)
    return Image.frombytes("RGB", (w, h), buf.raw, "raw", "BGRX")   # buf-ийг хуулна


def grab(root, path):
    """Цонхны screenshot (БД2, m-3).
    macOS: screencapture; Windows: PrintWindow; Linux: Pillow ImageGrab (X11)."""
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    if sys.platform == "darwin":
        subprocess.run(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", path], check=False)
        return
    try:
        from PIL import ImageGrab
    except ImportError:
        print("Pillow суугаагүй тул screenshot алгасав (pip install pillow)", file=sys.stderr)
        return
    if sys.platform == "win32":
        import ctypes
        hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)   # GA_ROOT
        img = _printwindow(hwnd)
        if img.width == 0 or img.height == 0:
            print(f"{path}: цонхны хэмжээ 0, screenshot алгасав", file=sys.stderr)
            return
        img.save(path)
    else:
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)


def run_one(sid):
    if sys.platform == "win32":
        # Tk-ийн координатыг дэлгэцийн бодит пикселтэй тааруулна (125%/150% scaling)
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    import tkinter as tk
    sys.path.insert(0, SRC)
    import ui

    chairs, students, interval, service, actions, end = SCENARIOS[sid]
    os.makedirs(OUT, exist_ok=True)
    errors = []
    # Modal цонх процессыг түгжихээс сэргийлж алдааны мессежийг барьж авна
    ui.messagebox.showerror = lambda title, msg, **kw: errors.append(f"{title}: {msg}")

    root = tk.Tk()
    app = ui.Dashboard(root)
    root.geometry("1370x900+0+30")
    for key, val in zip(("chairs", "students", "interval", "service"),
                        (chairs, students, interval, service)):
        app.form[key].delete(0, "end")
        app.form[key].insert(0, val)
    root.update()
    root.lift()
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))

    result = {"id": sid, "input": [chairs, students, interval, service], "shots": []}

    def state():
        return {"status": app.pill.cget("text").strip(), "served": app.display_served,
                "turned_away": app.display_away, "waiting": list(app.display_waiting),
                "current": app.display_current, "ta_state": app.display_state,
                "events": app.event_number}

    def snap(name):
        if root.state() == "iconic":        # бусад програм цонхыг minimize хийсэн бол сэргээнэ
            root.deiconify()
            for _ in range(10):
                root.update()
                time.sleep(0.03)
        root.update()
        grab(root, os.path.join(OUT, name + ".png"))
        result["shots"].append({"name": name, **state()})

    def wait_sleep(name, deadline):
        # TA дахин унтсан мөчийг хүлээж screenshot авна
        if app.display_state == "SLEEPING" and app.display_served >= 1:
            snap(name)
        elif deadline > 0:
            root.after(100, lambda: wait_sleep(name, deadline - 100))
        else:
            result["shots"].append({"name": name, "missed": True, **state()})

    def do(action):
        if action == "probe":
            result.setdefault("probes", []).append(state())
        elif action.startswith("shot_sleep:"):
            wait_sleep(action.split(":", 1)[1], 15000)
        elif action.startswith("shot:"):
            snap(action.split(":", 1)[1])
        else:
            getattr(app, action)()

    def finish():
        snap(sid)
        result.update(state())
        result["errors"] = errors
        with open(os.path.join(OUT, sid + ".json"), "w", encoding="utf8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=False))
        app.close()

    for delay, action in actions:
        root.after(int(delay * 1000), lambda a=action: do(a))
    root.after(int(end * 1000), finish)
    root.mainloop()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):          # Windows cp1252 дээр '●' хэвлэхэд унахгүй
        sys.stdout.reconfigure(encoding="utf-8")
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which == "all":
        for sid in SCENARIOS:
            subprocess.run([sys.executable, "-B", os.path.abspath(__file__), sid], check=False)
    else:
        run_one(which)
