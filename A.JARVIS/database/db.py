"""Central MySQL connection factory for AJARVIS."""

import mysql.connector
from config import Config


def get_connection():
    """Open a short-timeout UTF-8 connection using environment-based settings."""
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
