from .clipboard import copy_temporarily, clear_owned
from .entries import generate, storage_site, entry_identity
from .importer import parse, read_file
from pathlib import Path
import secrets
import threading
import time
import webview
from .exporter import export_entries
from .review import review_entries


class Bridge:
    def __init__(self, vault):
        self._vault = vault
        self._window = None
        self._pending_import = None
        self._auth_mutex = threading.Lock()
        self._failures = 0
        self._retry_at = 0

    def status(self):
        locked = self._vault.locked()
        if locked:
            self._pending_import = None
            clear_owned()
        return {"exists": self._vault.exists(), "locked": locked, "timeout": self._vault.timeout, "revision": self._vault.revision}

    def create(self, password, repeated):
        self._validate_master(password, repeated)
        self._vault.create(password)
        return self.status()

    def unlock(self, password):
        if len(password) > 1024:
            raise ValueError("Слишком длинный мастер-пароль")
        with self._auth_mutex:
            remaining = int(self._retry_at - time.monotonic()) + 1
            if remaining > 0:
                raise ValueError(f"Повторите через {remaining} сек.")
            try:
                self._vault.unlock(password)
            except ValueError:
                self._failures += 1
                if self._failures >= 3:
                    self._retry_at = time.monotonic() + min(30, 2 ** min(self._failures - 2, 5))
                raise
            self._failures = 0
            self._retry_at = 0
        return self.status()

    def _validate_master(self, password, repeated):
        if not isinstance(password, str) or not 8 <= len(password) <= 1024:
            raise ValueError("Мастер-пароль: от 8 до 1024 символов")
        if password != repeated:
            raise ValueError("Пароли не совпадают")

    def reset(self, password, repeated, confirmation):
        self._validate_master(password, repeated)
        if confirmation != "СБРОС":
            raise ValueError("Введите СБРОС для подтверждения")
        with self._auth_mutex:
            self._vault.reset(password)
            self._pending_import = None
            self._failures = 0
            self._retry_at = 0
        return self.status()

    def lock(self):
        self._vault.lock()
        clear_owned()
        self._pending_import = None
        return self.status()

    def list_entries(self):
        return [{"id": entry["id"], "domain": entry["domain"], "username": entry["username"]} for entry in self._vault.list_entries()]

    def review(self):
        return review_entries(self._vault.list_entries())

    def get(self, entry_id):
        return self._vault.get(entry_id)

    def save(self, domain, username, password, entry_id=None):
        if not password:
            raise ValueError("Укажите пароль")
        if len(username) > 320 or len(password) > 4096:
            raise ValueError("Слишком длинный логин или пароль")
        with self._vault.mutex:
            revision = self._vault.revision
            saved_id = self._vault.put(storage_site(domain), username, password, entry_id)
            return {"id": saved_id, "unchanged": revision == self._vault.revision}

    def delete(self, entry_id):
        self._vault.delete(entry_id)
        return True

    def generate(self, length):
        return generate(length)

    def copy(self, entry_id, field):
        if field not in ("username", "password"):
            raise ValueError("Неизвестное поле")
        copy_temporarily(self._vault.get(entry_id)[field])
        return True

    def preview_import(self):
        self._pending_import = None
        if self._vault.locked():
            raise PermissionError("Хранилище заблокировано")
        selected = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=("Текстовые таблицы (*.csv;*.tsv;*.txt)",))
        if not selected:
            return None
        path = Path(selected[0])
        data, digest = read_file(path)
        entries, counts = parse(data, path.suffix)
        known = {entry_identity(entry) for entry in self._vault.list_entries()}
        new = []
        for entry in entries:
            identity = entry_identity(entry)
            if identity not in known:
                new.append(entry)
                known.add(identity)
        token = secrets.token_hex(16)
        self._pending_import = (token, path, digest)
        return {"token": token, **counts, "new": len(new), "duplicates": len(entries) - len(new), "examples": [{"domain": entry["domain"], "username": entry["username"]} for entry in new[:5]]}

    def confirm_import(self, token):
        if self._vault.locked():
            self._pending_import = None
            raise PermissionError("Хранилище заблокировано")
        pending = self._pending_import
        self._pending_import = None
        if not pending or not secrets.compare_digest(token, pending[0]):
            raise ValueError("Выберите файл заново")
        data, digest = read_file(pending[1])
        if digest != pending[2]:
            raise ValueError("Файл изменился. Выберите его заново")
        entries, counts = parse(data, pending[1].suffix)
        return {**self._vault.import_entries(entries), "skipped": counts["skipped"]}

    def cancel_import(self):
        self._pending_import = None
        return True

    def export(self, format_name):
        if self._vault.locked():
            raise PermissionError("Хранилище заблокировано")
        if format_name not in ("csv", "tsv", "txt"):
            raise ValueError("Выберите CSV, TSV или TXT")
        if not self._window.create_confirmation_dialog("Экспорт паролей", "В файле будут открытые логины и пароли. Сохранить экспорт?"):
            return None
        selected = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=f"hexlock-export.{format_name}", file_types=(f"Таблица (*.{format_name})",))
        if not selected:
            return None
        destination = Path(selected[0])
        if destination.suffix.lower() != f".{format_name}":
            destination = destination.with_suffix(f".{format_name}")
        if destination.resolve() == self._vault.path.resolve():
            raise ValueError("Нельзя записать экспорт поверх хранилища")
        if destination.exists() and not self._window.create_confirmation_dialog("Экспорт паролей", "Заменить существующий файл?"):
            return None
        entries = self._vault.list_entries()
        export_entries(destination, entries, format_name)
        return {"count": len(entries)}
