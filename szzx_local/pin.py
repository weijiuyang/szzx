from __future__ import annotations

import hashlib
import hmac
import os


DEFAULT_PIN = "1234"


def hash_pin(pin: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    expected = hash_pin(pin, salt).split(":", 1)[1]
    return hmac.compare_digest(expected, digest_hex)

