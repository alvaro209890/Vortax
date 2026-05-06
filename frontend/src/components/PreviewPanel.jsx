import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Eye, EyeOff, Globe, Loader2, RefreshCw, Terminal } from "lucide-react";

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
  const [visible, setVisible] = useState(false);
  const [devServerStatus, setDevServerStatus] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const preview = useMemo(
    () => detectPreviewType(files, events),
    [files, events]
  );

  const previewUrl = useMemo(() => {
    if (!taskId || !preview) return null;
    if (preview.type === "dev_server") return preview.url;
    return `/api/files/preview/${taskId}/`;
  }, [taskId, preview]);

  // Check dev server status on mount and when preview changes
  useEffect(() => {
    if (!taskId || preview?.type !== "dev_server") return;
    const checkStatus = async () => {
      try {
        const resp = await fetch(`/api/files/preview-dev/${taskId}`);
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

  // Auto-show when preview becomes available
  useEffect(() => {
    if (preview) setVisible(true);
  }, [preview]);

  async function handleRefresh() {
    if (!taskId || preview?.type !== "dev_server") return;
    setRefreshing(true);
    try {
      await fetch(`/api/files/preview-dev/${taskId}`, { method: "DELETE" });
      setDevServerStatus(null);
    } catch {
      // ignore
    }
    setRefreshing(false);
  }

  if (!preview || !previewUrl) return null;

  const isDevServer = preview.type === "dev_server";

  return (
    <section className={`panel preview-panel ${visible ? "" : "collapsed"}`}>
      <div className="panel-title preview-header">
        <span>
          <Globe size={14} />
          Preview
        </span>
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
    </section>
  );
}
