import secrets
import string
import re
from urllib.parse import urlsplit
import ipaddress


def hostname(value):
    if not isinstance(value, str) or len(value) > 253:
        raise ValueError("Некорректный домен")
    address = value.strip().lower()
    if not address:
        raise ValueError("Укажите домен")
    parsed = urlsplit(address if "://" in address else "https://" + address)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.port:
        raise ValueError("Укажите домен без пути и порта")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Укажите домен без пути и порта")
    name = parsed.hostname.encode("idna").decode("ascii")
    try:
        return str(ipaddress.ip_address(name))
    except ValueError:
        pass
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in name.split(".")):
        raise ValueError("Некорректный домен")
    return name


def storage_site(value, name=""):
    address = value.strip()
    if len(address) > 4096:
        raise ValueError("Слишком длинный адрес")
    if not address:
        return name.strip()[:253] or "Без сайта"
    if "://" in address:
        parsed = urlsplit(address)
        if parsed.scheme not in ("http", "https"):
            return address
        if parsed.username or parsed.password:
            raise ValueError("Адрес содержит учётные данные")
        domain = parsed.hostname or ""
        return hostname(f"https://[{domain}]" if ":" in domain else domain)
    try:
        parsed = urlsplit("https://" + address)
        domain = parsed.hostname or ""
        if parsed.username or parsed.password:
            raise ValueError("Адрес содержит учётные данные")
        return hostname(f"https://[{domain}]" if ":" in domain else domain)
    except ValueError:
        if "/" in address or ":" in address:
            raise ValueError("Некорректный адрес") from None
        return address[:253]


def entry_identity(entry):
    return entry["domain"], entry["username"], entry["password"]


def generate(length=20):
    length = int(length)
    if not 12 <= length <= 128:
        raise ValueError("Длина от 12 до 128 символов")
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*_-+=?"
    return "".join(secrets.choice(alphabet) for _ in range(length))
