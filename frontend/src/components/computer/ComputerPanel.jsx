import { memo, useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { AppWindow, ChevronDown, ChevronLeft, ChevronRight, FolderOpen, Globe2, History, ListChecks, SquareTerminal, Undo2, WifiOff, X } from "lucide-react";

import { planStepStatus } from "../../hooks/useLiveTaskPlan.js";
import { formatClock, publicText } from "../../lib/text.js";
import { BrowserSurface } from "../BrowserSurface.jsx";
import { StatusIndicator } from "../StatusIndicator.jsx";
import { FilesPane } from "./FilesPane.jsx";
import { PreviewPane } from "./PreviewPane.jsx";
import { TerminalPane } from "./TerminalPane.jsx";

export const PANE_LABELS = { browser: "Navegador", files: "Arquivos", preview: "Preview", terminal: "Terminal" };
const PANE_ICONS = { browser: Globe2, files: FolderOpen, preview: AppWindow, terminal: SquareTerminal };
const OFFLINE_STATES = { closed: "desconectado", error: "falha na conexão", offline: "sem internet", paused: "conexão pausada", reconnecting: "reconectando" };

function FrameControls({ computer }) {
  const { frameCount, frameIndex, frames } = computer.browser;
  if (frameCount <= 1) return null;
  const current = frameIndex ?? frameCount - 1;
  const atLatest = !computer.isHistory || current >= frameCount - 1;
  return (
    <div className="vx-frames" role="group" aria-label="Histórico do navegador">
      <button aria-label="Registro anterior" className="vx-icon-btn" disabled={current <= 0} onClick={() => computer.selectFrame(current - 1)} type="button"><ChevronLeft size={15} /></button>
      <input
        aria-label="Navegar pelo histórico do navegador"
        aria-valuetext={`Registro ${current + 1} de ${frameCount}, ${formatClock(frames[current]?.capturedAt)}`}
        max={frameCount - 1}
        min={0}
        onChange={(event) => computer.selectFrame(Number(event.target.value))}
        type="range"
        value={current}
      />
      <button aria-label="Próximo registro" className="vx-icon-btn" disabled={current >= frameCount - 1} onClick={() => computer.selectFrame(current + 1)} type="button"><ChevronRight size={15} /></button>
      <span className="vx-frames__pos">{current + 1}/{frameCount}</span>
      <span className="vx-frames__time">{formatClock(frames[current]?.capturedAt)}</span>
      {atLatest ? null : <span className="vx-chip vx-chip--history">histórico</span>}
    </div>
  );
}

function PlanSection({ plan, agentStatus }) {
  const [open, setOpen] = useState(false);
  const steps = plan?.steps || [];
  if (!plan?.hasSteps || plan.isDirect || !steps.length) return null;
  return (
    <section className={`vx-plan ${open ? "is-open" : ""}`}>
      <button aria-expanded={open} className="vx-plan__toggle" onClick={() => setOpen((value) => !value)} type="button">
        <ListChecks aria-hidden="true" size={14} />
        <strong>Plano</strong>
        <span title="Conta apenas as etapas do plano">{plan.doneCount}/{plan.totalCount} etapas concluídas</span>
        <ChevronDown aria-hidden="true" className="vx-plan__chevron" size={14} />
      </button>
      {open ? (
        <ol className="vx-plan__list">
          {steps.map((step) => {
            const status = planStepStatus(step, plan, agentStatus);
            return (
              <li key={step.id}>
                <StatusIndicator size={13} status={status} />
                <span>{publicText(step.label)}</span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}

function paneAvailability(pane, computer, files) {
  if (pane === "browser") return computer.browser.frameCount;
  if (pane === "files") return files.length;
  if (pane === "terminal") return computer.terminal.entries.length;
  return computer.preview.entry ? 1 : 0;
}

export const ComputerPanel = memo(function ComputerPanel({
  activity,
  agentStatus,
  computer,
  connectionState,
  files,
  onClose,
  overlay,
  plan,
  taskId,
}) {
  const reduced = useReducedMotion();
  const closeRef = useRef(null);
  const { headline, pane } = computer;
  const offline = OFFLINE_STATES[connectionState];
  const busy = ["running", "paused", "waiting"].includes(computer.latestTurn?.status);
  const liveActionPane = computer.liveAction && ["running", "paused"].includes(computer.liveAction.status) ? computer.liveAction.pane : null;
  const preparingPreview = busy && (computer.latestTurn?.actions || []).some((action) => action.family === "file" && /\.html?$/i.test(action.target?.value || ""));

  useEffect(() => {
    if (!overlay) return undefined;
    closeRef.current?.focus();
    const onKey = (event) => {
      if (event.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, overlay]);

  let body = null;
  if (pane === "browser") {
    body = (
      <>
        <BrowserSurface
          active={computer.browser.active}
          connectionState={connectionState}
          isHistory={computer.isHistory}
          scene={computer.browser.scene}
          stale={computer.browser.stale}
          waitingAction={computer.browser.waitingAction}
        />
        <FrameControls computer={computer} />
      </>
    );
  } else if (pane === "files") {
    body = <FilesPane actions={activity.actions} computer={computer} files={files} latestTurn={computer.latestTurn} taskId={taskId} />;
  } else if (pane === "terminal") {
    body = <TerminalPane computer={computer} />;
  } else {
    body = <PreviewPane entry={computer.preview.entry} files={files} preparing={preparingPreview} taskId={taskId} />;
  }

  const selected = computer.selectedAction;
  return (
    <motion.aside
      animate={{ opacity: 1, x: 0 }}
      aria-label="Computador do Vortax"
      aria-modal={overlay ? "true" : undefined}
      className={`vx-computer ${overlay ? "is-overlay" : "is-docked"}`}
      exit={{ opacity: 0, x: reduced ? 0 : 24 }}
      initial={{ opacity: 0, x: reduced ? 0 : 24 }}
      role={overlay ? "dialog" : "complementary"}
      transition={{ duration: reduced ? 0 : 0.22, ease: [0.2, 0.7, 0.2, 1] }}
    >
      <header className="vx-computer__head">
        <div className="vx-computer__title">
          <strong>Computador do Vortax</strong>
          <span>
            <StatusIndicator size={12} status={headline.status} />
            <span className="vx-computer__headline">{headline.title}</span>
            {offline ? <em className="vx-computer__offline"><WifiOff aria-hidden="true" size={12} /> {offline}</em> : null}
          </span>
        </div>
        <button aria-label="Fechar o Computador do Vortax" className="vx-icon-btn" onClick={onClose} ref={closeRef} title="Fechar" type="button"><X size={17} /></button>
      </header>

      <div aria-label="Ambiente de trabalho" className="vx-tabs" role="tablist">
        {["browser", "files", "terminal", "preview"].map((key) => {
          const Icon = PANE_ICONS[key];
          const count = paneAvailability(key, computer, files);
          return (
            <button aria-selected={pane === key} className={`vx-tab ${pane === key ? "is-active" : ""}`} key={key} onClick={() => computer.selectPane(key)} role="tab" type="button">
              <Icon aria-hidden="true" size={14} />
              <span>{PANE_LABELS[key]}</span>
              {liveActionPane === key ? <span aria-label="em uso agora" className="vx-dot is-live" /> : count ? <em>{key === "preview" ? "" : count}</em> : null}
            </button>
          );
        })}
        {!computer.following && !computer.isHistory ? (
          <button className="vx-follow" onClick={computer.goLive} type="button"><Undo2 size={13} /> Seguir o agente</button>
        ) : null}
      </div>

      {computer.isHistory ? (
        <div className="vx-history-banner" role="status">
          <History aria-hidden="true" size={14} />
          <span>
            Histórico{selected ? `: ${selected.title}` : ""} · {formatClock(selected?.startedAt || computer.browser.scene?.capturedAt)}
          </span>
          <button onClick={computer.goLive} type="button">Voltar à atividade atual</button>
        </div>
      ) : null}

      <div className={`vx-computer__body vx-computer__body--${pane}`} key={pane}>
        {body}
      </div>

      <PlanSection agentStatus={agentStatus} plan={plan} />
    </motion.aside>
  );
});
