"""bedROK Loader — minimal dark injector, auto-find Minecraft (Windows x64)."""
from __future__ import annotations

import glob
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import ctypes
from ctypes import wintypes

try:
    import win32api
    import win32con
    import win32event
    import win32process
    import win32security
except ImportError as e:
    raise SystemExit("pip install pywin32") from e

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
kernel32.GetProcAddress.restype = ctypes.c_void_p

TH32CS_SNAPPROCESS = 0x2
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
PROCESS_ALL = (
    win32con.PROCESS_CREATE_THREAD
    | win32con.PROCESS_QUERY_INFORMATION
    | win32con.PROCESS_VM_OPERATION
    | win32con.PROCESS_VM_WRITE
    | win32con.PROCESS_VM_READ
)

# Palette — deep black + soft violet (client-style)
BG = "#09090b"
SURFACE = "#111114"
SURFACE2 = "#18181b"
LINE = "#27272a"
ACCENT = "#a78bfa"
ACCENT2 = "#8b5cf6"
TEXT = "#fafafa"
DIM = "#71717a"
GOOD = "#34d399"
BAD = "#f87171"

MC_NAMES = ("minecraft.windows.exe", "minecraft.exe", "minecraftbedrock.exe")


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def enable_debug_privilege() -> None:
    try:
        tok = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY,
        )
        pid = win32security.LookupPrivilegeValue(None, win32security.SE_DEBUG_NAME)
        win32security.AdjustTokenPrivileges(
            tok, False, [(pid, win32security.SE_PRIVILEGE_ENABLED)]
        )
        win32api.CloseHandle(tok)
    except Exception:
        pass


def list_processes() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return rows
    e = PROCESSENTRY32W()
    e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        name = str(e.szExeFile or "")
        if name.lower().endswith(".exe"):
            rows.append((int(e.th32ProcessID), name))
        ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    kernel32.CloseHandle(snap)
    return rows


def find_minecraft() -> tuple[int, str] | None:
    found = []
    for pid, name in list_processes():
        low = name.lower()
        if low in MC_NAMES or "minecraft" in low:
            found.append((pid, name))
    if not found:
        return None
    for pid, name in found:
        if name.lower() == "minecraft.windows.exe":
            return pid, name
    return found[0]


def default_dll_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (
        os.path.join(here, "bedrok.dll"),
        os.path.join(os.getcwd(), "bedrok.dll"),
        os.path.join(here, "..", "dll", "build", "Release", "bedrok.dll"),
    ):
        p = os.path.normpath(c)
        if os.path.isfile(p):
            return p
    return os.path.join(here, "bedrok.dll")


def try_launch_minecraft() -> str:
    for cmd in (
        ["explorer.exe", "shell:AppsFolder\\Microsoft.MinecraftUWP_8wekyb3d8bbwe!App"],
        ["cmd", "/c", "start", "minecraft:"],
    ):
        try:
            subprocess.Popen(cmd, shell=False)
            return "Launching Minecraft…"
        except Exception:
            continue
    for pattern in (
        os.path.expandvars(r"%ProgramFiles%\WindowsApps\Microsoft.MinecraftUWP*\Minecraft.Windows.exe"),
    ):
        for p in glob.glob(pattern):
            if os.path.isfile(p):
                try:
                    subprocess.Popen([p])
                    return "Launching Minecraft…"
                except Exception:
                    pass
    return "Open Minecraft manually"


def inject(pid: int, dll_path: str) -> str:
    dll_path = os.path.abspath(dll_path)
    if not os.path.isfile(dll_path):
        raise FileNotFoundError(dll_path)
    enable_debug_privilege()
    h = kernel32.GetModuleHandleW("kernel32.dll")
    load = kernel32.GetProcAddress(h, b"LoadLibraryW")
    if not load:
        load = ctypes.cast(kernel32.LoadLibraryW, ctypes.c_void_p).value
    hp = win32api.OpenProcess(PROCESS_ALL, False, pid)
    try:
        data = (dll_path + "\0").encode("utf-16-le")
        remote = win32process.VirtualAllocEx(
            hp, 0, len(data),
            win32con.MEM_COMMIT | win32con.MEM_RESERVE,
            win32con.PAGE_READWRITE,
        )
        win32process.WriteProcessMemory(hp, remote, data)
        ht, _ = win32process.CreateRemoteThread(hp, None, 0, load, remote, 0)
        win32event.WaitForSingleObject(ht, 15000)
        code = win32process.GetExitCodeThread(ht)
        win32api.CloseHandle(ht)
        if code == 0:
            raise OSError("LoadLibrary failed (arch / path / access)")
        return f"OK  ·  PID {pid}  ·  {code:#x}"
    finally:
        win32api.CloseHandle(hp)


