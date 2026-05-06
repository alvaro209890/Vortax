from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    APP_ENV: str = "local_lan"
    APP_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8010
    FRONTEND_PORT: int = 5173
    LAN_ONLY: bool = True
    ALLOW_NO_AUTH: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_TEMPERATURE: float = 0.1
    DEEPSEEK_TIMEOUT_SECONDS: float = 60.0
    LOG_API_ERROR_DETAILS: bool = False

    ENABLE_VISION_TESTS: bool = False
    VISION_PROVIDER: str = "groq_llama4_scout"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_VISION_TEMPERATURE: float = 0.1
    GROQ_VISION_TIMEOUT_SECONDS: float = 60.0

    MAX_ITERATIONS: int = 30
    WORKSPACE_PATH: Path = Path("/media/server/HD Backup/Servidores_NAO_MEXA/Vortax/workspace")
    SCREENSHOT_INTERVAL: int = 5
    STREAM_SCREENSHOT_INTERVAL: int = 2
    SHELL_TIMEOUT_SECONDS: int = 30
    SHELL_VERTEX_TIMEOUT_SECONDS: int = 300

    CHROME_BINARY: str = "/usr/bin/google-chrome"
    CHROME_DEBUG_PORT: int = 9222
    CHROME_PROFILE_PATH: Path = Path("/tmp/vortax-chrome-profile")

    ENABLE_DESKTOP_AUTOMATION: bool = True
    REQUIRE_CONFIRMATION_FOR_DESKTOP: bool = True

    DATABASE_BASE_PATH: Path = Path("/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados")
    DATABASE_EXTENSION: str = ".sqlite"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings(_env_file=PROJECT_ROOT / ".env")
    settings.WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
