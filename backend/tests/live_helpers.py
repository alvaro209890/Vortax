"""Helpers para testes live. NUNCA logar/imprimir a chave.

Ordem de resolução da DEEPSEEK_API_KEY:
1. env DEEPSEEK_API_KEY
2. env VORTAX_LIVE_DEEPSEEK=1 + chave do ~/.hermes/.env
3. arquivo backend/.env (gitignored)
"""

from __future__ import annotations

import os
from pathlib import Path


def load_deepseek_key() -> str | None:
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if key:
        return key
    # Hermes (este PC)
    hermes_env = Path.home() / ".hermes" / ".env"
    if hermes_env.is_file():
        try:
            for line in hermes_env.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        except OSError:
            pass
    # Vortax project .env
    proj = Path(__file__).resolve().parents[2] / ".env"
    if proj.is_file():
        try:
            for line in proj.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        except OSError:
            pass
    return None


def live_enabled() -> bool:
    """Live roda se houver chave E (VORTAX_LIVE=1 ou chave veio do ambiente/hermes)."""
    if os.environ.get("VORTAX_LIVE", "").strip() in {"0", "false", "no"}:
        return False
    key = load_deepseek_key()
    if not key:
        return False
    # Por padrão, se achou chave no hermes/env, permite live (CI sem chave pula)
    return True


def apply_key_to_settings() -> str | None:
    """Injeta a chave no settings do backend (sem printar)."""
    key = load_deepseek_key()
    if not key:
        return None
    os.environ["DEEPSEEK_API_KEY"] = key
    try:
        from config import get_settings, settings

        try:
            get_settings.cache_clear()
        except Exception:
            pass
        # mutar instância já importada pelos módulos
        try:
            settings.DEEPSEEK_API_KEY = key
        except Exception:
            try:
                object.__setattr__(settings, "DEEPSEEK_API_KEY", key)
            except Exception:
                pass
        try:
            import services.deepseek_client as ds

            ds.settings.DEEPSEEK_API_KEY = key
        except Exception:
            pass
    except Exception:
        pass
    return key
