import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  Check,
  Circle,
  Code2,
  FileCode2,
  FolderTree,
  Globe2,
  Loader2,
  Monitor,
  PanelRightOpen,
  Search,
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

function publicText(value) {
  return String(value || "")
    .replace(/\bOpenClaude\b/g, "Vortax")
    .replace(/\bVertex CLI\b/g, "Vortax")
    .replace(/\bVertex\b/g, "Vortax")
    .replace(/\bopenclaude\b/g, "Vortax")
    .replace(/\bvertex\b/g, "Vortax");
}

const codeAgentStageLabels = {
  starting: "Preparando ambiente",
  planning: "Planejando arquitetura",
  creating: "Criando estrutura",
  writing_file: "Escrevendo arquivo",
  editing: "Refinando codigo",
  reading_file: "Lendo contexto",
  installing: "Instalando dependencias",
  configuring: "Configurando projeto",
  executing: "Executando comandos",
  validating: "Validando preview",
  done: "Entrega pronta",
  error: "Corrigindo falha",
};

const codeAgentStageDescriptions = {
  starting: "Preparando a area de trabalho da conversa.",
  planning: "Separando requisitos em arquivos, componentes e validacoes.",
  creating: "Montando a base do projeto antes de editar detalhes.",
  writing_file: "Aplicando alteracoes em arquivos reais do workspace.",
  editing: "Ajustando layout, estados e comportamento.",
  reading_file: "Conferindo arquivos para decidir o proximo ajuste.",
  installing: "Preparando pacotes ou scripts necessarios.",
  configuring: "Ajustando configs, rotas ou comandos do projeto.",
  executing: "Aplicando acoes e sincronizando arquivos.",
  validating: "Abrindo o resultado e procurando problemas visuais.",
  done: "Arquivos salvos e resposta final pronta para o chat.",
  error: "A execucao retornou algo que precisa de correcao.",
};

function fileName(value) {
  return String(value || "").split(/[\\/]/).filter(Boolean).pop() || "";
}

function compactCommand(command = "") {
  const value = String(command).trim().replace(/^cd\s+[^&]+\s*&&\s*/, "");
  if (!value) return "vortax://workspace/projeto";
  if (/^openclaude\b/.test(value)) return "vortax://workspace/projeto";
  return value.length > 72 ? `${value.slice(0, 69)}...` : value;
}

function languageForFile(name = "") {
  const lower = name.toLowerCase();
  if (lower.endsWith(".jsx") || lower.endsWith(".tsx")) return "React";
  if (lower.endsWith(".js") || lower.endsWith(".ts")) return "JavaScript";
  if (lower.endsWith(".css") || lower.endsWith(".scss")) return "CSS";
  if (lower.endsWith(".html")) return "HTML";
  if (lower.endsWith(".py")) return "Python";
  if (lower.endsWith(".json")) return "JSON";
  if (lower.endsWith(".md")) return "Markdown";
  return "Codigo";
}

function normalizeFiles(files = []) {
  return files
    .map((item) => (typeof item === "string" ? item : item?.path || item?.name || ""))
    .filter(Boolean);
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

function isCodeAgentShell(event) {
  const command = String(event?.payload?.params?.command || "").trim();
  return /\bopenclaude\b/.test(command.replace(/^cd\s+[A-Za-z0-9_./-]+\s*&&\s*/, ""));
}

function latestPreview(events) {
  const frame = latestEvent(events, (event) => event.type === "screen_frame" && event.payload?.image_base64);
  const codeAgent = latestEvent(events, (event) => event.type === "vertex_progress");
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
  if (codeAgent) {
    candidates.push({
      createdAt: eventTime(codeAgent),
      file: codeAgent.payload?.file,
      label: publicText(codeAgent.payload?.message || "Vortax trabalhando"),
      mode: "editor",
      using: "Editor",
    });
  }
  if (shell) {
    candidates.push({
      createdAt: eventTime(shell),
      label: isCodeAgentShell(shell) ? "Vortax preparando o workspace" : publicText(shell.payload?.description || shell.payload?.params?.command || "Terminal"),
      mode: isCodeAgentShell(shell) ? "editor" : "terminal",
      using: isCodeAgentShell(shell) ? "Workspace" : "Terminal",
    });
  }

  if (candidates.length > 0) {
    return candidates.sort((a, b) => b.createdAt - a.createdAt)[0];
  }
  return { label: "Ambiente pronto", mode: "idle", using: "Computador" };
}

function framePreview(event, index) {
  const payload = event.payload || {};
  return {
    createdAt: eventTime(event),
    frameIndex: index,
    image: payload.image_base64,
    label: payload.caption || payload.title || "Navegador",
    mode: "browser",
    title: payload.title || "",
    url: payload.url || "",
    using: "Navegador",
  };
}

function screenFrameHistory(events) {
  return events
    .filter((event) => event.type === "screen_frame" && event.payload?.image_base64)
    .map(framePreview);
}

function ComputerPreview({ preview, snapshot }) {
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
      <small>{snapshot?.activeFile || fileName(preview.file) || preview.label}</small>
    </div>
  );
}

