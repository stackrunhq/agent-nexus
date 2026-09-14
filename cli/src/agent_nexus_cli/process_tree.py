"""Read-only parent PID snapshots for local benchmark processes."""

import ctypes
import os
from pathlib import Path


def parents():
    if os.name != "nt":
        result = {}
        for path in Path("/proc").glob("[0-9]*/stat"):
            try:
                result[int(path.parent.name)] = int(path.read_text().rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                continue
        return result
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("pid", wintypes.DWORD),
            ("heap", ctypes.c_size_t),
            ("module", wintypes.DWORD),
            ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD),
            ("priority", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("exe", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    for name in ("Process32FirstW", "Process32NextW"):
        getattr(kernel, name).argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError("Cannot enumerate process tree")
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        result = {}
        success = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while success:
            result[entry.pid] = entry.parent
            success = kernel.Process32NextW(handle, ctypes.byref(entry))
        return result
    finally:
        kernel.CloseHandle(handle)


def descendants(mapping, roots):
    selected = set(roots)
    while True:
        expanded = selected | {pid for pid, parent in mapping.items() if parent in selected}
        if expanded == selected:
            return selected
        selected = expanded
