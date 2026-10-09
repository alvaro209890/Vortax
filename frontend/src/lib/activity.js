// Modelo de atividade derivado SOMENTE dos eventos registrados pelo backend.
//
// Cada chamada de ferramenta vira uma "ação" com início (tool_call), fim (tool_result,
// ou erro) e os eventos que ela produziu (saída do terminal, capturas, arquivos,
// validações, fontes). O pareamento usa payload.call_id quando existe; conversas antigas
// sem esse campo usam a ordem das chamadas com o mesmo nome. Nada aqui inventa estado:
// uma ação sem retorno registrado fica "em execução" só enquanto o turno está ativo.

import { isBrowserScene } from "./browserScenes.js";
import { clip, eventTime, fileName, hostOf, publicText } from "./text.js";

export const BUSY_STATUSES = new Set(["queued", "thinking", "executing", "running"]);
const LIVE_TURN_STATES = new Set(["running", "paused", "waiting"]);

const SEARCH_TOOLS = new Set(["web_search", "browser_google_search"]);
const FILE_WRITE_TOOLS = new Set(["file_write", "file_edit", "file_append"]);
const FILE_INSPECT_TOOLS = new Set(["file_read", "glob", "grep"]);
const SHELL_TOOLS = new Set(["shell_run", "shell_exec", "shell_view", "shell_write", "shell_kill"]);
// Ferramentas que o loop nativo pode executar ao mesmo tempo (somente leitura).
const PARALLEL_TOOLS = new Set(["web_search", "web_fetch", "file_read", "glob", "grep", "validate_project", "exact_solve", "vision_analyze", "shell_view"]);
const VALIDATION_EVENTS = new Set([
  "project_validation_started",
  "project_validation_step",
  "project_validation_result",
  "web_validation_started",
  "web_validation_step",
  "web_validation_result",
]);

export function toolFamily(name = "") {
  if (SEARCH_TOOLS.has(name)) return "search";
  if (name === "web_fetch") return "web";
  if (name.startsWith("browser_")) return "browser";
  if (FILE_WRITE_TOOLS.has(name)) return "file";
  if (FILE_INSPECT_TOOLS.has(name)) return "inspect";
  if (SHELL_TOOLS.has(name)) return "terminal";
  if (name === "validate_project" || name.endsWith("_validation")) return "validation";
  if (name === "document_render") return "document";
  if (name === "vision_analyze") return "vision";
  if (name === "exact_solve") return "math";
  return "other";
}

// Em qual aba do Computador a ação aparece.
export function paneForFamily(family) {
  if (family === "search" || family === "web" || family === "browser") return "browser";
  if (family === "file" || family === "inspect" || family === "document") return "files";
  if (family === "terminal" || family === "validation") return "terminal";
  return null;
}

export function isCodeAgentCommand(command = "") {
  return /^(?:cd\s+\S+\s*&&\s*)?(?:\S*\/)?(?:vertex|openclaude)\b/.test(String(command || "").trim());
}

function resultFailed(name, result) {
  if (!result || typeof result !== "object") return false;
  if (result.success === false || result.blocked) return true;
  if (result.error && result.success !== true) return true;
  if (name === "validate_project" && ["failed", "blocked"].includes(result.status)) return true;
  if (SHELL_TOOLS.has(name) && Number.isFinite(result.returncode) && result.returncode !== 0) return true;
  return false;
}

function quote(value, max = 40) {
  const text = clip(publicText(value), max);
  return text ? `“${text}”` : "";
}

function scrollDirection(params = {}) {
  return params.direction === "up" ? "para cima" : "para baixo";
}

