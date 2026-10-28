"""Database connection factory for local MySQL or hosted PostgreSQL."""

from config import Config


def get_connection():
    """Open a connection using environment-based settings.

    Render uses DATABASE_URL and psycopg 3. Local development remains on the
    existing MySQL configuration unless DATABASE_URL is explicitly supplied.
    """
    if Config.DATABASE_URL:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL is set but psycopg is not installed. "
                "Install the web requirements or psycopg[binary]."
            ) from exc

        database_url = Config.DATABASE_URL
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        return psycopg.connect(
            database_url,
            connect_timeout=Config.MYSQL_CONNECT_TIMEOUT_SECONDS,
        )

    import mysql.connector

    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
        connection_timeout=Config.MYSQL_CONNECT_TIMEOUT_SECONDS,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        use_unicode=True,
        autocommit=False,
    )
