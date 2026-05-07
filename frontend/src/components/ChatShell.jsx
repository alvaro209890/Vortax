import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

export function ChatShell({ sidebar, main, inspector }) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  return (
    <div className={`app-shell ${isSidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
      <motion.aside
        className="sidebar"
        animate={{
          width: isSidebarOpen ? "280px" : "0px",
          opacity: isSidebarOpen ? 1 : 0,
          padding: isSidebarOpen ? "24px" : "0px",
          borderWidth: isSidebarOpen ? "1px" : "0px",
        }}
        transition={{
          type: "spring",
          stiffness: 200,
          damping: 26,
        }}
      >
        <div className="sidebar-toggle-container">
          <motion.button
            className="sidebar-toggle-btn"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setIsSidebarOpen(false)}
            title="Recolher menu"
          >
            <PanelLeftClose size={18} />
          </motion.button>
        </div>
        {sidebar}
      </motion.aside>
      <main className="chat-panel">
        <AnimatePresence>
          {!isSidebarOpen && (
            <motion.button
              className="sidebar-open-btn"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ type: "spring", stiffness: 200, damping: 20 }}
              onClick={() => setIsSidebarOpen(true)}
              title="Expandir menu"
            >
              <PanelLeftOpen size={18} />
            </motion.button>
          )}
        </AnimatePresence>
        {main}
      </main>
      <aside className="inspector">{inspector}</aside>
    </div>
  );
}
