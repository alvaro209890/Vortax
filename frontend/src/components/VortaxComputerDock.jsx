import { memo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AppWindow, ChevronDown, FileCode2, PanelRightOpen, SquareTerminal } from "lucide-react";

import { planStepStatus } from "../hooks/useLiveTaskPlan.js";
import { SCENE_SOURCE_LABELS } from "../lib/browserScenes.js";
import { clip, formatClock, hostOf, publicText, shortPath } from "../lib/text.js";
import { BrowserThumb } from "./BrowserSurface.jsx";
import { PANE_LABELS } from "./computer/ComputerPanel.jsx";
import { StatusIndicator } from "./StatusIndicator.jsx";

const CONNECTION_LABELS = { closed: "desconectado", error: "falha na conexão", offline: "sem internet", paused: "conexão pausada", reconnecting: "reconectando" };

// Descrição curta da cena que o painel expandido mostra agora.
function sceneLine(computer) {
  const { pane } = computer;
  if (pane === "browser") {
    const scene = computer.browser.scene;
    if (!scene) return computer.browser.waitingAction ? computer.browser.waitingAction.title : "nenhuma página ainda";
    const name = scene.title || hostOf(scene.url) || scene.view?.query || "página";
    return `${clip(name, 36)} · ${SCENE_SOURCE_LABELS[scene.source].toLowerCase()} ${formatClock(scene.capturedAt)}`;
  }
  if (pane === "files") {
    const { path, pendingAction, snapshotAction } = computer.files;
    if (!path) return "nenhum arquivo";
    if (pendingAction) return `${shortPath(path, 32)} · aguardando gravação`;
    if (snapshotAction) return `${shortPath(path, 32)} · registro de ${formatClock(snapshotAction.startedAt)}`;
    return `${shortPath(path, 32)} · versão atual`;
  }
  if (pane === "terminal") {
    const action = computer.terminal.action;
    return action ? clip(action.target?.value || action.title, 44) : "nenhum comando";
  }
  return computer.preview.entry ? `preview · ${computer.preview.entry}` : "preview indisponível";
}

function DockThumb({ computer }) {
  if (computer.pane === "browser") return <BrowserThumb scene={computer.browser.scene} />;
  const Icon = computer.pane === "files" ? FileCode2 : computer.pane === "terminal" ? SquareTerminal : AppWindow;
  return <span className="vx-thumb vx-thumb--icon"><Icon aria-hidden="true" size={16} /></span>;
}

export const VortaxComputerDock = memo(function VortaxComputerDock({ agentStatus, computer, connectionState, onOpen, onOpenDetails, open, plan }) {
  const [expanded, setExpanded] = useState(false);
  const reduced = useReducedMotion();
  const { headline } = computer;
  const hasPlan = plan?.hasSteps && !plan.isDirect && plan.steps?.length > 0;
  const connection = CONNECTION_LABELS[connectionState];

  return (
    <section aria-label="Atividade atual" className={`vx-dock ${expanded ? "is-expanded" : ""} ${open ? "is-linked" : ""}`}>
      <div className="vx-dock__bar">
        <button
          aria-expanded={open}
          aria-label={`${open ? "Computador do Vortax aberto" : "Abrir o Computador do Vortax"}: ${headline.title}`}
          className="vx-dock__main"
          onClick={onOpen}
          type="button"
        >
          <DockThumb computer={computer} />
          <span className="vx-dock__text">
            <span className="vx-dock__headline">
              <StatusIndicator size={13} status={headline.status} />
              <strong>{headline.title}</strong>
            </span>
            <small>
              {PANE_LABELS[computer.pane]} · {sceneLine(computer)}
              {computer.isHistory ? " · histórico" : ""}
              {connection ? ` · ${connection}` : ""}
            </small>
          </span>
        </button>
        {hasPlan ? (
          <button
            aria-expanded={expanded}
            aria-label={`Plano: ${plan.doneCount} de ${plan.totalCount} etapas concluídas`}
            className="vx-dock__plan"
            onClick={() => setExpanded((value) => !value)}
            title="Etapas do plano concluídas / total"
            type="button"
          >
            <span>{plan.doneCount}/{plan.totalCount}</span>
            <ChevronDown aria-hidden="true" className="vx-dock__chevron" size={14} />
          </button>
        ) : null}
        <button aria-label="Abrir detalhes técnicos da tarefa" className="vx-icon-btn" onClick={onOpenDetails} title="Detalhes técnicos" type="button">
          <PanelRightOpen size={16} />
        </button>
      </div>
      <AnimatePresence initial={false}>
        {expanded && hasPlan ? (
          <motion.ol
            animate={{ height: "auto", opacity: 1 }}
            className="vx-dock__steps"
            exit={{ height: 0, opacity: 0 }}
            initial={{ height: 0, opacity: 0 }}
            transition={{ duration: reduced ? 0 : 0.2, ease: [0.2, 0.7, 0.2, 1] }}
          >
            {plan.steps.map((step) => (
              <li key={step.id}>
                <StatusIndicator size={13} status={planStepStatus(step, plan, agentStatus)} />
                <span>{publicText(step.label)}</span>
              </li>
            ))}
            <li className="vx-dock__note">A contagem considera apenas as etapas do plano.</li>
          </motion.ol>
        ) : null}
      </AnimatePresence>
    </section>
  );
});
