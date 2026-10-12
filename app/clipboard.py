import ctypes
import threading


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13

kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
user32.SetClipboardData.restype = ctypes.c_void_p
user32.RegisterClipboardFormatW.argtypes = (ctypes.c_wchar_p,)
user32.RegisterClipboardFormatW.restype = ctypes.c_uint
owned_sequence = None
mutex = threading.RLock()


def _put(format_id, data):
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise OSError("Не удалось выделить память")
    try:
        address = kernel32.GlobalLock(handle)
        if not address:
            raise OSError("Не удалось открыть память")
        ctypes.memmove(address, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(format_id, handle):
            raise OSError("Не удалось скопировать")
        handle = None
    finally:
        if handle:
            kernel32.GlobalFree(handle)


def _set(value):
    data = (value + "\0").encode("utf-16-le")
    if not user32.OpenClipboard(None):
        raise OSError("Буфер обмена занят")
    try:
        if not user32.EmptyClipboard():
            raise OSError("Не удалось очистить буфер обмена")
        for name in ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard"):
            format_id = user32.RegisterClipboardFormatW(name)
            if not format_id:
                raise OSError("Не удалось защитить буфер обмена")
            _put(format_id, b"\x00\x00\x00\x00")
        _put(CF_UNICODETEXT, data)
        return user32.GetClipboardSequenceNumber()
    except OSError:
        user32.EmptyClipboard()
        raise
    finally:
        user32.CloseClipboard()


def clear_owned(sequence=None):
    global owned_sequence
    with mutex:
        target = owned_sequence if sequence is None else sequence
        if target is None or target != owned_sequence:
            return True
        if not user32.OpenClipboard(None):
            return False
        try:
            if user32.GetClipboardSequenceNumber() == target and not user32.EmptyClipboard():
                return False
            owned_sequence = None
            return True
        finally:
            user32.CloseClipboard()


def copy_temporarily(value):
    global owned_sequence
    with mutex:
        sequence = _set(value)
        owned_sequence = sequence

    def clear(attempt=0):
        if not clear_owned(sequence) and attempt < 3:
            retry = threading.Timer(1, clear, args=(attempt + 1,))
            retry.daemon = True
            retry.start()

    timer = threading.Timer(20, clear)
    timer.daemon = True
    timer.start()
