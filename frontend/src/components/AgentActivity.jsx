import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, ChevronRight, Circle, Code2, Loader2, Sparkles } from "lucide-react";

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
  let text = String(command || "").trim().replace(/^cd\s+[A-Za-z0-9_./-]+\s*&&\s*/, "");
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

// ── Vertex Progress ─────────────────────────────────────────────────────────

const stageLabels = {
  starting: "Iniciando",
  planning: "Planejando",
  creating: "Criando",
  writing_file: "Escrevendo",
  editing: "Editando",
  reading_file: "Lendo",
  installing: "Instalando",
  configuring: "Configurando",
  executing: "Executando",
  validating: "Revisando",
  done: "Entrega pronta",
  error: "Erro",
};

const stageIcons = {
  starting: "1",
  planning: "2",
  creating: "3",
  writing_file: "4",
  editing: "5",
  reading_file: "6",
  installing: "7",
  configuring: "8",
  executing: "9",
  validating: "10",
  done: "/",
  error: "!",
};

const stageOrder = [
  "starting",
  "planning",
  "creating",
  "writing_file",
  "editing",
  "reading_file",
  "installing",
  "configuring",
  "executing",
  "validating",
  "done",
];

function useVertexProgress(events) {
  return useMemo(() => {
    const progressEvents = events.filter((e) => e.type === "vertex_progress");
    const hasVertexActivity = progressEvents.length > 0 || events.some((e) => (
      e.type === "tool_call" &&
      e.payload?.name === "shell_run" &&
      isVertexCommand(e.payload?.params?.command)
    ));

    const items = [];
    const seen = new Set();
    progressEvents.forEach((event) => {
      const payload = event.payload || {};
      const stage = payload.stage || "executing";
      const message = payload.message || stageLabels[stage] || "Vertex trabalhando";
      const file = payload.file || null;
      const key = `${stage}:${message}:${file || ""}`;
      if (seen.has(key)) return;
      seen.add(key);
      items.push({
        id: `${event.created_at || items.length}-${key}`,
        stage,
        label: stageLabels[stage] || stage,
        message,
        file,
        status: payload.status || (stage === "done" ? "done" : "running"),
      });
    });

    const lastVertexCall = [...events].reverse().find(
      (e) => e.type === "tool_call" && e.payload?.name === "shell_run" && isVertexCommand(e.payload?.params?.command)
    );
    const lastVertexResult = [...events].reverse().find(
      (e) => e.type === "tool_result" && e.payload?.name === "shell_run"
    );
    const running = Boolean(lastVertexCall && (!lastVertexResult || lastVertexResult.created_at < lastVertexCall.created_at));
    const done = items.some((item) => item.stage === "done" || item.status === "done");
    const latest = items[items.length - 1] || null;

    return {
      items: items.slice(-12),
      hasVertexActivity,
      running,
      done,
      currentStage: latest?.stage || (running ? "executing" : done ? "done" : "starting"),
      currentMessage: latest?.message || "",
      currentFile: latest?.file || null,
    };
  }, [events]);
}

function latestPayload(events, type) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].type === type) return events[index].payload || {};
  }
  return null;
}

function validationLegend(events) {
  const project = latestPayload(events, "project_validation_result");
  const web = latestPayload(events, "web_validation_result");
  const failed = [project, web].find((item) => item?.status === "failed");
  if (failed) {
    const bug = Array.isArray(failed.bugs) ? failed.bugs[0] : failed.reason;
    return { tone: "error", label: "Ajuste necessario", detail: bug || "A revisao encontrou algo para corrigir." };
  }
  const blocked = [project, web].find((item) => item?.status === "blocked");
  if (blocked) return { tone: "error", label: "Revisao bloqueada", detail: blocked.reason || "Configuracao necessaria para testar a entrega." };
  const passed = [project, web].find((item) => item?.status === "passed");
  if (passed) return { tone: "ok", label: "Tudo pronto", detail: passed.reason || "Projeto revisado, arquivos gerados e entrega pronta para usar." };
  return null;
}

