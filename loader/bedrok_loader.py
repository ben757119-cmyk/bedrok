"""bedROK Loader — clean dark injector with auto Minecraft detect (Windows x64)."""
from __future__ import annotations

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

# --- Win32 ---
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

MC_NAMES = (
    "minecraft.windows.exe",
    "minecraft.exe",
    "minecraftbedrock.exe",
)

BG = "#0b0d12"
PANEL = "#12151c"
BORDER = "#1e2430"
ACCENT = "#5b8cff"
ACCENT_HOVER = "#7aa2ff"
TEXT = "#e8eaed"
MUTED = "#8b93a7"
OK = "#3dd68c"
ERR = "#ff6b6b"


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


def enable_debug_privilege() -> str:
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
        return "ok"
    except Exception as e:
        return str(e)


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
    """Prefer Minecraft.Windows.exe, then other MC names."""
    found: list[tuple[int, str]] = []
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
    candidates = [
        os.path.join(here, "bedrok.dll"),
        os.path.join(os.getcwd(), "bedrok.dll"),
        os.path.join(here, "..", "dll", "build", "Release", "bedrok.dll"),
    ]
    for c in candidates:
        p = os.path.normpath(c)
        if os.path.isfile(p):
            return p
    return os.path.join(here, "bedrok.dll")


def try_launch_minecraft() -> str:
    """Best-effort launch of Bedrock via shell / known paths."""
    # Xbox / Store app user model id style launch
    cmds = [
        ["explorer.exe", "shell:AppsFolder\\Microsoft.MinecraftUWP_8wekyb3d8bbwe!App"],
        ["cmd", "/c", "start", "minecraft:"],
    ]
    paths = [
        os.path.expandvars(
            r"%ProgramFiles%\WindowsApps\Microsoft.MinecraftUWP*\Minecraft.Windows.exe"
        ),
        os.path.expandvars(
            r"%LOCALAPPDATA%\Packages\Microsoft.MinecraftUWP_8wekyb3d8bbwe"
        ),
    ]
    for cmd in cmds:
        try:
            subprocess.Popen(cmd, shell=False)
            return "Launch requested (Store / protocol)"
        except Exception:
            continue
    for pattern in paths:
        # glob light
        import glob

        for p in glob.glob(pattern):
            exe = p if p.lower().endswith(".exe") else None
            if exe and os.path.isfile(exe):
                try:
                    subprocess.Popen([exe])
                    return f"Started {exe}"
                except Exception:
                    pass
    return "Could not auto-launch — open Minecraft Bedrock manually"


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
            hp,
            0,
            len(data),
            win32con.MEM_COMMIT | win32con.MEM_RESERVE,
            win32con.PAGE_READWRITE,
        )
        win32process.WriteProcessMemory(hp, remote, data)
        ht, _tid = win32process.CreateRemoteThread(hp, None, 0, load, remote, 0)
        win32event.WaitForSingleObject(ht, 15000)
        code = win32process.GetExitCodeThread(ht)
        win32api.CloseHandle(ht)
        if code == 0:
            raise OSError("LoadLibrary returned 0 — wrong arch, path, or blocked")
        return f"Injected into PID {pid}\nModule base: {code:#x}\n{dll_path}"
    finally:
        win32api.CloseHandle(hp)


