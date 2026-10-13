import hashlib
import hmac
import secrets

# PBKDF2-SHA256 из стандартной библиотеки: без дополнительных зависимостей
_ALGORITHM = 'pbkdf2_sha256'
_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """Хэш пароля в формате algorithm$iterations$salt$hash"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Проверка пароля против сохранённого хэша (сравнение за постоянное время)"""
    try:
        algorithm, iterations, salt, expected = stored_hash.split('$')
    except (ValueError, AttributeError):
        return False
    if algorithm != _ALGORITHM:
        return False
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)
