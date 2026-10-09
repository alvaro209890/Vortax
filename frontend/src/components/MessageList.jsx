import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowDown,
  BookOpen,
  Check,
  Copy,
  Download,
  ExternalLink,
  FileSpreadsheet,
  FileText,
  Presentation,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { staggerContainer, fadeInUp } from "../animations/variants.js";
import { useStickToBottom } from "../hooks/useStickToBottom.js";
import { fileDownloadUrl, getAuthToken, taskDownloadZipUrl } from "../lib/api.js";
import { attachDocumentDeliverables, presentSoftwareMessage } from "../lib/softwareDelivery.js";
import { StatusIndicator } from "./StatusIndicator.jsx";
import { PreparingTurn, TurnActivity } from "./TurnActivity.jsx";

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
  if (document?.kind === "word" || extension === ".docx") return "word";
  if (document?.kind === "presentation" || extension === ".pptx") return "presentation";
  if (document?.kind === "spreadsheet" || extension === ".xlsx") return "spreadsheet";
  if (document?.kind === "csv" || extension === ".csv") return "csv";
  return "document";
}

function documentLabel(document) {
  const kind = documentKind(document);
  if (kind === "markdown") return "Markdown";
  if (kind === "pdf") return "PDF";
  if (kind === "word") return "Word DOCX";
  if (kind === "presentation") return "PowerPoint PPTX";
  if (kind === "spreadsheet") return "Excel XLSX";
  if (kind === "csv") return "CSV";
  return "Documento";
}

function DocumentIcon({ kind, size = 17 }) {
  if (kind === "markdown") return <BookOpen size={size} />;
  if (kind === "presentation") return <Presentation size={size} />;
  if (kind === "spreadsheet" || kind === "csv") return <FileSpreadsheet size={size} />;
  return <FileText size={size} />;
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

function downloadBlob(taskId, path, filename) {
  const url = fileDownloadUrl(taskId, path);
  fetch(url)
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.blob();
    })
    .then((blob) => {
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename || path.split("/").pop() || "download";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    })
    .catch(() => {
      window.open(url, "_blank");
    });
}

function DocumentAttachmentCard({ document, onOpen, taskId }) {
  if (!document?.path || !taskId) return null;
  const kind = documentKind(document);
  const isMarkdown = kind === "markdown";
  const { content, loading, error } = useMarkdownFile(taskId, document, isMarkdown);
  const title = document.title || document.name || document.path;
  const size = formatBytes(document.size_bytes);

  const handleOpen = () => onOpen?.({ ...document, taskId });
  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleOpen();
    }
  };

  const handleDownload = (event) => {
    event.stopPropagation();
    event.preventDefault();
    downloadBlob(taskId, document.path, document.name || document.path);
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
          <DocumentIcon kind={kind} size={17} />
        </span>
        <div className="document-card-title">
          <strong>{title}</strong>
          <span>
            {documentLabel(document)}
            {size ? ` · ${size}` : ""}
            {document.project_name ? ` · ${document.project_name}` : ""}
          </span>
        </div>
        <button
          className="document-card-download"
          onClick={handleDownload}
          title={`Baixar ${document.name || document.path}`}
          type="button"
        >
          <Download size={15} />
        </button>
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
        ) : kind === "pdf" ? (
          <p>Documento PDF formatado · Clique para abrir no leitor ou use o botão para baixar.</p>
        ) : (
          <p>{documentLabel(document)} pronto para download.</p>
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
  const isPdf = kind === "pdf";
  const { content, loading, error } = useMarkdownFile(taskId, document, isMarkdown && Boolean(document?.path));
  const title = document?.title || document?.name || document?.path || "Documento";

  useEffect(() => {
    if (!document) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [document, onClose]);

  if (!document || !taskId || !document.path) return null;

  const handleDownload = () => {
    downloadBlob(taskId, document.path, document.name || document.path);
  };

  const handleExternalOpen = () => {
    window.open(fileDownloadUrl(taskId, document.path), "_blank");
  };

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
                <DocumentIcon kind={kind} size={18} />
              </span>
              <div>
                <strong>{title}</strong>
                <span>{documentLabel(document)}{document.path ? ` · ${document.path}` : ""}</span>
              </div>
            </div>
            <div className="document-viewer-actions">
              <button onClick={handleExternalOpen} title="Abrir em nova aba" type="button">
                <ExternalLink size={16} />
              </button>
              <button onClick={handleDownload} title="Baixar documento" type="button">
                <Download size={16} />
              </button>
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
            ) : isPdf ? (
              <iframe className="document-viewer-frame" src={fileDownloadUrl(taskId, document.path)} title={title} />
            ) : (
              <div className="document-download-panel">
                <span className="document-download-icon">
                  <DocumentIcon kind={kind} size={32} />
                </span>
                <strong>{documentLabel(document)} pronto</strong>
                <p>Este formato fica disponível para baixar e abrir no aplicativo compatível.</p>
                <button className="message-download-btn" onClick={handleDownload} type="button">
                  <Download size={16} />
                  <span>Baixar {document.name || document.path}</span>
                </button>
              </div>
            )}
          </div>
        </motion.section>
      </motion.div>
    </AnimatePresence>
  );
}