// Títulos em linguagem natural; o nome técnico fica nos detalhes.
function titleTemplates(action) {
  const { tool } = action;
  const params = action.params || {};
  const result = action.result || {};
  const path = params.path || result.path || "";
  const name = fileName(path) || path || "arquivo";
  const url = params.url || result.url || "";
  const host = hostOf(url) || clip(url, 32);
  const pageTitle = clip(result.title || result.opened?.title || "", 48);
  switch (tool) {
    case "file_write": {
      const overwrite = result.created === false || (result.created === undefined && action.pathSeenBefore);
      return overwrite
        ? { running: `Reescrevendo ${name}`, done: `Reescreveu ${name}`, failed: `Não conseguiu gravar ${name}` }
        : { running: `Criando ${name}`, done: `Criou ${name}`, failed: `Não conseguiu criar ${name}` };
    }
    case "file_edit":
      return { running: `Editando ${name}`, done: `Editou ${name}`, failed: `Não conseguiu editar ${name}` };
    case "file_append":
      return { running: `Acrescentando a ${name}`, done: `Acrescentou conteúdo a ${name}`, failed: `Não conseguiu alterar ${name}` };
    case "file_read":
      return { running: `Lendo ${name}`, done: `Leu ${name}`, failed: `Não conseguiu ler ${name}` };
    case "glob":
      return { running: `Procurando arquivos ${quote(params.pattern, 30)}`, done: `Listou arquivos ${quote(params.pattern, 30)}`, failed: "A listagem de arquivos falhou" };
    case "grep":
      return { running: `Buscando ${quote(params.pattern, 30)} no código`, done: `Buscou ${quote(params.pattern, 30)} no código`, failed: "A busca no código falhou" };
    case "shell_run":
    case "shell_exec":
      if (isCodeAgentCommand(params.command)) {
        return { running: "Motor de código trabalhando", done: "Motor de código terminou", failed: "O motor de código encontrou um erro" };
      }
      return {
        running: "Executando comando",
        done: "Executou comando",
        failed: Number.isFinite(result.returncode) && result.returncode !== 0 ? `Comando falhou (código ${result.returncode})` : "Comando falhou",
      };
    case "shell_view":
      return { running: "Lendo a saída do terminal", done: "Leu a saída do terminal", failed: "Não conseguiu ler o terminal" };
    case "shell_write":
      return { running: "Enviando entrada ao terminal", done: "Enviou entrada ao terminal", failed: "Não conseguiu enviar ao terminal" };
    case "shell_kill":
      return { running: "Encerrando processo", done: "Encerrou o processo", failed: "Não conseguiu encerrar o processo" };
    case "web_search":
    case "browser_google_search": {
      const q = quote(params.query || result.query, 44);
      return { running: `Pesquisando ${q}`, done: `Pesquisou ${q}`, failed: `A busca ${q} falhou` };
    }
    case "web_fetch":
      return { running: `Lendo ${host || "página"}`, done: `Leu ${pageTitle || host || "a página"}`, failed: `Não conseguiu ler ${host || "a página"}` };
    case "browser_navigate":
      return { running: `Abrindo ${host || "página"}`, done: `Abriu ${pageTitle || host || "a página"}`, failed: `Não conseguiu abrir ${host || "a página"}` };
    case "browser_click_text":
      return { running: `Clicando em ${quote(params.text)}`, done: `Clicou em ${quote(params.text)}`, failed: `Não conseguiu clicar em ${quote(params.text)}` };
    case "browser_click_selector":
      return { running: "Clicando em um elemento", done: "Clicou em um elemento", failed: "Não conseguiu clicar no elemento" };
    case "browser_click_link_by_index":
      return { running: `Abrindo o resultado ${params.index ?? ""}`.trim(), done: `Abriu ${pageTitle || `o resultado ${params.index ?? ""}`}`.trim(), failed: "Não conseguiu abrir o resultado" };
    case "browser_type":
      return { running: "Digitando em um campo", done: `Digitou ${result.typed_chars ? `${result.typed_chars} caracteres` : "no campo"}`, failed: "Não conseguiu digitar no campo" };
    case "browser_press_key":
      return { running: `Pressionando ${params.key || "tecla"}`, done: `Pressionou ${params.key || "tecla"}`, failed: "Não conseguiu pressionar a tecla" };
    case "browser_scroll":
      return { running: `Rolando a página ${scrollDirection(params)}`, done: `Rolou a página ${scrollDirection(params)}`, failed: "Não conseguiu rolar a página" };
    case "browser_extract_text":
    case "browser_extract_article":
      return { running: "Lendo o conteúdo da página", done: `Leu ${pageTitle || "o conteúdo da página"}`, failed: "Não conseguiu ler a página" };
    case "browser_extract_links":
      return { running: "Listando links da página", done: `Listou ${Array.isArray(result.links) ? result.links.length : ""} links`.replace("  ", " "), failed: "Não conseguiu listar os links" };
    case "browser_screenshot":
      return { running: "Capturando a tela", done: "Capturou a tela", failed: "Não conseguiu capturar a tela" };
    case "browser_get_state":
      return { running: "Verificando o navegador", done: "Verificou o navegador", failed: "Não conseguiu verificar o navegador" };
    case "browser_wait_for_text":
      return { running: `Aguardando ${quote(params.text)} na página`, done: `Encontrou ${quote(params.text)}`, failed: `${quote(params.text)} não apareceu` };
    case "browser_go_back":
      return { running: "Voltando à página anterior", done: "Voltou à página anterior", failed: "Não conseguiu voltar à página anterior" };
    case "browser_auth_login":
      return { running: "Entrando com autorização segura", done: "Entrou com autorização segura", failed: "O login autorizado falhou" };
    case "browser_auth_signup":
      return { running: "Criando cadastro", done: "Criou o cadastro", failed: "O cadastro falhou" };
    case "browser_auth_status":
      return { running: "Verificando a sessão", done: "Verificou a sessão", failed: "Não conseguiu verificar a sessão" };
    case "browser_auth_logout":
      return { running: "Encerrando a sessão", done: "Encerrou a sessão", failed: "Não conseguiu encerrar a sessão" };
    case "validate_project":
    case "project_validation":
    case "web_validation":
      return { running: "Validando o projeto", done: "Validação aprovada", failed: "Validação encontrou falhas" };
    case "document_render":
      return { running: `Gerando PDF de ${fileName(params.markdown_path) || "documento"}`, done: `Gerou ${fileName(result.path || params.pdf_path) || "o PDF"}`, failed: "Não conseguiu gerar o PDF" };
    case "vision_analyze":
      return { running: "Analisando a tela", done: "Analisou a tela", failed: "Não conseguiu analisar a tela" };
    case "exact_solve":
      return { running: "Resolvendo o cálculo", done: "Resolveu o cálculo", failed: "Não conseguiu resolver o cálculo" };
    default:
      return { running: `Executando ${tool}`, done: `Concluiu ${tool}`, failed: `${tool} falhou` };
  }
}

