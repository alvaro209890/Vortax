import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Check,
  ChevronDown,
  Circle,
  Code2,
  Globe2,
  Loader2,
  Maximize2,
  Monitor,
  PanelRightOpen,
  Search,
  X,
  XCircle,
} from "lucide-react";

function latestEvent(events, predicate) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (predicate(events[index])) return events[index];
  }
  return null;
}

function useNow(active) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

function formatElapsed(start, now) {
  if (!start) return "";
  const seconds = Math.max(0, Math.floor((now - new Date(start).getTime()) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes <= 0) return `0:${String(rest).padStart(2, "0")}`;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function statusLabel(status) {
  if (status === "done") return "Concluido";
  if (status === "error") return "Ajuste necessario";
  if (status === "stopped") return "Interrompido";
  if (["queued", "thinking", "executing", "running"].includes(status)) return "Pensando";
  return "Pronto";
}

function stepIcon(step) {
  if (step.status === "passed" || step.status === "skipped") return <Check size={13} />;
  if (step.status === "failed") return <XCircle size={13} />;
  if (step.status === "running") return <Loader2 size={13} className="spinner" />;
  return <Circle size={13} />;
}

function eventTime(event) {
  const value = event?.created_at ? new Date(event.created_at).getTime() : 0;
  return Number.isFinite(value) ? value : 0;
}

function latestBrowserActivity(events) {
  const event = latestEvent(events, (item) => {
    const name = item.payload?.name;
    return (item.type === "tool_call" || item.type === "tool_result") && typeof name === "string" && name.startsWith("browser_");
  });
  if (!event) return null;

  const payload = event.payload || {};
  const result = payload.result || {};
  const params = payload.params || {};
  const query = params.query || result.query || "";
  const url = result.url || result.opened?.href || "";
  const title = result.title || result.opened?.title || "";
  const label = query
    ? `Pesquisando: ${query}`
    : title || payload.description || "Navegando na web";

  return {
    createdAt: eventTime(event),
    label,
    mode: payload.name === "browser_google_search" ? "search" : "browser",
    query,
    title,
    url,
    using: "Navegador",
  };
}

function isVertexShell(event) {
  const command = String(event?.payload?.params?.command || "").trim();
  return /\bvertex\b/.test(command.replace(/^cd\s+[A-Za-z0-9_./-]+\s*&&\s*/, ""));
}

function latestPreview(events) {
  const frame = latestEvent(events, (event) => event.type === "screen_frame" && event.payload?.image_base64);
  const vertex = latestEvent(events, (event) => event.type === "vertex_progress");
  const shell = latestEvent(events, (event) => event.type === "tool_call" && event.payload?.name === "shell_run");
  const browser = latestBrowserActivity(events);
  const candidates = [];

  if (frame) {
    candidates.push({
      createdAt: eventTime(frame),
      image: frame.payload.image_base64,
      label: frame.payload.caption || frame.payload.title || "Navegador",
      mode: "browser",
      title: frame.payload.title || "",
      url: frame.payload.url || "",
      using: "Navegador",
    });
  }
  if (browser) {
    candidates.push(browser);
  }
  if (vertex) {
    candidates.push({
      createdAt: eventTime(vertex),
      file: vertex.payload?.file,
      label: vertex.payload?.message || "Vertex trabalhando",
      mode: "editor",
      using: "Editor",
    });
  }
  if (shell) {
    candidates.push({
      createdAt: eventTime(shell),
      label: isVertexShell(shell) ? "Vertex iniciando" : shell.payload?.description || shell.payload?.params?.command || "Terminal",
      mode: isVertexShell(shell) ? "editor" : "terminal",
      using: isVertexShell(shell) ? "Editor" : "Terminal",
    });
  }

  if (candidates.length > 0) {
    return candidates.sort((a, b) => b.createdAt - a.createdAt)[0];
  }
  return { label: "Ambiente pronto", mode: "idle", using: "Computador" };
}

function ComputerPreview({ preview }) {
  if (preview.image) {
    return (
      <div className="computer-preview image">
        <img alt="Tela atual do computador do Vortax" src={`data:image/jpeg;base64,${preview.image}`} />
      </div>
    );
  }

  return (
    <div className={`computer-preview ${preview.mode}`}>
      <div className="computer-code-window">
        <span />
        <span />
        <span />
        <span />
        <span />
      </div>
      <small>{preview.file ? preview.file.split("/").pop() : preview.label}</small>
    </div>
  );
}

function ComputerStage({ preview }) {
  if (preview.image) {
    return (
      <div className="computer-stage browser-live">
        <div className="computer-stage-address">{preview.url || preview.title || "Tela ao vivo"}</div>
        <img alt="Tela atual do computador do Vortax" src={`data:image/jpeg;base64,${preview.image}`} />
      </div>
    );
  }

  if (preview.mode === "search") {
    return (
      <div className="computer-stage search-live">
        <div className="computer-stage-address">
          {preview.query ? `https://www.google.com/search?q=${encodeURIComponent(preview.query)}` : "https://www.google.com/search"}
        </div>
        <div className="computer-search-page">
          <div className="computer-search-logo">Google</div>
          <div className="computer-search-box">
            <Search size={16} />
            <span>{preview.query || "Pesquisando na web"}</span>
          </div>
          <div className="computer-search-results">
            <span />
            <span />
            <span />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`computer-stage ${preview.mode}`}>
      <div className="computer-stage-address">
        {preview.mode === "editor" ? "Editor do Vertex" : preview.mode === "terminal" ? "Terminal" : "Computador do Vortax"}
      </div>
      <div className="computer-editor-page">
        <div className="computer-editor-sidebar">
          <span />
          <span />
          <span />
        </div>
        <div className="computer-editor-code">
          <strong>{preview.file ? preview.file.split("/").pop() : preview.label}</strong>
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>
    </div>
  );
}

function phaseStatus(started, done, failed = false) {
  if (failed) return "failed";
  if (done) return "passed";
  if (started) return "running";
  return "pending";
}

function phaseState(status) {
  if (status === "passed") return "done";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  return "pending";
}

function latestPayload(events, predicate) {
  const event = latestEvent(events, predicate);
  return event?.payload || null;
}

function progressStep(id, label, detail, status) {
  return {
    id,
    label,
    detail,
    status,
    state: phaseState(status),
  };
}

function visibleProgressSteps(steps, terminal) {
  if (terminal) return steps;
  let lastIndex = steps.findIndex((step) => step.status === "running");
  steps.forEach((step, index) => {
    if (step.status !== "pending") lastIndex = Math.max(lastIndex, index);
  });
  if (lastIndex < 0) return steps.slice(0, 1);
  return steps.slice(0, Math.min(steps.length, lastIndex + 2));
}

function buildVertexProgress(events, agentStatus) {
  const vertexEvents = events.filter((event) => event.type === "vertex_progress");
  const latestVertex = vertexEvents[vertexEvents.length - 1]?.payload || null;
  const delegated = events.some((event) =>
    event.type === "ai_exchange"
    && event.payload?.actor === "deepseek"
    && event.payload?.target === "vertex"
  );
  const shellVertex = latestEvent(events, (event) => event.type === "tool_call" && event.payload?.name === "shell_run" && isVertexShell(event));
  const active = delegated || shellVertex || vertexEvents.length > 0;
  if (!active) return null;

  const done = latestVertex?.status === "done" || latestVertex?.stage === "done";
  const filesPayload = latestPayload(events, (event) => event.type === "files_created" && event.payload?.files?.length);
  const files = filesPayload?.files || latestVertex?.files || [];
  const fileName = latestVertex?.file || files[0]?.path || files[0]?.name || "";
  const validationStarted = events.some((event) =>
    event.type === "web_validation_started"
    || event.type === "project_validation_started"
    || event.type === "web_validation_step"
    || event.type === "project_validation_step"
  );
  const validationResult = latestPayload(events, (event) =>
    event.type === "web_validation_result" || event.type === "project_validation_result"
  );
  const validationStatus = validationResult?.status || "";
  const validationFailed = validationStatus === "failed" || validationStatus === "blocked";
  const validationDone = ["passed", "skipped"].includes(validationStatus) || done;
  const hasWriting = vertexEvents.some((event) =>
    ["writing_file", "creating", "editing", "installing", "executing", "configuring"].includes(event.payload?.stage)
  ) || files.length > 0;
  const hasPlanning = vertexEvents.some((event) =>
    ["starting", "planning"].includes(event.payload?.stage)
  ) || delegated || shellVertex;
  const terminal = ["done", "stopped", "error", "idle"].includes(agentStatus) || done;

  const steps = [
    progressStep(
      "vertex-delegation",
      "Delegar ao Vertex",
      "DeepSeek enviou a parte de codigo para o Vertex CLI.",
      phaseStatus(active, hasPlanning || hasWriting || done),
    ),
    progressStep(
      "vertex-plan",
      "Planejar projeto",
      latestVertex?.stage === "planning" ? latestVertex.message : "Definir estrutura, arquivos e criterios de entrega.",
      phaseStatus(hasPlanning, hasWriting || validationStarted || done),
    ),
    progressStep(
      "vertex-write",
      "Criar arquivos",
      fileName ? `Trabalhando em ${String(fileName).split("/").pop()}.` : files.length ? `${files.length} arquivo(s) sincronizados.` : latestVertex?.message || "Escrever e ajustar a entrega.",
      phaseStatus(hasWriting, files.length > 0 || validationStarted || done),
    ),
    progressStep(
      "vertex-validate",
      "Validar entrega",
      validationResult?.reason || validationResult?.summary || (validationStarted ? "Revisao automatica em andamento." : "Aguardar revisao automatica do Vortax."),
      phaseStatus(validationStarted, validationDone, validationFailed),
    ),
    progressStep(
      "vertex-return",
      "Devolver resultado",
      done ? latestVertex?.message || "Vertex devolveu a entrega ao Vortax." : "A resposta final sera montada apos a revisao.",
      phaseStatus(done, done),
    ),
  ];

  return {
    doneCount: steps.filter((step) => step.status === "passed").length,
    steps: visibleProgressSteps(steps, terminal),
    title: "Trabalho do Vertex",
    totalCount: steps.length,
  };
}

export function VortaxComputerDock({ activeTask, agentStatus, connectionState, events, livePlan, onOpenDetails }) {
  const [expanded, setExpanded] = useState(false);
  const busy = ["queued", "thinking", "executing", "running"].includes(agentStatus);
  const now = useNow(busy);
  const preview = useMemo(() => latestPreview(events), [events]);
  const vertexProgress = useMemo(() => buildVertexProgress(events, agentStatus), [agentStatus, events]);
  const firstEvent = events.find((event) => event.type === "user_message" || event.type === "task_created");
  const elapsed = formatElapsed(firstEvent?.created_at || activeTask?.created_at, now);
  const total = livePlan.totalCount || 0;
  const done = livePlan.doneCount || 0;
  const progressSteps = vertexProgress?.steps || livePlan.visibleSteps || livePlan.steps;
  const progressTotal = vertexProgress?.totalCount || livePlan.totalCount || 0;
  const progressDone = vertexProgress?.doneCount || livePlan.doneCount || 0;
  const terminalLabel = agentStatus === "done"
    ? "Pedido concluido"
    : agentStatus === "error"
      ? "Ajuste necessario"
      : agentStatus === "stopped"
        ? "Tarefa interrompida"
        : "";
  const current = terminalLabel || livePlan.currentStep?.label || preview.label || activeTask?.description || "Computador do Vortax";

  if (!activeTask && !events.length && !livePlan.hasSteps) return null;

  return (
    <section className={`vortax-computer-dock ${expanded ? "expanded" : ""}`}>
      <button className="computer-dock-bar" onClick={() => setExpanded((value) => !value)} type="button">
        <ComputerPreview preview={preview} />
        <div className="computer-dock-main">
          <div>
            <span className="computer-live-dot" />
            <strong>{current}</strong>
          </div>
          <small>{elapsed ? `${elapsed} · ` : ""}{statusLabel(agentStatus)} · {connectionState}</small>
        </div>
        <span className="computer-dock-count">{done}/{total || 1}</span>
        <Maximize2 size={16} />
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <>
            <motion.button
              aria-label="Fechar computador do Vortax"
              className="computer-side-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setExpanded(false)}
              type="button"
            />
            <motion.aside
              className="computer-side-panel"
              initial={{ x: 560, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 560, opacity: 0 }}
              transition={{ type: "spring", stiffness: 260, damping: 30 }}
            >
              <header className="computer-side-header">
                <div>
                  <strong>Computador do Vortax</strong>
                  <span>
                    {preview.mode === "search" || preview.mode === "browser" ? <Globe2 size={14} /> : <Monitor size={14} />}
                    Vortax esta usando o {preview.using}
                  </span>
                </div>
                <div className="computer-side-actions">
                  <button onClick={onOpenDetails} title="Abrir detalhes tecnicos" type="button">
                    <PanelRightOpen size={16} />
                  </button>
                  <button onClick={() => setExpanded(false)} title="Fechar computador" type="button">
                    <X size={17} />
                  </button>
                </div>
              </header>

              <ComputerStage preview={preview} />

              <div className="computer-live-controls">
                <span>
                  <Circle size={9} fill="currentColor" />
                  {connectionState === "open" ? "ao vivo" : connectionState}
                </span>
                <button type="button">Pular para ao vivo</button>
              </div>

              <div className="computer-progress-card">
                <div className="computer-progress-head">
                  <strong>{vertexProgress?.title || "Progresso da tarefa"}</strong>
                  <span>{progressDone}/{progressTotal || 1}</span>
                </div>
                <div className="computer-progress-list">
                  {progressSteps.length > 0 ? (
                    progressSteps.map((step) => (
                      <div className={`computer-progress-step ${step.state}`} key={step.id}>
                        <span>{stepIcon(step)}</span>
                        <div>
                          <strong>{step.label}</strong>
                          <small>{step.detail || (step.status === "running" ? `${elapsed ? `${elapsed} · ` : ""}${statusLabel(agentStatus)}` : "")}</small>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="computer-progress-step running">
                      <span><Code2 size={13} /></span>
                      <div>
                        <strong>Preparando trabalho</strong>
                        <small>O progresso aparece aqui.</small>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </section>
  );
}