function CodingWorkspace({ snapshot }) {
  return (
    <div className="computer-coding-workspace">
      <div className="computer-ide-topbar">
        <div className="computer-window-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <span className="computer-ide-title">
          <Monitor size={13} />
          Computador do Vortax
        </span>
        <span className={`computer-ide-status ${snapshot.status === "done" ? "done" : "running"}`}>
          {snapshot.status === "done" ? "salvo" : "ao vivo"}
        </span>
      </div>
      <div className="computer-ide-body">
        <aside className="computer-file-tree">
          <div className="computer-file-tree-head">
            <FolderTree size={12} />
            projeto
          </div>
          {snapshot.files.map((path) => {
            const name = fileName(path);
            return (
              <span className={name === snapshot.activeFile ? "active" : ""} key={path}>
                <FileCode2 size={12} />
                {name}
              </span>
            );
          })}
        </aside>
        <main className="computer-code-editor">
          <div className="computer-editor-tabs">
            <span className="active">{snapshot.activeFile}</span>
            <small>{snapshot.language}</small>
          </div>
          <div className="computer-code-lines" aria-hidden="true">
            {snapshot.codeLines.map((line, index) => (
              <div key={`${line}-${index}`}>
                <em>{String(index + 1).padStart(2, "0")}</em>
                <span>{line}</span>
              </div>
            ))}
          </div>
        </main>
      </div>
      <div className="computer-editor-statusbar">
        <span>{snapshot.stageLabel}</span>
        <span>{snapshot.language}</span>
        <span>UTF-8</span>
        <span>Ln 84, Col 12</span>
      </div>
    </div>
  );
}

