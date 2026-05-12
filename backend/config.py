from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_BASE_PATH = Path("/media/server/HD Backup/Servidores_NAO_MEXA/Banco_de_dados")
DEFAULT_VORTAX_DATA_PATH = DEFAULT_DATABASE_BASE_PATH / "Vortax"


class Settings(BaseSettings):
    APP_ENV: str = "local_lan"
    APP_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8010
    FRONTEND_PORT: int = 5173
    LAN_ONLY: bool = True
    ALLOW_NO_AUTH: bool = False
    ALLOW_LAN_NO_AUTH: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://192.168.0.104:5173,https://notazap-2520f.web.app,https://notazap-2520f.firebaseapp.com"
    PUBLIC_HOSTS: str = "vortax-api.cursar.space"
    FIREBASE_PROJECT_ID: str = "notazap-2520f"
    FIREBASE_CREDENTIALS_PATH: str = ""
    FIREBASE_SERVICE_ACCOUNT_JSON: str = ""
    DEV_USER_ID: str = "local-dev-user"

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
    GROQ_TASK_PLANNER_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TASK_PLANNER_TEMPERATURE: float = 0.15
    GROQ_TASK_PLANNER_TIMEOUT_SECONDS: float = 20.0
    GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_VISION_TEMPERATURE: float = 0.1
    GROQ_VISION_TIMEOUT_SECONDS: float = 60.0

    MAX_ITERATIONS: int = 30
    DEEP_RESEARCH_DEPTH: int = 3
    CONTEXT_TOKEN_LIMIT: int = 24000
    CONTEXT_WARNING_RATIO: float = 0.70
    CONTEXT_COMPACT_RATIO: float = 0.88
    CONTEXT_RECENT_MESSAGES: int = 8
    CONTEXT_SUMMARY_MAX_CHARS: int = 5000
    WORKSPACE_PATH: Path = DEFAULT_VORTAX_DATA_PATH / "projetos"
    RUNTIME_PATH: Path = DEFAULT_VORTAX_DATA_PATH / "runtime"
    SCREENSHOT_INTERVAL: int = 5
    STREAM_SCREENSHOT_INTERVAL: int = 2
    SHELL_TIMEOUT_SECONDS: int = 30
    SHELL_CODE_AGENT_TIMEOUT_SECONDS: int = 300
    SHELL_VERTEX_TIMEOUT_SECONDS: int = 300  # legacy env fallback
    CODE_AGENT_COMMAND: str = "vertex"
    CODE_AGENT_LABEL: str = "Vertex"
    CODE_AGENT_PATH_EXTRA: str = "/home/server/.local/bin:/home/server/.nvm/versions/node/v20.20.0/bin"
    CODE_AGENT_STATIC_READY_SECONDS: float = 4.0
    VERTEX_STATIC_READY_SECONDS: float = 4.0  # legacy env fallback
    CODE_AGENT_STATIC_INCOMPLETE_SECONDS: float = 45.0
    VERTEX_STATIC_INCOMPLETE_SECONDS: float = 45.0  # legacy env fallback
    PROJECT_VALIDATION_TIMEOUT_SECONDS: int = 60

    CHROME_BINARY: str = "/usr/bin/google-chrome"
    CHROME_DEBUG_PORT: int = 9222
    CHROME_PROFILE_PATH: Path = DEFAULT_VORTAX_DATA_PATH / "chrome-profile"
    BROWSER_POOL_MAX_INSTANCES: int = 4

    ENABLE_DESKTOP_AUTOMATION: bool = True
    REQUIRE_CONFIRMATION_FOR_DESKTOP: bool = True

    DATABASE_BASE_PATH: Path = DEFAULT_DATABASE_BASE_PATH
    DATABASE_EXTENSION: str = ".sqlite"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def public_hosts_list(self) -> list[str]:
        return [host.strip().lower() for host in self.PUBLIC_HOSTS.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings(_env_file=PROJECT_ROOT / ".env")
    settings.WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
    settings.RUNTIME_PATH.mkdir(parents=True, exist_ok=True)
    settings.CHROME_PROFILE_PATH.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
