import csv
import ctypes
import io
import subprocess
from pathlib import Path


advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
advapi32.GetSecurityDescriptorDacl.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int))
advapi32.SetNamedSecurityInfoW.argtypes = (ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
advapi32.SetNamedSecurityInfoW.restype = ctypes.c_uint32
kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
kernel32.LocalFree.restype = ctypes.c_void_p


def protect_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    sid = next(csv.reader(io.StringIO(result.stdout.decode("utf-8", errors="replace"))))[-1].strip()
    if not sid.startswith("S-1-"):
        raise OSError("Не удалось определить пользователя Windows")
    descriptor = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(f"D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)", 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        present = ctypes.c_int()
        defaulted = ctypes.c_int()
        dacl = ctypes.c_void_p()
        if not advapi32.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)):
            raise ctypes.WinError(ctypes.get_last_error())
        for target in [path, *[path / name for name in ("vault.json", "runtime.json") if (path / name).exists()]]:
            error = advapi32.SetNamedSecurityInfoW(str(target), 1, 0x80000004, None, None, dacl, None)
            if error:
                raise ctypes.WinError(error)
    finally:
        kernel32.LocalFree(descriptor)
