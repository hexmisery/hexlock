import csv
import hashlib
import io
from pathlib import Path

from .entries import storage_site


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10000
SITE_HEADERS = ("url", "origin", "website", "site", "hostname", "domain", "login_uri", "сайт", "адрес")
USER_HEADERS = ("username", "login", "user", "user name", "email", "login_username", "логин", "пользователь")
PASSWORD_HEADERS = ("password", "pass", "login_password", "пароль")
NAME_HEADERS = ("name", "title", "название", "имя")


def read_file(path):
    file = Path(path)
    if file.suffix.lower() not in (".csv", ".tsv", ".txt"):
        raise ValueError("Нужен CSV, TSV или TXT")
    if file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Файл больше 10 МБ")
    data = file.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Файл больше 10 МБ")
    return data, hashlib.sha256(data).hexdigest()


def decode_text(data):
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return data.decode("utf-16")
        return data.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("Нужен текст в UTF-8 или UTF-16") from None


def column(headers, names):
    for name in names:
        if name in headers:
            return headers.index(name)
    raise ValueError("Не найдены колонки сайта, логина и пароля")


def parse(data, suffix):
    text = decode_text(data)
    if "\x00" in text:
        raise ValueError("Неверная кодировка файла")
    sample = text[:8192]
    if suffix.lower() == ".tsv":
        delimiter = "\t"
    else:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = "\t" if "\t" in sample else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        headers = [header.strip().lower() for header in next(reader)]
    except StopIteration:
        raise ValueError("Файл пуст") from None
    except csv.Error:
        raise ValueError("Не удалось разобрать таблицу") from None
    site_index = column(headers, SITE_HEADERS)
    user_index = column(headers, USER_HEADERS)
    password_index = column(headers, PASSWORD_HEADERS)
    name_index = next((headers.index(name) for name in NAME_HEADERS if name in headers), None)
    rows = []
    skipped = 0
    total = 0
    reasons = {}
    rejected = []
    try:
        for row in reader:
            total += 1
            if total > MAX_ROWS:
                raise ValueError("В файле больше 10 000 строк")
            try:
                if len(row) <= max(site_index, user_index, password_index):
                    raise ValueError("Не хватает колонок")
                address = row[site_index].strip()
                name = row[name_index] if name_index is not None and name_index < len(row) else ""
                site = storage_site(address, name)
                username = row[user_index].strip()
                password = row[password_index]
                if not password:
                    raise ValueError("Пустой пароль")
                if len(username) > 320 or len(password) > 4096:
                    raise ValueError("Слишком длинный логин или пароль")
                rows.append({"domain": site, "username": username, "password": password})
            except ValueError as error:
                skipped += 1
                reason = str(error)
                if reason not in ("Не хватает колонок", "Не указан сайт", "Адрес приложения или неподдерживаемая схема", "Адрес содержит учётные данные", "Пустой пароль", "Слишком длинный логин или пароль"):
                    reason = "Некорректный домен"
                reasons[reason] = reasons.get(reason, 0) + 1
                if len(rejected) < 20:
                    rejected.append({"line": reader.line_num, "reason": reason})
    except csv.Error:
        raise ValueError("Не удалось разобрать таблицу") from None
    return rows, {"total": total, "skipped": skipped, "reasons": reasons, "rejected": rejected}
