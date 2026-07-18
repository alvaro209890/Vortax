import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

const MOBILE_MQ = "(max-width: 768px)";

function isMobileViewport() {
  if (typeof window === "undefined") return false;
  return window.matchMedia(MOBILE_MQ).matches;
}

export function ChatShell({ sidebar, main }) {
  // Desktop: sidebar aberta por padrão; mobile: fechada (drawer)
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => !isMobileViewport());

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MQ);
    const onChange = (event) => {
      // ao entrar em mobile, fecha; ao sair, abre
      setIsSidebarOpen(!event.matches);
    };
    mq.addEventListener?.("change", onChange);
    mq.addListener?.(onChange); // Safari antigo
    return () => {
      mq.removeEventListener?.("change", onChange);
      mq.removeListener?.(onChange);
    };
  }, []);

  // Esc fecha o drawer no mobile
  useEffect(() => {
    if (!isSidebarOpen || !isMobileViewport()) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") setIsSidebarOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isSidebarOpen]);

  // Trava scroll do body quando drawer mobile aberto
  useEffect(() => {
    if (!isMobileViewport()) return undefined;
    if (isSidebarOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
    return undefined;
  }, [isSidebarOpen]);

  function handleSidebarClick(event) {
    if (!isMobileViewport()) return;
    // fecha ao escolher conversa, nova conversa ou tab (não ao digitar busca)
    if (
      event.target.closest(
        ".task-item, .task-list-header button, .sidebar-tab, .brand, .task-delete"
      )
    ) {
      // task-delete: deixa o handler do delete rodar; ainda fecha drawer
      setIsSidebarOpen(false);
    }
  }

  return (
    <div className={`app-shell manus-layout ${isSidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
      <AnimatePresence>
        {isSidebarOpen && (
          <motion.button
            aria-label="Fechar menu de conversas"
            className="sidebar-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsSidebarOpen(false)}
            type="button"
          />
        )}
      </AnimatePresence>
      <motion.aside
        className="sidebar"
        aria-hidden={!isSidebarOpen}
        onClickCapture={handleSidebarClick}
        animate={{
          x: isSidebarOpen ? 0 : -340,
          opacity: isSidebarOpen ? 1 : 0,
        }}
        transition={{
          type: "spring",
          stiffness: 260,
          damping: 28,
        }}
      >
        <div className="sidebar-toggle-container">
          <motion.button
            className="sidebar-toggle-btn"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setIsSidebarOpen(false)}
            type="button"
            title="Recolher menu"
            aria-label="Recolher menu"
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
              transition={{ type: "spring", stiffness: 220, damping: 20 }}
              onClick={() => setIsSidebarOpen(true)}
              type="button"
              title="Abrir conversas"
              aria-label="Abrir conversas"
            >
              <PanelLeftOpen size={18} />
            </motion.button>
          )}
        </AnimatePresence>
        {main}
      </main>
    </div>
  );
}
