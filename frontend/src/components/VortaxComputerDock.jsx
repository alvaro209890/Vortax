import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Check,
  Circle,
  Code2,
  FileCode2,
  FolderTree,
  Globe2,
  Loader2,
  Monitor,
  PanelRightOpen,
  RotateCcw,
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

function useElapsedTimer(busy, startTime) {
  const [now, setNow] = useState(Date.now());
  const [frozenElapsed, setFrozenElapsed] = useState("");
  const startRef = useRef(null);
  startRef.current = startTime;
  const wasBusyRef = useRef(false);

  useEffect(() => {
    if (busy) {
      wasBusyRef.current = true;
      setFrozenElapsed("");
      const timer = setInterval(() => setNow(Date.now()), 1000);
      return () => clearInterval(timer);
    }
    if (wasBusyRef.current) {
      setFrozenElapsed(formatElapsed(startRef.current, Date.now()));
      wasBusyRef.current = false;
    }
    return undefined;
  }, [busy]);

  const liveElapsed = useMemo(() => formatElapsed(startRef.current, now), [now]);

  return busy ? liveElapsed : frozenElapsed;
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
    const latest = candidates.sort((a, b) => b.createdAt - a.createdAt)[0];
    if (frame && latest.mode === "browser" && !latest.image) {
      return {
        ...latest,
        image: frame.payload.image_base64,
        label: latest.label || frame.payload.caption || frame.payload.title || "Navegador",
        title: latest.title || frame.payload.title || "",
        url: latest.url || frame.payload.url || "",
      };
    }
    return latest;
  }
  return { label: "Ambiente pronto", mode: "idle", using: "Computador" };
}

function framePreview(event, frameIndex, eventIndex = frameIndex) {
  const payload = event.payload || {};
  return {
    createdAt: eventTime(event),
    eventIndex,
    frameIndex,
    image: payload.image_base64,
    label: payload.caption || payload.title || "Navegador",
    mode: "browser",
    title: payload.title || "",
    url: payload.url || "",
    using: "Navegador",
  };
}

function screenFrameHistory(events, eventIndexOffset = 0) {
  return events
    .map((event, eventIndex) => ({ event, eventIndex }))
    .filter(({ event }) => event.type === "screen_frame" && event.payload?.image_base64)
    .map(({ event, eventIndex }, frameIndex) => framePreview(event, frameIndex, eventIndex + eventIndexOffset));
}

const BrowserFrame = memo(function BrowserFrame({ image }) {
  const [display, setDisplay] = useState({ prev: null, curr: image, seq: 0 });
  const currRef = useRef(image);
  const tidRef = useRef(null);

  useEffect(() => {
    if (!image || image === currRef.current) return;
    clearTimeout(tidRef.current);
    const prevImg = currRef.current;
    currRef.current = image;
    setDisplay((d) => ({ prev: prevImg, curr: image, seq: d.seq + 1 }));
    tidRef.current = setTimeout(() => setDisplay((d) => ({ ...d, prev: null })), 280);
  }, [image]);

  useEffect(() => () => clearTimeout(tidRef.current), []);

  return (
    <div className="browser-frame-wrap">
      {display.prev && (
        <img aria-hidden="true" className="browser-frame-prev" src={`data:image/jpeg;base64,${display.prev}`} />
      )}
      <img
        alt="Tela ao vivo"
        className="browser-frame-curr"
        key={display.seq}
        src={`data:image/jpeg;base64,${display.curr}`}
      />
    </div>
  );
});

const ComputerPreview = memo(function ComputerPreview({ preview, snapshot }) {
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
});

const CodingWorkspace = memo(function CodingWorkspace({ snapshot }) {
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
});

