import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Globe2, Loader2, LockKeyhole, MousePointer2, Search } from "lucide-react";
import { cursorPosition } from "../lib/browserScenes.js";

function safeLink(url) {
  return /^https?:\/\//i.test(String(url || "")) ? url : undefined;
}

export function BrowserSurface({ preview, busy = false }) {
  const reduced = useReducedMotion();
  const pointer = cursorPosition(preview.cursor, preview.viewport);
  const view = preview.view;
  const action = preview.cursor?.action;
  const label = preview.blocked ? "Tela protegida" : view ? (view.via === "cache" ? "Fontes da conversa" : "Leitura web") : "Captura do navegador";
  return (
    <div className="computer-stage browser-live browser-surface" aria-label="Navegador do Vortax">
      <div className="browser-chrome">
        <div className="browser-tab"><Globe2 size={13} /><span>{preview.title || "Navegador do Vortax"}</span><i className={busy ? "active" : ""} /></div>
        <div className="browser-address"><LockKeyhole size={12} /><span>{preview.url && preview.url !== "about:blank" ? preview.url : "Preparando a navegação"}</span>{busy && <Loader2 size={13} className="spinner" />}</div>
      </div>
      <div className="browser-viewport" style={preview.viewport ? {aspectRatio: `${preview.viewport.width} / ${preview.viewport.height}`} : undefined}>
        <AnimatePresence initial={false} mode="wait">
          <motion.div className="browser-content" key={preview.blocked ? "blocked" : view ? `${preview.createdAt}-reading` : preview.createdAt || "waiting"}
            initial={{opacity: reduced ? 1 : 0}} animate={{opacity: 1}} exit={{opacity: reduced ? 1 : 0}}
            transition={{duration: reduced ? 0 : 0.16}}>
            {preview.blocked ? <div className="browser-empty"><LockKeyhole size={30}/><strong>Tela protegida</strong><p>{preview.label}</p></div>
              : preview.image ? <img alt={preview.title || "Página capturada pelo Vortax"} src={`data:image/jpeg;base64,${preview.image}`} />
              : view?.kind === "search" ? <div className="browser-reading"><div className="browser-query"><Search size={18}/><h3>{view.query || "Resultados da pesquisa"}</h3></div>
                {view.results?.length ? view.results.map((item, i) => <motion.article key={`${item.href}-${i}`} initial={{opacity: reduced ? 1 : 0, y: reduced ? 0 : 8}} animate={{opacity: 1, y: 0}} transition={{delay: reduced ? 0 : i * 0.04}}>
                  <small>{item.href}</small><a href={safeLink(item.href)} target="_blank" rel="noopener noreferrer">{item.title}</a>{item.snippet && <p>{item.snippet}</p>}
                </motion.article>) : <p>A busca não retornou resultados. O Vortax pode tentar outra fonte.</p>}</div>
              : view ? <div className="browser-reading"><h3>{view.title}</h3><div className="browser-article-text">{view.text || "Página sem texto extraído."}</div></div>
              : <div className="browser-empty"><Globe2 size={30}/><strong>{busy ? "Abrindo a página" : "Aguardando uma página"}</strong><p>{preview.label}</p>{busy && <div className="browser-loading"><span/><span/><span/></div>}</div>}
          </motion.div>
        </AnimatePresence>
        {pointer && preview.image && !preview.blocked && <motion.div className={`browser-pointer ${action || "move"}`} aria-hidden="true"
          animate={{left: `${pointer.x}%`, top: `${pointer.y}%`}} transition={{duration: reduced ? 0 : 0.45, ease: [0.22, 1, 0.36, 1]}}>
          <MousePointer2 size={22} fill="white" stroke="#14221b" strokeWidth={1.6}/>
          <span className="browser-pointer-name">Vortax</span>
          {action === "click" && <span key={preview.createdAt} className="browser-click-ring"/>}
          {action === "scroll" && <span key={preview.createdAt} className="browser-scroll-mark">↕</span>}
          {action === "type" && <span key={preview.createdAt} className="browser-type-mark">I</span>}
        </motion.div>}
      </div>
      <div className="browser-footnote"><span className={busy ? "active" : ""}/>{label}<small>{busy ? "Em atividade" : "Última atividade"}</small></div>
    </div>
  );
}
