import argparse
import json
import ctypes
import re
import winreg
import io
from contextlib import redirect_stderr
from pathlib import Path


HOST = "org.hexmisery.kluch"
FIREFOX_ID = "kluch@hexmisery.org"


def install(browser, extension_id, executable):
    executable = executable.resolve(strict=True)
    if browser != "firefox" and not re.fullmatch(r"[a-p]{32}", extension_id or ""):
        raise ValueError("ID расширения должен содержать 32 буквы от a до p")
    base = Path.home() / "AppData" / "Local" / "Kluch" / "native-host"
    base.mkdir(parents=True, exist_ok=True)
    manifest = {"name": HOST, "description": "hexlock", "path": str(executable), "type": "stdio"}
    if browser == "firefox":
        manifest["allowed_extensions"] = [FIREFOX_ID]
        registry = "Software\\Mozilla\\NativeMessagingHosts\\" + HOST
    else:
        manifest["allowed_origins"] = [f"chrome-extension://{extension_id}/"]
        if browser == "edge":
            registry = rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST}"
        else:
            registry = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST}"
    manifest_file = base / f"{browser}.json"
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, registry) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_file))
    return manifest_file


def main(arguments=None, executable=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("browser", choices=["chrome", "edge", "firefox"])
    parser.add_argument("--extension-id")
    errors = io.StringIO()
    try:
        with redirect_stderr(errors):
            args = parser.parse_args(arguments)
    except SystemExit:
        raise ValueError(errors.getvalue().strip() or "Укажите браузер и ID расширения") from None
    if args.browser != "firefox" and not args.extension_id:
        raise ValueError("Для Chrome/Edge нужен --extension-id")
    if executable is None:
        raise ValueError("Сначала соберите hexlock.exe и выполните регистрацию через него")
    install(args.browser, args.extension_id, executable)
    ctypes.windll.user32.MessageBoxW(None, "Связь с браузером настроена. Перезапустите браузер. При перемещении hexlock.exe повторите регистрацию.", "hexlock", 0x40)


if __name__ == "__main__":
    main()
