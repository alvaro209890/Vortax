import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { FileText, Loader2, Terminal } from "lucide-react";

const stageLabels = {
  planning: "Planejando",
  writing_file: "Criando arquivo",
  creating: "Criando",
  installing: "Instalando",
  executing: "Executando",
  editing: "Editando",
  reading_file: "Lendo arquivo",
  configuring: "Configurando",
  validating: "Revisando",
  done: "Entrega pronta",
};

function publicText(value) {
  return String(value || "")
    .replace(/\bOpenClaude\b/g, "Vortax")
    .replace(/\bVertex CLI\b/g, "Vortax")
    .replace(/\bVertex\b/g, "Vortax")
    .replace(/\bopenclaude\b/g, "Vortax")
    .replace(/\bvertex\b/g, "Vortax");
}

function codeAgentProgressSummary(events) {
  const progressEvents = events.filter((event) => event.type === "vertex_progress");
  if (progressEvents.length === 0) return null;

  const last = progressEvents[progressEvents.length - 1].payload;
  const stagesSeen = progressEvents.map((e) => e.payload.stage);
  const done = stagesSeen.includes("done");

  return {
    stage: last.stage,
    message: publicText(last.message || ""),
    file: last.file || null,
    done,
    totalSteps: new Set(stagesSeen).size,
    interactiveRounds: last.interactive_rounds || 0,
  };
}

export function ShellOutput({ events }) {
  const endRef = useRef(null);

  const shellLines = events
    .filter((event) => event.type === "shell_stdout" || event.type === "shell_stderr")
    .slice(-200);

  const codeAgentProgress = codeAgentProgressSummary(events);
  const hasInteractivePrompt = events.some((event) => event.type === "shell_interactive_prompt");

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [shellLines.length, codeAgentProgress?.stage]);

  if (shellLines.length === 0 && !codeAgentProgress) return null;

  return (
    <motion.div
      className="shell-output"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <div className="shell-output-header">
        <Terminal size={14} />
        <span>Terminal</span>
        {codeAgentProgress && !codeAgentProgress.done && (
          <span className="shell-stage-badge">
            <Loader2 size={12} />
            {stageLabels[codeAgentProgress.stage] || codeAgentProgress.stage}
          </span>
        )}
        {codeAgentProgress?.done && (
          <span className="shell-stage-badge done">
            {stageLabels.done}
          </span>
        )}
        <small>{shellLines.length} linhas</small>
      </div>

      {codeAgentProgress && (
        <div className="code-agent-progress-bar">
          <div className="code-agent-progress-steps">
            {codeAgentProgress.stage !== "done" ? (
              <>
                <Loader2 size={12} className="spinner" />
                <span>
                  {codeAgentProgress.file ? (
                    <><FileText size={12} /> {codeAgentProgress.file}</>
                  ) : (
                    codeAgentProgress.message
                  )}
                </span>
              </>
            ) : (
              <span className="code-agent-done-msg">{codeAgentProgress.message}</span>
            )}
            {codeAgentProgress.interactiveRounds > 0 && (
              <span className="code-agent-interactive-note">
                {codeAgentProgress.interactiveRounds} resposta(s) automática(s)
              </span>
            )}
          </div>
        </div>
      )}

      {hasInteractivePrompt && (
        <div className="shell-interactive-note">
          O Vortax respondeu automaticamente a prompts interativos do comando.
        </div>
      )}

      <pre className="shell-output-lines">
        {shellLines.map((event, i) => (
          <span
            className={event.type === "shell_stderr" ? "stderr" : ""}
            key={`${event.created_at}-${i}`}
          >
            {publicText(event.payload?.line || "")}
          </span>
        ))}
      </pre>
      <div ref={endRef} />
    </motion.div>
  );
}
