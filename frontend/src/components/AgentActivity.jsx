import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Bot, CheckCircle2, ChevronDown, ChevronRight, Circle, Code2, Loader2, Sparkles } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { getTaskPlan } from "../lib/api.js";

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

function isCodeAgentCommand(command) {
  let text = String(command || "").trim().replace(/^cd\s+[A-Za-z0-9_./-]+\s*&&\s*/, "");
  return text.split(/\s+/)[0] === "openclaude";
}

function lastUserPrompt(events, fallbackDescription) {
  const lastUserIndex = lastIndexOfType(events, "user_message");
  const content = lastUserIndex >= 0 ? events[lastUserIndex].payload?.content : "";
  return String(content || fallbackDescription || "").trim();
}

function isQuickQuestion(prompt) {
  const text = (prompt || "").trim().toLowerCase();
  if (!text || text.length > 250) return false;
  // Keywords do modo rapido do backend
  const quickKeywords = /\b(o que e|o que é|quem e|quem é|como funciona|explique|resuma|defina|qual a diferenca|qual a diferença|bom dia|boa tarde|boa noite|ola|olá|oi)\b/i;
  const isQuestion = text.endsWith("?");
  const hasAction = /\b(abra|abrir|clique|clicar|baixe|baixar|instale|instalar|rode|rodar|execute|executar|publique|publicar|configure|configurar|mande|enviar|envie|suba|corrija|alterar|altere|edite|editar|pesquise|pesquisar|buscar|procure|crie|criar|faca|faça|desenvolva|implemente|gere)\b/i.test(text);

  return (quickKeywords.test(text) || isQuestion) && !hasAction;
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

function useTaskPlan(events, status, fallbackDescription) {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [visibleCount, setVisibleCount] = useState(0); // steps revelados um a um
  const [ready, setReady] = useState(false);
  const lastPromptRef = useRef("");
  const planRef = useRef(null);

  const prompt = useMemo(
    () => lastUserPrompt(events, fallbackDescription),
    [events, fallbackDescription],
  );

  const fetchPlan = useCallback(async (description) => {
    if (!description || description === lastPromptRef.current) return;
    lastPromptRef.current = description;
    setLoading(true);
    setReady(false);
    setVisibleCount(0);
    try {
      const data = await getTaskPlan(description);
      if (Array.isArray(data.plan)) {
        planRef.current = data.plan;
        setPlan(data.plan);
        return;
      }
    } catch {
      // fallback ao hardcoded abaixo
    } finally {
      setLoading(false);
    }
    planRef.current = null;
    setPlan(null);
  }, []);

  useEffect(() => {
    if (prompt) fetchPlan(prompt);
  }, [prompt, fetchPlan]);

  // Stream de steps: revela um a um a cada ~350ms
  useEffect(() => {
    const steps = plan || null;
    if (!steps || steps.length === 0) return;
    if (visibleCount >= steps.length) {
      setReady(true);
      return;
    }
    const timer = setTimeout(() => {
      setVisibleCount((c) => Math.min(c + 1, steps.length));
    }, 350);
    return () => clearTimeout(timer);
  }, [plan, visibleCount]);

  const fallbackPlan = useMemo(
    () => (plan === null && !isQuickQuestion(prompt) ? taskPlanForPrompt(prompt) : null),
    [plan, prompt],
  );

  // Fallback plan tbm aparece gradualmente se nao veio da API
  useEffect(() => {
    if (fallbackPlan && fallbackPlan.length > 0 && !plan) {
      if (visibleCount >= fallbackPlan.length) {
        setReady(true);
        return;
      }
      const timer = setTimeout(() => {
        setVisibleCount((c) => Math.min(c + 1, fallbackPlan.length));
      }, 350);
      return () => clearTimeout(timer);
    }
  }, [fallbackPlan, visibleCount, plan]);

  return { plan, loading, fallbackPlan, visibleCount, ready };
}

function buildSteps(events, status, fallbackDescription, plan, fallbackPlan) {
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

  // Se nao houve tool_call nem agent_status executando, e resposta ja saiu:
  // e resposta simples direta sem tasks — retorna vazio
  // Checa nos events COMPLETOS (nao apenas scopedEvents) porque a execucao
  // pode ter sido antes do ultimo user_message em conversas existentes
  const hadExecution = events.some((e) => e.type === "tool_call" || e.type === "confirmation_request")
    || events.some((e) => e.type === "agent_status" && (e.payload?.status === "executing" || e.payload?.status === "running"));
  if (answered && !hadExecution && !active) return [];

  const source = plan || fallbackPlan || [];
  return source.map((item, index) => {
    const label = typeof item.label === "string" ? item.label : String(item[0] || "");
    const detail = typeof item.detail === "string" ? item.detail : String(item[1] || "");
    return {
      id: `${index}-${label}`,
      label,
      detail,
      state: stateForStep(index, signals),
    };
  });
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

// ── OpenClaude Progress ─────────────────────────────────────────────────────

function useCodeAgentProgress(events, taskDescription) {
  const [codeAgentPlan, setCodeAgentPlan] = useState(null);
  const lastDescRef = useRef("");

  useEffect(() => {
    if (!taskDescription || taskDescription === lastDescRef.current) return;
    lastDescRef.current = taskDescription;
    getTaskPlan(taskDescription).then((data) => {
      if (Array.isArray(data.vertex_steps)) {
        setCodeAgentPlan(data.vertex_steps.length > 0 ? data.vertex_steps : null);
      }
    }).catch(() => setCodeAgentPlan(null));
  }, [taskDescription]);

  return useMemo(() => {
    const progressEvents = events.filter((e) => e.type === "vertex_progress");
    const hasCodeAgentActivity = progressEvents.length > 0 || events.some((e) => (
      e.type === "tool_call" &&
      e.payload?.name === "shell_run" &&
      isCodeAgentCommand(e.payload?.params?.command)
    ));

    const items = [];
    const seen = new Set();
    progressEvents.forEach((event) => {
      const payload = event.payload || {};
      const stage = payload.stage || "executing";
      const message = payload.message || "OpenClaude trabalhando";
      const file = payload.file || null;
      const key = `${stage}:${message}:${file || ""}`;
      if (seen.has(key)) return;
      seen.add(key);
      items.push({
        id: `${event.created_at || items.length}-${key}`,
        stage,
        message,
        file,
        status: payload.status || (stage === "done" ? "done" : "running"),
      });
    });

    const lastCodeAgentCall = [...events].reverse().find(
      (e) => e.type === "tool_call" && e.payload?.name === "shell_run" && isCodeAgentCommand(e.payload?.params?.command)
    );
    const lastCodeAgentResult = [...events].reverse().find(
      (e) => e.type === "tool_result" && e.payload?.name === "shell_run"
    );
    const running = Boolean(lastCodeAgentCall && (!lastCodeAgentResult || lastCodeAgentResult.created_at < lastCodeAgentCall.created_at));
    const done = items.some((item) => item.stage === "done" || item.status === "done");
    const latest = items[items.length - 1] || null;

    const steps = codeAgentPlan && codeAgentPlan.length > 0
      ? codeAgentPlan
      : null;

    const currentIdx = steps ? Math.min(items.length, steps.length - 1) : 0;
    const dynamicTrack = steps
      ? steps.map((s, i) => ({ label: s.label, done: i < items.length, active: i === currentIdx && running }))
      : null;

    return {
      items: items.slice(-12),
      hasCodeAgentActivity,
      running,
      done,
      currentStage: latest?.stage || (running ? "executing" : done ? "done" : "starting"),
      currentMessage: latest?.message || "",
      currentFile: latest?.file || null,
      dynamicTrack,
      codeAgentPlan: steps,
    };
  }, [events, codeAgentPlan]);
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

export function CodeAgentProgressPanel({ events, taskDescription }) {
  const [collapsed, setCollapsed] = useState(true);
  const { currentFile, currentStage, items, hasCodeAgentActivity, running, done, dynamicTrack, codeAgentPlan } = useCodeAgentProgress(events, taskDescription);
  const validation = validationLegend(events);

  if (!hasCodeAgentActivity) return null;

  const currentFileShort = currentFile ? currentFile.split("/").pop() : null;
  const doneCount = items.filter(i => i.status === "done" || i.stage === "done").length;
  const currentItem = items[items.length - 1];
  const currentLabel = codeAgentPlan && dynamicTrack
    ? (dynamicTrack.find(d => d.active)?.label || (done ? "Entrega pronta" : "Preparando..."))
    : (currentItem?.message || "OpenClaude trabalhando");

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
          {doneCount}/{dynamicTrack ? dynamicTrack.length : (items.length || 1)} etapas
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
        {dynamicTrack ? (
          <div className="vtx-stage-track vtx-dynamic">
            {dynamicTrack.map((step, idx) => (
              <span
                key={`${idx}-${step.label}`}
                className={`vtx-dot ${step.done ? "vtx-done" : ""} ${step.active ? "vtx-active" : ""}`}
                title={step.label}
              >
                {step.done ? "v" : step.active ? "·" : ""}
              </span>
            ))}
          </div>
        ) : (
          <div className="vtx-stage-track">
            <span className="vtx-dot vtx-done" title="OpenClaude em execucao">v</span>
            {items.slice(1).map((_, idx) => (
              <span key={idx} className="vtx-dot vtx-active" title="..." />
            ))}
          </div>
        )}

        <div className="vtx-current-card">
          <span className="vtx-current-badge">{done ? "Entrega pronta" : currentLabel}</span>
          <span className="vtx-current-file">{done ? "Projeto revisado e pronto" : currentFileShort || (codeAgentPlan && dynamicTrack ? dynamicTrack.find(d => d.active)?.label || "Preparando..." : "Preparando entrega...")}</span>
        </div>

        {validation && (
          <div className={`vtx-validation ${validation.tone}`}>
            <small>{validation.label}</small>
            <p>{validation.detail}</p>
          </div>
        )}

        <div className="vtx-items-scroll">
          <AnimatePresence initial={false}>
            {(codeAgentPlan && codeAgentPlan.length > 0 ? (
              codeAgentPlan.map((step, idx) => {
                const isItemDone = idx < items.length;
                const isItemActive = idx === items.length && running;
                return (
                  <motion.div
                    className={`vtx-item ${isItemDone ? "vtx-item-done" : ""}`}
                    key={`${idx}-${step.label}`}
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, height: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 25 }}
                  >
                    <span className={`vtx-item-dot ${isItemDone ? "vtx-item-dot-done" : ""}`}>
                      {isItemDone ? <CheckCircle2 size={11} /> : isItemActive ? <Loader2 size={11} className="spinner" /> : <Circle size={11} />}
                    </span>
                    <div>
                      <strong>{step.label}</strong>
                      <p>{step.detail}</p>
                    </div>
                  </motion.div>
                );
              })
            ) : items.length ? items.map((item) => {
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
                    <strong>{item.message?.split(" ").slice(0, 4).join(" ") || "OpenClaude"}</strong>
                    <p>{item.file ? item.file.split("/").pop() : item.message}</p>
                  </div>
                </motion.div>
              );
            }) : (
              <motion.div
                className="vtx-item"
                key="starting-fallback"
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ type: "spring", stiffness: 300, damping: 25 }}
              >
                <span className="vtx-item-dot">
                  <Loader2 size={11} className="spinner" />
                </span>
                <div>
                  <strong>Preparando execucao</strong>
                  <p>OpenClaude iniciando ambiente de trabalho.</p>
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
  if (actor === "openclaude" || actor === "vertex") return "OpenClaude";
  return "Vortax";
}

function actorIcon(actor) {
  if (actor === "openclaude" || actor === "vertex") return <Code2 size={14} />;
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
      title="DeepSeek ↔ OpenClaude"
    >
      <div className="ai-exchange-list">
        {exchanges.map((event, index) => {
          const payload = event.payload || {};
          const actor = payload.actor || "vortax";
          const actorClass = actor === "vertex" ? "openclaude" : actor;
          return (
            <div className={`ai-exchange-item ${actorClass}`} key={`${event.created_at}-${index}`}>
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
  const { plan, loading, fallbackPlan, visibleCount, ready } = useTaskPlan(events, status, taskDescription);
  const allSteps = useMemo(
    () => buildSteps(events, status, taskDescription, plan, fallbackPlan),
    [events, status, taskDescription, plan, fallbackPlan],
  );
  // So mostra os steps que ja foram "revelados" (streaming progressivo)
  const steps = useMemo(() => allSteps.slice(0, visibleCount), [allSteps, visibleCount]);

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
          animate={{ rotate: collapsed ? -90 : 180 }}
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
