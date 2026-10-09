// Old source-heavy messages stay in the audit history, with a compact chat presentation.
const sourceFile = /\.(py|jsx?|tsx?|html|css|vue|java|go|rs|sh|sql)$/i;
const codeAction = /\b(crie|criar|faca|faça|desenvolva|implemente|gere|corrija|corrigir|edite|editar|altere|alterar|publique|publicar|configure|configurar|automatize|construa|monte|programe)\b/i;
const codeTarget = /\b(codigo|código|site|app|software|sistema|script|api|backend|frontend|html|css|javascript|js|react|node|python|automacao|automação|bug|erro|falha)\b/i;
const explicitCode = /(?:mostre|cole|exiba|explique|exemplo|trecho|snippet).{0,60}(?:código|codigo)|(?:código|codigo).{0,30}(?:no chat|aqui na conversa)/i;
const documentFile = /\.(pdf|docx|xlsx|pptx|csv|md)$/i;

export function isProjectFile(path = "") {
  const parts = path.replaceAll("\\", "/").split("/");
  const name = parts.at(-1);
  return !parts.some((part) => [".git", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"].includes(part))
    && name !== ".gitkeep" && !/\.(pyc|pyo)$/.test(name)
    && !(name.startsWith(".env") && ![".env.example", ".env.sample", ".env.template"].includes(name));
}

export function documentKindFromPath(path = "") {
  const ext = path.split(".").pop().toLowerCase();
  if (ext === "md" || ext === "markdown") return "markdown";
  if (ext === "pdf") return "pdf";
  if (ext === "docx") return "word";
  if (ext === "pptx") return "presentation";
  if (ext === "xlsx") return "spreadsheet";
  if (ext === "csv") return "csv";
  return "document";
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

export function attachDocumentDeliverables(message, files = [], events = []) {
  if (message.role !== "assistant" || !message.final) return message;
  if (message.delivery) return message;

  const existingDocs = message.documents || [];
  const existingDocPaths = new Set(existingDocs.map((d) => d?.path).filter(Boolean));

  // Determinar eventos do turno
  const maxIdx = message.eventIndex ?? events.length;
  const turnStart = events.slice(0, maxIdx + 1).findLastIndex((e) => e.type === "user_message");
  const turnEvents = events.slice(turnStart >= 0 ? turnStart : 0, maxIdx + 1);

  // Caminhos gerados ou referenciados neste turno
  const createdPaths = new Set(
    turnEvents
      .filter((e) => ["file_created", "files_created"].includes(e.type))
      .flatMap((e) => (e.type === "files_created" ? (e.payload?.files || []).map((f) => f.path) : [e.payload?.path || e.payload?.file?.path]))
      .filter(Boolean)
  );

  turnEvents.forEach((e) => {
    if (e.type === "tool_call" || e.type === "tool_result") {
      const p = e.payload?.params || e.payload?.result;
      if (p?.pdf_path) createdPaths.add(p.pdf_path);
      if (p?.markdown_path) createdPaths.add(p.markdown_path);
      if (p?.path) createdPaths.add(p.path);
    }
  });

  const content = String(message.content || "");
  const mentionedFileNames = new Set(
    (content.match(/\b[\w.-]+\.(pdf|docx|xlsx|pptx|csv|md)\b/gi) || []).map((s) => s.toLowerCase())
  );

  const candidateFiles = files.filter((f) => {
    if (!f?.path || existingDocPaths.has(f.path)) return false;
    if (!documentFile.test(f.path)) return false;
    const name = f.path.split("/").pop().toLowerCase();
    return createdPaths.has(f.path) || mentionedFileNames.has(name) || (createdPaths.size === 0 && files.length <= 5);
  });

  if (!candidateFiles.length) return message;

  // Priorizar PDF primeiro, depois office, depois markdown
  const sortedCandidates = [...candidateFiles].sort((a, b) => {
    const extA = a.path.split(".").pop().toLowerCase();
    const extB = b.path.split(".").pop().toLowerCase();
    if (extA === "pdf" && extB !== "pdf") return -1;
    if (extB === "pdf" && extA !== "pdf") return 1;
    return 0;
  });

  const newDocs = sortedCandidates.map((file, idx) => ({
    path: file.path,
    name: file.name || file.path.split("/").pop(),
    title: file.title || file.name || file.path.split("/").pop(),
    extension: file.extension || ("." + file.path.split(".").pop().toLowerCase()),
    kind: documentKindFromPath(file.path),
    size_bytes: file.size_bytes || 0,
    previewable: true,
    primary: existingDocs.length === 0 && idx === 0,
    source: "generated",
  }));

  const newDownloads = sortedCandidates.map((file) => ({
    path: file.path,
    name: file.name || file.path.split("/").pop(),
    extension: file.extension || ("." + file.path.split(".").pop().toLowerCase()),
    size_bytes: file.size_bytes || 0,
  }));

  const existingDownloads = message.downloads || [];
  const existingDownloadPaths = new Set(existingDownloads.map((d) => d?.path).filter(Boolean));

  return {
    ...message,
    documents: [...existingDocs, ...newDocs],
    downloads: [
      ...existingDownloads,
      ...newDownloads.filter((d) => !existingDownloadPaths.has(d.path)),
    ],
  };
}
