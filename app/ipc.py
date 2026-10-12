import json
import os
import secrets
import threading
import uuid
from multiprocessing.connection import Listener
from pathlib import Path

from .entries import hostname


def runtime_file():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Kluch" / "runtime.json"


class Server:
    def __init__(self, vault, wake, approve=None):
        self.vault = vault
        self.wake = wake
        self.approve = approve
        self.path = runtime_file()
        self.address = rf"\\.\pipe\kluch-{uuid.uuid4().hex}"
        self.auth = secrets.token_bytes(32)
        self.listener = None
        self.running = False
        self.slots = threading.BoundedSemaphore(8)

    def start(self):
        self.listener = Listener(self.address, family="AF_PIPE", authkey=self.auth)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"address": self.address, "auth": self.auth.hex()}), encoding="utf-8")
        os.chmod(self.path, 0o600)
        self.running = True
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while self.running:
            try:
                connection = self.listener.accept()
            except (OSError, EOFError):
                break
            if not self.slots.acquire(blocking=False):
                connection.close()
                continue
            threading.Thread(target=self._handle, args=(connection,), daemon=True).start()

    def _handle(self, connection):
        with connection:
            try:
                if not connection.poll(5):
                    raise TimeoutError("request")
                request = json.loads(connection.recv_bytes(maxlength=8192))
                if not isinstance(request, dict):
                    raise ValueError("request")
                action = request.get("action")
                if self.vault.locked():
                    self.wake()
                    response = {"error": "locked"}
                elif action == "list":
                    domain = hostname(request["domain"])
                    response = {"entries": [{"id": entry["id"], "username": entry["username"]} for entry in self.vault.list_entries(domain)]}
                elif action == "get":
                    domain = hostname(request["domain"])
                    entry = self.vault.get(request["id"])
                    if entry["domain"] != domain:
                        response = {"error": "domain"}
                    elif self.approve is None or not self.approve(domain, entry["username"]):
                        response = {"error": "declined"}
                    else:
                        entry = self.vault.get(request["id"])
                        response = {"entry": {"username": entry["username"], "password": entry["password"]}} if entry["domain"] == domain else {"error": "domain"}
                else:
                    response = {"error": "request"}
                connection.send_bytes(json.dumps(response).encode("utf-8"))
            except (EOFError, OSError, KeyError, TypeError, ValueError, AttributeError, PermissionError, TimeoutError, json.JSONDecodeError):
                try:
                    connection.send_bytes(b'{"error":"request"}')
                except OSError:
                    pass
            finally:
                self.slots.release()

    def stop(self):
        self.running = False
        if self.listener:
            self.listener.close()
        self.path.unlink(missing_ok=True)
