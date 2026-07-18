"""Permissões por ação no Vortax.

Diferencia leitura, criação de arquivos, shell, navegação e ações destrutivas.
Por padrão usuários autenticados (ou LAN/dev) têm capabilities completas;
restrições vêm de env `VORTAX_DENIED_CAPABILITIES` (csv) ou perfil futuro.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet

from fastapi import HTTPException, status

from auth import AuthUser
from config import settings


# Capabilities canônicas
CAP_READ = "read"
CAP_WRITE_FILES = "write_files"
CAP_SHELL = "shell"
CAP_BROWSER = "browser"
CAP_DESKTOP = "desktop"
CAP_DESTRUCTIVE = "destructive"  # delete task, stop, limpar workspace
CAP_EXPORT = "export"
CAP_ADMIN = "admin"

ALL_CAPS = frozenset(
    {
        CAP_READ,
        CAP_WRITE_FILES,
        CAP_SHELL,
        CAP_BROWSER,
        CAP_DESKTOP,
        CAP_DESTRUCTIVE,
        CAP_EXPORT,
        CAP_ADMIN,
    }
)

# Mapa tool → capability mínima
TOOL_CAPABILITIES: dict[str, str] = {
    "shell_run": CAP_SHELL,
    "file_read": CAP_READ,
    "file_write": CAP_WRITE_FILES,
    "file_edit": CAP_WRITE_FILES,
    "file_append": CAP_WRITE_FILES,
    "glob": CAP_READ,
    "grep": CAP_READ,
    "browser_google_search": CAP_BROWSER,
    "browser_navigate": CAP_BROWSER,
    "browser_click": CAP_BROWSER,
    "browser_type": CAP_BROWSER,
    "browser_extract_text": CAP_BROWSER,
    "browser_extract_article": CAP_BROWSER,
    "browser_extract_links": CAP_BROWSER,
    "browser_screenshot": CAP_BROWSER,
    "browser_scroll": CAP_BROWSER,
    "browser_press_key": CAP_BROWSER,
    "vision_analyze": CAP_READ,
    "exact_solve": CAP_READ,
}


@dataclass(frozen=True)
class CapabilitySet:
    granted: FrozenSet[str]

    def allows(self, cap: str) -> bool:
        if CAP_ADMIN in self.granted:
            return True
        return cap in self.granted


@lru_cache(maxsize=1)
def _denied_from_env() -> FrozenSet[str]:
    raw = str(getattr(settings, "VORTAX_DENIED_CAPABILITIES", "") or "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def capabilities_for(user: AuthUser) -> CapabilitySet:
    denied = _denied_from_env()
    granted = set(ALL_CAPS)
    # Dev/LAN sem Firebase: sem CAP_ADMIN por padrão (evita ops perigosas se restringir env)
    if user.is_dev and denied:
        granted -= denied
    else:
        granted -= denied
    return CapabilitySet(granted=frozenset(granted))


def require_capability(user: AuthUser, cap: str) -> None:
    caps = capabilities_for(user)
    if not caps.allows(cap):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permissao negada: capability '{cap}' nao liberada para este usuario.",
        )


def tool_allowed(user: AuthUser, tool_name: str) -> bool:
    cap = TOOL_CAPABILITIES.get(tool_name, CAP_READ)
    return capabilities_for(user).allows(cap)


def assert_tool_allowed(user: AuthUser | None, tool_name: str) -> None:
    if user is None:
        return
    if not tool_allowed(user, tool_name):
        raise PermissionError(f"Tool '{tool_name}' bloqueada pela politica de permissoes.")
