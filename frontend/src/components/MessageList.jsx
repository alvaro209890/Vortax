import { useEffect, useRef } from "react";
import { Sparkles, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MessageList({ messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div className="message-list">
      {messages.map((message) => (
        <article className={`message ${message.role}`} key={message.id}>
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
                    <img
                      alt={image.filename || "Imagem enviada para analise"}
                      src={`data:${image.content_type};base64,${image.image_base64}`}
                    />
                    <span>{image.filename || "Imagem"}</span>
                  </a>
                ))}
              </div>
            )}
          </div>
        </article>
      ))}
      <div ref={endRef} />
    </div>
  );
}
