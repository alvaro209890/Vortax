import re
from typing import Any


GITHUB_HOST_RE = re.compile(
    r"(?:https?://)?github\.com/(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9._-]+)(?:\.git)?(?:[/?#][^\s]*)?",
    re.IGNORECASE,
)
OWNER_REPO_RE = re.compile(
    r"(?<![\w.-])(?P<owner>[A-Za-z0-9-]{1,39})/(?P<repo>[A-Za-z0-9._-]{1,100})(?:\.git)?(?![\w.-])"
)
GITHUB_CONTEXT_RE = re.compile(r"\b(github|repo|repositorio|reposit[oó]rio)\b", re.IGNORECASE)
ANALYSIS_RE = re.compile(
    r"\b(analis(?:e|ar|ando)|auditor(?:ia|ar)|rev(?:ise|isar|isao|isão)|code\s+review|"
    r"diagn[oó]stico|map(?:ear|eamento)|arquitetura|estrutura|qualidade|bugs?|"
    r"vulnerabilidade|seguran[cç]a|performance|depend[eê]ncias|retornos?)\b",
    re.IGNORECASE,
)


def normalize_public_github_repo(text: str) -> dict[str, Any] | None:
    value = str(text or "")
    match = GITHUB_HOST_RE.search(value)
    if not match and GITHUB_CONTEXT_RE.search(value):
        match = OWNER_REPO_RE.search(value)
    if not match:
        return None

    owner = match.group("owner")
    repo = match.group("repo")
    repo = re.sub(r"\.git$", "", repo, flags=re.IGNORECASE)
    if not owner or not repo or owner.lower() in {"github.com", "http:", "https:"}:
        return None

    return {
        "owner": owner,
        "repo": repo,
        "full_name": f"{owner}/{repo}",
        "clone_url": f"https://github.com/{owner}/{repo}.git",
        "html_url": f"https://github.com/{owner}/{repo}",
    }


def is_github_repo_analysis_request(text: str) -> bool:
    return bool(normalize_public_github_repo(text) and ANALYSIS_RE.search(str(text or "")))
