"""Software stays in files; chat receives a short, evidence-based delivery."""
import io
import os
import re
import zipfile
from pathlib import Path

from services.exact_solver import is_code_creation_request

DELIVERY_INSTRUCTION = (
    "Em criação ou alteração de software, grave o código nos arquivos do workspace. "
    "Na resposta final descreva brevemente o que foi feito, os arquivos, a validação real e pendências. "
    "Não cole código-fonte, árvore completa, tabelas de endpoints ou exemplos extensos no chat. "
    "O Vortax oferece o ZIP com os arquivos quando o usuário pedir; não recrie o projeto para enviar ZIP. "
    "Exemplos curtos de código são permitidos quando o usuário pedir explicitamente um trecho ou explicação."
)
IGNORED_ARCHIVE_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".vue", ".java", ".go", ".rs", ".sh", ".sql"}


def archive_requested(prompt: str) -> bool:
    value = prompt or ''
    if re.search(r'\b(?:não|nao|sem).{0,25}\b(?:zip|compactad[oa])\b', value, re.I):
        return False
    return bool(re.fullmatch(r'\s*(?:o\s+)?zip[?.!\s]*', value, re.I) or re.search(
        r'\b(?:mande|manda|envie|enviar|entregue|baixar|baixe|quero|preciso|gere|gerar|crie|criar|disponibilize).{0,100}\b(?:zip|compactad[oa]s?)\b|\b(?:compacte|compactar)\b', value, re.I))


def explicit_chat_code(prompt: str) -> bool:
    return bool(re.search(r"(?:mostre|cole|exiba|explique|exemplo|trecho|snippet).{0,60}(?:código|codigo)|(?:código|codigo).{0,30}(?:no chat|aqui na conversa)", prompt or "", re.I))


def software_request(prompt: str) -> bool:
    return is_code_creation_request(prompt) and not explicit_chat_code(prompt)


def deliverable_path(path: str) -> bool:
    parts = Path(path).parts
    if any(part in IGNORED_ARCHIVE_DIRS for part in parts):
        return False
    name = Path(path).name
    return name != '.gitkeep' and not (name.startswith('.env') and name not in {'.env.example', '.env.sample', '.env.template'}) and Path(path).suffix not in {'.pyc', '.pyo'}


def project_manifest(project_dir: Path) -> list[dict]:
    base = project_dir.resolve()
    if not base.is_dir():
        return []
    files = []
    for folder, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_ARCHIVE_DIRS and not (Path(folder)/d).is_symlink())
        for name in sorted(names):
            path = Path(folder)/name
            rel = path.relative_to(base).as_posix()
            if not path.is_file() or path.is_symlink() or not deliverable_path(rel):
                continue
            files.append({'path': rel, 'size_bytes': path.stat().st_size})
    return files


def build_project_zip(project_dir: Path) -> io.BytesIO:
    manifest = project_manifest(project_dir)
    if not manifest:
        raise FileNotFoundError('Nenhum arquivo de projeto disponível')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in manifest:
            archive.write(project_dir/file['path'], file['path'])
    buffer.seek(0)
    return buffer


def validation_status(events: list[dict]) -> str:
    for event in reversed(events):
        if event.get('type') in {'project_validation_result', 'web_validation_result'}:
            return str(event.get('payload', {}).get('status') or 'unknown')
    return 'unknown'


def delivery_payload(task_id: str, prompt: str, events: list[dict], project_dir: Path) -> dict | None:
    software = software_request(prompt)
    wants_zip = archive_requested(prompt)
    if not software and not wants_zip:
        return None
    files = project_manifest(project_dir)
    if not files:
        return {'content': 'Ainda não há arquivos de projeto disponíveis para entregar. Não foi gerado um ZIP.', 'delivery': {'kind': 'software', 'file_count': 0, 'validation_status': 'unknown'}}
    current_events = events
    if software:
        last_user = next((i for i in range(len(events)-1, -1, -1) if events[i].get('type') == 'user_message'), -1)
        current_events = events[last_user+1:]
    status = validation_status(current_events)
    paths = [file['path'] for file in files]
    docs = next((p for p in paths if Path(p).name.lower() in {'readme.md', 'documentacao.md'}), None)
    categories = []
    if any(Path(p).suffix in SOURCE_SUFFIXES for p in paths): categories.append('código-fonte')
    if any(Path(p).name in {'requirements.txt', 'package.json', 'pyproject.toml'} for p in paths): categories.append('configuração de dependências')
    if docs: categories.append('documentação')
    if any('tests' in Path(p).parts or Path(p).name.startswith('test_') for p in paths): categories.append('testes')
    lines = ['**Projeto preparado**' if software else '**Arquivos do projeto**']
    if software:
        objective = re.sub(r'\s+', ' ', prompt).strip()[:320].replace('`', '')
        lines.append('Pedido: ' + objective)
    lines.append(f"O projeto contém **{len(files)} arquivos**" + (', incluindo ' + ', '.join(categories) if categories else '') + '.')
    if status == 'passed': lines.append('**Validação:** aprovada na verificação registrada do projeto.')
    elif status == 'failed': lines.append('**Validação:** há falhas registradas; o projeto ainda precisa de correção.')
    else: lines.append('**Validação:** ainda não há uma verificação concluída registrada.')
    if docs: lines.append(f'As instruções de uso estão em `{docs}`. Os arquivos ficam disponíveis no painel **Arquivos**.')
    else: lines.append('Os arquivos ficam disponíveis no painel **Arquivos**.')
    lines.append('Baixe o ZIP no cartão abaixo.' if wants_zip else 'Peça o ZIP quando quiser baixar o projeto completo.')
    payload = {'content': '\n\n'.join(lines), 'delivery': {'kind': 'software', 'file_count': len(files), 'validation_status': status, 'documentation_path': docs}}
    if wants_zip:
        payload['archive'] = {'name': f'vortax-{task_id[:8]}.zip', 'file_count': len(files)}
    return payload
