import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
)


def hash_password(password: str) -> str:
    """Hash new passwords with Argon2id."""
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, stored: str) -> bool:
    """Verify Argon2id and legacy PBKDF2 hashes during the migration window."""
    if not stored:
        return False
    if stored.startswith("$argon2"):
        try:
            return _PASSWORD_HASHER.verify(stored, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError, ValueError):
            return False

    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def needs_password_rehash(stored: str) -> bool:
    """Return true for legacy or weaker Argon2 parameters so successful logins can upgrade them."""
    if not stored or not stored.startswith("$argon2"):
        return True
    try:
        return _PASSWORD_HASHER.check_needs_rehash(stored)
    except (InvalidHashError, ValueError):
        return True


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
