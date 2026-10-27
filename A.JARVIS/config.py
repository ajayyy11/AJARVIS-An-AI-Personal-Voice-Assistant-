import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    MYSQL_USER = os.getenv("MYSQL_USER", "ajarvis_user")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "ajarvis_db")

    SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
