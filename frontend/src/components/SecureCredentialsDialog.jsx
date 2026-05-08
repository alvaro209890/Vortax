import { useState } from "react";
import { Lock, X } from "lucide-react";

export function SecureCredentialsDialog({ activeTaskId, disabled, onClose, onSubmit, open }) {
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [allowedOrigins, setAllowedOrigins] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  async function submit(event) {
    event.preventDefault();
    if (disabled || submitting) return;
    setSubmitting(true);
    const payload = {
      url: url.trim(),
      description: description.trim() || "Faça login e execute a tarefa solicitada dentro do app autorizado.",
      username,
      password,
      allowed_origins: allowedOrigins
        .split(/[,\n]/)
        .map((item) => item.trim())
        .filter(Boolean),
    };
    try {
      await onSubmit(payload);
      setUrl("");
      setDescription("");
      setUsername("");
      setPassword("");
      setAllowedOrigins("");
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="secure-login-backdrop" role="presentation">
      <form className="secure-login-dialog" onSubmit={submit}>
        <div className="secure-login-header">
          <div>
            <span className="secure-login-kicker"><Lock size={14} /> Login seguro</span>
            <h2>{activeTaskId ? "Autorizar site nesta conversa" : "Criar tarefa com login seguro"}</h2>
            <p>As credenciais são enviadas por canal estruturado e não entram no chat, eventos ou histórico do modelo.</p>
          </div>
          <button onClick={onClose} type="button" aria-label="Fechar">
            <X size={18} />
          </button>
        </div>

        <label>
          Site ou URL de login
          <input autoComplete="url" onChange={(event) => setUrl(event.target.value)} placeholder="https://app.exemplo.com/login" required type="url" value={url} />
        </label>

        <label>
          O que o Vortax deve fazer após entrar?
          <textarea onChange={(event) => setDescription(event.target.value)} placeholder="Analise bugs, melhorias ou execute uma atividade autorizada..." rows={3} value={description} />
        </label>

        <div className="secure-login-grid">
          <label>
            Usuário/e-mail
            <input autoComplete="username" onChange={(event) => setUsername(event.target.value)} required type="text" value={username} />
          </label>
          <label>
            Senha
            <input autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
          </label>
        </div>

        <label>
          Domínios extras permitidos (opcional)
          <textarea onChange={(event) => setAllowedOrigins(event.target.value)} placeholder="https://auth.exemplo.com, https://app.exemplo.com" rows={2} value={allowedOrigins} />
        </label>

        <div className="secure-login-warning">
          Não use para burlar CAPTCHA, 2FA, paywalls ou acessar sistemas sem autorização. O Vortax vai parar se encontrar desafio de segurança.
        </div>

        <div className="secure-login-actions">
          <button onClick={onClose} type="button">Cancelar</button>
          <button disabled={disabled || submitting} type="submit">{submitting ? "Enviando..." : "Autorizar login"}</button>
        </div>
      </form>
    </div>
  );
}
