import ctypes
import re
import sys
from pathlib import Path


def main():
    arguments = sys.argv[1:]
    chromium = bool(arguments and re.fullmatch(r"chrome-extension://[a-p]{32}/", arguments[0]))
    firefox = len(arguments) >= 2 and arguments[1] == "kluch@hexmisery.org" and arguments[0].endswith(".json")
    if arguments == ["--native-host"] or chromium or firefox:
        from native_host.host import main as run_host
        run_host()
        return
    if arguments and arguments[0] == "--register":
        from native_host.install import main as register
        try:
            register(arguments[1:], Path(sys.executable) if getattr(sys, "frozen", False) else None)
        except (OSError, ValueError) as error:
            ctypes.windll.user32.MessageBoxW(None, str(error), "hexlock", 0x10)
            raise SystemExit(1)
        return
    if arguments:
        ctypes.windll.user32.MessageBoxW(None, "Регистрация: hexlock.exe --register chrome|edge --extension-id ID\nFirefox: hexlock.exe --register firefox", "hexlock", 0x40)
        return
    from app.main import main as run_app
    run_app()


if __name__ == "__main__":
    main()
