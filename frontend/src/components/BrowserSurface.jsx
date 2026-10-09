import { memo, useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Expand, Globe2, LockKeyhole, MousePointer2, Search, Shrink, ShieldAlert, WifiOff } from "lucide-react";

import { cursorPosition, SCENE_SOURCE_LABELS } from "../lib/browserScenes.js";
import { displayUrl, formatAge, formatClock, hostOf, isHttpUrl } from "../lib/text.js";
import { StatusIndicator } from "./StatusIndicator.jsx";

const OFFLINE_STATES = new Set(["reconnecting", "offline", "error", "closed", "paused"]);

function safeLink(url) {
  return isHttpUrl(url) ? url : undefined;
}

function useNow(enabled, interval = 15000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), interval);
    return () => clearInterval(timer);
  }, [enabled, interval]);
  return now;
}

// Mantém a última imagem decodificada visível enquanto a próxima carrega; a nova entra
// por cima com fade curto. No máximo duas imagens ficam decodificadas ao mesmo tempo.
function useCaptureLayers(scene) {
  const src = scene?.image ? `data:image/jpeg;base64,${scene.image}` : null;
  const [layers, setLayers] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!src) {
      if (scene?.blocked) setLayers([]);
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    const image = new Image();
    image.src = src;
    const ready = typeof image.decode === "function" ? image.decode() : Promise.resolve();
    ready.catch(() => {}).then(() => {
      if (cancelled) return;
      setLayers((current) => {
        if (current[current.length - 1]?.src === src) return current;
        return [...current.slice(-1), { key: scene.eventIndex, scene, src, width: image.naturalWidth, height: image.naturalHeight }];
      });
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [src, scene?.blocked]); // eslint-disable-line react-hooks/exhaustive-deps

  const dropUnderlay = () => setLayers((current) => (current.length > 1 ? current.slice(-1) : current));
  return { dropUnderlay, layers, loading };
}

const Pointer = memo(function Pointer({ scene, jump }) {
  const reduced = useReducedMotion();
  const pointer = cursorPosition(scene.cursor, scene.viewport);
  if (!pointer) return null;
  const action = scene.cursor?.action || "move";
  const labels = { click: "Clique registrado", move: "Ponteiro", scroll: "Rolagem registrada", type: "Digitação registrada" };
  return (
    <motion.div
      aria-label={labels[action] || "Ponteiro"}
      className={`vx-pointer vx-pointer--${action}`}
      initial={false}
      animate={{ left: `${pointer.x}%`, top: `${pointer.y}%` }}
      role="img"
      transition={{ duration: reduced || jump ? 0 : 0.32, ease: [0.2, 0.7, 0.2, 1] }}
    >
      <MousePointer2 aria-hidden="true" fill="white" size={20} stroke="#14221b" strokeWidth={1.6} />
      {action === "click" && !reduced ? <span className="vx-pointer__ring" key={`click-${scene.eventIndex}`} /> : null}
      {action === "type" ? <span className="vx-pointer__tag" key={`type-${scene.eventIndex}`}>digitando</span> : null}
      {action === "scroll" ? <span className="vx-pointer__tag" key={`scroll-${scene.eventIndex}`}>rolando</span> : null}
    </motion.div>
  );
});

function CaptureStage({ scene, zoom }) {
  const { dropUnderlay, layers, loading } = useCaptureLayers(scene);
  const previousFrameRef = useRef(null);
  const top = layers[layers.length - 1];
  const shownScene = top?.scene;
  const jump = previousFrameRef.current !== null && shownScene && Math.abs(shownScene.frameIndex - previousFrameRef.current) > 1;
  useEffect(() => {
    if (shownScene) previousFrameRef.current = shownScene.frameIndex;
  }, [shownScene]);

  if (!top) {
    return (
      <div className="vx-browser__placeholder">
        <StatusIndicator size={18} status="running" label="Carregando captura" />
        <span>Carregando captura…</span>
      </div>
    );
  }
  const viewport = shownScene.viewport?.width > 0 ? shownScene.viewport : { width: top.width || 16, height: top.height || 9 };
  const ratio = viewport.width / viewport.height;
  return (
    <>
      <div className={`vx-stage vx-stage--${zoom}`} style={{ "--vx-ratio": ratio, "--vx-natural-width": `${viewport.width}px` }}>
        {layers.map((layer, index) => (
          <img
            alt={index === layers.length - 1 ? `Captura de ${shownScene.title || hostOf(shownScene.url) || "página"}` : ""}
            aria-hidden={index === layers.length - 1 ? undefined : "true"}
            className={index === layers.length - 1 ? "vx-stage__img is-top" : "vx-stage__img is-under"}
            decoding="async"
            draggable={false}
            key={layer.key}
            onAnimationEnd={index === layers.length - 1 ? dropUnderlay : undefined}
            src={layer.src}
          />
        ))}
        <Pointer jump={Boolean(jump)} scene={shownScene} />
      </div>
      {loading ? <span className="vx-browser__badge" role="status">Carregando nova captura…</span> : null}
    </>
  );
}

function ReadingView({ view }) {
  if (view.kind === "search") {
    return (
      <div className="vx-reading" key={`search-${view.query}`}>
        <div className="vx-reading__query"><Search aria-hidden="true" size={16} /><h3>{view.query || "Resultados da pesquisa"}</h3></div>
        {view.results?.length ? view.results.map((item, index) => (
          <article key={`${item.href}-${index}`}>
            <small>{item.href}</small>
            <a href={safeLink(item.href)} rel="noopener noreferrer" target="_blank">{item.title || item.href}</a>
            {item.snippet ? <p>{item.snippet}</p> : null}
          </article>
        )) : <p>A busca não retornou resultados.</p>}
      </div>
    );
  }
  return (
    <div className="vx-reading">
      <h3>{view.title || "Página lida"}</h3>
      <div className="vx-reading__text">{view.text || "A página não tinha texto extraível."}</div>
    </div>
  );
}

/**
 * Superfície do navegador. Mostra exatamente uma cena registrada (captura, leitura HTTP,
 * busca ou tela protegida), com a origem e o frescor sempre visíveis.
 */
export const BrowserSurface = memo(function BrowserSurface({
  active = false,
  connectionState = "open",
  isHistory = false,
  scene,
  stale = false,
  waitingAction = null,
}) {
  const [zoom, setZoom] = useState("fit");
  const now = useNow(Boolean(scene) && !isHistory);
  const source = scene?.source || null;
  const offline = OFFLINE_STATES.has(connectionState);
  const url = scene?.url || scene?.view?.url || "";
  const title = scene?.title || scene?.view?.title || (scene ? hostOf(url) : "") || "Navegador do Vortax";
  const capturedAt = scene?.capturedAt || 0;

  let freshness = "";
  if (scene) {
    if (isHistory) freshness = `Histórico · ${formatClock(capturedAt)}`;
    else if (active) freshness = `Atualizada ${formatAge(capturedAt, now)}`;
    else freshness = `Última ${source === "capture" ? "captura" : "atualização"} · ${stale ? formatAge(capturedAt, now) : formatClock(capturedAt)}`;
  }

  let body;
  if (!scene) {
    body = (
      <div className="vx-browser__placeholder">
        {waitingAction ? <StatusIndicator size={18} status="running" /> : <Globe2 aria-hidden="true" size={26} />}
        <strong>{waitingAction ? waitingAction.title : "Nenhuma página aberta nesta tarefa"}</strong>
        <span>{waitingAction ? "A captura aparece quando a ação terminar." : "Capturas e leituras de páginas aparecem aqui quando o Vortax usar o navegador."}</span>
      </div>
    );
  } else if (scene.blocked) {
    body = (
      <div className="vx-browser__placeholder vx-browser__placeholder--blocked" role="status">
        <ShieldAlert aria-hidden="true" size={28} />
        <strong>Tela protegida</strong>
        <span>A página tem campos sensíveis (como senha). A imagem não foi registrada nem exibida.</span>
      </div>
    );
  } else if (scene.image) {
    body = <CaptureStage key="capture" scene={scene} zoom={zoom} />;
  } else if (scene.view) {
    body = <ReadingView view={scene.view} />;
  }

  return (
    <section aria-label="Navegador do Vortax" className={`vx-browser ${active ? "is-active" : ""}`} data-source={source || "empty"}>
      <header className="vx-browser__bar">
        <div className="vx-browser__address">
          {source === "search" || source === "cache" ? <Search aria-hidden="true" size={13} /> : <LockKeyhole aria-hidden="true" size={13} />}
          <span className="vx-browser__title">{title}</span>
          <span className="vx-browser__url" title={url}>{url ? displayUrl(url) : "sem endereço"}</span>
        </div>
        {scene?.image && !scene.blocked ? (
          <button
            aria-label={zoom === "fit" ? "Ver captura em tamanho real" : "Ajustar captura ao painel"}
            className="vx-icon-btn"
            onClick={() => setZoom((value) => (value === "fit" ? "actual" : "fit"))}
            title={zoom === "fit" ? "Tamanho real (100%)" : "Ajustar ao painel"}
            type="button"
          >
            {zoom === "fit" ? <Expand size={15} /> : <Shrink size={15} />}
          </button>
        ) : null}
      </header>
      <div className={`vx-browser__viewport vx-browser__viewport--${zoom}`}>
        {body}
        {waitingAction && scene ? (
          <span className="vx-browser__badge vx-browser__badge--top" role="status">
            <StatusIndicator size={12} status="running" />
            {waitingAction.title} · aguardando nova captura
          </span>
        ) : null}
      </div>
      <footer className="vx-browser__status">
        <span className={`vx-dot ${active && !offline ? "is-live" : ""}`} aria-hidden="true" />
        <span>{source ? SCENE_SOURCE_LABELS[source] : "Navegador"}</span>
        {freshness ? <span className="vx-browser__fresh">{freshness}</span> : null}
        {offline ? (
          <span className="vx-browser__offline"><WifiOff aria-hidden="true" size={12} /> Conexão interrompida — exibindo o último registro recebido</span>
        ) : null}
      </footer>
    </section>
  );
});

// Miniatura para o dock: a mesma cena, sem controles.
export const BrowserThumb = memo(function BrowserThumb({ scene }) {
  if (!scene) return <span className="vx-thumb vx-thumb--icon"><Globe2 aria-hidden="true" size={16} /></span>;
  if (scene.blocked) return <span className="vx-thumb vx-thumb--icon"><ShieldAlert aria-hidden="true" size={16} /></span>;
  if (scene.image) return <img alt="" className="vx-thumb" decoding="async" src={`data:image/jpeg;base64,${scene.image}`} />;
  return <span className="vx-thumb vx-thumb--icon">{scene.source === "search" || scene.source === "cache" ? <Search aria-hidden="true" size={16} /> : <Globe2 aria-hidden="true" size={16} />}</span>;
});
