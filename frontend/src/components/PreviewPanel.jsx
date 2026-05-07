import { useMemo } from "react";
import { ExternalLink, Eye, EyeOff, Globe } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { usePersistentState } from "../hooks/usePersistentState.js";
import { API_BASE_URL } from "../lib/api.js";

function detectPreviewType(files) {
  const indexFile = files.find(
    (f) => f.path === "index.html" || f.path.endsWith("/index.html")
  );
  if (indexFile) {
    return { type: "static_html", path: indexFile.path };
  }
  return null;
}

export function PreviewPanel({ files, taskId }) {
  const [visible, setVisible] = usePersistentState("vortax.inspector.preview.visible", true);

  const preview = useMemo(
    () => detectPreviewType(files),
    [files]
  );

  const previewUrl = useMemo(() => {
    if (!taskId || !preview) return null;
    const encodedPath = preview.path === "index.html"
      ? ""
      : String(preview.path || "").split("/").map((part) => encodeURIComponent(part)).join("/");
    return `${API_BASE_URL}/api/files/preview/${encodeURIComponent(taskId)}/${encodedPath}`;
  }, [taskId, preview]);

  if (!preview || !previewUrl) return null;

  return (
    <CollapsiblePanel
      className="preview-panel"
      storageKey="vortax.inspector.preview.collapsed"
      title="Preview"
      titleIcon={<Globe size={14} />}
    >
      <div className="preview-header-actions">
        <a
          href={previewUrl}
          target="_blank"
          rel="noreferrer"
          className="preview-external-btn"
          title="Abrir em nova aba"
        >
          <ExternalLink size={13} />
        </a>
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          title={visible ? "Ocultar preview" : "Mostrar preview"}
        >
          {visible ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>

      {visible && (
        <div className="preview-body">
          <iframe
            key={`${taskId}-${preview.type}`}
            src={previewUrl}
            className="preview-iframe"
            title="Preview do projeto"
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      )}
    </CollapsiblePanel>
  );
}
