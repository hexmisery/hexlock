import ctypes
import hashlib
from pathlib import Path


kernel32 = ctypes.windll.kernel32
kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
ERROR_ALREADY_EXISTS = 183


def acquire(path):
    digest = hashlib.sha256(str(Path(path).resolve()).lower().encode("utf-8")).hexdigest()[:32]
    handle = kernel32.CreateMutexW(None, False, "Local\\Kluch-" + digest)
    if not handle:
        raise OSError("Не удалось открыть хранилище")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle


def release(handle):
    kernel32.CloseHandle(handle)
