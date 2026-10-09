"""
Capture a multi-frame animated GIF of Limitline running in --demo mode.
Steps:
  1. Launch limitline --demo
  2. Wait for window to appear
  3. Find the window by title, capture it
  4. Send key presses to cycle tabs (1, 2, 3, 4)
  5. Assemble frames into docs/img/demo.gif
"""
import subprocess, sys, time, os, ctypes, ctypes.wintypes
from PIL import ImageGrab, Image

LIMITLINE = [sys.executable, "limitline.py", "--demo"]
TITLE = "Limitline"
FRAME_DELAY = 1200  # ms per frame in the final GIF
TAB_PAUSE = 1.2     # seconds to wait after switching tab

# ── helpers ──────────────────────────────────────────────────────────────────
user32 = ctypes.windll.user32

def find_window(title_fragment):
    result = []
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if title_fragment.lower() in buf.value.lower():
                result.append(hwnd)
        return True
    ctypes.windll.user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(cb), 0)
    return result[0] if result else None

def get_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom

def grab_window(hwnd):
    import mss, numpy as np
    l, t, r, b = get_rect(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    with mss.mss() as sct:
        monitor = {"left": l, "top": t, "width": r - l, "height": b - t}
        raw = sct.grab(monitor)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

def send_key(hwnd, vk):
    """Post a WM_KEYDOWN/WM_KEYUP to the window."""
    WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)

VK = {'1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34}

# ── main ─────────────────────────────────────────────────────────────────────
print("Launching Limitline demo...")
proc = subprocess.Popen(LIMITLINE)

# Wait for window to appear (up to 10s)
hwnd = None
for _ in range(40):
    hwnd = find_window(TITLE)
    if hwnd:
        break
    time.sleep(0.25)

if not hwnd:
    proc.terminate()
    sys.exit("ERROR: Could not find Limitline window")

print(f"Window found: hwnd={hwnd}")
time.sleep(1.5)  # let it fully render

frames = []
tab_sequence = ['1', '2', '3', '4', '1']  # end back on overview
labels = ["Overview", "History", "Projects", "Sessions", "Overview"]

for tab, label in zip(tab_sequence, labels):
    send_key(hwnd, VK[tab])
    time.sleep(TAB_PAUSE)
    try:
        frame = grab_window(hwnd)
        frames.append(frame)
        print(f"  Captured: {label}")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"  WARN: {label} failed: {e}")

proc.terminate()

if not frames:
    sys.exit("ERROR: No frames captured")

out = os.path.join("docs", "img", "demo.gif")
os.makedirs(os.path.dirname(out), exist_ok=True)

# Resize to reasonable GIF width (keep aspect ratio)
MAX_W = 420
frames_resized = []
for f in frames:
    w, h = f.size
    scale = MAX_W / w
    frames_resized.append(f.resize((MAX_W, int(h * scale)), Image.LANCZOS))

frames_resized[0].save(
    out,
    save_all=True,
    append_images=frames_resized[1:],
    duration=FRAME_DELAY,
    loop=0,
    optimize=True,
)
print(f"\nSaved {len(frames_resized)}-frame GIF → {out}  ({os.path.getsize(out)//1024} KB)")
