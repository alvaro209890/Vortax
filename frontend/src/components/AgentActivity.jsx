import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, ChevronRight, Circle, Code2, FileText, Loader2, Sparkles, Terminal } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";

const busyStatuses = new Set(["queued", "thinking", "executing", "running"]);

function lastIndexOfType(events, type) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].type === type) return index;
  }
  return -1;
}

function hasEvent(events, types) {
  return events.some((event) => types.includes(event.type));
}

function isVertexCommand(command) {
  let text = String(command || "").trim();
  for (const prefix of ["cd workspace && ", "cd ./workspace && ", "cd /workspace && "]) {
    if (text.startsWith(prefix)) text = text.slice(prefix.length).trim();
  }
  return text.split(/\s+/)[0] === "vertex";
}

function lastUserPrompt(events, fallbackDescription) {
  const lastUserIndex = lastIndexOfType(events, "user_message");
  const content = lastUserIndex >= 0 ? events[lastUserIndex].payload?.content : "";
  return String(content || fallbackDescription || "").trim();
}

function taskPlanForPrompt(prompt) {
  const text = prompt.toLowerCase();
  const compactPrompt = prompt.length > 90 ? `${prompt.slice(0, 90)}...` : prompt;

  if (/(site|landing|pagina|página|frontend|interface|app|dashboard|html|css|react|vite)/i.test(text)) {
    return [
      ["Entender tela solicitada", `Interpretar layout, conteúdo e comportamento: ${compactPrompt}`],
      ["Definir estrutura visual", "Organizar seções, componentes, estados e responsividade."],
      ["Implementar interface", "Criar ou alterar componentes, estilos e interações necessárias."],
      ["Revisar experiência", "Checar acabamento visual, hierarquia, espaçamento e adaptação mobile."],
      ["Entregar resultado", "Finalizar com o resumo do que foi feito."],
    ];
  }

  if (/(pesquise|pesquisar|buscar|procure|comparar|compare|notícia|noticia|preço|preco|mercado|fonte)/i.test(text)) {
    return [
      ["Entender pesquisa", `Delimitar a pergunta e os critérios: ${compactPrompt}`],
      ["Buscar fontes", "Pesquisar páginas relevantes e abrir os melhores resultados."],
      ["Ler evidências", "Extrair dados, contexto e pontos confiáveis das fontes."],
      ["Comparar achados", "Cruzar informações e remover ruído ou duplicidade."],
      ["Responder com síntese", "Entregar conclusão clara com o que foi encontrado."],
    ];
  }

  if (/(imagem|foto|print|screenshot|analise esta imagem|analisar esta imagem)/i.test(text)) {
    return [
      ["Receber imagem", `Associar arquivo e pergunta: ${compactPrompt || "análise visual"}`],
      ["Inspecionar conteúdo", "Identificar elementos, texto, contexto e possíveis problemas."],
      ["Interpretar pedido", "Relacionar a imagem com a pergunta feita."],
      ["Validar resposta", "Organizar a análise em pontos úteis e objetivos."],
      ["Enviar análise", "Responder com a conclusão visual."],
    ];
  }

  if (/(corrija|bug|erro|falha|teste|testes|build|refator|implemente|crie|adicione|ajuste|mude|alterar|código|codigo)/i.test(text)) {
    return [
      ["Analisar pedido técnico", `Mapear o alvo da mudança: ${compactPrompt}`],
      ["Localizar arquivos", "Encontrar componentes, serviços ou estilos envolvidos."],
      ["Aplicar alteração", "Editar o código mantendo o padrão atual do projeto."],
      ["Verificar comportamento", "Executar build, teste ou checagem cabível."],
      ["Reportar conclusão", "Explicar objetivamente o que mudou."],
    ];
  }

  return [
    ["Entender pedido", compactPrompt || "Ler a solicitação enviada."],
    ["Planejar resposta", "Definir as etapas necessárias para cumprir a tarefa."],
    ["Executar ação", "Usar as ferramentas disponíveis para avançar."],
    ["Conferir resultado", "Validar se a saída atende ao pedido."],
    ["Responder", "Entregar a conclusão no chat."],
  ];
}

function stateForStep(index, signals) {
  const { active, answered, failed, hasProgress, hasToolCall, hasToolResult } = signals;
  if (failed) return index >= 3 ? "error" : "done";
  if (answered) return "done";
  if (index === 0) return "done";
  if (index === 1) {
    if (hasToolCall || hasToolResult) return "done";
    return active || hasProgress ? "active" : "pending";
  }
  if (index === 2) {
    if (hasToolResult) return "done";
    return active && hasToolCall ? "active" : "pending";
  }
  if (index === 3) {
    return active && hasToolResult ? "active" : "pending";
  }
  return "pending";
}

