import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name, default, minimum, maximum):
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


class Config:
    # No hard-coded fallback: set a unique random value in the local .env file.
    SECRET_KEY = os.getenv("SECRET_KEY")
    if (
        not isinstance(SECRET_KEY, str)
        or len(SECRET_KEY) < 32
        or SECRET_KEY.strip().lower() in {
            "your_super_secret_key_here",
            "replace-with-a-unique-random-secret",
            "change-me",
        }
    ):
        raise RuntimeError(
            "SECRET_KEY must be a unique random value of at least 32 characters. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = _env_int("MYSQL_PORT", 3306, 1, 65535)
    MYSQL_USER = os.getenv("MYSQL_USER", "ajarvis_user")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "ajarvis_db")
    MYSQL_CONNECT_TIMEOUT_SECONDS = _env_int(
        "MYSQL_CONNECT_TIMEOUT_SECONDS", 5, 1, 60
    )
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
    CLOUD_MODE = _env_bool("CLOUD_MODE", False)
    MAX_CONTENT_LENGTH_BYTES = _env_int(
        "MAX_CONTENT_LENGTH_BYTES", 10 * 1024 * 1024, 1024 * 1024, 50 * 1024 * 1024
    )

    SESSION_TIMEOUT_MINUTES = _env_int("SESSION_TIMEOUT_MINUTES", 30, 1, 1440)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", CLOUD_MODE)
