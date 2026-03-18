import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql://scheduler:scheduler@localhost:5432/scheduler_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    # Set to True in tests to skip pg_advisory_xact_lock (not supported by SQLite)
    SKIP_ADVISORY_LOCKS = os.getenv("SKIP_ADVISORY_LOCKS", "false").lower() == "true"

    # OpenAPI / flask-smorest
    API_TITLE = "Unified Service Scheduler"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.1.0"
    OPENAPI_URL_PREFIX = "/"
    OPENAPI_SWAGGER_UI_PATH = "/swagger-ui"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_ECHO = False

    # If TEST_DATABASE_URL is set, run against real PostgreSQL (enables advisory locks).
    # Otherwise fall back to SQLite in-memory (fast, no Postgres required).
    _test_db = os.getenv("TEST_DATABASE_URL", "")
    SQLALCHEMY_DATABASE_URI = _test_db if _test_db else "sqlite:///:memory:"

    # Advisory locks: enabled when using a real Postgres URL, disabled for SQLite
    SKIP_ADVISORY_LOCKS = not bool(_test_db)

    # SQLite StaticPool rejects pool_size; PostgreSQL is fine with defaults
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_size": 5, "pool_recycle": 300, "pool_pre_ping": True}
        if _test_db
        else {}
    )


class ProductionConfig(Config):
    DEBUG = False
