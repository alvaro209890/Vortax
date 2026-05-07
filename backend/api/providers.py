from fastapi import APIRouter, Depends

from auth import AuthUser, require_auth
from config import settings

router = APIRouter()


@router.get("/")
async def provider_status(current_user: AuthUser = Depends(require_auth)) -> dict:
    _ = current_user
    return {
        "providers": [
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "model": settings.DEEPSEEK_MODEL,
                "base_url": settings.DEEPSEEK_BASE_URL,
                "configured": bool(settings.DEEPSEEK_API_KEY.strip()),
                "role": "text_planning",
            },
            {
                "id": settings.VISION_PROVIDER,
                "name": "Groq/Llama 4 Scout",
                "model": settings.GROQ_VISION_MODEL,
                "base_url": settings.GROQ_BASE_URL,
                "configured": settings.ENABLE_VISION_TESTS and bool(settings.GROQ_API_KEY.strip()),
                "role": "vision_tests",
            },
        ]
    }
