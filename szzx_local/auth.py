from __future__ import annotations

import base64
import hashlib
import hmac
import os


_SCRYPT_N = 1 << 14


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=8, p=1, dklen=32
    )
    return "scrypt${}${}${}".format(
        _SCRYPT_N,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n_text, salt_text, digest_text = stored.split("$", 3)
        if algorithm != "scrypt":
            return False
        n = int(n_text)
        if n < (1 << 14) or n > (1 << 18):
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n, r=8, p=1, dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
