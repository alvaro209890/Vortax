import { ChevronDown, ChevronRight } from "lucide-react";

import { usePersistentState } from "../hooks/usePersistentState.js";

export function CollapsiblePanel({
  children,
  className = "",
  count,
  defaultCollapsed = false,
  storageKey,
  title,
  titleIcon = null,
}) {
  const [collapsed, setCollapsed] = usePersistentState(storageKey, defaultCollapsed);
  const panelClassName = ["panel", "collapsible-panel", className, collapsed ? "collapsed" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={panelClassName}>
      <button
        aria-expanded={!collapsed}
        className="collapsible-toggle"
        onClick={() => setCollapsed((current) => !current)}
        type="button"
      >
        <span>
          {titleIcon}
          {title}
        </span>
        {count !== undefined && <small>{count}</small>}
        {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
      </button>
      <div className="collapsible-content">{children}</div>
    </section>
  );
}
