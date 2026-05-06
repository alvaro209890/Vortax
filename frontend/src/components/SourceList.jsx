import { ExternalLink } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";

export function SourceList({ error, loading, sources }) {
  return (
    <CollapsiblePanel className="sources-panel" count={sources.length} storageKey="vortax.inspector.sources.collapsed" title="Fontes">
      {loading ? (
        <p className="panel-state">Carregando fontes...</p>
      ) : error ? (
        <p className="panel-state error">Nao foi possivel carregar as fontes.</p>
      ) : sources.length === 0 ? (
        <p className="panel-state">As fontes abertas aparecem aqui.</p>
      ) : (
        sources.map((source) => (
          <a className="source-item" href={source.url} key={`${source.id}-${source.url}`} target="_blank" rel="noreferrer">
            <div>
              <strong>{source.title || source.url}</strong>
              <span>{source.source_type || "web"} · {source.quality_score ?? 0}/100</span>
            </div>
            <ExternalLink size={14} />
          </a>
        ))
      )}
    </CollapsiblePanel>
  );
}