export function VertexProgressPanel({ events }) {
  const [collapsed, setCollapsed] = useState(true);
  const { currentFile, currentStage, items, hasVertexActivity, running, done } = useVertexProgress(events);
  const validation = validationLegend(events);

  if (!hasVertexActivity) return null;

  const activeStage = currentStage || "executing";
  const activeIndex = Math.max(0, stageOrder.indexOf(activeStage));
  const currentLabel = stageLabels[activeStage] || "Trabalhando";
  const currentFileShort = currentFile ? currentFile.split("/").pop() : null;
  const activeCount = items.filter(i => i.status !== "done" && i.stage !== "done").length;
  const doneCount = items.filter(i => i.status === "done" || i.stage === "done").length;

  return (
    <div className={`vtx-toast ${done ? "vtx-done" : ""} ${collapsed ? "vtx-collapsed" : ""}`}>
      <button
        className="vtx-toast-bar"
        onClick={() => setCollapsed((c) => !c)}
        type="button"
      >
        <span className="vtx-toast-icon">
          {running && <Loader2 size={15} className="spinner" />}
          {done && <CheckCircle2 size={15} />}
          {!running && !done && <Code2 size={15} />}
        </span>
        <span className="vtx-toast-label">
          {done ? "Entrega pronta" : currentFileShort || currentLabel}
        </span>
        <span className="vtx-toast-stats">
          {doneCount}/{items.length || 1} etapas
        </span>
        <motion.span
          className="vtx-toast-chevron"
          animate={{ rotate: collapsed ? 0 : 180 }}
          transition={{ type: "spring", stiffness: 200, damping: 20 }}
        >
          <ChevronDown size={14} />
        </motion.span>
      </button>

      <motion.div
        className="vtx-toast-body"
        initial={false}
        animate={{
          maxHeight: collapsed ? 0 : 500,
          opacity: collapsed ? 0 : 1,
        }}
        transition={{ duration: 0.25, ease: "easeInOut" }}
      >
        <div className="vtx-stage-track">
          {stageOrder.map((stage, idx) => {
            const isDone = items.some(i => i.stage === stage && (i.status === "done" || i.stage === "done"));
            const isActive = stage === activeStage;
            const hideAfter = stage === "done" && !isDone;
            if (hideAfter) return <span key={stage} className="vtx-dot vtx-future" />;
            return (
              <span
                key={stage}
                className={`vtx-dot ${isDone ? "vtx-done" : ""} ${isActive ? "vtx-active" : ""}`}
                title={stageLabels[stage]}
              >
                {isDone ? "v" : isActive ? "·" : ""}
              </span>
            );
          })}
        </div>

        <div className="vtx-current-card">
          <span className="vtx-current-badge">{currentLabel}</span>
          <span className="vtx-current-file">{done ? "Projeto revisado e pronto" : currentFileShort || "Preparando entrega..."}</span>
        </div>

        {validation && (
          <div className={`vtx-validation ${validation.tone}`}>
            <small>{validation.label}</small>
            <p>{validation.detail}</p>
          </div>
        )}

        <div className="vtx-items-scroll">
          <AnimatePresence initial={false}>
            {(items.length ? items : [{ id: "starting", stage: "starting", label: "Iniciando", message: "Preparando execucao do Vertex.", status: "running" }]).map((item) => {
              const isItemDone = item.status === "done" || item.stage === "done";
              return (
                <motion.div
                  className={`vtx-item ${isItemDone ? "vtx-item-done" : ""}`}
                  key={item.id}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 25 }}
                >
                  <span className={`vtx-item-dot ${isItemDone ? "vtx-item-dot-done" : ""}`}>
                    {isItemDone ? <CheckCircle2 size={11} /> : <Loader2 size={11} className="spinner" />}
                  </span>
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.file ? item.file.split("/").pop() : item.message}</p>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      </motion.div>
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

  if (steps.length === 0) return null;

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
        <motion.div
          className="activity-toggle"
          animate={{ rotate: collapsed ? -90 : 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 20 }}
        >
          <ChevronDown size={16} />
        </motion.div>
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
      </div>
    </section>
  );
}