export function actionTitle(action) {
  const templates = titleTemplates(action);
  if (action.status === "done") return templates.done;
  if (action.status === "failed") return templates.failed;
  return templates.running;
}

// Alvo verificável da ação (arquivo, comando, endereço ou consulta).
function actionTarget(action) {
  const { tool } = action;
  const params = action.params || {};
  const result = action.result || {};
  if (FILE_WRITE_TOOLS.has(tool) || tool === "file_read") return { type: "file", value: params.path || result.path || "" };
  if (tool === "glob" || tool === "grep") return { type: "pattern", value: params.pattern || "" };
  if (tool === "shell_run" || tool === "shell_exec") {
    return { type: "command", value: isCodeAgentCommand(params.command) ? "motor de código do Vortax" : publicText(params.command || "") };
  }
  if (tool === "shell_view" || tool === "shell_write" || tool === "shell_kill") return { type: "session", value: params.session_id || "" };
  if (SEARCH_TOOLS.has(tool)) return { type: "query", value: params.query || result.query || "" };
  if (tool === "document_render") return { type: "file", value: params.markdown_path || "" };
  const url = result.url || params.url || result.opened?.href || "";
  if (url) return { type: "url", value: url };
  return null;
}

function actionMeta(action) {
  const { tool } = action;
  const result = action.result || {};
  if (!action.result) return "";
  if (tool === "file_write" && result.line_count !== undefined) return `${result.line_count} linhas`;
  if (tool === "file_edit" && result.start_line) {
    return result.end_line && result.end_line !== result.start_line ? `linhas ${result.start_line}–${result.end_line}` : `linha ${result.start_line}`;
  }
  if (tool === "file_read" && result.total_lines !== undefined) return `${result.total_lines} linhas`;
  if (tool === "glob" && result.count !== undefined) return `${result.count} arquivos`;
  if (tool === "grep") return result.count !== undefined ? `${result.count} arquivos` : result.files !== undefined ? `${result.files} arquivos` : "";
  if (SEARCH_TOOLS.has(tool) && Array.isArray(result.results)) return `${result.results.length} resultados`;
  if ((tool === "shell_run" || tool === "shell_exec") && Number.isFinite(result.returncode)) return `código ${result.returncode}`;
  if (tool === "validate_project" && Array.isArray(result.bugs) && result.bugs.length) return `${result.bugs.length} problema(s)`;
  if (tool === "browser_extract_links" && Array.isArray(result.links)) return `${result.links.length} links`;
  return "";
}

