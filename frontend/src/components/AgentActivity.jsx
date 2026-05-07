import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, ChevronRight, Circle, Code2, Loader2, Sparkles } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { staggerContainer, fadeInUp } from "../animations/variants.js";

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
  writing_file: "Criando arquivo",
  creating: "Criando",
  installing: "Instalando",
  executing: "Executando",
  editing: "Editando",
  reading_file: "Lendo arquivo",
  configuring: "Configurando",
  validating: "Verificando",
  done: "Concluído",
  error: "Erro",
};

const stageDetails = {
  starting: "Preparando a CLI, permissões e pasta persistente da conversa.",
  planning: "Estimando estrutura, arquivos necessários e sequência de implementação.",
  creating: "Montando pastas, arquivos base e pontos de entrada do projeto.",
  writing_file: "Gravando arquivos de código, estilos, telas ou scripts.",
  editing: "Refinando o que já foi criado e corrigindo inconsistências.",
  installing: "Preparando dependências locais quando o projeto exige.",
  executing: "Executando comandos internos do Vertex e acompanhando a saída.",
  configuring: "Ajustando configuração, scripts, rotas ou integração local.",
  reading_file: "Lendo arquivos gerados para decidir o próximo ajuste.",
  validating: "O Vortax está testando o resultado antes de liberar a resposta.",
  done: "Criação finalizada e validação local registrada no stream.",
  error: "A validação encontrou algo que precisa voltar para correção.",
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
    return { tone: "error", label: "Correção pendente", detail: bug || "A validação encontrou bugs." };
  }
  const blocked = [project, web].find((item) => item?.status === "blocked");
  if (blocked) return { tone: "error", label: "Validação bloqueada", detail: blocked.reason || "Configuração necessária para testar." };
  const passed = [project, web].find((item) => item?.status === "passed");
  if (passed) return { tone: "ok", label: "Validação aprovada", detail: passed.reason || "Checagens locais passaram." };
  return null;
}

export function VertexProgressPanel({ events }) {
  const [collapsed, setCollapsed] = useState(false);
  const { currentFile, currentMessage, currentStage, items, hasVertexActivity, running, done } = useVertexProgress(events);
  const validation = validationLegend(events);

  if (!hasVertexActivity) return null;

  const activeStage = currentStage || "executing";
  const activeIndex = Math.max(0, stageOrder.indexOf(activeStage));
  const activeDetail = currentFile ? `Arquivo atual: ${currentFile}` : currentMessage || stageDetails[activeStage] || "Acompanhando a criação em tempo real.";

  return (
    <div className={`vertex-progress-panel ${done ? "done" : ""} ${collapsed ? "collapsed" : ""}`}>
      <button
        className="vertex-progress-header"
        onClick={() => setCollapsed((c) => !c)}
        type="button"
      >
        <div className="vertex-progress-title">
          <Code2 size={13} />
          <span>Vertex</span>
          {running && <Loader2 size={11} className="spinner" />}
          {done && <span className="vertex-stage-pill done">Concluído</span>}
        </div>
        <div className="vertex-progress-meta">
          <small>{items.length || 1} etapa(s)</small>
          <motion.span
            animate={{ rotate: collapsed ? -90 : 0 }}
            transition={{ type: "spring", stiffness: 200, damping: 20 }}
            style={{ display: "inline-flex" }}
          >
            <ChevronDown size={14} />
          </motion.span>
        </div>
      </button>

      <motion.div
        className="vertex-progress-body"
        animate={{
          maxHeight: collapsed ? 0 : 600,
          opacity: collapsed ? 0 : 1,
        }}
        transition={{ duration: 0.24, ease: "easeInOut" }}
      >
        <div className="vertex-live-legend">
          <div className="vertex-live-main">
            <small>Agora</small>
            <strong>{stageLabels[activeStage] || "Trabalhando"}</strong>
            <p>{activeDetail}</p>
          </div>
          <div className="vertex-live-estimate">
            <small>Estimativa</small>
            <p>{stageDetails[activeStage] || "Inferindo etapa pelo stream do Vertex."}</p>
          </div>
          {validation && (
            <div className={`vertex-live-validation ${validation.tone}`}>
              <small>{validation.label}</small>
              <p>{validation.detail}</p>
            </div>
          )}
        </div>

        <div className="vertex-stage-rail" aria-label="Etapas estimadas do Vertex">
          {stageOrder.map((stage, index) => (
            <motion.span
              className={`${index <= activeIndex || done ? "reached" : ""} ${stage === activeStage ? "active" : ""}`}
              key={stage}
              title={stageLabels[stage]}
              animate={stage === activeStage ? { scale: [1, 1.3, 1] } : { scale: 1 }}
              transition={stage === activeStage ? { duration: 1.2, repeat: Infinity, ease: "easeInOut" } : {}}
            />
          ))}
        </div>

        <div className="vertex-progress-list">
          <AnimatePresence initial={false}>
            {(items.length ? items : [{ id: "starting", stage: "starting", label: "Iniciando", message: "Preparando execucao do Vertex.", status: "running" }]).map((item) => (
              <motion.div
                className={`vertex-progress-item ${item.status === "done" || item.stage === "done" ? "done" : ""}`}
                key={item.id}
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, borderTopWidth: 0 }}
                transition={{ type: "spring", stiffness: 200, damping: 22 }}
              >
                <div className="vertex-progress-icon">
                  {item.status === "done" || item.stage === "done" ? <CheckCircle2 size={14} /> : <Loader2 size={14} />}
                </div>
                <div>
                  <strong>{item.label}</strong>
                  <p>{item.file ? `Arquivo: ${item.file}` : item.message}</p>
                </div>
              </motion.div>
            ))}
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
  const { hasVertexActivity } = useVertexProgress(events);

  if (steps.length === 0 && !hasVertexActivity) return null;

  const label = currentLabel(events, status);
  const detail = currentDetail(events);
  const completedCount = steps.filter((step) => step.state === "done").length;

  return (
    <motion.section
      className={`agent-activity ${collapsed ? "collapsed" : ""}`}
      initial={{ opacity: 0, y: 8, scale: 0.99 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 180, damping: 22 }}
    >
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

      <motion.div
        className="activity-steps"
        aria-label="Tasks da atividade"
        initial={false}
        animate={{ opacity: collapsed ? 0 : 1 }}
        transition={{ duration: 0.18 }}
      >
        {steps.map((step) => (
          <motion.button
            className={`activity-step ${step.state} ${expandedTaskId === step.id ? "expanded" : ""}`}
            key={step.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 200, damping: 22 }}
            layout
            whileHover={{ x: 2 }}
            whileTap={{ scale: 0.995 }}
            onClick={() => setExpandedTaskId((current) => (current === step.id ? null : step.id))}
            type="button"
          >
            <div className="activity-step-main">
              <StepIcon state={step.state} />
              <span>{step.label}</span>
              {expandedTaskId === step.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </div>
            <p>{step.detail}</p>
          </motion.button>
        ))}

        {hasVertexActivity && (
          <div className="activity-vertex-slot">
            <VertexProgressPanel events={events} />
          </div>
        )}
      </motion.div>
    </motion.section>
  );
}
