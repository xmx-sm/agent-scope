"""应用配置：全部来自 backend/.env（进程环境变量优先）。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agent Scope Platform"
    app_env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = "postgresql+asyncpg://mx:990108@127.0.0.1:5432/agent_scope"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    refresh_token_expire_days: int = 7

    allow_register: bool = True
    default_role: str = "user"

    # 首次启动的超级管理员与演示账号
    seed_admin_username: str = "admin"
    seed_admin_password: str = "000000"
    seed_admin_nickname: str = "admin"
    seed_admin_email: str = "admin@example.com"
    seed_demo_users: bool = True

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    rate_limit_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
