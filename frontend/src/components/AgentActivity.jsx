import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Circle, Loader2, Sparkles } from "lucide-react";

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
      </div>
    </section>
  );
}
