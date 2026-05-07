import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle2, LockKeyhole, Mail, MessageSquareText, Sparkles, UserRound } from "lucide-react";

import { useAuth } from "../auth/AuthProvider.jsx";

function firebaseErrorMessage(error) {
  const code = error?.code || "";
  if (code.includes("auth/email-already-in-use")) return "Este email ja tem uma conta.";
  if (code.includes("auth/invalid-email")) return "Digite um email valido.";
  if (code.includes("auth/weak-password")) return "Use uma senha com pelo menos 6 caracteres.";
  if (code.includes("auth/invalid-credential") || code.includes("auth/wrong-password")) return "Email ou senha incorretos.";
  if (code.includes("auth/popup-closed-by-user")) return "Login com Google cancelado.";
  return error?.message || "Nao foi possivel autenticar agora.";
}

export function AuthScreen() {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { loginWithEmail, loginWithGoogle, registerWithEmail } = useAuth();

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "register") {
        await registerWithEmail({ email, password, name });
      } else {
        await loginWithEmail(email, password);
      }
    } catch (reason) {
      setError(firebaseErrorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGoogle() {
    setError("");
    setSubmitting(true);
    try {
      await loginWithGoogle();
    } catch (reason) {
      setError(firebaseErrorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  const registering = mode === "register";

  return (
    <main className="auth-page">
      <section className="auth-visual">
        <motion.div
          className="auth-brand-panel"
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 160, damping: 22 }}
        >
          <img src="/vortax-logo.png" alt="Vortax" />
          <div className="auth-hero-copy">
            <span>Seu assistente pessoal</span>
            <h1>Transforme pedidos em entregas prontas.</h1>
            <p>Converse com o Vortax para criar, pesquisar, organizar ideias e acompanhar cada resposta com clareza.</p>
          </div>
          <div className="auth-prompt-preview" aria-hidden="true">
            <div className="auth-prompt user">
              <MessageSquareText size={15} />
              <span>Crie uma pagina bonita para meu negocio</span>
            </div>
            <div className="auth-prompt assistant">
              <Sparkles size={15} />
              <span>Claro. Vou montar uma proposta e entregar os arquivos.</span>
            </div>
          </div>
          <div className="auth-benefits">
            <span><CheckCircle2 size={15} /> Comece em segundos</span>
            <span><Sparkles size={15} /> Veja o progresso</span>
            <span><LockKeyhole size={15} /> Historico privado</span>
          </div>
        </motion.div>
      </section>

      <motion.section
        className="auth-card"
        initial={{ opacity: 0, x: 22 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ type: "spring", stiffness: 170, damping: 24 }}
      >
        <div className="auth-switch" role="tablist" aria-label="Autenticacao">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")} type="button">
            Entrar
          </button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")} type="button">
            Criar conta
          </button>
        </div>

        <div className="auth-card-head">
          <strong>{registering ? "Crie sua conta" : "Bem-vindo de volta"}</strong>
          <span>{registering ? "Guarde suas conversas e continue de onde parou." : "Entre para acessar suas conversas e novas entregas."}</span>
        </div>

        <button className="auth-google-btn" disabled={submitting} onClick={handleGoogle} type="button">
          <span>G</span>
          Continuar com Google
        </button>

        <div className="auth-divider"><span>ou use email</span></div>

        <form className="auth-form" onSubmit={submit}>
          {registering && (
            <label>
              Nome
              <div>
                <UserRound size={17} />
                <input autoComplete="name" onChange={(event) => setName(event.target.value)} placeholder="Seu nome" value={name} />
              </div>
            </label>
          )}
          <label>
            Email
            <div>
              <Mail size={17} />
              <input autoComplete="email" onChange={(event) => setEmail(event.target.value)} placeholder="voce@email.com" required type="email" value={email} />
            </div>
          </label>
          <label>
            Senha
            <div>
              <LockKeyhole size={17} />
              <input autoComplete={registering ? "new-password" : "current-password"} minLength={6} onChange={(event) => setPassword(event.target.value)} placeholder="Sua senha" required type="password" value={password} />
            </div>
          </label>
          {error ? <p className="auth-error">{error}</p> : null}
          <button className="auth-submit-btn" disabled={submitting} type="submit">
            {submitting ? "Aguarde..." : registering ? "Criar conta" : "Entrar"}
            <ArrowRight size={17} />
          </button>
        </form>
      </motion.section>
    </main>
  );
}