function actionError(action) {
  const { result } = action;
  if (!action.failed) return "";
  if (action.errorMessage) return publicText(action.errorMessage);
  if (!result) return "";
  if (result.error) return publicText(result.error);
  if (action.tool === "validate_project" || action.tool.endsWith("_validation")) {
    return publicText(result.reason || result.bugs?.[0]?.message || result.bugs?.[0] || "");
  }
  if (result.stderr) return publicText(String(result.stderr).trim().split("\n").slice(-1)[0] || "");
  return "";
}

function newAction(base) {
  return {
    callId: null,
    endIndex: null,
    endedAt: 0,
    errorMessage: "",
    failed: false,
    files: [],
    frames: [],
    output: [],
    params: {},
    result: null,
    sources: [],
    validation: [],
    progress: [],
    warnings: [],
    ...base,
  };
}

function turnOutcome(turnEvents, { isLatest, liveStatus, pendingConfirmation }) {
  let lastStatus = null;
  let hasFinal = false;
  for (const event of turnEvents) {
    if (event.type === "agent_status") lastStatus = event.payload || {};
    if (event.type === "assistant_message_done" && !event.payload?.notice) hasFinal = true;
  }
  if (isLatest) {
    if (pendingConfirmation) return "waiting";
    if (liveStatus === "paused") return /aguardando/i.test(lastStatus?.label || "") ? "waiting" : "paused";
    if (BUSY_STATUSES.has(liveStatus)) return "running";
    if (liveStatus === "stopped") return "interrupted";
    if (liveStatus === "error") return "failed";
    if (liveStatus === "done") return "done";
  }
  const status = lastStatus?.status;
  if (status === "stopped") return "interrupted";
  if (status === "error") return "failed";
  if (hasFinal || status === "done") return "done";
  return "unknown";
}

// Divide os eventos em turnos (cada mensagem do usuário abre um turno).
function splitTurns(events) {
  const turns = [];
  let current = { userIndex: -1, start: 0, events: [] };
  events.forEach((event, index) => {
    if (event?.type === "user_message") {
      if (current.events.length || current.userIndex >= 0) turns.push(current);
      current = { userIndex: index, start: index, events: [] };
    }
    current.events.push({ event, index });
  });
  if (current.events.length || current.userIndex >= 0) turns.push(current);
  return turns;
}

function legacyActivityActions(turn, turnIndex) {
  // Conversas antigas do runner legado registravam só agent_activity.
  return turn.events
    .filter(({ event }) => event.type === "agent_activity" && String(event.payload?.title || "").trim())
    .map(({ event, index }) => {
      const payload = event.payload || {};
      const kindToFamily = { search: "search", source: "web", browser: "browser", code: "terminal", file: "file", validation: "validation" };
      const action = newAction({
        id: event.event_id !== undefined ? `activity-${event.event_id}` : `activity-${index}`,
        family: kindToFamily[payload.kind] || "other",
        legacyTitle: publicText(payload.title),
        legacyDetail: publicText(payload.detail || ""),
        startIndex: index,
        startedAt: eventTime(event),
        tool: payload.tool || "agent_activity",
        turnIndex,
        legacyStatus: payload.status,
      });
      return action;
    });
}

