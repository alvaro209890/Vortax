import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Eye, EyeOff, Globe, Loader2, RefreshCw } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { usePersistentState } from "../hooks/usePersistentState.js";
import { API_BASE_URL } from "../lib/api.js";

function detectPreviewType(files, events) {
  const hasIndexHtml = files.some(
    (f) => f.path === "index.html" || f.path.endsWith("/index.html")
  );
  // Check dev server events
  const devServerEvent = [...events].reverse().find(
    (e) => e.type === "dev_server_started"
  );
  if (devServerEvent?.payload) {
    return {
      type: "dev_server",
      url: devServerEvent.payload.url,
      port: devServerEvent.payload.port,
    };
  }
  if (hasIndexHtml) {
    return { type: "static_html" };
  }
  return null;
}

export function PreviewPanel({ files, events, taskId }) {
  const [visible, setVisible] = usePersistentState("vortax.inspector.preview.visible", true);
  const [devServerStatus, setDevServerStatus] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const preview = useMemo(
    () => detectPreviewType(files, events),
    [files, events]
  );

  const previewUrl = useMemo(() => {
    if (!taskId || !preview) return null;
    if (preview.type === "dev_server") return preview.url;
    return `${API_BASE_URL}/api/files/preview/${encodeURIComponent(taskId)}/`;
  }, [taskId, preview]);

  // Check dev server status on mount and when preview changes
  useEffect(() => {
    if (!taskId || preview?.type !== "dev_server") return;
    const checkStatus = async () => {
      try {
        const resp = await fetch(`${API_BASE_URL}/api/files/preview-dev/${encodeURIComponent(taskId)}`);
        const data = await resp.json();
        setDevServerStatus(data);
      } catch {
        setDevServerStatus(null);
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 10000);
    return () => clearInterval(interval);
  }, [taskId, preview?.type]);

  async function handleRefresh() {
    if (!taskId || preview?.type !== "dev_server") return;
    setRefreshing(true);
    try {
      await fetch(`${API_BASE_URL}/api/files/preview-dev/${encodeURIComponent(taskId)}`, { method: "DELETE" });
      setDevServerStatus(null);
    } catch {
      // ignore
    }
    setRefreshing(false);
  }

  if (!preview || !previewUrl) return null;

  const isDevServer = preview.type === "dev_server";

  return (
    <CollapsiblePanel
      className="preview-panel"
      storageKey="vortax.inspector.preview.collapsed"
      title="Preview"
      titleIcon={<Globe size={14} />}
    >
      <div className="preview-header-actions">
        {isDevServer && (
          <small className={devServerStatus?.running ? "live" : ""}>
            {devServerStatus?.running ? `:${preview.port}` : "offline"}
          </small>
        )}
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
          {isDevServer && !devServerStatus?.running && (
            <div className="preview-dev-banner">
              <Loader2 size={13} className="spinner" />
              <span>Aguardando servidor iniciar...</span>
              <button
                type="button"
                onClick={handleRefresh}
                disabled={refreshing}
                title="Reiniciar servidor"
              >
                <RefreshCw size={13} className={refreshing ? "spinner" : ""} />
              </button>
            </div>
          )}
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
