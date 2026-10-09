import { memo, useEffect, useState } from "react";
import { AppWindow, RotateCw } from "lucide-react";

import { getAuthToken, taskPreviewUrl } from "../../lib/api.js";
import { formatClock } from "../../lib/text.js";
import { previewSignature } from "../../lib/workspace.js";
import { StatusIndicator } from "../StatusIndicator.jsx";

function useDebounced(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [delay, value]);
  return debounced;
}

/**
 * Preview estático servido pelo backend (index.html do workspace). O iframe não recebe
 * allow-same-origin: o site gerado roda isolado da origem do Vortax.
 */
export const PreviewPane = memo(function PreviewPane({ entry, files, preparing, taskId }) {
  const signature = useDebounced(previewSignature(files), 900);
  const [manualReload, setManualReload] = useState(0);
  const [check, setCheck] = useState({ status: "idle" });
  const [frameLoaded, setFrameLoaded] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [loadedAt, setLoadedAt] = useState(0);
  const url = entry ? taskPreviewUrl(taskId, entry === "index.html" ? "" : entry) : null;
  const frameKey = `${signature}:${manualReload}`;
  // Mesmo iframe, nova versão: o conteúdo anterior continua visível até a nova pintura.
  const frameSrc = url ? `${url}${url.includes("?") ? "&" : "?"}v=${encodeURIComponent(frameKey).slice(-40)}` : null;

  useEffect(() => {
    if (!url) {
      setCheck({ status: "idle" });
      return undefined;
    }
    const controller = new AbortController();
    setCheck((current) => (current.status === "ready" ? current : { status: "checking" }));
    setReloading(true);
    getAuthToken()
      .then(() => fetch(url, { cache: "no-store", signal: controller.signal }))
      .then((response) => {
        setCheck(response.ok ? { status: "ready" } : { status: "unavailable", code: response.status });
        if (!response.ok) setFrameLoaded(false);
      })
      .catch((error) => {
        if (error?.name !== "AbortError") setCheck({ status: "unavailable", code: "rede" });
      });
    return () => controller.abort();
  }, [url, frameKey]);

  useEffect(() => {
    setFrameLoaded(false);
  }, [url]);

  let state = "unavailable";
  if (url && check.status === "ready") state = frameLoaded ? "available" : "preparing";
  else if (url && (check.status === "checking" || check.status === "idle")) state = "preparing";
  else if (!url && preparing) state = "preparing";

  const label = { available: "Preview disponível", preparing: "Preparando preview", unavailable: "Preview indisponível" }[state];

  return (
    <div className="vx-preview">
      <header className="vx-preview__bar">
        <StatusIndicator size={13} status={state === "available" ? "done" : state === "preparing" ? "running" : "unknown"} label={label} />
        <div className="vx-preview__title">
          <strong>{label}</strong>
          <span>{entry ? `Preview do projeto · ${entry}` : "Nenhum index.html no workspace"}{loadedAt && state === "available" ? ` · carregado ${formatClock(loadedAt)}` : ""}</span>
        </div>
        {url ? (
          <button aria-label="Recarregar preview" className="vx-icon-btn" onClick={() => setManualReload((value) => value + 1)} title="Recarregar preview" type="button">
            <RotateCw size={15} />
          </button>
        ) : null}
      </header>
      <div className="vx-preview__body">
        {url && check.status === "ready" ? (
          <iframe
            className={frameLoaded ? "is-loaded" : ""}
            key={url}
            onLoad={() => {
              setFrameLoaded(true);
              setReloading(false);
              setLoadedAt(Date.now());
            }}
            referrerPolicy="no-referrer"
            sandbox="allow-scripts allow-forms allow-modals"
            src={frameSrc}
            title={`Preview de ${entry}`}
          />
        ) : null}
        {state === "available" && reloading ? <span className="vx-browser__badge" role="status">Atualizando preview…</span> : null}
        {state !== "available" ? (
          <div className="vx-pane-empty vx-preview__overlay" role="status">
            {state === "preparing" ? <StatusIndicator size={20} status="running" /> : <AppWindow aria-hidden="true" size={24} />}
            <strong>{label}</strong>
            <span>
              {state === "preparing"
                ? url ? "Carregando o index.html atual do workspace." : "O Vortax está gravando arquivos de página; o preview abre quando existir um index.html."
                : url
                  ? `O servidor não entregou o preview (${check.code}).`
                  : "Esta tarefa não tem um site estático com index.html. Projetos de API, scripts e documentos aparecem em Arquivos e Terminal."}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
});
