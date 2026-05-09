import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  Check,
  Code2,
  Copy,
  Download,
  ExternalLink,
  FileSearch,
  FileText,
  Loader2,
  Monitor,
  Search,
  ShieldCheck,
  Sparkles,
  User,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { staggerContainer, fadeInUp } from "../animations/variants.js";
import { fileDownloadUrl } from "../lib/api.js";

/* ── Code Block with Copy Button ─────────────────────────────────── */

const langAliases = {
  js: "JavaScript",
  jsx: "React JSX",
  ts: "TypeScript",
  tsx: "React TSX",
  py: "Python",
  python: "Python",
  java: "Java",
  html: "HTML",
  css: "CSS",
  scss: "SCSS",
  json: "JSON",
  yaml: "YAML",
  yml: "YAML",
  sh: "Shell",
  bash: "Bash",
  sql: "SQL",
  md: "Markdown",
  xml: "XML",
  c: "C",
  cpp: "C++",
  cs: "C#",
  go: "Go",
  rs: "Rust",
  rb: "Ruby",
  php: "PHP",
  swift: "Swift",
  kt: "Kotlin",
  dart: "Dart",
  r: "R",
  lua: "Lua",
  dockerfile: "Dockerfile",
  makefile: "Makefile",
  toml: "TOML",
  ini: "INI",
  env: ".env",
  txt: "Text",
};

function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);

  // Extract language and code text from children
  const codeElement = children?.props ? children : null;
  const className = codeElement?.props?.className || "";
  const langMatch = className.match(/language-(\w+)/);
  const lang = langMatch ? langMatch[1] : "";
  const langLabel = langAliases[lang] || (lang ? lang.charAt(0).toUpperCase() + lang.slice(1) : "Código");

  const codeText = typeof codeElement?.props?.children === "string"
    ? codeElement.props.children
    : String(codeElement?.props?.children || "");

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(codeText.replace(/\n$/, "")).then(() => {
      setCopied(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 2000);
    });
  }, [codeText]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="code-block-lang">{langLabel}</span>
        <button
          className={`code-block-copy ${copied ? "copied" : ""}`}
          onClick={handleCopy}
          title={copied ? "Copiado!" : "Copiar código"}
          type="button"
        >
          {copied ? (
            <>
              <Check size={13} />
              <span>Copiado</span>
            </>
          ) : (
            <>
              <Copy size={13} />
              <span>Copiar</span>
            </>
          )}
        </button>
      </div>
      <pre>{children}</pre>
    </div>
  );
}

const markdownComponents = {
  pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
};

function fileExtension(path = "") {
  const match = String(path).toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? `.${match[1]}` : "";
}

function documentKind(document) {
  const extension = String(document?.extension || fileExtension(document?.path)).toLowerCase();
  if (document?.kind === "markdown" || extension === ".md" || extension === ".markdown") return "markdown";
  if (document?.kind === "pdf" || extension === ".pdf") return "pdf";
  return "document";
}

function documentLabel(document) {
  const kind = documentKind(document);
  if (kind === "markdown") return "Markdown";
  if (kind === "pdf") return "PDF";
  return "Documento";
}

