import { useEffect, useMemo, useState } from "react";
import { BookOpen, Download, FileText, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { fileDownloadUrl } from "../lib/api.js";

function isMarkdownFile(file) {
  const path = String(file?.path || "").toLowerCase();
  return path.endsWith(".md") || path.endsWith(".markdown");
}

function sortDocumentationFiles(files) {
  const preferred = ["documentacao", "documentação", "readme", "docs", "guia", "manual"];
  return [...files].sort((a, b) => {
    const aPath = String(a.path || "");
    const bPath = String(b.path || "");
    const aName = aPath.split("/").pop().toLowerCase();
    const bName = bPath.split("/").pop().toLowerCase();
    const aPreferred = preferred.some((token) => aName.includes(token)) ? 0 : 1;
    const bPreferred = preferred.some((token) => bName.includes(token)) ? 0 : 1;
    return aPreferred - bPreferred || aPath.split("/").length - bPath.split("/").length || aPath.localeCompare(bPath);
  });
}

export function DocumentationPanel({ files, taskId }) {
  const docs = useMemo(
    () => sortDocumentationFiles((files || []).filter(isMarkdownFile)),
    [files],
  );
  const [selectedPath, setSelectedPath] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!docs.length) {
      setSelectedPath("");
      return;
    }
    setSelectedPath((current) => (docs.some((doc) => doc.path === current) ? current : docs[0].path));
  }, [docs]);

  const selected = docs.find((doc) => doc.path === selectedPath) || null;

  useEffect(() => {
    if (!taskId || !selected?.path) {
      setContent("");
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(fileDownloadUrl(taskId, selected.path))
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then((text) => {
        if (!cancelled) setContent(text);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [taskId, selected?.path]);

  return (
    <CollapsiblePanel
      className="documentation-panel"
      count={docs.length}
      storageKey="vortax.inspector.documentation.collapsed"
      title="Documentação"
      titleIcon={<BookOpen size={14} />}
    >
      {docs.length === 0 ? (
        <p className="panel-state">Nenhuma documentação Markdown gerada.</p>
      ) : (
        <>
          <div className="documentation-list">
            {docs.map((doc) => (
              <button
                className={`documentation-file ${doc.path === selectedPath ? "active" : ""}`}
                key={doc.path}
                onClick={() => setSelectedPath(doc.path)}
                title={doc.path}
                type="button"
              >
                <FileText size={14} />
                <span>{doc.path}</span>
              </button>
            ))}
          </div>

          <div className="documentation-card">
            <div className="documentation-card-header">
              <strong>{selected?.path || "Documento"}</strong>
              {selected?.path && (
                <a
                  className="documentation-download"
                  download
                  href={fileDownloadUrl(taskId, selected.path)}
                  title="Baixar documentação"
                >
                  <Download size={14} />
                  <span>Baixar</span>
                </a>
              )}
            </div>

            <div className="documentation-content markdown-body">
              {loading ? (
                <p className="documentation-loading"><Loader2 className="spinner" size={14} /> Carregando documentação...</p>
              ) : error ? (
                <p className="panel-state error">Nao foi possivel abrir este Markdown.</p>
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || "Documento vazio."}</ReactMarkdown>
              )}
            </div>
          </div>
        </>
      )}
    </CollapsiblePanel>
  );
}
