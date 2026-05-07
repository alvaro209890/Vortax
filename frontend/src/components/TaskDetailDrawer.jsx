import { AnimatePresence, motion } from "framer-motion";
import { ListChecks, X } from "lucide-react";

export function TaskDetailDrawer({ children, onClose, open }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button
            aria-label="Fechar detalhes"
            className="detail-drawer-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            type="button"
          />
          <motion.aside
            className="task-detail-drawer"
            initial={{ x: 420, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 420, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 30 }}
          >
            <header className="detail-drawer-header">
              <div className="detail-drawer-title">
                <span className="detail-drawer-mark">
                  <ListChecks size={16} />
                </span>
                <div>
                  <strong>Detalhes da tarefa</strong>
                  <span>Arquivos, fontes, timeline e trocas tecnicas</span>
                </div>
              </div>
              <button onClick={onClose} title="Fechar detalhes" type="button">
                <X size={18} />
              </button>
            </header>
            <div className="detail-drawer-content">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
