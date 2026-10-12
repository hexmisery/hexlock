import os
import ctypes
import threading
from pathlib import Path

import webview

from .bridge import Bridge
from .ipc import Server
from .single_instance import acquire, release
from .permissions import protect_directory
from .clipboard import clear_owned
from .vault import Vault
from .native_fill import start as start_native_fill


def main():
    data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Kluch"
    instance = acquire(data / "vault.json")
    if instance is None:
        ctypes.windll.user32.MessageBoxW(None, "hexlock уже открыт", "hexlock", 0x40)
        return
    try:
        protect_directory(data)
    except OSError:
        release(instance)
        ctypes.windll.user32.MessageBoxW(None, "Не удалось защитить папку хранилища. Проверьте права доступа Windows.", "hexlock", 0x10)
        return
    vault = Vault(data / "vault.json")
    bridge = Bridge(vault)
    page = Path(__file__).parent / "ui" / "index.html"
    window = webview.create_window("hexlock", page.as_uri(), width=920, height=640, min_size=(680, 440))
    window.expose(bridge.status, bridge.create, bridge.unlock, bridge.reset, bridge.lock, bridge.list_entries, bridge.get, bridge.save, bridge.delete, bridge.generate, bridge.copy, bridge.preview_import, bridge.confirm_import, bridge.cancel_import, bridge.export, bridge.review)
    bridge._window = window

    def wake():
        window.show()
        window.restore()

    def approve(domain, username):
        return window.create_confirmation_dialog("Заполнение пароля", f"Передать пароль для {domain}\nЛогин: {username}?")

    server = Server(vault, wake, approve)
    server.start()
    def approve_program(domain, username, destination):
        return window.create_confirmation_dialog("Вставка в приложение", f"Передать пароль для {domain}\nЛогин: {username or 'Без логина'}\nПрограмма: {destination}\n\nДомен этой программы Windows не проверяет. Разрешить?")

    try:
        stop_native_fill = start_native_fill(vault, wake, approve_program)
    except OSError:
        stop_native_fill = lambda: None
        ctypes.windll.user32.MessageBoxW(None, "Заполнение в приложениях недоступно. Копирование и браузерное расширение работают.", "hexlock", 0x40)
    stopped = threading.Event()

    def watch_lock():
        while not stopped.wait(1):
            if vault.locked():
                clear_owned()

    threading.Thread(target=watch_lock, daemon=True).start()
    window.events.closed += lambda: (stopped.set(), bridge.lock(), server.stop())
    window.events.minimized += bridge.lock
    try:
        webview.start(debug=False)
    finally:
        stop_native_fill()
        stopped.set()
        bridge.lock()
        server.stop()
        release(instance)


if __name__ == "__main__":
    main()