const ComputerStage = memo(function ComputerStage({ preview, snapshot }) {
  if (preview.image) {
    return (
      <div className="computer-stage browser-live">
        <div className="computer-stage-address">{preview.url || preview.title || "Tela ao vivo"}</div>
        <BrowserFrame image={preview.image} />
      </div>
    );
  }

  if (preview.mode === "browser") {
    return (
      <div className="computer-stage browser-live">
        <div className="computer-stage-address">{preview.url || preview.title || preview.label || "Navegador"}</div>
        <div className="computer-browser-placeholder">
          <Globe2 size={28} />
          <strong>{preview.title || "Aguardando captura da tela"}</strong>
          <span>{preview.url || preview.label || "O proximo print do navegador aparece aqui."}</span>
        </div>
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
});

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

function focusToolKind(name = "") {
  if (name === "browser_google_search") return "search";
  if (name?.startsWith("browser_")) return "browser";
  if (name === "shell_run") return "code";
  return "analysis";
}

function focusEventPreview(event, activity, fallbackPreview) {
  const payload = event?.payload || {};
  const metadata = activity?.metadata || {};
  const tool = activity?.tool || payload.name || "";
  const kind = activity?.kind || focusToolKind(tool);

  if (event?.type === "screen_frame" && payload.image_base64) {
    return framePreview(event, 0, activity?.eventIndex);
  }

  if (kind === "search" || tool === "browser_google_search") {
    const params = payload.params || {};
    const result = payload.result || {};
    const query = metadata.query || params.query || result.query || activity?.detail || "";
    return {
      createdAt: eventTime(event),
      label: query ? `Pesquisando: ${query}` : activity?.title || "Pesquisando na web",
      mode: "search",
      query,
      title: activity?.title || "Pesquisa",
      url: query ? `https://duckduckgo.com/?q=${encodeURIComponent(query)}` : "",
      using: "Navegador",
    };
  }

  if (kind === "source" || kind === "browser") {
    const params = payload.params || {};
    const result = payload.result || {};
    const url = metadata.url || params.url || result.url || result.opened?.href || "";
    const title = metadata.source_title || metadata.title || result.title || result.opened?.title || activity?.title || "Navegador";
    return {
      createdAt: eventTime(event),
      label: activity?.detail || title || "Navegando na web",
      mode: "browser",
      title,
      url,
      using: "Navegador",
    };
  }

  if (kind === "code" || kind === "file") {
    return {
      createdAt: eventTime(event),
      file: metadata.file || payload.file,
      label: activity?.detail || activity?.title || "Vortax trabalhando no workspace",
      mode: "editor",
      title: activity?.title || "Editor",
      using: "Editor",
    };
  }

  return fallbackPreview;
}

function focusSnapshot(snapshot, focusRequest) {
  const activity = focusRequest?.activity || {};
  const event = focusRequest?.event || {};
  const payload = event.payload || {};
  const metadata = activity.metadata || {};
  const focusedFile = fileName(metadata.file || payload.file || metadata.files?.[0]?.path || metadata.files?.[0]?.name || snapshot.activeFile);
  const command = event.type === "tool_call" && payload.name === "shell_run"
    ? compactCommand(payload.params?.command)
    : snapshot.command;

  return {
    ...snapshot,
    activeFile: focusedFile || snapshot.activeFile,
    command,
    stageDetail: publicText(activity.detail || payload.message || snapshot.stageDetail),
    stageLabel: publicText(activity.title || snapshot.stageLabel),
    status: activity.status === "done" ? "done" : activity.status === "failed" ? "error" : snapshot.status,
    codeLines: [
      `// ${publicText(activity.title || "Vortax trabalhando")}`,
      focusedFile ? `workspace.open("${focusedFile}")` : "workspace.focusCurrentTask();",
      activity.detail ? `note("${publicText(activity.detail).slice(0, 60)}");` : "inspectCurrentContext();",
      "syncComputerScene();",
      "reportProgressToChat();",
    ],
  };
}

function nearestFrameIndex(frameHistory, targetTime) {
  if (!frameHistory.length || !targetTime) return null;
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  frameHistory.forEach((frame, index) => {
    const distance = Math.abs(frame.createdAt - targetTime);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function focusSceneFromRequest(focusRequest, frameHistory, preview, snapshot) {
  if (!focusRequest) return null;
  const event = focusRequest.event || {};
  const activity = focusRequest.activity || {};
  const targetTime = eventTime(event);
  const browserLike = ["screen_frame", "source_saved"].includes(event.type)
    || ["search", "source", "browser"].includes(activity.kind)
    || String(activity.tool || "").startsWith("browser_");
  const exactFrameIndex = frameHistory.findIndex((frame) => (
    frame.eventIndex === focusRequest.eventIndex
    || (event.type === "screen_frame" && frame.createdAt === targetTime)
  ));
  const frameIndex = exactFrameIndex >= 0
    ? exactFrameIndex
    : browserLike ? nearestFrameIndex(frameHistory, targetTime) : null;

  return {
    activity,
    frameIndex,
    preview: frameIndex === null ? focusEventPreview(event, activity, preview) : null,
    requestId: focusRequest.requestId,
    snapshot: focusSnapshot(snapshot, focusRequest),
  };
}

const ComputerProgressCard = memo(function ComputerProgressCard({ agentStatus, elapsed, progressDone, progressSteps, progressTitle, progressTotal }) {
  return (
    <div className="computer-progress-card">
      <div className="computer-progress-head">
        <strong>{progressTitle || "Progresso da tarefa"}</strong>
        <span>{progressDone}/{progressTotal || 1}</span>
      </div>
      <div className="computer-progress-list">
        <AnimatePresence initial={false}>
          {progressSteps.length > 0 ? (
            progressSteps.map((step, index) => (
              <motion.div
                className={`computer-progress-step ${step.state}`}
                key={step.id}
                initial={{ opacity: 0, y: -10, height: 0 }}
                animate={{ opacity: 1, y: 0, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.22, ease: "easeOut", delay: index * 0.04 }}
              >
                <span>{stepIcon(step)}</span>
                <div>
                  <strong>{step.label}</strong>
                  <small>{step.detail || (step.status === "running" ? `${elapsed ? `${elapsed} · ` : ""}${statusLabel(agentStatus)}` : "")}</small>
                </div>
              </motion.div>
            ))
          ) : (
            <motion.div
              className="computer-progress-step running"
              key="preparing"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
            >
              <span><Code2 size={13} /></span>
              <div>
                <strong>Preparando trabalho</strong>
                <small>O progresso aparece aqui.</small>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
});

const ComputerLiveControls = memo(function ComputerLiveControls({ activeFrameIndex, frameCount, isLive, onFrameChange, onJumpLive, onNextFrame, onPrevFrame }) {
  if (frameCount <= 0) return null;

  return (
    <div className="computer-live-controls">
      <div className="computer-frame-controls">
        <button disabled={activeFrameIndex <= 0} onClick={onPrevFrame} title="Frame anterior" type="button">
          <ChevronLeft size={15} />
        </button>
        <button disabled={isLive || activeFrameIndex >= frameCount - 1} onClick={onNextFrame} title="Próximo frame" type="button">
          <ChevronRight size={15} />
        </button>
      </div>
      <input
        aria-label="Navegar pelo histórico da tela"
        className="computer-frame-range"
        max={Math.max(frameCount - 1, 0)}
        min="0"
        onChange={(event) => onFrameChange(Number(event.target.value))}
        type="range"
        value={activeFrameIndex}
      />
      <span className={`computer-live-state ${isLive ? "live" : "replay"}`}>
        <Circle size={9} />
        {isLive ? "ao vivo" : `${activeFrameIndex + 1}/${frameCount}`}
      </span>
      <button className="computer-jump-live-btn" disabled={isLive} onClick={onJumpLive} type="button">
        <RotateCcw size={13} />
        Ao vivo
      </button>
    </div>
  );
});

const ComputerSidePanel = memo(function ComputerSidePanel({
  agentStatus,
  focusScene,
  connectionState,
  current,
  elapsed,
  frameHistory,
  onClose,
  preview,
  progressDone,
  progressSteps,
  progressTitle,
  progressTotal,
  snapshot,
}) {
  const [selectedFrameIndex, setSelectedFrameIndex] = useState(null);
  const [sceneOverride, setSceneOverride] = useState(null);
  const [activityOverride, setActivityOverride] = useState(null);
  const [snapshotOverride, setSnapshotOverride] = useState(null);

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    setSelectedFrameIndex((index) => {
      if (index === null) return null;
      if (frameHistory.length === 0) return null;
      return Math.min(index, frameHistory.length - 1);
    });
  }, [frameHistory.length]);

  useEffect(() => {
    if (!focusScene) return;
    setActivityOverride(focusScene.activity || null);
    setSnapshotOverride(focusScene.snapshot || null);
    if (focusScene.frameIndex !== null && focusScene.frameIndex !== undefined) {
      setSelectedFrameIndex(focusScene.frameIndex);
      setSceneOverride(null);
      return;
    }
    setSelectedFrameIndex(null);
    setSceneOverride(focusScene.preview || null);
  }, [focusScene?.requestId]);

  const frameCount = frameHistory.length;
  const isLive = selectedFrameIndex === null && !sceneOverride;
  const activeFrameIndex = selectedFrameIndex ?? Math.max(frameCount - 1, 0);
  const selectedFrame = selectedFrameIndex !== null && frameCount > 0 ? frameHistory[activeFrameIndex] : null;
  const visiblePreview = selectedFrame || sceneOverride || preview;
  const visibleSnapshot = snapshotOverride || snapshot;
  const visibleActivity = activityOverride || {
    detail: visiblePreview.label || current,
    kind: visiblePreview.mode || "analysis",
    status: isLive ? "running" : "done",
    title: isLive ? "Tela ao vivo" : "Cena selecionada",
    tool: visiblePreview.using || "",
  };

  const handlePrevFrame = () => {
    setSceneOverride(null);
    setSelectedFrameIndex((index) => Math.max((index ?? frameCount - 1) - 1, 0));
  };

  const handleNextFrame = () => {
    setSceneOverride(null);
    setSelectedFrameIndex((index) => {
      const nextIndex = Math.min((index ?? frameCount - 1) + 1, frameCount - 1);
      return nextIndex >= frameCount - 1 ? null : nextIndex;
    });
  };

  return (
    <>
      <motion.button
        aria-label="Fechar computador do Vortax"
        className="computer-side-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        type="button"
      />
      <motion.aside
        aria-label="Computador do Vortax"
        aria-modal="true"
        className="computer-side-panel"
        initial={{ x: 420, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 420, opacity: 0 }}
        role="dialog"
        transition={{ type: "spring", stiffness: 380, damping: 38 }}
      >
        <header className="computer-side-header">
          <div>
            <strong>Computador do Vortax</strong>
            <span>
              {visiblePreview.mode === "search" || visiblePreview.mode === "browser" ? <Globe2 size={13} /> : <Monitor size={13} />}
              {elapsed ? `${elapsed} · ` : ""}{current} · {statusLabel(agentStatus)} · {connectionState}
            </span>
          </div>
          <div className="computer-side-actions">
            <button onClick={onClose} title="Fechar computador" type="button">
              <X size={18} />
            </button>
          </div>
        </header>

        <div className={`computer-side-context ${visibleActivity.kind || "analysis"} ${visibleActivity.status || "running"}`}>
          <span>{visibleActivity.status === "running" ? <Loader2 size={14} /> : stepIcon({ status: visibleActivity.status === "done" ? "passed" : visibleActivity.status })}</span>
          <div>
            <strong>{visibleActivity.title || "Atividade do Vortax"}</strong>
            <small>{visibleActivity.detail || visibleActivity.tool || "Acompanhando a execução."}</small>
          </div>
          {visibleActivity.tool ? <em>{visibleActivity.tool}</em> : null}
        </div>

        <ComputerStage preview={visiblePreview} snapshot={visibleSnapshot} />

        <ComputerLiveControls
          activeFrameIndex={activeFrameIndex}
          frameCount={frameCount}
          isLive={isLive}
          onFrameChange={(index) => {
            setSceneOverride(null);
            setActivityOverride(null);
            setSnapshotOverride(null);
            setSelectedFrameIndex(index);
          }}
          onJumpLive={() => {
            setSelectedFrameIndex(null);
            setSceneOverride(null);
            setActivityOverride(null);
            setSnapshotOverride(null);
          }}
          onNextFrame={handleNextFrame}
          onPrevFrame={handlePrevFrame}
        />

        <div className="computer-side-progress">
          <ComputerProgressCard
            agentStatus={agentStatus}
            elapsed={elapsed}
            progressDone={progressDone}
            progressSteps={progressSteps}
            progressTitle={progressTitle}
            progressTotal={progressTotal}
          />
        </div>
      </motion.aside>
    </>
  );
});

export const VortaxComputerDock = memo(function VortaxComputerDock({ activeTask, agentStatus, connectionState, events, focusRequest, livePlan, onOpenDetails }) {
  const [expanded, setExpanded] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const busy = ["queued", "thinking", "executing", "running"].includes(agentStatus);
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
  const firstEvent = events[latestUserEventIndex]
    || promptEvents.find((event) => event.type === "user_message" || event.type === "task_created")
    || events.find((event) => event.type === "user_message" || event.type === "task_created");
  const elapsed = useElapsedTimer(busy, firstEvent?.created_at || activeTask?.created_at);
  const frameHistory = useMemo(() => screenFrameHistory(events), [events]);
  const livePreview = useMemo(() => latestPreview(promptEvents), [promptEvents]);
  const preview = livePreview;
  const codingSnapshot = useMemo(() => buildCodingSnapshot(promptEvents, preview), [promptEvents, preview]);
  const focusScene = useMemo(
    () => focusSceneFromRequest(focusRequest, frameHistory, preview, codingSnapshot),
    [codingSnapshot, focusRequest, frameHistory, preview],
  );
  const codeAgentProgress = useMemo(() => buildCodeAgentProgress(promptEvents, agentStatus), [agentStatus, promptEvents]);
  const noWorkEventsYet = promptEvents.length === 0;
  const planningFallbackSteps = busy && (livePlan.isGeneratingPlan || noWorkEventsYet)
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
    || frameHistory.length > 0
    || Boolean(focusRequest)
    || promptEvents.some((event) => ["agent_activity", "agent_progress", "tool_call", "tool_result", "source_saved"].includes(event.type));

  const handleOpenSide = useCallback(() => setSideOpen(true), []);
  const handleCloseSide = useCallback(() => setSideOpen(false), []);
  const handleToggleExpand = useCallback(() => setExpanded((value) => !value), []);

  useEffect(() => {
    if (focusRequest) setSideOpen(true);
  }, [focusRequest]);

  if (!hasDockContent) return null;

  return (
    <section className={`vortax-computer-dock ${expanded ? "expanded" : ""}`}>
      <div className="computer-dock-bar">
        <button
          aria-label="Ver o computador do Vortax"
          className="computer-dock-open"
          data-tooltip="Ver o computador do Vortax"
          onClick={handleOpenSide}
          type="button"
        >
          <ComputerPreview preview={preview} snapshot={codingSnapshot} />
          <div className="computer-dock-main">
            <div>
              <span className="computer-live-dot" />
              <strong>Computador do Vortax</strong>
            </div>
            <small>{elapsed ? `${elapsed} · ` : ""}{current} · {statusLabel(agentStatus)} · {connectionState}</small>
          </div>
          <span className="computer-dock-count">{done}/{total || 1}</span>
        </button>
        <button
          aria-expanded={expanded}
          className="computer-dock-toggle"
          onClick={handleToggleExpand}
          title={expanded ? "Recolher progresso" : "Mostrar progresso"}
          type="button"
        >
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
            <ComputerProgressCard
              agentStatus={agentStatus}
              elapsed={elapsed}
              progressDone={progressDone}
              progressSteps={progressSteps}
              progressTitle={codeAgentProgress?.title || "Progresso da tarefa"}
              progressTotal={progressTotal}
            />
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {sideOpen && (
          <ComputerSidePanel
            agentStatus={agentStatus}
            connectionState={connectionState}
            current={current}
            elapsed={elapsed}
            focusScene={focusScene}
            frameHistory={frameHistory}
            key="computer-side-panel"
            onClose={handleCloseSide}
            preview={preview}
            progressDone={progressDone}
            progressSteps={progressSteps}
            progressTitle={codeAgentProgress?.title || "Progresso da tarefa"}
            progressTotal={progressTotal}
            snapshot={codingSnapshot}
          />
        )}
      </AnimatePresence>
    </section>
  );
});
