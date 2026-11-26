"""应用配置：全部来自 backend/.env（进程环境变量优先）。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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

    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/agent_scope"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout: int = Field(default=30, ge=1)
    db_pool_recycle: int = Field(default=1800, ge=-1)

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
    redis_max_connections: int = Field(default=100, ge=1)
    rate_limit_enabled: bool = True

    # 标准 A2A 为可选能力：安装 backend/requirements-a2a.txt 后，
    # 再把 A2A_STANDARD_ENABLED 设为 true；否则仅保留 A2A Lite。
    # A2A_PUBLIC_URL 为公网可访问的根地址，例如 https://example.com/agent_scope
    a2a_standard_enabled: bool = False
    a2a_public_url: str = ""
    a2a_agent_name: str = "Agent Scope"
    a2a_agent_description: str = "Agent Scope 标准 A2A 智能体"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
