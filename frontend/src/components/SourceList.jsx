import { ExternalLink } from "lucide-react";

export function SourceList({ sources }) {
  return (
    <section className="panel sources-panel">
      <div className="panel-title">
        <span>Fontes</span>
        <small>{sources.length}</small>
      </div>
      {sources.length === 0 ? (
        <p className="muted">As fontes abertas aparecem aqui.</p>
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
    </section>
  );
}