class PillButton(tk.Canvas):
    def __init__(self, master, text, command, primary=True, **kw):
        super().__init__(master, height=44, highlightthickness=0, bg=BG, **kw)
        self.command = command
        self.primary = primary
        self.text = text
        self.enabled = True
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self._draw(False)

    def _draw(self, hover: bool):
        self.delete("all")
        w = int(self.winfo_width() or 200)
        h = 44
        if self.primary:
            fill = ACCENT_HOVER if hover and self.enabled else ACCENT
            if not self.enabled:
                fill = "#2a3344"
            fg = "#0b0d12" if self.enabled else MUTED
        else:
            fill = "#1a2030" if hover else PANEL
            fg = TEXT if self.enabled else MUTED
        self.create_rectangle(0, 0, w, h, fill=fill, outline=BORDER if not self.primary else fill)
        self.create_text(w // 2, h // 2, text=self.text, fill=fg, font=("Segoe UI Semibold", 11))

    def _click(self, _e=None):
        if self.enabled and self.command:
            self.command()

    def _enter(self, _e=None):
        self._draw(True)

    def _leave(self, _e=None):
        self._draw(False)

    def set_enabled(self, on: bool):
        self.enabled = on
        self._draw(False)

    def set_text(self, t: str):
        self.text = t
        self._draw(False)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("bedROK")
        self.geometry("420x520")
        self.minsize(400, 480)
        self.configure(bg=BG)
        self.resizable(False, False)

        self.q: queue.Queue = queue.Queue()
        self.mc_pid: int | None = None
        self.mc_name: str | None = None
        self.dll = tk.StringVar(value=default_dll_path())

        # Header
        header = tk.Frame(self, bg=BG)
        header.pack(fill=tk.X, padx=28, pady=(28, 8))
        tk.Label(
            header, text="bedROK", bg=BG, fg=TEXT, font=("Segoe UI", 22, "bold")
        ).pack(anchor=tk.W)
        tk.Label(
            header,
            text="Minecraft Bedrock companion",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor=tk.W, pady=(2, 0))

        # Status card
        card = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill=tk.X, padx=28, pady=12)

        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill=tk.X, padx=16, pady=14)

        tk.Label(inner, text="TARGET", bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(
            anchor=tk.W
        )
        self.mc_label = tk.Label(
            inner,
            text="Searching…",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI Semibold", 12),
            anchor=tk.W,
        )
        self.mc_label.pack(fill=tk.X, pady=(2, 10))

        tk.Label(inner, text="DLL", bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(
            anchor=tk.W
        )
        dll_row = tk.Frame(inner, bg=PANEL)
        dll_row.pack(fill=tk.X, pady=(2, 0))
        self.dll_entry = tk.Entry(
            dll_row,
            textvariable=self.dll,
            bg="#0b0d12",
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            font=("Consolas", 9),
        )
        self.dll_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        tk.Button(
            dll_row,
            text="…",
            command=self.browse,
            bg="#1a2030",
            fg=TEXT,
            relief=tk.FLAT,
            width=3,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Buttons
        btns = tk.Frame(self, bg=BG)
        btns.pack(fill=tk.X, padx=28, pady=(8, 4))

        self.inject_btn = PillButton(btns, "Inject", self.do_inject, primary=True)
        self.inject_btn.pack(fill=tk.X, pady=(0, 8))
        self.inject_btn.bind("<Configure>", lambda e: self.inject_btn._draw(False))

        row2 = tk.Frame(btns, bg=BG)
        row2.pack(fill=tk.X)
        self.refresh_btn = PillButton(row2, "Refresh", self.scan, primary=False)
        self.refresh_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.refresh_btn.bind("<Configure>", lambda e: self.refresh_btn._draw(False))
        self.launch_btn = PillButton(row2, "Launch MC", self.launch_mc, primary=False)
        self.launch_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        self.launch_btn.bind("<Configure>", lambda e: self.launch_btn._draw(False))

        # Log
        tk.Label(
            self, text="LOG", bg=BG, fg=MUTED, font=("Segoe UI", 8)
        ).pack(anchor=tk.W, padx=28, pady=(16, 4))
        self.log = tk.Text(
            self,
            height=8,
            bg=PANEL,
            fg=MUTED,
            relief=tk.FLAT,
            font=("Consolas", 9),
            wrap=tk.WORD,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=28, pady=(0, 24))

        self.after(80, self.scan)
        self.after(100, self.poll)
        self.after(2000, self._auto_rescan)

    def log_line(self, msg: str, color: str | None = None):
        self.log.insert(tk.END, msg + "\n")
        if color:
            pass
        self.log.see(tk.END)

    def browse(self):
        p = filedialog.askopenfilename(filetypes=[("DLL", "*.dll"), ("All", "*.*")])
        if p:
            self.dll.set(p)

    def scan(self):
        hit = find_minecraft()
        if hit:
            self.mc_pid, self.mc_name = hit
            self.mc_label.configure(
                text=f"{self.mc_name}  ·  PID {self.mc_pid}", fg=OK
            )
            self.log_line(f"Found {self.mc_name} (PID {self.mc_pid})")
        else:
            self.mc_pid = self.mc_name = None
            self.mc_label.configure(text="Minecraft not running", fg=ERR)
            self.log_line("Minecraft not found — start it or press Launch MC")

        dll = self.dll.get().strip()
        if os.path.isfile(dll):
            self.log_line(f"DLL ready: {os.path.basename(dll)}")
        else:
            self.log_line("DLL missing — browse to bedrok.dll")

    def _auto_rescan(self):
        if self.mc_pid is None:
            hit = find_minecraft()
            if hit:
                self.mc_pid, self.mc_name = hit
                self.mc_label.configure(
                    text=f"{self.mc_name}  ·  PID {self.mc_pid}", fg=OK
                )
                self.log_line(f"Auto-detected {self.mc_name} (PID {self.mc_pid})")
        self.after(2500, self._auto_rescan)

    def launch_mc(self):
        self.log_line(try_launch_minecraft())
        self.after(3000, self.scan)

    def do_inject(self):
        if self.mc_pid is None:
            self.scan()
        if self.mc_pid is None:
            messagebox.showwarning("bedROK", "Start Minecraft Bedrock first.")
            return
        dll = self.dll.get().strip()
        if not dll or not os.path.isfile(dll):
            messagebox.showwarning("bedROK", "Select a valid bedrok.dll")
            return

        self.inject_btn.set_enabled(False)
        self.inject_btn.set_text("Injecting…")
        pid = self.mc_pid

        def work():
            try:
                # brief wait if game just launched
                time.sleep(0.15)
                msg = inject(pid, dll)
                self.q.put(("ok", msg))
            except Exception as e:
                self.q.put(("err", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                self.log_line(payload)
                self.inject_btn.set_enabled(True)
                self.inject_btn.set_text("Inject")
                if kind == "ok":
                    messagebox.showinfo("bedROK", payload)
                else:
                    messagebox.showerror("bedROK", payload)
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == "__main__":
    App().mainloop()
