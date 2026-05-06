import { AlertTriangle, CheckCircle2, Circle, Globe2, Monitor, Search, Terminal } from "lucide-react";

const hiddenTypes = new Set(["task_created", "user_message", "assistant_message_delta", "agent_status"]);

function iconFor(event) {
  const tool = event.payload?.name || event.payload?.tool;
  if (event.type === "error") return <AlertTriangle size={16} />;
  if (event.type === "screen_frame") return <Monitor size={16} />;
  if (event.type === "source_saved") return <Globe2 size={16} />;
  if (event.type === "assistant_message_done") return <CheckCircle2 size={16} />;
  if (tool === "browser_google_search") return <Search size={16} />;
  if (tool?.startsWith("browser_")) return <Globe2 size={16} />;
  if (event.type === "tool_call" || event.type === "tool_result") return <Terminal size={16} />;
  return <Circle size={16} />;
}

function titleFor(event) {
  const payload = event.payload || {};
  if (event.type === "agent_progress") return payload.label || "Andamento";
  if (event.type === "tool_call") return toolTitle(payload.name, "Executando");
  if (event.type === "tool_result") return toolTitle(payload.name, "Resultado");
  if (event.type === "screen_frame") return "Tela atualizada";
  if (event.type === "source_saved") return "Fonte salva";
  if (event.type === "assistant_message_done") return "Resposta final";
  if (event.type === "error") return "Erro";
  return event.type;
}

function toolTitle(name, fallback) {
  const labels = {
    browser_google_search: "Pesquisa no Google",
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
  if (event.type === "tool_result") return summarizeToolResult(payload.result);
  if (payload.description) return payload.description;
  if (event.type === "source_saved") return `${payload.title || payload.url} (${payload.quality_score || 0}/100)`;
  if (payload.detail) return payload.detail;
  if (payload.message) return payload.message;
  if (payload.content) return payload.content;
  if (payload.caption) return payload.caption;
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
  return "Concluido";
}

export function ActionTimeline({ events }) {
  const operationalEvents = events.filter((event) => !hiddenTypes.has(event.type));

  return (
    <section className="panel timeline-panel">
      <div className="panel-title">
        <span>Atividade</span>
        <small>{operationalEvents.length}</small>
      </div>
      <div className="timeline">
        {operationalEvents.length === 0 ? (
          <p className="muted">O andamento aparece aqui.</p>
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
    </section>
  );
}
