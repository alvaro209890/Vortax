import { useEffect, useRef } from "react";
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
  validating: "Verificando",
  done: "Concluído",
};

function vertexProgressSummary(events) {
  const progressEvents = events.filter((event) => event.type === "vertex_progress");
  if (progressEvents.length === 0) return null;

  const last = progressEvents[progressEvents.length - 1].payload;
  const stagesSeen = progressEvents.map((e) => e.payload.stage);
  const done = stagesSeen.includes("done");

  return {
    stage: last.stage,
    message: last.message || "",
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

  const vertexProgress = vertexProgressSummary(events);
  const hasInteractivePrompt = events.some((event) => event.type === "shell_interactive_prompt");

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [shellLines.length, vertexProgress?.stage]);

  if (shellLines.length === 0 && !vertexProgress) return null;

  return (
    <div className="shell-output">
      <div className="shell-output-header">
        <Terminal size={14} />
        <span>Terminal</span>
        {vertexProgress && !vertexProgress.done && (
          <span className="shell-stage-badge">
            <Loader2 size={12} />
            {stageLabels[vertexProgress.stage] || vertexProgress.stage}
          </span>
        )}
        {vertexProgress?.done && (
          <span className="shell-stage-badge done">
            {stageLabels.done}
          </span>
        )}
        <small>{shellLines.length} linhas</small>
      </div>

      {vertexProgress && (
        <div className="vertex-progress-bar">
          <div className="vertex-progress-steps">
            {vertexProgress.stage !== "done" ? (
              <>
                <Loader2 size={12} className="spinner" />
                <span>
                  {vertexProgress.file ? (
                    <><FileText size={12} /> {vertexProgress.file}</>
                  ) : (
                    vertexProgress.message
                  )}
                </span>
              </>
            ) : (
              <span className="vertex-done-msg">{vertexProgress.message}</span>
            )}
            {vertexProgress.interactiveRounds > 0 && (
              <span className="vertex-interactive-note">
                {vertexProgress.interactiveRounds} resposta(s) automática(s)
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
            {event.payload?.line || ""}
          </span>
        ))}
      </pre>
      <div ref={endRef} />
    </div>
  );
}
