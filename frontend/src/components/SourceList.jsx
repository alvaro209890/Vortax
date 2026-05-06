import { useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";

export function SourceList({ sources }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <section className={`panel sources-panel ${collapsed ? "collapsed" : ""}`}>
      <button
        aria-expanded={!collapsed}
        className="sources-toggle"
        onClick={() => setCollapsed((current) => !current)}
        type="button"
      >
        <span>Fontes</span>
        <small>{sources.length}</small>
        {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
      </button>
      <div className="sources-content">
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
      </div>
    </section>
  );
}
