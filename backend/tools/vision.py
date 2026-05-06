import json
import re
from typing import Any

import httpx

from config import settings
from services.provider_errors import map_httpx_error
from services.safe_diagnostics import format_exception_for_user


class VisionError(RuntimeError):
    pass


def vision_configured() -> bool:
    return settings.ENABLE_VISION_TESTS and bool(settings.GROQ_API_KEY.strip())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def _groq_url() -> str:
    return f"{settings.GROQ_BASE_URL.rstrip('/')}/chat/completions"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _normalize_result(content: str, *, model: str, usage: dict[str, Any] | None) -> dict[str, Any]:
    parsed = _extract_json_object(content)
    if parsed is None:
        return {
            "summary": content.strip(),
            "visible_text": "",
            "ui_elements": [],
            "objects": [],
            "suggested_action": "",
            "confidence": "low",
            "model": model,
            "usage": usage or {},
        }

    confidence = str(parsed.get("confidence") or "medium").lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    return {
        "summary": str(parsed.get("summary") or "").strip(),
        "visible_text": parsed.get("visible_text") or "",
        "ui_elements": parsed.get("ui_elements") or [],
        "objects": parsed.get("objects") or [],
        "suggested_action": str(parsed.get("suggested_action") or "").strip(),
        "confidence": confidence,
        "model": model,
        "usage": usage or {},
    }


class VisionTool:
    async def analyze(
        self,
        image_base64: str | None = None,
        question: str = "Analise esta imagem.",
        content_type: str = "image/jpeg",
        task_id: str | None = None,
    ) -> dict[str, Any]:
        if not vision_configured():
            raise VisionError("Visao Groq nao configurada. Defina ENABLE_VISION_TESTS=true e GROQ_API_KEY.")

        # Se nenhuma imagem foi passada, tenta capturar screenshot automaticamente.
        if not image_base64 or not image_base64.strip():
            from tools.browser import browser_tool
            frame = await browser_tool.screenshot(task_id=task_id or "vision")
            image_base64 = (frame or {}).get("image_base64") or ""
            content_type = "image/jpeg"
            if not image_base64.strip():
                raise VisionError("Nenhuma imagem fornecida e nao foi possivel capturar screenshot.")

        if not image_base64.strip():
            raise VisionError("Imagem vazia para analise.")

        system_prompt = (
            "Voce e o modulo de visao do Vortax. Analise a imagem enviada e responda somente "
            "com um objeto JSON valido contendo: summary, visible_text, ui_elements, objects, "
            "suggested_action e confidence. Use confidence como low, medium ou high. "
            "Quando a pergunta pedir revisao de frontend, seja rigoroso: descreva bugs visuais em suggested_action; "
            "se nao houver bug aparente, diga claramente que nao ha bugs aparentes."
        )
        payload = {
            "model": settings.GROQ_VISION_MODEL,
            "temperature": settings.GROQ_VISION_TEMPERATURE,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question.strip() or "Analise esta imagem."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{content_type};base64,{image_base64}"},
                        },
                    ],
                },
            ],
        }

        timeout = httpx.Timeout(settings.GROQ_VISION_TIMEOUT_SECONDS, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(_groq_url(), headers=_headers(), json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            mapped = map_httpx_error(exc, provider_name="Groq")
            if settings.LOG_API_ERROR_DETAILS:
                raise VisionError(format_exception_for_user(mapped)) from exc
            raise VisionError(str(mapped)) from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VisionError("Resposta Groq sem choices[0].message.content") from exc

        return _normalize_result(
            str(content),
            model=str(data.get("model") or settings.GROQ_VISION_MODEL),
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else {},
        )


vision_tool = VisionTool()
