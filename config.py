import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def database_url():
    value = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'instance' / 'profut.db').as_posix()}")
    # Some managed providers still expose the historical postgres:// prefix.
    if value.startswith("postgres://"):
        value = "postgresql://" + value.removeprefix("postgres://")
    return value


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me-profut")
    SQLALCHEMY_DATABASE_URI = database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024
    AUTO_SEED = os.getenv("AUTO_SEED", "true").lower() == "true"
    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "true").lower() == "true"


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    AUTO_SEED = False
    AUTO_CREATE_DB = False


class ProductionConfig(Config):
    DEBUG = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    AUTO_SEED = os.getenv("AUTO_SEED", "false").lower() == "true"
    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "false").lower() == "true"
    SESSION_COOKIE_SECURE = True


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
