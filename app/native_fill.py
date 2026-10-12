import ctypes
import os
import threading
from ctypes import wintypes

from .clipboard import clear_owned, copy_temporarily


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)


class MouseEvent(ctypes.Structure):
    _fields_ = [("point", wintypes.POINT), ("data", wintypes.DWORD), ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.IsWindowEnabled.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetAncestor.restype = wintypes.HWND
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, ctypes.c_uint, ctypes.c_size_t, wintypes.LPCWSTR]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
user32.CreateWindowExW.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def password_target(window):
    name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(window, name, len(name))
    style = user32.GetWindowLongW(window, -16)
    if name.value.lower() != "edit" or not style & 0x20 or style & 0x800 or not user32.IsWindowEnabled(window):
        return None
    process = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process))
    if process.value == os.getpid():
        return None
    return window, process.value


def program_name(process_id):
    process = kernel32.OpenProcess(0x1000, False, process_id)
    if not process:
        raise OSError("Не удалось определить программу")
    try:
        name = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(name))
        if not kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)):
            raise OSError("Не удалось определить программу")
        return name.value
    finally:
        kernel32.CloseHandle(process)


def paste_password(vault, target, entry_id, approve):
    destination = program_name(target[1])
    entry = vault.get(entry_id)
    entry.pop("password")
    if not approve(entry["domain"], entry["username"], destination):
        return
    if password_target(target[0]) != target or program_name(target[1]) != destination:
        raise OSError("Поле или программа изменились. Выберите запись заново")
    entry = vault.get(entry_id)
    copy_temporarily(entry["password"])
    try:
        result = ctypes.c_size_t()
        if not user32.SendMessageTimeoutW(target[0], 0xB1, 0, -1, 2, 500, ctypes.byref(result)):
            raise OSError("Не удалось выбрать поле пароля")
        if not user32.SendMessageTimeoutW(target[0], 0x302, 0, 0, 2, 500, ctypes.byref(result)):
            raise OSError("Программа не приняла вставку. Используйте копирование вручную")
    finally:
        clear_owned()


def show_menu(vault, target, point, wake, approve):
    locked = vault.locked()
    entries = [] if locked else [{"id": item["id"], "domain": item["domain"], "username": item["username"]} for item in vault.list_entries()]
    owner = user32.CreateWindowExW(0x80, "STATIC", "hexlock", 0x80000000, point.x, point.y, 0, 0, None, None, kernel32.GetModuleHandleW(None), None)
    menu = user32.CreatePopupMenu()
    choices = user32.CreatePopupMenu()
    if not owner or not menu or not choices:
        if choices:
            user32.DestroyMenu(choices)
        if menu:
            user32.DestroyMenu(menu)
        if owner:
            user32.DestroyWindow(owner)
        raise OSError("Не удалось открыть меню hexlock")
    try:
        if locked:
            user32.AppendMenuW(choices, 0, 1, "Разблокировать hexlock")
        elif entries:
            for index, entry in enumerate(entries):
                label = f"{entry['domain']} · {entry['username'] or 'Без логина'}".replace("&", "&&")
                user32.AppendMenuW(choices, 0, index + 1, label[:180])
        else:
            user32.AppendMenuW(choices, 1, 0, "Нет записей")
        user32.AppendMenuW(menu, 0x10, choices, "Вставить из hexlock")
        user32.ShowWindow(owner, 4)
        user32.SetForegroundWindow(owner)
        selected = user32.TrackPopupMenu(menu, 0x102, point.x, point.y, 0, owner, None)
    finally:
        user32.DestroyMenu(menu)
        user32.DestroyWindow(owner)
    if not selected:
        return
    if locked:
        wake()
        return
    paste_password(vault, target, entries[selected - 1]["id"], approve)


def start(vault, wake, approve):
    ready = threading.Event()
    state = {"thread": None, "error": None}

    def run():
        pending = None
        suppress = False
        thread_id = kernel32.GetCurrentThreadId()
        state["thread"] = thread_id

        @callback_type
        def on_mouse(code, event, data):
            nonlocal pending, suppress
            if code >= 0 and event == 0x204:
                mouse = ctypes.cast(data, ctypes.POINTER(MouseEvent)).contents
                target = password_target(user32.WindowFromPoint(mouse.point))
                if target:
                    pending = target, wintypes.POINT(mouse.point.x, mouse.point.y)
                    suppress = True
                    return 1
            if code >= 0 and event == 0x205 and suppress:
                suppress = False
                user32.PostThreadMessageW(thread_id, 0x8001, 0, 0)
                return 1
            return user32.CallNextHookEx(None, code, event, data)

        hook = user32.SetWindowsHookExW(14, on_mouse, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            state["error"] = "Не удалось включить заполнение в приложениях"
            ready.set()
            return
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x8001 and pending:
                    target, point = pending
                    pending = None
                    try:
                        show_menu(vault, target, point, wake, approve)
                    except (OSError, PermissionError, KeyError):
                        ctypes.windll.user32.MessageBoxW(None, "Не удалось вставить пароль. Проверьте блокировку хранилища и права программы.", "hexlock", 0x10)
                else:
                    user32.TranslateMessage(ctypes.byref(message))
                    user32.DispatchMessageW(ctypes.byref(message))
        finally:
            user32.UnhookWindowsHookEx(hook)

    threading.Thread(target=run, daemon=True).start()
    ready.wait(5)
    if state["error"]:
        raise OSError(state["error"])

    def stop():
        if state["thread"]:
            user32.PostThreadMessageW(state["thread"], 0x12, 0, 0)

    return stop