function attachDerived(action, event, index) {
  const payload = event.payload || {};
  if (event.type === "shell_stdout" || event.type === "shell_stderr") {
    action.output.push({ index, stream: event.type === "shell_stderr" ? "stderr" : "stdout", text: publicText(payload.line ?? "") });
    if (action.output.length > 2000) action.output.splice(0, action.output.length - 2000);
  } else if (isBrowserScene(event)) {
    action.frames.push(index);
  } else if (event.type === "files_created") {
    action.files = payload.files || [];
  } else if (event.type === "source_saved") {
    if (payload.url) action.sources.push({ url: payload.url, title: payload.title || "", via: payload.via || "" });
  } else if (VALIDATION_EVENTS.has(event.type)) {
    action.validation.push({ index, type: event.type, payload });
  } else if (event.type === "vertex_progress") {
    action.progress.push({ index, stage: payload.stage, message: publicText(payload.message || ""), file: payload.file || "" });
  } else if (event.type === "error") {
    action.errorMessage = payload.message || action.errorMessage;
  }
}

/**
 * @returns {{ turns: object[], actions: object[], byId: Map<string, object>, frames: object[] }}
 */
export function buildActivity(events = [], { agentStatus = "idle", pendingConfirmation = null } = {}) {
  const turns = splitTurns(events);
  const allActions = [];
  const byId = new Map();
  const frames = [];
  const seenPaths = new Set();

  turns.forEach((turn, turnIndex) => {
    const isLatest = turnIndex === turns.length - 1;
    const outcome = turnOutcome(turn.events.map((item) => item.event), { isLatest, liveStatus: agentStatus, pendingConfirmation: isLatest ? pendingConfirmation : null });
    const actions = [];
    const byCall = new Map();
    const openByName = new Map();
    const errors = [];
    let lastProgress = "";
    let lastProgressIndex = -1;
    let question = "";

    const openAction = (event, index) => {
      const payload = event.payload || {};
      const tool = payload.name || "ferramenta";
      const path = payload.params?.path;
      const action = newAction({
        callId: payload.call_id || null,
        family: toolFamily(tool),
        id: payload.call_id || (event.event_id !== undefined ? `ev-${event.event_id}` : `idx-${index}`),
        params: payload.params || {},
        pathSeenBefore: Boolean(path && seenPaths.has(path)),
        startIndex: index,
        startedAt: eventTime(event),
        tool,
        turnIndex,
      });
      if (path) seenPaths.add(path);
      actions.push(action);
      if (action.callId) byCall.set(action.callId, action);
      const key = SEARCH_TOOLS.has(tool) ? "search" : tool;
      if (!openByName.has(key)) openByName.set(key, []);
      openByName.get(key).push(action);
    };

    const closeAction = (action, event, index) => {
      action.endIndex = index;
      action.endedAt = eventTime(event);
      const key = SEARCH_TOOLS.has(action.tool) ? "search" : action.tool;
      const queue = openByName.get(key) || [];
      const position = queue.indexOf(action);
      if (position >= 0) queue.splice(position, 1);
    };

    const findOpen = (payload) => {
      if (payload.call_id && byCall.has(payload.call_id)) return byCall.get(payload.call_id);
      if (payload.call_id) return null;
      const key = SEARCH_TOOLS.has(payload.name || payload.tool) ? "search" : payload.name || payload.tool;
      const queue = openByName.get(key) || [];
      return queue.find((action) => !action.callId && !action.errorClosed) || queue.find((action) => !action.callId) || null;
    };

    // Sem call_id, um evento derivado pertence à ação mais recente compatível ainda aberta
    // (ou recém-encerrada, porque capturas e arquivos saem logo depois do resultado).
    const ownerFor = (event) => {
      const payload = event.payload || {};
      if (payload.call_id) return byCall.get(payload.call_id) || null;
      const wantsBrowser = isBrowserScene(event) || event.type === "source_saved";
      const wantsTerminal = event.type === "shell_stdout" || event.type === "shell_stderr" || event.type === "vertex_progress";
      for (let i = actions.length - 1; i >= 0; i -= 1) {
        const action = actions[i];
        if (wantsBrowser && !["browser", "search", "web"].includes(action.family)) continue;
        if (wantsTerminal && action.family !== "terminal") continue;
        if (VALIDATION_EVENTS.has(event.type) && !["validation", "terminal"].includes(action.family)) continue;
        if (event.type === "files_created" && !["file", "terminal", "document"].includes(action.family)) continue;
        return action;
      }
      return null;
    };

    turn.events.forEach(({ event, index }) => {
      const payload = event.payload || {};
      switch (event.type) {
        case "tool_call":
          openAction(event, index);
          break;
        case "tool_result": {
          const action = findOpen(payload);
          if (!action) break;
          action.result = payload.result && typeof payload.result === "object" ? payload.result : { value: payload.result };
          action.failed = resultFailed(action.tool, action.result);
          closeAction(action, event, index);
          break;
        }
        case "error": {
          const action = payload.call_id ? byCall.get(payload.call_id) : payload.tool ? findOpen({ name: payload.tool }) : null;
          if (action && action.result) {
            // Erro depois do resultado (ex.: captura pós-ação) não muda o desfecho da ação.
            action.warnings.push(publicText(payload.message || ""));
          } else if (action) {
            // Conversas antigas: uma exceção não publicava tool_result; o erro encerra a chamada.
            // Ela continua na fila para receber o tool_result, se ele vier depois do erro.
            action.errorMessage = payload.message || "";
            action.failed = true;
            action.errorClosed = true;
            action.endIndex = index;
            action.endedAt = eventTime(event);
          } else if (payload.message) {
            errors.push({ index, message: publicText(payload.message) });
          }
          break;
        }
        case "agent_progress":
          lastProgress = publicText(payload.label || payload.detail || "");
          lastProgressIndex = index;
          break;
        case "confirmation_request":
          question = publicText(payload.message || payload.question || "");
          break;
        default: {
          const derived = isBrowserScene(event) || ["shell_stdout", "shell_stderr", "files_created", "source_saved", "vertex_progress"].includes(event.type) || VALIDATION_EVENTS.has(event.type);
          if (!derived) break;
          const owner = ownerFor(event);
          if (owner) attachDerived(owner, event, index);
          if (isBrowserScene(event)) frames.push({ eventIndex: index, actionId: owner?.id || null, turnIndex });
          if (!owner && VALIDATION_EVENTS.has(event.type)) {
            // Validação automática sem ferramenta associada (fluxo do motor de código antigo).
            const kind = event.type.startsWith("web_") ? "web_validation" : "project_validation";
            let action = [...actions].reverse().find((item) => item.tool === kind && item.endIndex === null);
            if (!action) {
              action = newAction({ family: "validation", id: event.event_id !== undefined ? `val-${event.event_id}` : `val-${index}`, startIndex: index, startedAt: eventTime(event), tool: kind, turnIndex });
              actions.push(action);
            }
            action.validation.push({ index, type: event.type, payload });
            if (event.type.endsWith("_result")) {
              action.result = payload;
              action.failed = ["failed", "blocked"].includes(payload.status);
              action.endIndex = index;
              action.endedAt = eventTime(event);
            }
          }
        }
      }
    });

    const finalActions = actions.length ? actions : legacyActivityActions(turn, turnIndex);
    finalActions.forEach((action, position) => {
      if (action.legacyTitle) {
        const legacy = action.legacyStatus;
        action.status = legacy === "done" ? "done" : legacy === "failed" || legacy === "blocked" ? "failed" : LIVE_TURN_STATES.has(outcome) && position === finalActions.length - 1 ? outcome : outcome === "interrupted" ? "interrupted" : "unknown";
        action.title = action.legacyTitle;
        action.target = action.legacyDetail ? { type: "text", value: action.legacyDetail } : null;
        action.meta = "";
        action.error = "";
      } else {
        if (action.result || action.endIndex !== null) {
          action.status = action.failed ? "failed" : "done";
        } else if (LIVE_TURN_STATES.has(outcome)) {
          // Uma chamada sequencial seguida por outra sem retorno registrado não está mais rodando.
          const laterCall = finalActions.slice(position + 1).some((other) => other.startIndex > action.startIndex && !other.legacyTitle);
          action.status = laterCall && !PARALLEL_TOOLS.has(action.tool) ? "unknown" : outcome;
        } else {
          action.status = outcome === "interrupted" || outcome === "failed" ? "interrupted" : "unknown";
        }
        action.title = actionTitle(action);
        action.target = actionTarget(action);
        action.meta = actionMeta(action);
        action.error = actionError(action);
      }
      action.pane = paneForFamily(action.family);
      action.durationMs = action.endedAt && action.startedAt ? action.endedAt - action.startedAt : null;
      byId.set(action.id, action);
      allActions.push(action);
    });

    turn.index = turnIndex;
    turn.id = turn.userIndex >= 0 ? `turn-${events[turn.userIndex]?.event_id ?? turn.userIndex}` : "turn-initial";
    turn.status = outcome;
    turn.actions = finalActions;
    turn.errors = errors;
    turn.question = question;
    turn.lastProgress = lastProgressIndex > (finalActions.at(-1)?.startIndex ?? -1) ? lastProgress : "";
    turn.isLatest = isLatest;
    turn.startedAt = eventTime(turn.events[0]?.event);
    turn.endedAt = eventTime(turn.events.at(-1)?.event);
  });

  return { actions: allActions, byId, frames, turns };
}

