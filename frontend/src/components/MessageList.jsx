import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Copy, Download, FileText, Globe2, Sparkles, User } from "lucide-react";
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

/* ── Downloads ───────────────────────────────────────────────────── */

function MessageDownloads({ downloads = [], taskId }) {
  const items = downloads.filter((item) => item?.path);
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

export function MessageList({ activity, activityVersion, isTyping = false, messages, activeSearch }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isTyping, activityVersion]);

  return (
    <motion.div
      className="message-list"
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
    >
      <AnimatePresence mode="popLayout">
        {messages.map((message) => (
          <motion.article
            className={`message ${message.role}`}
            key={message.id}
            variants={fadeInUp}
            layout
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
              <MessageDownloads downloads={message.downloads} taskId={message.taskId} />
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
        ))}
      </AnimatePresence>
      {activity}
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
            <div className="message-role">Vortax</div>
            <div aria-label="Vortax esta digitando" className="typing-dots" role="status">
              <span />
              <span />
              <span />
            </div>
          </div>
        </motion.article>
      )}
      {activeSearch && (
        <motion.article
          className="message assistant search-message"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 22 }}
        >
          <div className="message-avatar">
            <Sparkles size={18} />
          </div>
          <div className="message-content">
            <div className="message-role">Vortax pesquisando...</div>
            <div className="search-animation-container">
              <div className="search-radar">
                <div className="radar-sweep"></div>
                <Globe2 size={24} className="radar-icon" />
              </div>
              <div className="search-details">
                <span className="search-query">"{activeSearch.query}"</span>
                <span className="search-status">Buscando em milhares de fontes...</span>
              </div>
            </div>
          </div>
        </motion.article>
      )}
      <div ref={endRef} />
    </motion.div>
  );
}
