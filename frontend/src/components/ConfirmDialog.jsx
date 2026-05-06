import { Check, X } from "lucide-react";

export function ConfirmDialog({ confirmation, onAnswer }) {
  if (!confirmation) return null;

  return (
    <div className="confirm-dialog">
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
    </div>
  );
}
