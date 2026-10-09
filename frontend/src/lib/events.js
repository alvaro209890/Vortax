// Eventos que provam trabalho de ferramenta num turno (busca, navegador, shell, arquivos).
// Turno sem nenhum deles foi conversa: não abre cartão de progresso nem o computador.
const TOOL_WORK_EVENTS = new Set([
  "tool_call",
  "tool_result",
  "source_saved",
  "screen_frame",
  "vertex_progress",
  "files_created",
]);

export function isToolWorkEvent(event) {
  return TOOL_WORK_EVENTS.has(event?.type);
}
