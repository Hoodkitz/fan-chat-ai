"""Password hashing with Argon2id."""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()
# Used to equalize timing when the user does not exist.
_DUMMY_HASH = _ph.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return _ph.verify(hashed or _DUMMY_HASH, password) and hashed is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("Passwort muss mindestens 10 Zeichen haben")
    if len(password) > 256:
        problems.append("Passwort ist zu lang")
    if password.lower() == password or password.upper() == password:
        problems.append("Passwort braucht Groß- und Kleinbuchstaben")
    if not any(c.isdigit() for c in password):
        problems.append("Passwort braucht mindestens eine Ziffer")
    return problems
