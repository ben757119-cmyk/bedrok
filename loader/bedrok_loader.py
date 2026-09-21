"""bedROK Loader — Tkinter DLL injector (Windows x64)."""
from __future__ import annotations
import os, queue, threading, tkinter as tk
from tkinter import filedialog, messagebox, ttk
import ctypes
from ctypes import wintypes

try:
    import win32api, win32con, win32process, win32event, win32security
except ImportError:
    raise SystemExit("pip install pywin32")

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
    win32con.PROCESS_CREATE_THREAD | win32con.PROCESS_QUERY_INFORMATION
    | win32con.PROCESS_VM_OPERATION | win32con.PROCESS_VM_WRITE | win32con.PROCESS_VM_READ
)

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
    ]

def enable_debug_privilege():
    try:
        tok = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY)
        pid = win32security.LookupPrivilegeValue(None, win32security.SE_DEBUG_NAME)
        win32security.AdjustTokenPrivileges(tok, False, [(pid, win32security.SE_PRIVILEGE_ENABLED)])
        win32api.CloseHandle(tok)
        return "debug ok"
    except Exception as e:
        return str(e)

def list_processes():
    rows, snap = [], kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return rows
    e = PROCESSENTRY32W(); e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        name = str(e.szExeFile or "")
        if name.lower().endswith(".exe"):
            rows.append((int(e.th32ProcessID), name))
        ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    kernel32.CloseHandle(snap)
    rows.sort(key=lambda r: (0 if "minecraft" in r[1].lower() else 1, r[1].lower()))
    return rows

def inject(pid, dll_path):
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
        remote = win32process.VirtualAllocEx(hp, 0, len(data), win32con.MEM_COMMIT | win32con.MEM_RESERVE, win32con.PAGE_READWRITE)
        win32process.WriteProcessMemory(hp, remote, data)
        ht, tid = win32process.CreateRemoteThread(hp, None, 0, load, remote, 0)
        win32event.WaitForSingleObject(ht, 15000)
        code = win32process.GetExitCodeThread(ht)
        win32api.CloseHandle(ht)
        if code == 0:
            raise OSError("LoadLibrary returned 0 — wrong arch or blocked")
        return f"OK PID {pid} module={code:#x}\n{dll_path}"
    finally:
        win32api.CloseHandle(hp)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("bedROK Loader")
        self.geometry("560x420")
        self.configure(bg="#0f1115")
        self.q = queue.Queue()
        self.rows = []
        f = ttk.Frame(self, padding=16); f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="bedROK Loader").pack(anchor=tk.W)
        self.dll = tk.StringVar()
        here = os.path.dirname(os.path.abspath(__file__))
        for c in [os.path.join(here, "bedrok.dll"), os.path.join(here, "..", "dll", "build", "Release", "bedrok.dll")]:
            if os.path.isfile(c):
                self.dll.set(os.path.normpath(c)); break
        row = ttk.Frame(f); row.pack(fill=tk.X, pady=6)
        ttk.Entry(row, textvariable=self.dll).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse", command=self.browse).pack(side=tk.LEFT, padx=6)
        ttk.Button(f, text="Refresh processes", command=self.refresh).pack(anchor=tk.W)
        self.lb = tk.Listbox(f, height=12, bg="#12151c", fg="#e8eaed")
        self.lb.pack(fill=tk.BOTH, expand=True, pady=8)
        self.btn = ttk.Button(f, text="Inject", command=self.do_inject)
        self.btn.pack(anchor=tk.W)
        self.log = tk.Text(f, height=5, bg="#12151c", fg="#aeb4bc")
        self.log.pack(fill=tk.X, pady=8)
        self.after(100, self.poll)
        self.refresh()

    def browse(self):
        p = filedialog.askopenfilename(filetypes=[("DLL", "*.dll")])
        if p: self.dll.set(p)

    def refresh(self):
        self.rows = list_processes()
        self.lb.delete(0, tk.END)
        for pid, name in self.rows:
            self.lb.insert(tk.END, f"{pid:>6}  {name}")
            if "minecraft" in name.lower():
                self.lb.selection_clear(0, tk.END)
                self.lb.selection_set(tk.END)

    def do_inject(self):
        sel = self.lb.curselection()
        if not sel or not self.dll.get().strip():
            messagebox.showwarning("bedROK", "Select process and DLL"); return
        pid = self.rows[sel[0]][0]
        dll = self.dll.get().strip()
        self.btn.configure(state=tk.DISABLED)
        def work():
            try:
                self.q.put(("ok", inject(pid, dll)))
            except Exception as e:
                self.q.put(("err", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                k, p = self.q.get_nowait()
                self.log.insert(tk.END, p + "\n")
                if k == "ok":
                    messagebox.showinfo("OK", p)
                else:
                    messagebox.showerror("Failed", p)
                self.btn.configure(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.after(100, self.poll)

if __name__ == "__main__":
    App().mainloop()