function buildSteps(events, status, fallbackDescription) {
  const prompt = lastUserPrompt(events, fallbackDescription);
  if (!prompt) return [];

  const lastUserIndex = lastIndexOfType(events, "user_message");
  const scopedEvents = lastUserIndex >= 0 ? events.slice(lastUserIndex) : events;
  const failed = status === "error" || hasEvent(scopedEvents, ["error"]);
  const answered = hasEvent(scopedEvents, ["assistant_message_done"]);
  const hasProgress = hasEvent(scopedEvents, ["agent_progress"]);
  const hasToolCall = hasEvent(scopedEvents, ["tool_call", "confirmation_request"]);
  const hasToolResult = hasEvent(scopedEvents, ["tool_result", "screen_frame", "source_saved"]);
  const active = busyStatuses.has(status);
  const signals = { active, answered, failed, hasProgress, hasToolCall, hasToolResult };

  return taskPlanForPrompt(prompt).map(([label, detail], index) => ({
    id: `${index}-${label}`,
    label,
    detail,
    state: stateForStep(index, signals),
  }));
}

function currentLabel(events, status) {
  if (status === "error") return "Execução interrompida";
  if (status === "done") return "Pedido concluído";

  const progress = [...events].reverse().find((event) => event.type === "agent_progress");
  if (progress?.payload?.label) return progress.payload.label;
  if (busyStatuses.has(status)) return "Trabalhando no pedido";
  return "Atividade";
}

function currentDetail(events) {
  const progress = [...events].reverse().find((event) => event.type === "agent_progress");
  return progress?.payload?.detail || "";
}

function StepIcon({ state }) {
  if (state === "done") return <CheckCircle2 size={15} />;
  if (state === "active") return <Loader2 size={15} />;
  if (state === "error") return <AlertTriangle size={15} />;
  return <Circle size={15} />;
}

// ── Vertex Live Terminal ────────────────────────────────────────────────────

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

function useVertexTerminal(events) {
  return useMemo(() => {
    const shellLines = events
      .filter((e) => e.type === "shell_stdout" || e.type === "shell_stderr")
      .slice(-200);

    const progressEvents = events.filter((e) => e.type === "vertex_progress");
    const hasShellActivity = shellLines.length > 0;
    const hasVertexActivity = progressEvents.length > 0 || events.some((e) => (
      e.type === "tool_call" &&
      e.payload?.name === "shell_run" &&
      isVertexCommand(e.payload?.params?.command)
    ));

    let progress = null;
    if (progressEvents.length > 0) {
      const last = progressEvents[progressEvents.length - 1].payload;
      const stagesSeen = progressEvents.map((e) => e.payload.stage);
      progress = {
        stage: last.stage,
        message: last.message || "",
        file: last.file || null,
        done: stagesSeen.includes("done"),
        totalSteps: new Set(stagesSeen).size,
        interactiveRounds: last.interactive_rounds || 0,
      };
    }

    // Detecta se tem shell rodando (último tool_call foi shell_run sem tool_result correspondente)
    const lastShellCall = [...events].reverse().find(
      (e) => e.type === "tool_call" && e.payload?.name === "shell_run"
    );
    const lastShellResult = [...events].reverse().find(
      (e) => e.type === "tool_result" && e.payload?.name === "shell_run"
    );
    const shellRunning = lastShellCall && (!lastShellResult || lastShellResult.created_at < lastShellCall.created_at);

    return { shellLines, progress, hasShellActivity, hasVertexActivity, shellRunning };
  }, [events]);
}

