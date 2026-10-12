import json
import hashlib
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag

from .crypto import decode, decrypt, derive_key, encode, encrypt, wipe
from .entries import entry_identity


VERSION = 2
CHECK = b"kluch-vault-v1"


def catalogue_digest(document):
    return hashlib.sha256(json.dumps(document["entries"], sort_keys=True, separators=(",", ":")).encode("utf-8")).digest()


class Vault:
    def __init__(self, path, timeout=300):
        self.path = Path(path)
        self.timeout = timeout
        self.key = None
        self.document = None
        self.last_used = 0
        self.revision = 0
        self.mutex = threading.RLock()

    def exists(self):
        return self.path.exists()

    def locked(self):
        with self.mutex:
            if self.key is not None and time.monotonic() - self.last_used >= self.timeout:
                self.lock()
            return self.key is None

    def lock(self):
        with self.mutex:
            if self.key is not None:
                self.revision += 1
            wipe(self.key)
            self.key = None
            self.document = None

    def _touch(self):
        if self.locked():
            raise PermissionError("Хранилище заблокировано")
        self.last_used = time.monotonic()

    def create(self, password):
        with self.mutex:
            if self.path.exists():
                raise FileExistsError("Хранилище уже существует")
            salt = os.urandom(16)
            key = derive_key(password, salt, memory=131072)
            document = {"version": VERSION, "salt": encode(salt), "check": encrypt(key, CHECK, b"check-v2"), "entries": []}
            try:
                self._save(document, key)
            except Exception:
                wipe(key)
                raise
            self.lock()
            self.key = key
            self.document = document
            self.last_used = time.monotonic()
            self.revision += 1

    def unlock(self, password):
        with self.mutex:
            try:
                if self.path.stat().st_size > 32 * 1024 * 1024:
                    raise ValueError("Хранилище больше 32 МБ")
                document = json.loads(self.path.read_text(encoding="utf-8"))
            except OSError:
                raise OSError("Не удалось прочитать хранилище. Проверьте доступ к файлу") from None
            except (json.JSONDecodeError, UnicodeError):
                raise ValueError("Файл хранилища повреждён: не удалось прочитать его структуру") from None
            try:
                version = document["version"]
                if version not in (1, 2):
                    raise ValueError("Неподдерживаемая версия хранилища")
                salt = decode(document["salt"])
                if len(salt) != 16 or not isinstance(document["entries"], list):
                    raise ValueError("Некорректная структура хранилища")
                records = [document["check"]]
                if version == 2:
                    records.append(document["seal"])
                for record in records:
                    if len(decode(record["nonce"])) != 12 or len(decode(record["data"])) < 16:
                        raise ValueError("Повреждённая проверка хранилища")
            except (KeyError, TypeError, ValueError):
                raise ValueError("Файл хранилища повреждён или имеет неподдерживаемый формат") from None
            key = derive_key(password, salt, memory=65536 if version == 1 else 131072)
            try:
                try:
                    check = decrypt(key, document["check"], f"check-v{version}".encode())
                except InvalidTag:
                    raise ValueError("Пароль не подходит к этому хранилищу либо повреждена его проверка") from None
                if check != CHECK:
                    raise ValueError("Файл хранилища имеет неизвестную проверку")
                if version == 2:
                    try:
                        seal = decrypt(key, document["seal"], b"catalogue-v2")
                    except InvalidTag:
                        raise ValueError("Мастер-пароль принят, но проверка целостности повреждена") from None
                    if seal != catalogue_digest(document):
                        raise ValueError("Мастер-пароль принят, но содержимое хранилища изменено")
            except Exception:
                wipe(key)
                raise
            self.lock()
            self.key = key
            self.document = document
            self.last_used = time.monotonic()
            self.revision += 1

    def _save(self, document, key=None):
        if document["version"] == 2:
            document["seal"] = encrypt(key if key is not None else self.key, catalogue_digest(document), b"catalogue-v2")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, prefix=".kluch-", delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                json.dump(document, stream, ensure_ascii=False, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def reset(self, password):
        with self.mutex:
            self.lock()
            salt = os.urandom(16)
            key = derive_key(password, salt, memory=131072)
            document = {"version": VERSION, "salt": encode(salt), "check": encrypt(key, CHECK, b"check-v2"), "entries": []}
            try:
                self._save(document, key)
            except Exception:
                wipe(key)
                raise
            self.key = key
            self.document = document
            self.last_used = time.monotonic()
            self.revision += 1

    def _entry(self, record):
        raw = decrypt(self.key, record, ("entry-v1:" + record["id"]).encode("ascii"))
        return {"id": record["id"], **json.loads(raw)}

    def list_entries(self, domain=None):
        with self.mutex:
            self._touch()
            entries = [self._entry(record) for record in self.document["entries"]]
            if domain is not None:
                entries = [entry for entry in entries if entry["domain"] == domain]
            return sorted(entries, key=lambda entry: (entry["domain"], entry["username"]))

    def get(self, entry_id):
        with self.mutex:
            self._touch()
            for record in self.document["entries"]:
                if record["id"] == entry_id:
                    return self._entry(record)
            raise KeyError("Запись не найдена")

    def put(self, domain, username, password, entry_id=None):
        with self.mutex:
            self._touch()
            if entry_id is not None and not any(item["id"] == entry_id for item in self.document["entries"]):
                raise KeyError("Запись не найдена")
            for existing in self.list_entries():
                if entry_identity(existing) == (domain, username, password):
                    if entry_id is not None and entry_id != existing["id"]:
                        raise ValueError("Такая запись уже есть")
                    return existing["id"]
            entry_id = entry_id or str(uuid.uuid4())
            entry = {"domain": domain, "username": username, "password": password}
            raw = json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            record = {"id": entry_id, **encrypt(self.key, raw, ("entry-v1:" + entry_id).encode("ascii"))}
            updated = [item for item in self.document["entries"] if item["id"] != entry_id]
            updated.append(record)
            document = {**self.document, "entries": updated}
            self._save(document)
            self.document = document
            self.revision += 1
            return entry_id

    def delete(self, entry_id):
        with self.mutex:
            self._touch()
            updated = [item for item in self.document["entries"] if item["id"] != entry_id]
            if len(updated) == len(self.document["entries"]):
                raise KeyError("Запись не найдена")
            document = {**self.document, "entries": updated}
            self._save(document)
            self.document = document
            self.revision += 1

    def import_entries(self, entries):
        with self.mutex:
            self._touch()
            known = {entry_identity(entry) for entry in self.list_entries()}
            updated = list(self.document["entries"])
            added = 0
            duplicates = 0
            for entry in entries:
                identity = entry_identity(entry)
                if identity in known:
                    duplicates += 1
                    continue
                known.add(identity)
                entry_id = str(uuid.uuid4())
                raw = json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                updated.append({"id": entry_id, **encrypt(self.key, raw, ("entry-v1:" + entry_id).encode("ascii"))})
                added += 1
            if added:
                document = {**self.document, "entries": updated}
                self._save(document)
                self.document = document
                self.revision += 1
            return {"added": added, "duplicates": duplicates}
