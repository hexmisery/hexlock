import hashlib
import hmac
import secrets
from collections import Counter


def review_entries(entries):
    key = secrets.token_bytes(32)
    fingerprints = [hmac.digest(key, entry["password"].encode("utf-8"), hashlib.sha256) for entry in entries]
    counts = Counter(fingerprints)
    issues = []
    for entry, fingerprint in zip(entries, fingerprints):
        reused = counts[fingerprint] > 1
        short = len(entry["password"]) < 12
        if reused or short:
            issues.append({"id": entry["id"], "reused": reused, "short": short})
    return {"total": len(entries), "reused": sum(item["reused"] for item in issues), "short": sum(item["short"] for item in issues), "issues": issues}
