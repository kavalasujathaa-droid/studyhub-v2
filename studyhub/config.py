import os
from datetime import timedelta

class BaseConfig:
    """Base configuration with safe defaults."""
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "studyhub-dev-insecure-secret-key-replace-in-production")
    
    # 100 MB per file limit
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_FILE_SIZE_BYTES", 100 * 1024 * 1024))
    MAX_TENANT_STORAGE_BYTES = int(os.environ.get("MAX_TENANT_STORAGE_BYTES", 9 * 1024 * 1024 * 1024)) # 9 GiB safety limit
    
    # Session & Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # SQLAlchemy Core
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Owner Setup Token
    OWNER_BOOTSTRAP_TOKEN = os.environ.get("OWNER_BOOTSTRAP_TOKEN", "")

    # Cloudflare R2 Credentials
    R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
    R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")

    # Flask-Limiter
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_DEFAULT = "200 per minute"
    RATELIMIT_STRATEGY = "fixed-window"

    @staticmethod
    def get_database_uri():
        """Builds TiDB Cloud connection string or falls back to DATABASE_URL."""
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            return db_url

        host = os.environ.get("TIDB_HOST")
        if host:
            user = os.environ.get("TIDB_USER", "root")
            password = os.environ.get("TIDB_PASSWORD", "")
            port = os.environ.get("TIDB_PORT", "4000")
            database = os.environ.get("TIDB_DATABASE", "studyhub_v2")
            return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

        return "sqlite:///studyhub_dev.db"

    @staticmethod
    def get_engine_options(uri):
        """Engine options optimized for TiDB Cloud and connection stability."""
        options = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
        }
        if "mysql" in uri:
            options["pool_size"] = 5
            options["max_overflow"] = 2
            ca_path = os.environ.get("TIDB_CA_PATH")
            ssl_args = {"ssl_mode": "REQUIRED"}
            if ca_path and os.path.exists(ca_path):
                ssl_args["ca"] = ca_path
            options["connect_args"] = {"ssl": ssl_args}
        return options


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    
    SQLALCHEMY_DATABASE_URI = BaseConfig.get_database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = BaseConfig.get_engine_options(SQLALCHEMY_DATABASE_URI)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False
    
    SQLALCHEMY_DATABASE_URI = BaseConfig.get_database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = BaseConfig.get_engine_options(SQLALCHEMY_DATABASE_URI)


class TestingConfig(BaseConfig):
    DEBUG = False
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }
    # Keep attributes loaded across commits during tests
    SQLALCHEMY_SESSION_OPTIONS = {
        "expire_on_commit": False,
    }
    OWNER_BOOTSTRAP_TOKEN = "test-bootstrap-token-12345"
    R2_ACCOUNT_ID = "test-account"
    R2_BUCKET_NAME = "test-bucket"
    R2_ACCESS_KEY_ID = "test-key"
    R2_SECRET_ACCESS_KEY = "test-secret"
    RATELIMIT_ENABLED = False


config_by_name = {
    "production": ProductionConfig,
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
