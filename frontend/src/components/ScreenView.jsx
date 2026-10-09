import { ChevronLeft, ChevronRight, Maximize2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { BrowserSurface } from "./BrowserSurface.jsx";
import { browserScene, isBrowserScene } from "../lib/browserScenes.js";

export function ScreenView({ events, connectionState }) {
  const frames = useMemo(() => events.filter(isBrowserScene).map((event, index) => browserScene(event, index, index)), [events]);
  const [selected, setSelected] = useState(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { setSelected(null); setExpanded(false); }, [events[0]?.task_id]);
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e) => { if (e.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);
  const index = selected === null ? frames.length - 1 : Math.min(selected, frames.length - 1);
  const preview = frames[index] || { mode: "browser", label: "A tela aparecerá quando o Vortax navegar ou pesquisar." };
  const surface = <BrowserSurface preview={preview}/>;
  return <CollapsiblePanel className="screen-panel" count={frames.length ? `${index + 1}/${frames.length}` : connectionState} storageKey="vortax.inspector.screen.collapsed" title="Tela">
    {surface}
    <div className="computer-live-controls">
      <button disabled={index <= 0} onClick={() => setSelected(index - 1)} title="Atividade anterior"><ChevronLeft size={16}/></button>
      <button disabled={index >= frames.length - 1} onClick={() => setSelected(index + 1)} title="Próxima atividade"><ChevronRight size={16}/></button>
      <button disabled={selected === null} onClick={() => setSelected(null)}>Ao vivo</button>
      <button onClick={() => setExpanded(true)} title="Ampliar navegador"><Maximize2 size={16}/></button>
    </div>
    {expanded && <div className="image-modal-overlay" onClick={() => setExpanded(false)}>
      <button className="image-modal-close" onClick={() => setExpanded(false)} title="Fechar"><X size={18}/></button>
      <div style={{width:"min(1100px, 94vw)"}} onClick={(e) => e.stopPropagation()}>{surface}</div>
    </div>}
  </CollapsiblePanel>;
}
