// Old source-heavy messages stay in the audit history, with a compact chat presentation.
const sourceFile = /\.(py|jsx?|tsx?|html|css|vue|java|go|rs|sh|sql)$/i;
const codeAction = /\b(crie|criar|faca|faça|desenvolva|implemente|gere|corrija|corrigir|edite|editar|altere|alterar|publique|publicar|configure|configurar|automatize|construa|monte|programe)\b/i;
const codeTarget = /\b(codigo|código|site|app|software|sistema|script|api|backend|frontend|html|css|javascript|js|react|node|python|automacao|automação|bug|erro|falha)\b/i;
const explicitCode = /(?:mostre|cole|exiba|explique|exemplo|trecho|snippet).{0,60}(?:código|codigo)|(?:código|codigo).{0,30}(?:no chat|aqui na conversa)/i;

export function isProjectFile(path = "") {
  const parts = path.replaceAll("\\", "/").split("/");
  const name = parts.at(-1);
  return !parts.some((part) => [".git", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"].includes(part))
    && name !== ".gitkeep" && !/\.(pyc|pyo)$/.test(name)
    && !(name.startsWith(".env") && ![".env.example", ".env.sample", ".env.template"].includes(name));
}

export function presentSoftwareMessage(message, files = [], events = []) {
  if (message.role !== "assistant" || !message.final || message.delivery || explicitCode.test(message.prompt || "")) return message;
  if (!codeAction.test(message.prompt || "") || !codeTarget.test(message.prompt || "") || !/```/.test(message.content || "")) return message;
  // Use only files known by this message's delivery, so a later project cannot prove an old result.
  const paths = new Set(events.slice(0, message.eventIndex + 1)
    .filter((event) => ["file_created", "files_created"].includes(event.type))
    .flatMap((event) => event.type === "files_created" ? (event.payload?.files || []).map((file) => file.path) : [event.payload?.path || event.payload?.file?.path]).filter(Boolean));
  const projectFiles = files.filter((file) => paths.has(file.path) && isProjectFile(file.path));
  if (!projectFiles.some((file) => sourceFile.test(file.path))) return message;
  const turnStart = events.slice(0, message.eventIndex + 1).findLastIndex((event) => event.type === "user_message");
  const validation = events.slice(turnStart + 1, message.eventIndex + 1).findLast((event) => ["project_validation_result", "web_validation_result"].includes(event.type));
  const status = validation?.payload?.status;
  const readme = projectFiles.find((file) => /(^|\/)readme\.md$/i.test(file.path));
  const content = [
    "**Projeto preparado**",
    `Foram disponibilizados **${projectFiles.length} arquivos** de projeto no painel **Arquivos**.`,
    status === "passed" ? "**Validação:** aprovada na verificação registrada do projeto." : status === "failed" ? "**Validação:** há falhas registradas; o projeto ainda precisa de correção." : "**Validação:** não há uma verificação concluída registrada nesta entrega.",
    readme ? `As instruções de uso estão em \`${readme.path}\`.` : "",
    "Peça o ZIP quando quiser baixar o projeto completo.",
  ].filter(Boolean).join("\n\n");
  return { ...message, content, downloads: [], documents: [], documentation: null };
}