def round_rect(c: tk.Canvas, x1, y1, x2, y2, r, **kw):
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return c.create_polygon(points, smooth=True, **kw)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("bedROK")
        self.geometry("380x460")
        self.configure(bg=BG)
        self.resizable(False, False)
        try:
            self.attributes("-alpha", 0.98)
        except Exception:
            pass

        self.q: queue.Queue = queue.Queue()
        self.mc_pid: int | None = None
        self.mc_name: str | None = None
        self.dll_path = default_dll_path()
        self._busy = False

        # —— header ——
        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=32, pady=(36, 0))

        tk.Label(
            top, text="bedROK", bg=BG, fg=TEXT,
            font=("Segoe UI", 26, "bold"),
        ).pack(anchor="w")
        tk.Label(
            top, text="bedrock companion", bg=BG, fg=DIM,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 4))

        # accent line
        line = tk.Canvas(self, height=2, bg=BG, highlightthickness=0)
        line.pack(fill=tk.X, padx=32, pady=(20, 24))
        line.create_rectangle(0, 0, 80, 2, fill=ACCENT, outline="")

        # —— status row ——
        status = tk.Frame(self, bg=SURFACE, highlightthickness=0)
        status.pack(fill=tk.X, padx=32)

        # fake rounded via padding frame
        sf = tk.Frame(status, bg=SURFACE)
        sf.pack(fill=tk.X, padx=1, pady=1)

        row = tk.Frame(sf, bg=SURFACE)
        row.pack(fill=tk.X, padx=18, pady=16)

        self.dot = tk.Canvas(row, width=10, height=10, bg=SURFACE, highlightthickness=0)
        self.dot.pack(side=tk.LEFT)
        self._set_dot(DIM)

        self.status_lbl = tk.Label(
            row, text="Waiting for Minecraft", bg=SURFACE, fg=TEXT,
            font=("Segoe UI", 11), anchor="w",
        )
        self.status_lbl.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)

        self.pid_lbl = tk.Label(
            row, text="", bg=SURFACE, fg=DIM, font=("Segoe UI", 9),
        )
        self.pid_lbl.pack(side=tk.RIGHT)

        # —— dll path (minimal) ——
        dll_f = tk.Frame(self, bg=BG)
        dll_f.pack(fill=tk.X, padx=32, pady=(18, 0))
        tk.Label(dll_f, text="DLL", bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(anchor="w")

        dll_row = tk.Frame(dll_f, bg=SURFACE2)
        dll_row.pack(fill=tk.X, pady=(6, 0))

        self.dll_var = tk.StringVar(value=self.dll_path)
        ent = tk.Entry(
            dll_row, textvariable=self.dll_var, bg=SURFACE2, fg=DIM,
            insertbackground=TEXT, relief=tk.FLAT, font=("Segoe UI", 9),
            highlightthickness=0,
        )
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(12, 0))

        tk.Label(
            dll_row, text="  browse  ", bg=SURFACE2, fg=ACCENT,
            font=("Segoe UI", 9), cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(0, 8))
        dll_row.bind("<Button-1>", lambda e: self.browse())
        for w in dll_row.winfo_children():
            w.bind("<Button-1>", lambda e: self.browse())

        # —— primary inject ——
        self.btn_canvas = tk.Canvas(
            self, height=48, bg=BG, highlightthickness=0, cursor="hand2",
        )
        self.btn_canvas.pack(fill=tk.X, padx=32, pady=(28, 0))
        self.btn_canvas.bind("<Button-1>", lambda e: self.do_inject())
        self.btn_canvas.bind("<Enter>", lambda e: self._paint_btn(True))
        self.btn_canvas.bind("<Leave>", lambda e: self._paint_btn(False))
        self.btn_canvas.bind("<Configure>", lambda e: self._paint_btn(False))
        self._btn_label = "Inject"

        # secondary actions
        sec = tk.Frame(self, bg=BG)
        sec.pack(fill=tk.X, padx=32, pady=(12, 0))

        for text, cmd in (("Launch game", self.launch_mc), ("Refresh", self.scan)):
            b = tk.Label(
                sec, text=text, bg=BG, fg=DIM, font=("Segoe UI", 9),
                cursor="hand2",
            )
            b.pack(side=tk.LEFT, padx=(0, 20))
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.configure(fg=TEXT))
            b.bind("<Leave>", lambda e, w=b: w.configure(fg=DIM))

        # footer status line
        self.foot = tk.Label(
            self, text="", bg=BG, fg=DIM, font=("Segoe UI", 9), anchor="w",
        )
        self.foot.pack(fill=tk.X, padx=32, pady=(24, 28), side=tk.BOTTOM)

        self.after(50, self.scan)
        self.after(100, self.poll)
        self.after(2000, self._tick)

    def _set_dot(self, color: str):
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 9, 9, fill=color, outline="")

    def _paint_btn(self, hover: bool):
        c = self.btn_canvas
        c.delete("all")
        w = max(c.winfo_width(), 200)
        h = 48
        fill = ACCENT2 if hover and not self._busy else ACCENT
        if self._busy:
            fill = SURFACE2
        round_rect(c, 0, 0, w - 1, h - 1, 10, fill=fill, outline="")
        fg = "#0a0a0a" if not self._busy else DIM
        c.create_text(
            w // 2, h // 2, text=self._btn_label,
            fill=fg, font=("Segoe UI Semibold", 12),
        )

    def set_footer(self, msg: str, ok: bool | None = None):
        if ok is True:
            self.foot.configure(text=msg, fg=GOOD)
        elif ok is False:
            self.foot.configure(text=msg, fg=BAD)
        else:
            self.foot.configure(text=msg, fg=DIM)

    def browse(self):
        p = filedialog.askopenfilename(filetypes=[("DLL", "*.dll")])
        if p:
            self.dll_var.set(p)
            self.dll_path = p

    def scan(self):
        hit = find_minecraft()
        if hit:
            self.mc_pid, self.mc_name = hit
            self._set_dot(GOOD)
            self.status_lbl.configure(text="Minecraft found", fg=TEXT)
            self.pid_lbl.configure(text=f"PID {self.mc_pid}")
            self.set_footer(f"Ready  ·  {self.mc_name}")
        else:
            self.mc_pid = self.mc_name = None
            self._set_dot(BAD)
            self.status_lbl.configure(text="Minecraft not running", fg=TEXT)
            self.pid_lbl.configure(text="")
            self.set_footer("Start the game or click Launch game")

    def _tick(self):
        if self.mc_pid is None:
            hit = find_minecraft()
            if hit:
                self.mc_pid, self.mc_name = hit
                self._set_dot(GOOD)
                self.status_lbl.configure(text="Minecraft found", fg=TEXT)
                self.pid_lbl.configure(text=f"PID {self.mc_pid}")
                self.set_footer(f"Ready  ·  {self.mc_name}", True)
        self.after(2000, self._tick)

    def launch_mc(self):
        self.set_footer(try_launch_minecraft())
        self.after(2500, self.scan)

    def do_inject(self):
        if self._busy:
            return
        if self.mc_pid is None:
            self.scan()
        if self.mc_pid is None:
            self.set_footer("Minecraft is not running", False)
            return
        dll = self.dll_var.get().strip()
        if not dll or not os.path.isfile(dll):
            self.set_footer("bedrok.dll not found — browse to it", False)
            return

        self._busy = True
        self._btn_label = "Injecting…"
        self._paint_btn(False)
        pid = self.mc_pid

        def work():
            try:
                time.sleep(0.1)
                self.q.put(("ok", inject(pid, dll)))
            except Exception as e:
                self.q.put(("err", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                self._busy = False
                self._btn_label = "Inject"
                self._paint_btn(False)
                if kind == "ok":
                    self.set_footer(payload, True)
                else:
                    self.set_footer(payload, False)
                    messagebox.showerror("bedROK", payload)
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == "__main__":
    App().mainloop()