function ComputerStage({ preview, snapshot }) {
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
          {preview.query ? `https://duckduckgo.com/?q=${encodeURIComponent(preview.query)}` : "https://duckduckgo.com"}
        </div>
        <div className="computer-search-page">
          <div className="computer-search-logo">Web</div>
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
        {snapshot.command}
      </div>
      <CodingWorkspace snapshot={snapshot} />
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

function buildCodingSnapshot(events, preview) {
  const codeAgentEvents = events.filter((event) => event.type === "vertex_progress");
  const latestCodeAgent = codeAgentEvents[codeAgentEvents.length - 1]?.payload || {};
  const filesPayload = latestPayload(events, (event) => event.type === "files_created" && event.payload?.files?.length);
  const realFiles = normalizeFiles(latestCodeAgent.files?.length ? latestCodeAgent.files : filesPayload?.files || []);
  const lastShellCall = latestEvent(events, (event) => event.type === "tool_call" && event.payload?.name === "shell_run");
  const lastShellResult = latestEvent(events, (event) => event.type === "tool_result" && event.payload?.name === "shell_run");
  const hasCodingActivity = codeAgentEvents.length > 0 || Boolean(lastShellCall) || realFiles.length > 0;
  const activeFile = fileName(latestCodeAgent.file || realFiles[0]) || (hasCodingActivity ? "App.jsx" : "");
  const stage = hasCodingActivity ? latestCodeAgent.stage || "executing" : preview.mode || "idle";
  const validation = latestPayload(events, (event) =>
    event.type === "web_validation_result" || event.type === "project_validation_result"
  );
  const files = realFiles.length
    ? realFiles.slice(0, 5)
    : ["src/App.jsx", "src/index.css", "package.json", "README.md"];
  const status = latestCodeAgent.status || (lastShellResult ? "done" : lastShellCall ? "running" : "idle");
  const stageLabel = hasCodingActivity ? codeAgentStageLabels[stage] || "Programando" : preview.label || "Computador pronto";
  const stageDetail = publicText(latestCodeAgent.message
    || validation?.summary
    || validation?.reason
    || codeAgentStageDescriptions[stage]
    || "Acompanhando a sessao de desenvolvimento.");
  const command = hasCodingActivity ? compactCommand(lastShellCall?.payload?.params?.command) : "Computador do Vortax";

  const codeLines = [
    "const task = await vortax.readContext();",
    `workspace.open("${activeFile}")`,
    "applyChanges({ focused: true });",
    validation?.status === "failed" ? "fixVisualIssues(report);" : "runQualityCheck();",
    "saveWorkspace();",
  ];

  return {
    activeFile,
    command,
    files,
    hasCodingActivity,
    language: languageForFile(activeFile),
    stage,
    stageDetail,
    stageLabel,
    status,
    codeLines,
  };
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

function buildCodeAgentProgress(events, agentStatus) {
  const codeAgentEvents = events.filter((event) => event.type === "vertex_progress");
  const latestCodeAgent = codeAgentEvents[codeAgentEvents.length - 1]?.payload || null;
  const delegated = events.some((event) =>
    event.type === "ai_exchange"
    && event.payload?.actor === "deepseek"
    && (event.payload?.target === "openclaude" || event.payload?.target === "vertex")
  );
  const shellCodeAgent = latestEvent(events, (event) => event.type === "tool_call" && event.payload?.name === "shell_run" && isCodeAgentShell(event));
  const active = delegated || shellCodeAgent || codeAgentEvents.length > 0;
  if (!active) return null;

  const done = latestCodeAgent?.status === "done" || latestCodeAgent?.stage === "done";
  const filesPayload = latestPayload(events, (event) => event.type === "files_created" && event.payload?.files?.length);
  const files = filesPayload?.files || latestCodeAgent?.files || [];
  const fileName = latestCodeAgent?.file || files[0]?.path || files[0]?.name || "";
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
  const hasWriting = codeAgentEvents.some((event) =>
    ["writing_file", "creating", "editing", "installing", "executing", "configuring"].includes(event.payload?.stage)
  ) || files.length > 0;
  const hasPlanning = codeAgentEvents.some((event) =>
    ["starting", "planning"].includes(event.payload?.stage)
  ) || delegated || shellCodeAgent;
  const terminal = ["done", "stopped", "error", "idle"].includes(agentStatus) || done;

  const steps = [
    progressStep(
      "vortax-prepare",
      "Preparar execução",
      "Vortax organizou a parte tecnica no workspace.",
      phaseStatus(active, hasPlanning || hasWriting || done),
    ),
    progressStep(
      "vortax-plan",
      "Planejar projeto",
      latestCodeAgent?.stage === "planning" ? publicText(latestCodeAgent.message) : "Definir estrutura, arquivos e criterios de entrega.",
      phaseStatus(hasPlanning, hasWriting || validationStarted || done),
    ),
    progressStep(
      "vortax-write",
      "Criar arquivos",
      fileName ? `Trabalhando em ${String(fileName).split("/").pop()}.` : files.length ? `${files.length} arquivo(s) sincronizados.` : publicText(latestCodeAgent?.message || "Escrever e ajustar a entrega."),
      phaseStatus(hasWriting, files.length > 0 || validationStarted || done),
    ),
    progressStep(
      "vortax-validate",
      "Validar entrega",
      validationResult?.reason || validationResult?.summary || (validationStarted ? "Revisao automatica em andamento." : "Aguardar revisao automatica do Vortax."),
      phaseStatus(validationStarted, validationDone, validationFailed),
    ),
    progressStep(
      "vortax-return",
      "Devolver resultado",
      done ? publicText(latestCodeAgent?.message || "Vortax terminou a entrega.") : "A resposta final sera montada apos a revisao.",
      phaseStatus(done, done),
    ),
  ];

  return {
    doneCount: steps.filter((step) => step.status === "passed").length,
    steps: visibleProgressSteps(steps, terminal),
    title: "Trabalho do Vortax",
    totalCount: steps.length,
  };
}

export function VortaxComputerDock({ activeTask, agentStatus, connectionState, events, livePlan, onOpenDetails }) {
  const [expanded, setExpanded] = useState(false);
  const busy = ["queued", "thinking", "executing", "running"].includes(agentStatus);
  const now = useNow(busy);
  const latestUserEventIndex = useMemo(() => {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      if (events[index].type === "user_message") return index;
    }
    return -1;
  }, [events]);
  const promptEvents = useMemo(
    () => (latestUserEventIndex >= 0 ? events.slice(latestUserEventIndex + 1) : events),
    [events, latestUserEventIndex],
  );
  const frameHistory = useMemo(() => screenFrameHistory(promptEvents), [promptEvents]);
  const livePreview = useMemo(() => latestPreview(promptEvents), [promptEvents]);
  const preview = livePreview;
  const codingSnapshot = useMemo(() => buildCodingSnapshot(promptEvents, preview), [promptEvents, preview]);
  const codeAgentProgress = useMemo(() => buildCodeAgentProgress(promptEvents, agentStatus), [agentStatus, promptEvents]);
  const firstEvent = events[latestUserEventIndex]
    || promptEvents.find((event) => event.type === "user_message" || event.type === "task_created")
    || events.find((event) => event.type === "user_message" || event.type === "task_created");
  const elapsed = formatElapsed(firstEvent?.created_at || activeTask?.created_at, now);
  const planningFallbackSteps = busy && livePlan.isGeneratingPlan
    ? [
      progressStep(
        "instant-plan",
        "Criar plano de tarefas",
        "Organizando os passos antes de executar.",
        "running",
      ),
      progressStep(
        "instant-context",
        "Preparar contexto",
        "Separando arquivos, ferramentas e validacoes provaveis.",
        "pending",
      ),
      progressStep(
        "instant-run",
        "Executar trabalho",
        "O progresso detalhado entra aqui assim que o Vortax comecar.",
        "pending",
      ),
    ]
    : [];
  const planSteps = livePlan.visibleSteps?.length ? livePlan.visibleSteps : livePlan.steps || [];
  const progressSteps = codeAgentProgress?.steps || (planSteps.length ? planSteps : planningFallbackSteps);
  const progressTotal = codeAgentProgress?.totalCount || livePlan.totalCount || planningFallbackSteps.length || 0;
  const progressDone = codeAgentProgress?.doneCount || livePlan.doneCount || 0;
  const total = progressTotal || livePlan.totalCount || 0;
  const done = progressDone || livePlan.doneCount || 0;
  const terminalLabel = agentStatus === "done"
    ? "Pedido concluido"
    : agentStatus === "error"
      ? "Ajuste necessario"
      : agentStatus === "stopped"
        ? "Tarefa interrompida"
        : "";
  const current = terminalLabel
    || (codingSnapshot.hasCodingActivity ? codingSnapshot.stageLabel : "")
    || livePlan.currentStep?.label
    || (busy ? "Criando plano de tarefas" : "")
    || preview.label
    || activeTask?.description
    || "Computador do Vortax";
  const hasDockContent = Boolean(codeAgentProgress)
    || (livePlan.hasSteps && !livePlan.isDirect)
    || codingSnapshot.hasCodingActivity
    || frameHistory.length > 0;

  if (!hasDockContent) return null;

  return (
    <section className={`vortax-computer-dock ${expanded ? "expanded" : ""}`}>
      <div className="computer-dock-bar">
        <button className="computer-dock-toggle" onClick={() => setExpanded((value) => !value)} type="button">
          <ComputerPreview preview={preview} snapshot={codingSnapshot} />
          <div className="computer-dock-main">
            <div>
              <span className="computer-live-dot" />
              <strong>Computador do Vortax</strong>
            </div>
            <small>{elapsed ? `${elapsed} · ` : ""}{current} · {statusLabel(agentStatus)} · {connectionState}</small>
          </div>
          <span className="computer-dock-count">{done}/{total || 1}</span>
          <ChevronDown className="computer-dock-chevron" size={16} />
        </button>
        <button
          className="computer-dock-detail-btn"
          onClick={onOpenDetails}
          title="Abrir detalhes tecnicos"
          type="button"
        >
          <PanelRightOpen size={16} />
        </button>
      </div>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            className="computer-dock-inline-panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            <div className="computer-dock-inline-meta">
              {preview.mode === "search" || preview.mode === "browser" ? <Globe2 size={14} /> : <Monitor size={14} />}
              <span>
                {preview.image
                  ? "Tela real do navegador disponivel nos detalhes."
                  : preview.mode === "search" || preview.mode === "browser"
                    ? `Vortax esta usando o ${preview.using}.`
                    : codingSnapshot.stageDetail}
              </span>
            </div>
            <div className="computer-progress-card">
              <div className="computer-progress-head">
                <strong>{codeAgentProgress?.title || "Progresso da tarefa"}</strong>
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
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
