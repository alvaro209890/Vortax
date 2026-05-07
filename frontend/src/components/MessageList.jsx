import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Download, FileText, Sparkles, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { staggerContainer, fadeInUp } from "../animations/variants.js";
import { fileDownloadUrl } from "../lib/api.js";

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

export function MessageList({ isTyping = false, messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isTyping]);

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
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
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
      <div ref={endRef} />
    </motion.div>
  );
}
