import { ChevronLeft, ChevronRight, Monitor, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";

export function ScreenView({ events, connectionState }) {
  const frames = useMemo(
    () => events.filter((event) => event.type === "screen_frame" && event.payload?.image_base64),
    [events],
  );
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    if (frames.length === 0) {
      setSelectedIndex(0);
      return;
    }
    setSelectedIndex((current) => (current >= frames.length - 1 ? frames.length - 1 : current));
  }, [frames.length]);

  useEffect(() => {
    if (frames.length > 0 && !isModalOpen) {
      setSelectedIndex(frames.length - 1);
    }
  }, [frames.length, isModalOpen]);

  const selectedFrame = frames[selectedIndex] || null;
  const image = selectedFrame?.payload?.image_base64;
  const caption = selectedFrame?.payload?.caption || selectedFrame?.payload?.title || "Tela do navegador";
  const canGoBack = selectedIndex > 0;
  const canGoForward = selectedIndex < frames.length - 1;

  function goPrevious() {
    setSelectedIndex((current) => Math.max(current - 1, 0));
  }

  function goNext() {
    setSelectedIndex((current) => Math.min(current + 1, frames.length - 1));
  }

  return (
    <CollapsiblePanel
      className="screen-panel"
      count={frames.length > 0 ? `${selectedIndex + 1}/${frames.length}` : connectionState}
      storageKey="vortax.inspector.screen.collapsed"
      title="Tela"
    >
      <div className="screen-view">
        {image ? (
          <>
            <button className="screen-nav left" disabled={!canGoBack} onClick={goPrevious} title="Print anterior" type="button">
              <ChevronLeft size={17} />
            </button>
            <img alt="Tela atual do PC" src={`data:image/jpeg;base64,${image}`} onClick={() => setIsModalOpen(true)} />
            <button className="screen-nav right" disabled={!canGoForward} onClick={goNext} title="Proximo print" type="button">
              <ChevronRight size={17} />
            </button>
            <div className="screen-caption">{caption}</div>
          </>
        ) : (
          <div className="screen-placeholder">
            <Monitor size={34} />
            <p>Os prints do stream aparecem aqui.</p>
          </div>
        )}
      </div>

      {isModalOpen && image && (
        <div className="image-modal-overlay" onClick={() => setIsModalOpen(false)}>
          <button className="image-modal-close" onClick={() => setIsModalOpen(false)} title="Fechar" type="button">
            <X size={18} />
          </button>
          <button className="image-modal-nav left" disabled={!canGoBack} onClick={(event) => { event.stopPropagation(); goPrevious(); }} title="Print anterior" type="button">
            <ChevronLeft size={22} />
          </button>
          <img
            alt="Tela ampliada"
            className="image-modal-content"
            src={`data:image/jpeg;base64,${image}`}
            onClick={(event) => event.stopPropagation()}
          />
          <button className="image-modal-nav right" disabled={!canGoForward} onClick={(event) => { event.stopPropagation(); goNext(); }} title="Proximo print" type="button">
            <ChevronRight size={22} />
          </button>
          <div className="image-modal-counter">
            {selectedIndex + 1} / {frames.length}
          </div>
        </div>
      )}
    </CollapsiblePanel>
  );
}
