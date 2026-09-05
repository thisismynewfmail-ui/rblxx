"""Password hashing, signed tokens and the server secret."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from .. import config

_SECRET: bytes | None = None


def server_secret() -> bytes:
    """Load (or create) the per-installation HMAC secret."""
    global _SECRET
    if _SECRET is not None:
        return _SECRET
    env = os.environ.get("RBLXX_SECRET")
    if env:
        _SECRET = hashlib.sha256(env.encode()).digest()
        return _SECRET
    path = config.SECRET_PATH
    if path.exists():
        _SECRET = path.read_bytes().strip()
    else:
        _SECRET = base64.urlsafe_b64encode(os.urandom(48))
        path.write_bytes(_SECRET)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return _SECRET


# --------------------------------------------------------------------------
# Passwords — PBKDF2-HMAC-SHA256 with a per-user salt
# --------------------------------------------------------------------------
def hash_password(password: str, *, iterations: int | None = None) -> str:
    iterations = iterations or config.PASSWORD_ITERATIONS
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations, base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                 int(iters), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        _, iters, _, _ = stored.split("$")
        return int(iters) < config.PASSWORD_ITERATIONS
    except ValueError:
        return True


# --------------------------------------------------------------------------
# Signed, expiring tokens (sessions, game tickets, node auth)
# --------------------------------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def sign_token(payload: dict, ttl: int, *, purpose: str = "session") -> str:
    body = dict(payload)
    body["_p"] = purpose
    body["_e"] = int(time.time()) + int(ttl)
    body["_n"] = secrets.token_urlsafe(6)
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    encoded = _b64e(raw)
    sig = hmac.new(server_secret(), encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_b64e(sig[:24])}"


def verify_token(token: str, *, purpose: str = "session") -> dict | None:
    if not token or "." not in token:
        return None
    encoded, _, sig = token.partition(".")
    try:
        expect = hmac.new(server_secret(), encoded.encode(),
                          hashlib.sha256).digest()[:24]
        if not hmac.compare_digest(_b64d(sig), expect):
            return None
        body = json.loads(_b64d(encoded))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if body.get("_p") != purpose:
        return None
    if int(body.get("_e", 0)) < time.time():
        return None
    return body


def random_id(nbytes: int = 16) -> str:
    return secrets.token_urlsafe(nbytes)


def hmac_hex(message: str) -> str:
    return hmac.new(server_secret(), message.encode(), hashlib.sha256).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a or "", b or "")