// Resumo do que está acontecendo agora num turno (para o chat e o dock).
export function turnHeadline(turn) {
  if (!turn) return { status: "pending", title: "Pronto para começar" };
  const running = [...turn.actions].reverse().find((action) => ["running", "paused"].includes(action.status));
  if (turn.status === "waiting") return { status: "waiting", title: "Aguardando sua resposta", detail: turn.question };
  if (turn.status === "paused") return { status: "paused", title: running ? `Pausado · ${running.title}` : "Pausado", action: running };
  if (turn.status === "running") {
    if (running) return { status: "running", title: running.title, action: running };
    return { status: "running", title: turn.lastProgress || (turn.actions.length ? "Decidindo o próximo passo" : "Preparando a tarefa") };
  }
  if (turn.status === "done") return { status: "done", title: "Concluído" };
  if (turn.status === "failed") return { status: "failed", title: "Terminou com erro" };
  if (turn.status === "interrupted") return { status: "interrupted", title: "Interrompido" };
  return { status: "unknown", title: "Sem confirmação de término" };
}

function groupKey(action) {
  if (action.legacyTitle) return null;
  if (action.family === "inspect") return "inspect";
  if (action.family === "file") return "write";
  if (action.family === "search" || action.family === "web") return "research";
  if (action.family === "browser") return `browser:${hostOf(action.target?.value || "") || "pagina"}`;
  if (action.family === "terminal") return "terminal";
  return null;
}

