# config.py

import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env file

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "ajarvis_fallback_key")

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "ajarvis_db")

    SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))