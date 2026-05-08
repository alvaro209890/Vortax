import { AlertTriangle, Bot, CheckCircle2, Circle, Code2, Globe2, Monitor, Search, Terminal } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";

const hiddenTypes = new Set([
  "task_created",
  "task_plan_created",
  "task_plan_replanned",
  "task_step_started",
  "task_step_updated",
  "task_step_completed",
  "task_step_failed",
  "user_message",
  "assistant_message_delta",
  "agent_status",
  "agent_progress",
  "shell_stdout",
  "shell_stderr",
  "screen_frame",
  "ai_exchange",
  "context_status",
  "context_compacted",
  "web_validation_step",
  "project_validation_step",
  "dev_server_started",
  "dev_server_stopped",
]);

const importantCodeAgentStages = new Set(["starting", "validating", "done", "error"]);

function publicText(value) {
  return String(value || "")
    .replace(/\bOpenClaude\b/g, "Vortax")
    .replace(/\bVertex CLI\b/g, "Vortax")
    .replace(/\bVertex\b/g, "Vortax")
    .replace(/\bopenclaude\b/g, "Vortax")
    .replace(/\bvertex\b/g, "Vortax");
}

function iconFor(event) {
  const tool = event.payload?.name || event.payload?.tool;
  if (event.type === "error") return <AlertTriangle size={16} />;
  if (event.type === "agent_activity") {
    const kind = event.payload?.kind;
    if (kind === "search") return <Search size={16} />;
    if (kind === "source") return <Globe2 size={16} />;
    if (kind === "browser") return <Monitor size={16} />;
    if (kind === "code" || kind === "file") return <Code2 size={16} />;
    if (kind === "validation" || kind === "finalizing") return <CheckCircle2 size={16} />;
  }
  if (event.type === "screen_frame") return <Monitor size={16} />;
  if (event.type === "vertex_progress") return <Code2 size={16} />;
  if (event.type === "ai_exchange") return ["openclaude", "vertex"].includes(event.payload?.actor) ? <Code2 size={16} /> : <Bot size={16} />;
  if (event.type === "web_validation_started" || event.type === "web_validation_step") return <Monitor size={16} />;
  if (event.type === "web_validation_result") {
    return event.payload?.status === "passed" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />;
  }
  if (event.type === "project_validation_started" || event.type === "project_validation_result") {
    return event.payload?.status === "passed" ? <CheckCircle2 size={16} /> : <Terminal size={16} />;
  }
  if (event.type === "files_created") return <Code2 size={16} />;
  if (event.type === "source_saved") return <Globe2 size={16} />;
  if (event.type === "assistant_message_done") return <CheckCircle2 size={16} />;
  if (tool === "browser_google_search") return <Search size={16} />;
  if (tool?.startsWith("browser_")) return <Globe2 size={16} />;
  if (event.type === "tool_call" || event.type === "tool_result") return <Terminal size={16} />;
  return <Circle size={16} />;
}

function titleFor(event) {
  const payload = event.payload || {};
  if (event.type === "agent_activity") return payload.title || "Atividade do Vortax";
  if (event.type === "agent_progress") return payload.label || "Andamento";
  if (event.type === "tool_call") return toolTitle(payload.name, "Executando");
  if (event.type === "tool_result") return toolTitle(payload.name, "Resultado");
  if (event.type === "screen_frame") return "Tela atualizada";
  if (event.type === "vertex_progress") return "Vortax trabalhando";
  if (event.type === "ai_exchange") return "Vortax coordenando";
  if (event.type === "web_validation_started") return "Revisao do site";
  if (event.type === "web_validation_step") return payload.label || "Testando site";
  if (event.type === "web_validation_result") return payload.status === "passed" ? "Site revisado" : "Ajustes no site";
  if (event.type === "project_validation_started") return "Revisao do projeto";
  if (event.type === "project_validation_result") return payload.status === "passed" ? "Projeto revisado" : "Ajustes no projeto";
  if (event.type === "shell_interactive_prompt") return "Prompt interativo";
  if (event.type === "dev_server_started") return "Preview interno iniciado";
  if (event.type === "dev_server_stopped") return "Preview interno encerrado";
  if (event.type === "files_created") return "Arquivos gerados";
  if (event.type === "source_saved") return "Fonte salva";
  if (event.type === "assistant_message_done") return "Resposta final";
  if (event.type === "error") return "Erro";
  return event.type;
}

function toolTitle(name, fallback) {
  const labels = {
    browser_google_search: "Pesquisa na web",
    browser_click_link_by_index: "Abrindo resultado",
    browser_extract_text: "Lendo pagina",
    browser_extract_links: "Extraindo links",
    browser_go_back: "Voltando",
    browser_navigate: "Navegando",
    browser_screenshot: "Capturando tela",
  };
  return labels[name] || fallback;
}