function groupTitle(key, actions, status) {
  const count = actions.length;
  const active = ["running", "paused", "waiting"].includes(status);
  if (key === "inspect") return active ? `Consultando arquivos (${count})` : `Consultou ${count} arquivos`;
  if (key === "write") {
    const names = new Set(actions.map((action) => action.target?.value).filter(Boolean));
    return active ? `Alterando arquivos (${names.size})` : `Alterou ${names.size} ${names.size === 1 ? "arquivo" : "arquivos"}`;
  }
  if (key === "research") {
    const reads = actions.filter((action) => action.family === "web").length;
    const searches = count - reads;
    const parts = [];
    if (searches) parts.push(`${searches} ${searches === 1 ? "busca" : "buscas"}`);
    if (reads) parts.push(`${reads} ${reads === 1 ? "página lida" : "páginas lidas"}`);
    return active ? `Pesquisando · ${parts.join(", ")}` : `Pesquisa · ${parts.join(", ")}`;
  }
  if (key.startsWith("browser:")) {
    const host = key.slice(8);
    return active ? `Navegando em ${host} · ${count} ações` : `Navegou em ${host} · ${count} ações`;
  }
  if (key === "terminal") return active ? `Executando comandos (${count})` : `Executou ${count} comandos`;
  return `${count} ações`;
}

