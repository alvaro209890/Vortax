import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, X } from "lucide-react";

export function AlertDialog({ open, title, message, confirmLabel = "Confirmar", cancelLabel = "Cancelar", onConfirm, onCancel, danger = false }) {
  if (!open) return null;
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="alert-dialog-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onCancel}
          />
          <motion.div
            className="alert-dialog"
            initial={{ opacity: 0, scale: 0.94, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: 8 }}
            transition={{ type: "spring", stiffness: 300, damping: 24 }}
          >
            <div className={`alert-dialog-icon ${danger ? "danger" : ""}`}>
              <AlertTriangle size={20} />
            </div>
            <div className="alert-dialog-body">
              <strong>{title}</strong>
              {message && <p>{message}</p>}
            </div>
            <div className="alert-dialog-actions">
              <button className="alert-dialog-cancel" onClick={onCancel} type="button">
                {cancelLabel}
              </button>
              <button className={`alert-dialog-confirm ${danger ? "danger" : ""}`} onClick={onConfirm} type="button">
                {confirmLabel}
              </button>
            </div>
            <button className="alert-dialog-close" onClick={onCancel} type="button">
              <X size={14} />
            </button>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
