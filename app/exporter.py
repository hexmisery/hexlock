import csv
import os
import tempfile
from pathlib import Path
from .entries import hostname


def export_entries(path, entries, format_name):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=path.parent, prefix=".hexlock-export-", delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            writer = csv.writer(stream, delimiter="," if format_name == "csv" else "\t")
            writer.writerow(("name", "url", "username", "password"))
            for entry in entries:
                site = entry["domain"]
                if "://" in site:
                    address = site
                else:
                    try:
                        domain = hostname(f"https://[{site}]" if ":" in site else site)
                        address = "https://" + (f"[{domain}]" if ":" in domain else domain) if domain == site else ""
                    except ValueError:
                        address = ""
                writer.writerow((site, address, entry["username"], entry["password"]))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
