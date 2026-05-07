import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";

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
        <motion.span
          animate={{ rotate: collapsed ? -90 : 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 20 }}
          style={{ display: "inline-flex" }}
        >
          <ChevronDown size={16} />
        </motion.span>
      </button>
      <motion.div
        className="collapsible-content"
        animate={{
          height: collapsed ? 0 : "auto",
          opacity: collapsed ? 0 : 1,
        }}
        transition={{ duration: 0.2, ease: "easeInOut" }}
      >
        {children}
      </motion.div>
    </section>
  );
}
