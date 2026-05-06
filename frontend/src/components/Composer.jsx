import { useState } from "react";
import { Send } from "lucide-react";

export function Composer({ disabled, onSubmit }) {
  const [value, setValue] = useState("");

  async function submit() {
    const description = value.trim();
    if (!description || disabled) return;
    setValue("");
    await onSubmit(description);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="composer">
      <textarea
        aria-label="Mensagem"
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? "Backend indisponivel" : "Digite uma tarefa para o Vortax..."}
        rows={3}
        value={value}
      />
      <button disabled={disabled || !value.trim()} onClick={submit} title="Enviar" type="button">
        <Send size={18} />
      </button>
    </div>
  );
}