function formatBytes(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function useMarkdownFile(taskId, document, enabled) {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const path = document?.path || "";

  useEffect(() => {
    if (!enabled || !taskId || !path) {
      setContent("");
      setLoading(false);
      setError(false);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError(false);
    fetch(fileDownloadUrl(taskId, path))
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then((text) => {
        if (!cancelled) setContent(text);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [enabled, taskId, path]);

  return { content, loading, error };
}

function DocumentAttachmentCard({ document, onOpen, taskId }) {
  if (!document?.path || !taskId) return null;
  const kind = documentKind(document);
  const isMarkdown = kind === "markdown";
  const { content, loading, error } = useMarkdownFile(taskId, document, isMarkdown);
  const title = document.title || document.name || document.path;
  const size = formatBytes(document.size_bytes);
  const downloadUrl = fileDownloadUrl(taskId, document.path);

  const handleOpen = () => onOpen?.({ ...document, taskId });
  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleOpen();
    }
  };

  return (
    <article
      className={`document-attachment-card ${kind}`}
      onClick={handleOpen}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      title={`Abrir ${title}`}
    >
      <div className="document-card-header">
        <span className="document-card-icon">
          {isMarkdown ? <BookOpen size={17} /> : <FileText size={17} />}
        </span>
        <div className="document-card-title">
          <strong>{title}</strong>
          <span>
            {documentLabel(document)}
            {size ? ` · ${size}` : ""}
            {document.project_name ? ` · ${document.project_name}` : ""}
          </span>
        </div>
        <a
          className="document-card-download"
          download
          href={downloadUrl}
          onClick={(event) => event.stopPropagation()}
          title={`Baixar ${document.name || document.path}`}
        >
          <Download size={15} />
        </a>
      </div>

      <div className="document-card-preview markdown-body">
        {isMarkdown ? (
          loading ? (
            <p>Carregando prévia...</p>
          ) : error ? (
            <p>Não foi possível carregar a prévia deste Markdown.</p>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || "Documento Markdown pronto para leitura."}</ReactMarkdown>
          )
        ) : (
          <p>PDF pronto para leitura no visualizador interno e download.</p>
        )}
      </div>
    </article>
  );
}

function MessageDocuments({ documents = [], onOpenDocument, taskId }) {
  const items = documents.filter((item) => item?.path && item?.previewable !== false);
  if (!taskId || items.length === 0) return null;

  return (
    <div className="message-documents">
      {items.map((document) => (
        <DocumentAttachmentCard
          document={document}
          key={document.path}
          onOpen={onOpenDocument}
          taskId={taskId}
        />
      ))}
    </div>
  );
}

function DocumentViewerOverlay({ document, onClose, taskId }) {
  const kind = documentKind(document);
  const isMarkdown = kind === "markdown";
  const { content, loading, error } = useMarkdownFile(taskId, document, isMarkdown && Boolean(document?.path));
  const title = document?.title || document?.name || document?.path || "Documento";
  const fileUrl = document?.path && taskId ? fileDownloadUrl(taskId, document.path) : "";

  useEffect(() => {
    if (!document) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [document, onClose]);

  if (!document || !taskId || !fileUrl) return null;

  return (
    <AnimatePresence>
      <motion.div
        className="document-viewer-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.section
          className={`document-viewer ${kind}`}
          initial={{ opacity: 0, y: 18, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 12, scale: 0.985 }}
          transition={{ type: "spring", stiffness: 240, damping: 28 }}
        >
          <header className="document-viewer-header">
            <div className="document-viewer-title">
              <span className="document-card-icon">
                {isMarkdown ? <BookOpen size={18} /> : <FileText size={18} />}
              </span>
              <div>
                <strong>{title}</strong>
                <span>{documentLabel(document)}{document.path ? ` · ${document.path}` : ""}</span>
              </div>
            </div>
            <div className="document-viewer-actions">
              <a href={fileUrl} target="_blank" rel="noreferrer" title="Abrir em nova aba">
                <ExternalLink size={16} />
              </a>
              <a href={fileUrl} download title="Baixar documento">
                <Download size={16} />
              </a>
              <button onClick={onClose} title="Fechar documento" type="button">
                <X size={18} />
              </button>
            </div>
          </header>

          <div className="document-viewer-body">
            {isMarkdown ? (
              <div className="document-viewer-markdown markdown-body">
                {loading ? (
                  <p>Carregando documento...</p>
                ) : error ? (
                  <p>Não foi possível abrir este Markdown.</p>
                ) : (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {content || "Documento vazio."}
                  </ReactMarkdown>
                )}
              </div>
            ) : (
              <iframe className="document-viewer-frame" src={fileUrl} title={title} />
            )}
          </div>
        </motion.section>
      </motion.div>
    </AnimatePresence>
  );
}

function MessageArticle({ message, onOpenDocument }) {
  const documentPaths = new Set((message.documents || []).map((item) => item?.path).filter(Boolean));
  return (
    <motion.article
      className={`message ${message.role}`}
      key={message.id}
      variants={fadeInUp}
    >
      <div className="message-avatar">
        {message.role === "user" ? <User size={18} /> : <Sparkles size={18} />}
      </div>
      <div className="message-content">
        <div className="message-role">{message.role === "user" ? "Você" : "Vortax"}</div>
        {message.content ? (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {message.content}
            </ReactMarkdown>
          </div>
        ) : null}
        <MessageDocuments documents={message.documents} onOpenDocument={onOpenDocument} taskId={message.taskId} />
        <MessageDownloads downloads={message.downloads} excludedPaths={documentPaths} taskId={message.taskId} />
        {message.images?.length > 0 && (
          <div className="message-images">
            {message.images.map((image, index) => (
              <a
                href={`data:${image.content_type};base64,${image.image_base64}`}
                key={`${image.filename || "imagem"}-${index}`}
                rel="noreferrer"
                target="_blank"
                title="Abrir imagem"
              >
                {image.image_base64 ? (
                  <img
                    alt={image.filename || "Imagem enviada para analise"}
                    src={`data:${image.content_type};base64,${image.image_base64}`}
                  />
                ) : (
                  <div className="message-image-pending" />
                )}
                <span>{image.filename || "Imagem"}</span>
              </a>
            ))}
          </div>
        )}
      </div>
    </motion.article>
  );
}

function numericIndex(value) {
  return Number.isFinite(value) ? value : null;
}

function publicText(value) {
  return String(value || "")
    .replace(/\bOpenClaude\b/g, "Vortax")
    .replace(/\bVertex CLI\b/g, "Vortax")
    .replace(/\bVertex\b/g, "Vortax")
    .replace(/\bopenclaude\b/g, "Vortax")
    .replace(/\bvertex\b/g, "Vortax");
}

function latestUserMessage(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "user") return messages[index];
  }
  return null;
}

function likelyTaskPrompt(prompt = "") {
  const value = String(prompt || "").trim().toLowerCase();
  return /(pesquis|busc|procure|not[ií]cia|crie|criar|construa|monte|gere|gerar|desenvolv|implemente|program|c[oó]digo|fa[cç]a|calcule|analise|compare|investigue|verifique|colete|acesse|site|app|dashboard|relat[oó]rio|arquivo|imagem|pdf|planilha|documento|automatize|corrija|edite|altere|melhore|otimize|publique|execute|rode|instale)/i.test(value);
}

function isDirectPlanEvent(event) {
  if (event?.type !== "task_plan_created" && event?.type !== "task_plan_replanned") return false;
  const payload = event.payload || {};
  if (payload.direct) return true;
  const steps = Array.isArray(payload.steps) ? payload.steps : [];
  return steps.length === 1
    && String(steps[0]?.tool_hint || "").toLowerCase() === "deliver"
    && /responder mensagem|resposta direta/i.test(String(steps[0]?.label || steps[0]?.detail || ""));
}

function latestEventIndexBefore(events, beforeIndex, predicate) {
  const limit = Number.isFinite(beforeIndex) ? beforeIndex : events.length;
  for (let index = limit - 1; index >= 0; index -= 1) {
    if (predicate(events[index])) return index;
  }
  return -1;
}

function isDirectResponseSegment(events, previousUserIndex, currentUserIndex, nextUserIndex, message) {
  if (currentUserIndex === null) return false;
  const previousAssistantDoneIndex = latestEventIndexBefore(
    events,
    currentUserIndex,
    (event) => event?.type === "assistant_message_done",
  );
  const start = Math.max(previousUserIndex ?? -1, previousAssistantDoneIndex);
  const end = nextUserIndex ?? events.length;
  const scoped = events.filter((_, index) => index > start && index < end);
  if (scoped.some(isDirectPlanEvent)) return true;
  return !likelyTaskPrompt(message?.content || "")
    && scoped.some((event) => event.type === "agent_progress" && /resposta r[aá]pida/i.test(String(event.payload?.label || "")));
}

function toolKind(name = "") {
  if (name === "browser_google_search") return "search";
  if (["browser_extract_article", "browser_extract_text", "browser_extract_links"].includes(name)) return "source";
  if (name.startsWith("browser_")) return "browser";
  if (name === "shell_run") return "code";
  if (name === "exact_solve") return "validation";
  return "analysis";
}

function stepKind(step = {}) {
  const hint = String(step.tool_hint || "").toLowerCase();
  if (/(research|search|web)/.test(hint)) return "search";
  if (/(code|editor|openclaude|execute|shell|terminal)/.test(hint)) return "code";
  if (/(valid|review|quality)/.test(hint)) return "validation";
  if (/(deliver|finish|file|document|report)/.test(hint)) return "file";
  return "analysis";
}

function toolTitle(name = "", fallback = "Executando etapa") {
  const labels = {
    browser_click_link_by_index: "Abrindo resultado",
    browser_extract_article: "Lendo fonte",
    browser_extract_links: "Extraindo links",
    browser_extract_text: "Lendo pagina",
    browser_get_state: "Verificando navegador",
    browser_google_search: "Pesquisando na web",
    browser_navigate: "Navegando",
    browser_screenshot: "Capturando tela",
    shell_run: "Executando comando",
  };
  return labels[name] || fallback;
}

function summarizeToolResult(result) {
  if (!result) return "";
  if (typeof result === "string") return result;
  if (result.query && Array.isArray(result.results)) return `${result.results.length} resultados para "${result.query}"`;
  if (Array.isArray(result.links)) return `${result.links.length} links encontrados`;
  if (result.opened?.title) return result.opened.title;
  if (result.title && result.url) return `${result.title} - ${result.url}`;
  if (result.text) return String(result.text).slice(0, 220);
  if (result.error) return result.error;
  if (result.success === false) return "A ferramenta retornou falha.";
  return "Pronto";
}

function actionDetail(payload = {}) {
  const params = payload.params || {};
  return payload.description
    || params.query
    || params.url
    || params.command
    || payload.name
    || "";
}

function normalizeOperationalEvent(event, index) {
  const payload = event?.payload || {};
  const id = event?.event_id !== undefined && event?.event_id !== null
    ? `activity-event-${event.event_id}`
    : `activity-${event?.type || "event"}-${event?.created_at || index}-${index}`;

  if (event?.type === "agent_activity") {
    const title = String(payload.title || "").trim();
    if (!title) return null;
    return {
      createdAt: event.created_at || "",
      detail: publicText(payload.detail || ""),
      event,
      eventIndex: index,
      id,
      kind: payload.kind || "analysis",
      metadata: payload.metadata || {},
      status: payload.status || "running",
      title: publicText(title),
      tool: payload.tool || "",
    };
  }

  if (event?.type === "agent_progress") {
    const tool = payload.tool || "";
    const title = payload.label || payload.detail || "Andamento";
    return {
      createdAt: event.created_at || "",
      detail: publicText(payload.detail || ""),
      event,
      eventIndex: index,
      id,
      kind: toolKind(tool),
      metadata: { ...(payload.origin ? { url: payload.origin } : {}) },
      status: "running",
      title: publicText(title),
      tool,
    };
  }

  if (event?.type === "tool_call") {
    const name = payload.name || "";
    return {
      createdAt: event.created_at || "",
      detail: publicText(actionDetail(payload)),
      event,
      eventIndex: index,
      id,
      kind: toolKind(name),
      metadata: payload.params || {},
      status: "running",
      title: toolTitle(name),
      tool: name,
    };
  }

  if (event?.type === "tool_result") {
    const name = payload.name || "";
    const result = payload.result || {};
    return {
      createdAt: event.created_at || "",
      detail: publicText(summarizeToolResult(result)),
      event,
      eventIndex: index,
      id,
      kind: toolKind(name),
      metadata: result || {},
      status: result?.success === false || result?.error ? "failed" : "done",
      title: toolTitle(name, "Resultado"),
      tool: name,
    };
  }

  if (event?.type?.startsWith("task_step_")) {
    const step = payload.step || {};
    const failed = event.type === "task_step_failed" || step.status === "failed";
    const done = event.type === "task_step_completed" || ["passed", "skipped"].includes(step.status);
    return {
      createdAt: event.created_at || "",
      detail: publicText(step.evidence_summary?.at?.(-1) || step.detail || ""),
      event,
      eventIndex: index,
      id,
      kind: stepKind(step),
      metadata: { step_id: step.id, tool_hint: step.tool_hint },
      status: failed ? "failed" : done ? "done" : "running",
      title: publicText(step.label || "Etapa da tarefa"),
      tool: step.tool_hint || "",
    };
  }

  if (event?.type === "source_saved") {
    return {
      createdAt: event.created_at || "",
      detail: publicText(payload.url || payload.title || ""),
      event,
      eventIndex: index,
      id,
      kind: "source",
      metadata: { source_title: payload.title, url: payload.url },
      status: "done",
      title: "Fonte salva",
      tool: "source_saved",
    };
  }

  if (event?.type === "screen_frame") {
    return {
      createdAt: event.created_at || "",
      detail: publicText(payload.caption || payload.title || payload.url || "Tela atualizada"),
      event,
      eventIndex: index,
      id,
      kind: "browser",
      metadata: { title: payload.title, url: payload.url },
      status: "done",
      title: "Tela atualizada",
      tool: "screen_frame",
    };
  }

  if (event?.type === "vertex_progress") {
    const stage = payload.stage || payload.current_stage || "";
    return {
      createdAt: event.created_at || "",
      detail: publicText(payload.file ? `${payload.message || "Trabalhando em"} ${payload.file}` : payload.message || ""),
      event,
      eventIndex: index,
      id,
      kind: "code",
      metadata: { file: payload.file, stage },
      status: payload.status === "done" || stage === "done" ? "done" : payload.status === "error" || stage === "error" ? "failed" : "running",
      title: publicText(payload.title || payload.label || "Vortax no editor"),
      tool: "vertex_progress",
    };
  }

  if (event?.type === "files_created") {
    const fileCount = payload.files?.length || 0;
    const projectCount = payload.projects?.length || 0;
    return {
      createdAt: event.created_at || "",
      detail: `${fileCount} arquivo(s) em ${projectCount || 1} projeto(s).`,
      event,
      eventIndex: index,
      id,
      kind: "file",
      metadata: { files: payload.files || [], projects: payload.projects || [] },
      status: "done",
      title: "Arquivos gerados",
      tool: "files_created",
    };
  }

  return null;
}

function normalizeActivityEvent(event, index) {
  return normalizeOperationalEvent(event, index);
}

function scopedActivities(events = [], afterEventIndex = null, beforeEventIndex = null) {
  return events
    .map((event, index) => ({ activity: normalizeActivityEvent(event, index), index }))
    .filter(({ activity, index }) => activity
      && (afterEventIndex === null || index > afterEventIndex)
      && (beforeEventIndex === null || index < beforeEventIndex))
    .map(({ activity }) => activity);
}

function activityOpening(activities, activeSearch) {
  const latest = activities[activities.length - 1];
  if (latest?.tool === "planning") {
    return "Iniciando ambiente antes da execução.";
  }
  const kind = latest?.kind || (activeSearch ? "search" : "analysis");
  if (kind === "search" || kind === "source" || kind === "browser") {
    return "Pesquisando e verificando fontes.";
  }
  if (kind === "code" || kind === "file") {
    return "Preparando arquivos e execução.";
  }
  if (kind === "validation") {
    return "Conferindo a entrega.";
  }
  if (kind === "finalizing") {
    return "Organizando a resposta final.";
  }
  return "Acompanhando a tarefa.";
}

function activityIcon(kind, size = 14) {
  if (kind === "search") return <Search size={size} />;
  if (kind === "source") return <FileSearch size={size} />;
  if (kind === "browser") return <Monitor size={size} />;
  if (kind === "code") return <Code2 size={size} />;
  if (kind === "file") return <FileText size={size} />;
  if (kind === "validation") return <ShieldCheck size={size} />;
  if (kind === "finalizing") return <Check size={size} />;
  return <Sparkles size={size} />;
}

function activityPillLabel(activity) {
  const metadata = activity.metadata || {};
  if (activity.kind === "search") return metadata.query || activity.detail || activity.title;
  if (activity.kind === "source") return metadata.source_title || metadata.url || activity.detail || activity.title;
  if (activity.kind === "browser") return metadata.url || activity.detail || activity.title;
  if (activity.kind === "file") return metadata.file || activity.detail || activity.title;
  return activity.detail || activity.title;
}

function activityStatusLabel(status) {
  if (status === "done") return "concluído";
  if (status === "failed") return "ajuste";
  if (status === "blocked") return "bloqueado";
  return "em andamento";
}

function normalizeActivityText(value = "") {
  return publicText(value)
    .replace(/https?:\/\/(www\.)?/gi, "")
    .replace(/[?#].*$/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function lowSignalActivity(activity = {}) {
  const title = normalizeActivityText(activity.title);
  return activity.tool === "screen_frame"
    || /planejando proximo passo|planejando próximo passo|tela atualizada|verificando navegador/.test(title);
}

function activitySignature(activity = {}) {
  const metadata = activity.metadata || {};
  const subject = metadata.query
    || metadata.source_title
    || metadata.url
    || metadata.file
    || activity.detail
    || activity.title;
  return [
    activity.kind || "",
    activity.tool || "",
    normalizeActivityText(activity.title),
    normalizeActivityText(subject).slice(0, 140),
  ].join(":");
}

function primaryProgressActivity(activities = [], activeSearch) {
  const meaningful = [...activities].reverse().find((activity) => !activity.synthetic && !lowSignalActivity(activity));
  if (meaningful) return meaningful;
  if (activities.length > 0) return activities[activities.length - 1];
  return {
    detail: activeSearch?.query || "",
    kind: "search",
    status: "running",
    synthetic: true,
    title: "Pesquisando na web",
  };
}

function compactProgressActivities(activities = [], latest) {
  const selected = [];
  const seen = new Set(latest ? [activitySignature(latest)] : []);

  [...activities].reverse().forEach((activity) => {
    if (!activity || activity.synthetic || activity.id === latest?.id) return;
    if (lowSignalActivity(activity) && selected.length > 0) return;
    const signature = activitySignature(activity);
    if (seen.has(signature)) return;
    seen.add(signature);
    selected.push(activity);
  });

  return selected.slice(0, 3).reverse();
}

function pendingPreparationActivity() {
  return {
    createdAt: new Date().toISOString(),
    detail: "Criando plano de tarefas",
    id: "pending-preparation",
    kind: "analysis",
    metadata: {},
    status: "running",
    synthetic: true,
    title: "Iniciando ambiente",
    tool: "planning",
  };
}

function normalizeMessageText(value = "") {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function matchesPendingPreparation(message, pendingPreparation) {
  if (!message || !pendingPreparation) return false;
  if (message.id && message.id === pendingPreparation.id) return true;
  const messageClientId = String(message.clientMessageId || "").trim();
  const pendingClientId = String(pendingPreparation.clientMessageId || "").trim();
  if (messageClientId && pendingClientId) return messageClientId === pendingClientId;
  if (messageClientId || pendingClientId) return false;

  const messageContent = normalizeMessageText(message.content);
  const pendingContent = normalizeMessageText(pendingPreparation.content);
  if (!messageContent || messageContent !== pendingContent) return false;

  const messageTaskId = message.taskId;
  const pendingTaskId = pendingPreparation.taskId;
  return !messageTaskId
    || !pendingTaskId
    || messageTaskId === pendingTaskId
    || messageTaskId === "new"
    || pendingTaskId === "new";
}

function ChatProgressArticle({ activities = [], activeSearch, onComputerFocus }) {
  if (!activities.length && !activeSearch) return null;
  const latest = primaryProgressActivity(activities, activeSearch);
  const visibleActivities = compactProgressActivities(activities, latest);
  const latestDisabled = latest.synthetic || !latest.event;
  const focusActivity = (activity) => onComputerFocus?.({
    activity,
    event: activity.event,
    eventIndex: activity.eventIndex,
  });

  return (
    <article className="message assistant progress-message chat-progress-message">
      <div className="message-avatar">
        <Sparkles size={18} />
      </div>
      <div className="message-content">
        <div className="message-role">Vortax trabalhando</div>
        <div className="chat-progress-copy">{activityOpening(activities, activeSearch)}</div>
        <button
          className={`chat-progress-current ${latest.status || "running"} ${latestDisabled ? "" : "clickable"}`}
          disabled={latestDisabled}
          onClick={() => focusActivity(latest)}
          title={latestDisabled ? undefined : "Ver esta cena no computador do Vortax"}
          type="button"
        >
          <span className="chat-progress-current-icon">
            {latest.status === "running" ? <Loader2 size={14} /> : activityIcon(latest.kind, 14)}
          </span>
          <div>
            <strong>{latest.title}</strong>
            {latest.detail ? <small>{latest.detail}</small> : null}
          </div>
          <em>{activityStatusLabel(latest.status)}</em>
        </button>
        {visibleActivities.length > 0 && (
          <div className="chat-progress-activity-list">
            {visibleActivities.map((activity) => (
              <button
                className={`chat-progress-activity ${activity.kind} ${activity.status}`}
                key={activity.id}
                onClick={() => focusActivity(activity)}
                title="Ver esta cena no computador do Vortax"
                type="button"
              >
                <span className="chat-progress-activity-icon">
                  {activity.status === "running" ? <Loader2 size={13} /> : activityIcon(activity.kind, 13)}
                </span>
                <span className="chat-progress-activity-copy">
                  <strong>{activity.title}</strong>
                  {activity.detail ? <small>{activityPillLabel(activity)}</small> : null}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function buildTimelineItems(messages, events, agentBusy, activeSearch, pendingPreparation) {
  const items = [];
  const latestUser = latestUserMessage(messages);
  let pendingPreparationRendered = false;
  let realProgressRendered = false;

  messages.forEach((message, messageIndex) => {
    items.push({
      key: `message-${message.id}`,
      message,
      type: "message",
    });

    if (message.role === "user") {
      const currentIndex = numericIndex(message.eventIndex);
      const previousUser = [...messages.slice(0, messageIndex)].reverse().find((item) => item.role === "user");
      const previousUserIndex = numericIndex(previousUser?.eventIndex);
      const nextUser = messages.slice(messageIndex + 1).find((item) => item.role === "user");
      const nextUserIndex = numericIndex(nextUser?.eventIndex);
      const isDirectResponse = isDirectResponseSegment(events, previousUserIndex, currentIndex, nextUserIndex, message);
      let activities = currentIndex === null
        ? []
        : scopedActivities(events, currentIndex, nextUserIndex);
      const isLatestUser = message.id === latestUser?.id;

      if (isDirectResponse) {
        activities = [];
      }

      if (!isDirectResponse && isLatestUser && activeSearch && !activities.some((activity) => activity.kind === "search")) {
        activities = [
          ...activities,
          {
            detail: activeSearch.query,
            id: `active-search-${activeSearch.query}`,
            kind: "search",
            metadata: { query: activeSearch.query },
            status: "running",
            synthetic: true,
            title: "Pesquisando na web",
            tool: "browser_google_search",
          },
        ];
      }

      const shouldShowPendingPreparation = !isDirectResponse
        && isLatestUser
        && activities.length === 0
        && (
          matchesPendingPreparation(message, pendingPreparation)
          || (agentBusy && likelyTaskPrompt(message.content))
        );

      if (shouldShowPendingPreparation) {
        activities = [pendingPreparationActivity()];
        pendingPreparationRendered = true;
      }

      const isOnlyPendingPreparation = activities.length === 1 && activities[0]?.tool === "planning";
      if (activities.length > 0 && !isOnlyPendingPreparation) {
        realProgressRendered = true;
      }
      if ((!isLatestUser || !agentBusy) && activities.length > 0 && !isOnlyPendingPreparation) {
        activities = activities.map((activity) => (
          activity.status === "running" ? { ...activity, status: "done" } : activity
        ));
      }

      if (activities.length > 0) {
        items.push({
          activities,
          activeSearch: isLatestUser ? activeSearch : null,
          key: `progress-${message.id}-${activities.map((activity) => activity.id).join("-")}`,
          type: "progress",
        });
      }
    }
  });

  if (pendingPreparation && !pendingPreparationRendered && !realProgressRendered) {
    items.push({
      activities: [pendingPreparationActivity()],
      activeSearch,
      key: `progress-pending-preparation-${pendingPreparation.id || pendingPreparation.createdAt || "current"}`,
      type: "progress",
    });
  }

  if (items.length === 0 && agentBusy) {
    items.push({
      activities: [pendingPreparationActivity()],
      activeSearch,
      key: "progress-pending-empty",
      type: "progress",
    });
  }

  return items;
}

/* ── Downloads ───────────────────────────────────────────────────── */

function MessageDownloads({ downloads = [], excludedPaths = new Set(), taskId }) {
  const items = downloads.filter((item) => item?.path && !excludedPaths.has(item.path));
  if (!taskId || items.length === 0) return null;

  return (
    <div className="message-downloads">
      {items.map((item) => (
        <a
          className="message-download-btn"
          download
          href={fileDownloadUrl(taskId, item.path)}
          key={item.path}
          title={`Baixar ${item.name || item.path}`}
        >
          <FileText size={15} />
          <span>{item.name || item.path}</span>
          <Download size={14} />
        </a>
      ))}
    </div>
  );
}

/* ── Message List ────────────────────────────────────────────────── */

export function MessageList({
  activeSearch,
  agentBusy = false,
  events = [],
  isTyping = false,
  messages,
  onComputerFocus,
  pendingPreparation,
}) {
  const endRef = useRef(null);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const timelineItems = useMemo(
    () => buildTimelineItems(messages, events, agentBusy, activeSearch, pendingPreparation),
    [activeSearch, agentBusy, events, messages, pendingPreparation],
  );
  const showTypingMessage = isTyping && !timelineItems.some((item) => item.type === "progress");
  const lastTimelineKey = timelineItems.at(-1)?.key || "";

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [showTypingMessage, lastTimelineKey, timelineItems.length]);

  return (
    <motion.div
      className="message-list"
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
    >
      <div className="message-list-inner">
        <AnimatePresence initial={false}>
          {timelineItems.map((item) => {
            if (item.type === "progress") {
              return (
                <ChatProgressArticle
                  activities={item.activities}
                  activeSearch={item.activeSearch}
                  key={item.key}
                  onComputerFocus={onComputerFocus}
                />
              );
            }
            return (
              <MessageArticle
                key={item.key}
                message={item.message}
                onOpenDocument={setSelectedDocument}
              />
            );
          })}
        </AnimatePresence>
        {showTypingMessage && (
          <motion.article
            className="message assistant typing-message"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 200, damping: 22 }}
          >
            <div className="message-avatar">
              <Sparkles size={18} />
            </div>
            <div className="message-content">
              <div aria-label="Vortax esta pensando" className="typing-status" role="status">
                <span>Vortax está pensando</span>
                <span className="typing-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </div>
          </motion.article>
        )}
        <div ref={endRef} />
      </div>
      <DocumentViewerOverlay
        document={selectedDocument}
        onClose={() => setSelectedDocument(null)}
        taskId={selectedDocument?.taskId}
      />
    </motion.div>
  );
}
