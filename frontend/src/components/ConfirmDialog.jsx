import { motion, AnimatePresence } from "framer-motion";
import { Check, X } from "lucide-react";

import { slideUp } from "../animations/variants.js";

export function ConfirmDialog({ confirmation, onAnswer }) {
  return (
    <AnimatePresence>
      {confirmation && (
        <motion.div
          className="confirm-dialog"
          variants={slideUp}
          initial="hidden"
          animate="visible"
          exit="exit"
        >
          <strong>{confirmation.title || "Confirmar acao"}</strong>
          <p>{confirmation.message || "A IA precisa de aprovacao para continuar."}</p>
          <div>
            <button onClick={() => onAnswer(false)} type="button">
              <X size={16} />
              Recusar
            </button>
            <button onClick={() => onAnswer(true)} type="button">
              <Check size={16} />
              Aprovar
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