export function VertexTerminal({ events }) {
  const endRef = useRef(null);
  const [collapsed, setCollapsed] = useState(false);
  const { shellLines, progress, hasShellActivity, hasVertexActivity, shellRunning } = useVertexTerminal(events);

  useEffect(() => {
    if (!collapsed) {
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [shellLines.length, collapsed]);

  if (!hasShellActivity && !progress) return null;

  return (
    <div className={`vertex-terminal ${progress?.done ? "done" : ""} ${collapsed ? "collapsed" : ""}`}>
      <button
        className="vertex-terminal-header"
        onClick={() => setCollapsed((c) => !c)}
        type="button"
      >
        <div className="vertex-terminal-title">
          <Terminal size={13} />
          <span>{hasVertexActivity ? "Vertex trabalhando" : "Terminal"}</span>
          {shellRunning && <Loader2 size={11} className="spinner" />}
          {progress && !progress.done && (
            <span className="vertex-stage-pill">
              {stageLabels[progress.stage] || progress.stage}
            </span>
          )}
          {progress?.done && (
            <span className="vertex-stage-pill done">Concluído</span>
          )}
        </div>
        <div className="vertex-terminal-meta">
          {progress && !progress.done && progress.file && (
            <span className="vertex-current-file">
              <FileText size={11} /> {progress.file}
            </span>
          )}
          <small>{shellLines.length} linhas</small>
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      <div className="vertex-terminal-body">
        {progress && (
          <div className="vertex-terminal-progress">
            <div className="vertex-progress-track">
              {["planning", "creating", "executing", "done"].map((stage) => {
                const reached = progress.totalSteps > 0 && (
                  stage === "planning" ? true :
                  stage === "creating" ? ["writing_file", "creating", "installing"].some(s =>
                    events.some(e => e.type === "vertex_progress" && e.payload?.stage === s)
                  ) :
                  stage === "executing" ? ["executing", "editing", "validating", "configuring"].some(s =>
                    events.some(e => e.type === "vertex_progress" && e.payload?.stage === s)
                  ) :
                  progress.done
                );
                return (
                  <div
                    key={stage}
                    className={`vertex-progress-dot ${reached ? "reached" : ""} ${stage === "done" && progress.done ? "done" : ""}`}
                  />
                );
              })}
            </div>
            <span className="vertex-progress-label">
              {progress.done ? progress.message : (progress.file ? `Criando ${progress.file}` : progress.message)}
            </span>
          </div>
        )}

        <pre className="vertex-terminal-lines">
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
    </div>
  );
}

function actorLabel(actor) {
  if (actor === "deepseek") return "DeepSeek";
  if (actor === "vertex") return "Vertex";
  return "Vortax";
}

function actorIcon(actor) {
  if (actor === "vertex") return <Code2 size={14} />;
  if (actor === "deepseek") return <Bot size={14} />;
  return <Sparkles size={14} />;
}

function exchangeEvents(events) {
  return events
    .filter((event) => event.type === "ai_exchange")
    .slice(-30);
}

export function AiExchangePanel({ events }) {
  const exchanges = useMemo(() => exchangeEvents(events), [events]);

  if (exchanges.length === 0) return null;

  return (
    <CollapsiblePanel
      className="ai-exchange-panel"
      count={exchanges.length}
      storageKey="vortax.inspector.ai_exchange.collapsed"
      title="DeepSeek ↔ Vertex"
    >
      <div className="ai-exchange-list">
        {exchanges.map((event, index) => {
          const payload = event.payload || {};
          const actor = payload.actor || "vortax";
          return (
            <div className={`ai-exchange-item ${actor}`} key={`${event.created_at}-${index}`}>
              <div className="ai-exchange-icon">{actorIcon(actor)}</div>
              <div>
                <strong>
                  {actorLabel(actor)}
                  {payload.target ? ` → ${actorLabel(payload.target)}` : ""}
                </strong>
                <p>{payload.message || ""}</p>
              </div>
            </div>
          );
        })}
      </div>
    </CollapsiblePanel>
  );
}

// ── Main Component ──────────────────────────────────────────────────────────

export function AgentActivity({ events, status, taskDescription }) {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedTaskId, setExpandedTaskId] = useState(null);
  const steps = useMemo(() => buildSteps(events, status, taskDescription), [events, status, taskDescription]);
  const { hasShellActivity } = useVertexTerminal(events);

  if (steps.length === 0 && !hasShellActivity) return null;

  const label = currentLabel(events, status);
  const detail = currentDetail(events);
  const completedCount = steps.filter((step) => step.state === "done").length;

  return (
    <section className={`agent-activity ${collapsed ? "collapsed" : ""}`}>
      <button className="activity-header" onClick={() => setCollapsed((current) => !current)} type="button">
        <div className="activity-summary">
          <div className="activity-mark">
            <Sparkles size={16} />
          </div>
          <div className="activity-copy">
            <strong>{label}</strong>
            <span>{completedCount}/{steps.length} tasks concluídas{detail ? ` · ${detail}` : ""}</span>
          </div>
        </div>
        <div className="activity-toggle">
          {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
        </div>
      </button>

      <div className="activity-steps" aria-label="Tasks da atividade">
        {steps.map((step) => (
          <button
            className={`activity-step ${step.state} ${expandedTaskId === step.id ? "expanded" : ""}`}
            key={step.id}
            onClick={() => setExpandedTaskId((current) => (current === step.id ? null : step.id))}
            type="button"
          >
            <div className="activity-step-main">
              <StepIcon state={step.state} />
              <span>{step.label}</span>
              {expandedTaskId === step.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </div>
            <p>{step.detail}</p>
          </button>
        ))}

        {/* Vertex Terminal inline dentro da atividade */}
        {hasShellActivity && (
          <div className="activity-vertex-slot">
            <VertexTerminal events={events} />
          </div>
        )}
      </div>
    </section>
  );
}