function groupStatus(actions) {
  const statuses = actions.map((action) => action.status);
  for (const candidate of ["running", "waiting", "paused"]) {
    if (statuses.includes(candidate)) return candidate;
  }
  return statuses[statuses.length - 1];
}

// Agrupa ações consecutivas parecidas; repetições idênticas viram uma linha com contador.
export function groupActions(actions = []) {
  const collapsed = [];
  actions.forEach((action) => {
    const previous = collapsed[collapsed.length - 1];
    const sameTarget = previous
      && previous.action.tool === action.tool
      && (previous.action.target?.value || "") === (action.target?.value || "")
      && previous.action.status === action.status
      && ["shell_view", "browser_get_state", "browser_screenshot", "file_read", "glob"].includes(action.tool);
    if (sameTarget) {
      previous.repeats.push(action);
      previous.action = action;
    } else {
      collapsed.push({ action, repeats: [action] });
    }
  });

  const groups = [];
  collapsed.forEach((item) => {
    const key = groupKey(item.action);
    const last = groups[groups.length - 1];
    if (key && last && last.key === key) {
      last.items.push(item);
    } else {
      groups.push({ id: `group-${item.action.id}`, items: [item], key });
    }
  });

  return groups.map((group) => {
    const actionsInGroup = group.items.flatMap((item) => item.repeats);
    const status = groupStatus(actionsInGroup);
    if (group.items.length === 1) {
      return { id: group.id, single: true, item: group.items[0], status, actions: actionsInGroup };
    }
    return {
      id: group.id,
      single: false,
      items: group.items,
      status,
      actions: actionsInGroup,
      failures: actionsInGroup.filter((action) => action.status === "failed").length,
      title: groupTitle(group.key, actionsInGroup, status),
      family: group.items[0].action.family,
    };
  });
}

// Arquivos e fontes que um turno realmente produziu ou consultou.
export function turnResults(turn) {
  const files = new Map();
  const sources = new Map();
  (turn?.actions || []).forEach((action) => {
    if (action.status === "done" && ["file_write", "file_edit", "file_append", "document_render"].includes(action.tool)) {
      const path = action.tool === "document_render" ? action.result?.path : action.target?.value;
      if (path) {
        const created = files.get(path)?.change === "created"
          || (action.tool === "file_write" && action.result?.created !== false && !action.pathSeenBefore);
        files.set(path, { path, change: created ? "created" : "edited", actionId: action.id });
      }
    }
    action.sources.forEach((source) => {
      if (source.url && !sources.has(source.url)) sources.set(source.url, { ...source, actionId: action.id });
    });
    if (action.tool === "web_fetch" && action.status === "done" && action.result?.url && !sources.has(action.result.url)) {
      sources.set(action.result.url, { url: action.result.url, title: action.result.title || "", actionId: action.id });
    }
  });
  return { files: [...files.values()], sources: [...sources.values()] };
}

export const STATUS_LABELS = {
  pending: "Pendente",
  running: "Em execução",
  done: "Concluído",
  failed: "Falhou",
  paused: "Pausado",
  waiting: "Aguardando você",
  interrupted: "Interrompido",
  unknown: "Sem confirmação",
};