function labelFor(event) {
  const payload = event.payload || {};
  if (event.type === "tool_result") return publicText(summarizeToolResult(payload.result));
  if (payload.description) return publicText(payload.description);
  if (event.type === "source_saved") return `${payload.title || payload.url} (${payload.quality_score || 0}/100)`;
  if (event.type === "vertex_progress") return payload.file ? `Criando ${payload.file}` : publicText(payload.message);
  if (event.type === "ai_exchange") return publicText(payload.message);
  if (event.type === "web_validation_started") return "Abrindo o preview e revisando o site antes de concluir.";
  if (event.type === "web_validation_result") {
    if (payload.status === "passed") return `${payload.viewports_checked || 0} viewport(s) analisada(s) com visao.`;
    return publicText((payload.bugs || []).join("; ") || payload.reason || "Revisao visual encontrou ajustes.");
  }
  if (event.type === "project_validation_started") {
    const project = payload.project || {};
    return `${project.file_count || 0} arquivo(s); tipo detectado: ${project.kind || "generico"}.`;
  }
  if (event.type === "project_validation_result") {
    if (payload.status === "passed") return publicText(payload.reason || "Entrega revisada e pronta.");
    return publicText((payload.bugs || []).join("; ") || payload.reason || "Revisao do projeto encontrou ajustes.");
  }
  if (event.type === "shell_interactive_prompt") return payload.prompt;
  if (event.type === "dev_server_started") return "Servidor temporario usado apenas para revisao interna.";
  if (event.type === "dev_server_stopped") return publicText(payload.reason || "Servidor temporario encerrado.");
  if (event.type === "files_created") {
    const fileCount = payload.files?.length || 0;
    const projectCount = payload.projects?.length || 0;
    return `${fileCount} arquivo(s) em ${projectCount || 1} projeto(s).`;
  }
  if (payload.detail) return publicText(payload.detail);
  if (payload.message) return publicText(payload.message);
  if (payload.content) return publicText(payload.content);
  if (payload.caption) return publicText(payload.caption);
  return "";
}

function summarizeToolResult(result) {
  if (!result) return "";
  if (typeof result === "string") return result;
  if (result.query && Array.isArray(result.results)) {
    return `${result.results.length} resultados para "${result.query}"`;
  }
  if (Array.isArray(result.links)) return `${result.links.length} links encontrados`;
  if (result.opened?.title) return result.opened.title;
  if (result.title && result.url) return `${result.title} - ${result.url}`;
  if (result.text) return result.text.slice(0, 180);
  if (result.error) return result.error;
  return "Pronto";
}

function isHighSignalEvent(event) {
  if (hiddenTypes.has(event.type)) return false;
  if (event.type === "vertex_progress") {
    const stage = event.payload?.stage || event.payload?.current_stage;
    return importantCodeAgentStages.has(stage);
  }
  if (event.type === "tool_call") {
    const tool = event.payload?.name;
    return tool === "browser_google_search" || tool === "confirmation_request";
  }
  if (event.type === "tool_result") {
    const result = event.payload?.result;
    return result?.success === false || Boolean(result?.error);
  }
  if (event.type === "web_validation_started" || event.type === "project_validation_started") {
    return false;
  }
  return true;
}

function compactOperationalEvents(events) {
  const compacted = [];
  for (const event of events.filter(isHighSignalEvent)) {
    const title = titleFor(event);
    const label = labelFor(event);
    const previous = compacted[compacted.length - 1];
    if (previous && titleFor(previous) === title && labelFor(previous) === label) {
      compacted[compacted.length - 1] = event;
    } else {
      compacted.push(event);
    }
  }
  return compacted.slice(-24);
}

export function ActionTimeline({ events }) {
  const operationalEvents = compactOperationalEvents(events);

  return (
    <CollapsiblePanel
      className="timeline-panel"
      count={operationalEvents.length}
      storageKey="vortax.inspector.activity.collapsed"
      title="Atividade"
    >
      <div className="timeline">
        {operationalEvents.length === 0 ? (
          <p className="panel-state">O andamento aparece aqui.</p>
        ) : (
          operationalEvents.map((event, index) => (
            <div className={`timeline-item ${event.type}`} key={`${event.created_at}-${index}`}>
              <div className="timeline-icon">{iconFor(event)}</div>
              <div>
                <strong>{titleFor(event)}</strong>
                <p>{labelFor(event)}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </CollapsiblePanel>
  );
}