function AssistantByline({ label = "Vortax" }) {
  return (
    <div className="message-role">
      <img alt="" className="message-role-mark" src="/vortax-icon-32.png" />
      {label}
    </div>
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
      <div className="message-content">
        {message.role !== "user" && <AssistantByline />}
        {message.content ? (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {message.content}
            </ReactMarkdown>
          </div>
        ) : null}
        <MessageDocuments documents={message.documents} onOpenDocument={onOpenDocument} taskId={message.taskId} />
        <MessageDownloads downloads={message.downloads} excludedPaths={documentPaths} taskId={message.taskId} />
        {message.archive && <ProjectArchive archive={message.archive} taskId={message.taskId} />}
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

function likelyTaskPrompt(prompt = "") {
  const value = String(prompt || "").trim().toLowerCase();
  return /(pesquis|busc|procure|not[ií]cia|crie|criar|construa|monte|gere|gerar|desenvolv|implemente|program|c[oó]digo|fa[cç]a|calcule|analise|compare|investigue|verifique|colete|acesse|site|app|dashboard|relat[oó]rio|arquivo|imagem|pdf|planilha|documento|automatize|corrija|edite|altere|melhore|otimize|publique|execute|rode|instale|naveg)/i.test(value);
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

// Um turno só mostra acompanhamento quando houve trabalho de ferramenta (ou ele está
// começando um pedido de tarefa). Conversa simples não ganha cartão de progresso.
function showsActivity(turn, message) {
  if (!turn) return false;
  if (turn.actions.length > 0) return true;
  if (!["running", "paused", "waiting"].includes(turn.status)) return false;
  if (turn.events.some(({ event }) => isDirectPlanEvent(event))) return false;
  return turn.status === "waiting" || likelyTaskPrompt(message?.content || "");
}

function buildTimelineItems(messages, turns, pendingPreparation, agentBusy) {
  const turnByUserIndex = new Map(turns.filter((turn) => turn.userIndex >= 0).map((turn) => [turn.userIndex, turn]));
  const items = [];
  let activityShown = false;
  messages.forEach((message) => {
    items.push({ key: `message-${message.id}`, message, type: "message" });
    if (message.role !== "user") return;
    const turn = Number.isFinite(message.eventIndex) ? turnByUserIndex.get(message.eventIndex) : null;
    if (showsActivity(turn, message)) {
      items.push({ key: `activity-${turn.id}`, turn, type: "activity" });
      activityShown = true;
    } else if (!turn && pendingPreparation && message.clientMessageId && message.clientMessageId === pendingPreparation.clientMessageId) {
      items.push({ key: `activity-pending-${message.id}`, type: "preparing" });
      activityShown = true;
    }
  });
  if (!activityShown && agentBusy && pendingPreparation) {
    items.push({ key: "activity-pending", type: "preparing" });
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

function ProjectArchive({ archive, taskId }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let active = true;
    getAuthToken().then(() => { if (active) setUrl(taskDownloadZipUrl(taskId)); });
    return () => { active = false; };
  }, [taskId]);
  return <div className="message-downloads">
    <a className="message-download-btn" href={url || undefined} download={archive.name} aria-disabled={!url}>
      {url ? <Download size={15} /> : <StatusIndicator size={14} status="running" label="Preparando ZIP" />}
      <span>{url ? `Baixar projeto ZIP · ${archive.file_count} arquivos` : "Preparando ZIP…"}</span>
    </a>
  </div>;
}

export function MessageList({
  activity,
  agentBusy = false,
  events = [],
  files = [],
  isTyping = false,
  messages,
  onFocusAction,
  pendingPreparation,
  taskId,
}) {
  const [selectedDocument, setSelectedDocument] = useState(null);
  const turns = activity?.turns || [];
  const timelineItems = useMemo(
    () => buildTimelineItems(messages.map((message) => attachDocumentDeliverables(presentSoftwareMessage(message, files, events), files, events)), turns, pendingPreparation, agentBusy),
    [agentBusy, events, files, messages, pendingPreparation, turns],
  );
  const showTypingMessage = isTyping && !timelineItems.some((item) => item.type !== "message" && (item.type === "preparing" || ["running", "paused", "waiting"].includes(item.turn?.status)));
  const latestTurn = turns[turns.length - 1];
  const changeKey = `${timelineItems.length}:${latestTurn?.actions.length || 0}:${latestTurn?.status || ""}:${showTypingMessage}`;
  const { ref, scrollToBottom, stuck, unseen } = useStickToBottom(changeKey, { resetKey: taskId || "new" });

  return (
    <motion.div
      className="message-list"
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
      ref={ref}
    >
      <div className="message-list-inner">
        <AnimatePresence initial={false}>
          {timelineItems.map((item) => {
            if (item.type === "activity") {
              return <TurnActivity key={item.key} onFocus={onFocusAction} turn={item.turn} />;
            }
            if (item.type === "preparing") {
              return <PreparingTurn key={item.key} />;
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
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.18, ease: [0.2, 0.7, 0.2, 1] }}
          >
            <div className="message-content">
              <AssistantByline />
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
      </div>
      {!stuck ? (
        <button className="vx-jump vx-jump--chat" onClick={() => scrollToBottom()} type="button">
          <ArrowDown size={14} /> {unseen ? "Novas atualizações" : "Ir para o fim"}
        </button>
      ) : null}
      <DocumentViewerOverlay
        document={selectedDocument}
        onClose={() => setSelectedDocument(null)}
        taskId={selectedDocument?.taskId}
      />
    </motion.div>
  );
}
