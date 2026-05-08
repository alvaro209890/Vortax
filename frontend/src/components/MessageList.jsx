import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BookOpen, Check, Copy, Download, ExternalLink, FileText, Globe2, Sparkles, User, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { staggerContainer, fadeInUp } from "../animations/variants.js";
import { InlineTaskTimeline } from "./InlineTaskTimeline.jsx";
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

function ActivityArticle({ children }) {
  if (!children) return null;
  return (
    <motion.article
      className="message assistant progress-message"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ type: "spring", stiffness: 210, damping: 24 }}
      layout
    >
      <div className="message-avatar">
        <Sparkles size={18} />
      </div>
      <div className="message-content">
        <div className="message-role">Vortax trabalhando</div>
        {children}
      </div>
    </motion.article>
  );
}

function SearchActivityArticle({ activeSearch }) {
  if (!activeSearch) return null;
  return (
    <ActivityArticle>
      <div className="search-animation-container inline-search-activity">
        <div className="search-radar">
          <div className="radar-sweep"></div>
          <Globe2 size={24} className="radar-icon" />
        </div>
        <div className="search-details">
          <span className="search-query">"{activeSearch.query}"</span>
          <span className="search-status">Buscando fontes para melhorar a entrega...</span>
        </div>
      </div>
    </ActivityArticle>
  );
}

function visiblePlanSegments(planSegments = []) {
  return planSegments
    .filter((segment) => segment?.plan?.hasSteps && !segment.plan.isDirect)
    .sort((a, b) => (a.anchorEventIndex || 0) - (b.anchorEventIndex || 0));
}

function TaskPlanArticle({ segment }) {
  if (!segment?.plan?.hasSteps || segment.plan.isDirect) return null;
  return (
    <article className="message assistant progress-message">
      <div className="message-avatar">
        <Sparkles size={18} />
      </div>
      <div className="message-content">
        <div className="message-role">Vortax trabalhando</div>
        <InlineTaskTimeline livePlan={segment.plan} showEmpty={false} />
      </div>
    </article>
  );
}

function numericIndex(value) {
  return Number.isFinite(value) ? value : null;
}

function nextUserEventIndex(messages, currentMessageIndex) {
  for (let index = currentMessageIndex + 1; index < messages.length; index += 1) {
    if (messages[index].role === "user") {
      return numericIndex(messages[index].eventIndex);
    }
  }
  return null;
}

function latestUserMessageId(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "user") return messages[index].id;
  }
  return "";
}

function buildTimelineItems(messages, planSegments, activeSearch) {
  const segments = visiblePlanSegments(planSegments);
  const segmentsById = new Map(segments.map((segment) => [segment.id, segment]));
  const renderedSegments = new Set();
  const items = [];
  const latestUserId = latestUserMessageId(messages);
  let searchRendered = false;

  const pushPlanSegment = (segment) => {
    if (!segment || renderedSegments.has(segment.id)) return;
    renderedSegments.add(segment.id);
    items.push({
      key: `plan-${segment.id}`,
      segment,
      type: "plan",
    });
  };

  messages.forEach((message, messageIndex) => {
    if (message.role === "assistant" && message.planSegmentId) {
      pushPlanSegment(segmentsById.get(message.planSegmentId));
    }

    items.push({
      key: `message-${message.id}`,
      message,
      type: "message",
    });

    if (message.role !== "user") return;

    const currentEventIndex = numericIndex(message.eventIndex);
    const nextUserIndex = nextUserEventIndex(messages, messageIndex);
    if (currentEventIndex !== null) {
      segments.forEach((segment) => {
        if (renderedSegments.has(segment.id)) return;
        const anchorIndex = numericIndex(segment.anchorEventIndex);
        if (anchorIndex === null) return;
        if (anchorIndex < currentEventIndex) return;
        if (nextUserIndex !== null && anchorIndex >= nextUserIndex) return;
        pushPlanSegment(segment);
      });
    }

    if (activeSearch && message.id === latestUserId) {
      searchRendered = true;
      items.push({
        activeSearch,
        key: `search-${activeSearch.query}`,
        type: "search",
      });
    }
  });

  segments.forEach(pushPlanSegment);

  if (activeSearch && !searchRendered) {
    items.push({
      activeSearch,
      key: `search-${activeSearch.query}`,
      type: "search",
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

export function MessageList({ activeSearch, isTyping = false, messages, planSegments = [] }) {
  const endRef = useRef(null);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const timelineItems = useMemo(
    () => buildTimelineItems(messages, planSegments, activeSearch),
    [activeSearch, messages, planSegments],
  );
  const scrollKey = useMemo(
    () => timelineItems.map((item) => item.key).join("|"),
    [timelineItems],
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [isTyping, scrollKey]);

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
            if (item.type === "plan") {
              return <TaskPlanArticle key={item.key} segment={item.segment} />;
            }
            if (item.type === "search") {
              return <SearchActivityArticle activeSearch={item.activeSearch} key={item.key} />;
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
        {isTyping && (
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
