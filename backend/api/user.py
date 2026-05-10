from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import AuthUser, require_auth
from database import database

router = APIRouter()

FACT_KEYS_DISPLAY = {
    "nome": {"label": "Nome", "type": "personal", "editable": True},
    "idade": {"label": "Idade", "type": "personal", "editable": True},
    "localizacao": {"label": "Localização", "type": "personal", "editable": True},
    "escolaridade": {"label": "Escolaridade", "type": "personal", "editable": True},
    "trabalho": {"label": "Trabalho", "type": "professional", "editable": True},
    "cargo": {"label": "Cargo", "type": "professional", "editable": True},
    "ferramentas_gis": {"label": "Ferramentas GIS", "type": "professional", "editable": True},
    "stack_principal": {"label": "Stack", "type": "professional", "editable": True},
    "estilo_comunicacao": {"label": "Estilo de comunicação", "type": "preference", "editable": True},
    "preferencia_resposta": {"label": "Preferência de resposta", "type": "preference", "editable": True},
    "tom_voz": {"label": "Tom de voz", "type": "preference", "editable": True},
    "nivel_detalhe": {"label": "Nível de detalhe", "type": "preference", "editable": True},
}


class UserSettingsUpdate(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=500)
    fact_type: str = Field(default="preference", max_length=30)


@router.get("/settings")
async def get_user_settings(current_user: AuthUser = Depends(require_auth)) -> dict:
    """Retorna as configurações e perfil do usuário."""
    facts = database.get_user_facts(current_user.uid)
    mapped = {}
    for f in facts:
        mapped[f["fact_key"]] = {
            "key": f["fact_key"],
            "value": f["fact_value"],
            "type": f["fact_type"],
            "confidence": f["confidence"],
        }

    # Garante que todas as chaves conhecidas apareçam
    display_fields = []
    for key, meta in FACT_KEYS_DISPLAY.items():
        display_fields.append({
            "key": key,
            "label": meta["label"],
            "type": meta["type"],
            "editable": meta["editable"],
            "value": mapped[key]["value"] if key in mapped else "",
            "confidence": mapped[key]["confidence"] if key in mapped else 0,
            "is_set": key in mapped,
        })

    return {"fields": display_fields}


@router.put("/settings")
async def update_user_setting(payload: UserSettingsUpdate, current_user: AuthUser = Depends(require_auth)) -> dict:
    """Atualiza uma configuração do usuário."""
    if payload.key not in FACT_KEYS_DISPLAY:
        raise HTTPException(status_code=400, detail="Chave de configuração desconhecida")

    key_meta = FACT_KEYS_DISPLAY[payload.key]
    fact_type = payload.fact_type if payload.fact_type in ("personal", "professional", "preference") else key_meta["type"]

    database.upsert_user_fact(
        user_id=current_user.uid,
        fact_key=payload.key,
        fact_value=payload.value.strip(),
        fact_type=fact_type,
        confidence=1.0,
        source_task_id=None,
    )

    return {"ok": True, "key": payload.key, "value": payload.value.strip()}
