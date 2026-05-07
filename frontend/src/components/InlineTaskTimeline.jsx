import { useState } from "react";
import {
  Check,
  ChevronDown,
  Circle,
  Code2,
  FileSearch,
  Loader2,
  Monitor,
  Search,
  Terminal,
  XCircle,
} from "lucide-react";

function statusIcon(step) {
  if (step.status === "passed" || step.status === "skipped") return <Check size={14} />;
  if (step.status === "failed") return <XCircle size={14} />;
  if (step.status === "running") return <Loader2 size={14} className="spinner" />;
  return <Circle size={14} />;
}

function hintIcon(hint = "") {
  const value = hint.toLowerCase();
  if (value.includes("research") || value.includes("search") || value.includes("web")) return <Search size={13} />;
  if (value.includes("vertex") || value.includes("code") || value.includes("editor") || value.includes("execute")) return <Code2 size={13} />;
  if (value.includes("validation") || value.includes("validate")) return <Monitor size={13} />;
  if (value.includes("shell") || value.includes("terminal")) return <Terminal size={13} />;
  return <FileSearch size={13} />;
}

function hintLabel(step, sourceCount) {
  const hint = String(step.tool_hint || "").toLowerCase();
  if (hint.includes("research") || hint.includes("search") || hint.includes("web")) {
    return sourceCount > 0 ? `Conhecimento recuperado(${sourceCount})` : "Conhecimento";
  }
  if (hint.includes("understand")) return "Analise do pedido";
  if (hint.includes("vertex") || hint.includes("code") || hint.includes("editor")) return "Editor";
  if (hint.includes("execute")) return "Execucao";
  if (hint.includes("validation") || hint.includes("validate")) return "Validacao";
  if (hint.includes("delivery") || hint.includes("deliver") || hint.includes("finish")) return "Entrega";
  if (hint.includes("shell") || hint.includes("terminal")) return "Terminal";
  return "";
}

function latestStepLine(step, livePlan) {
  if (step.status === "running" && livePlan.latestProgress) return livePlan.latestProgress;
  if (step.evidence_summary?.length > 0) return step.evidence_summary[step.evidence_summary.length - 1];
  return step.detail || "";
}

export function InlineTaskTimeline({ livePlan, showEmpty = false }) {
  const [expandedId, setExpandedId] = useState(null);
  const { currentStep, doneCount, isDirect, percent, sourceCount, totalCount } = livePlan;
  const steps = livePlan.visibleSteps || livePlan.steps || [];
  const allSteps = livePlan.steps || [];

  if (!allSteps.length) {
    if (!showEmpty) return null;
    return (
      <section className="inline-task-timeline empty">
        <div className="inline-plan-head">
          <span>Plano Vivo</span>
          <small>0/0</small>
        </div>
        <p>O plano aparece aqui.</p>
      </section>
    );
  }

  if (isDirect) {
    const step = allSteps[0];
    const done = step?.status === "passed" || step?.status === "skipped";
    const running = step?.status === "running";
    return (
      <section className={`inline-task-timeline direct ${done ? "done" : running ? "running" : "pending"}`} aria-label="Resposta rapida">
        <span className="inline-direct-node">{done ? <Check size={13} /> : running ? <Loader2 size={13} className="spinner" /> : <Circle size={13} />}</span>
        <div>
          <strong>{done ? "Resposta pronta" : running ? "Respondendo" : "Preparando resposta"}</strong>
          <small>{done ? "A resposta vem logo abaixo." : livePlan.latestProgress || "Sem pesquisa, sem Vertex."}</small>
        </div>
      </section>
    );
  }

  return (
    <section className="inline-task-timeline" aria-label="Plano Vivo da tarefa">
      <div className="inline-plan-head">
        <span>{currentStep?.label || "Plano Vivo"}</span>
        <small>{doneCount}/{totalCount} · {percent}%</small>
      </div>
      <ol className="inline-plan-list">
        {steps.map((step) => {
          const expanded = expandedId === step.id;
          const criteria = step.acceptance_criteria || [];
          const evidence = step.evidence_summary || [];
          const toolLabel = hintLabel(step, sourceCount);
          const line = latestStepLine(step, livePlan);

          return (
            <li className={`inline-plan-step ${step.state}`} key={step.id}>
              <span className="inline-step-node">{statusIcon(step)}</span>
              <button
                className="inline-step-title"
                onClick={() => setExpandedId((current) => (current === step.id ? null : step.id))}
                type="button"
              >
                <strong>{step.label}</strong>
                <ChevronDown size={14} />
              </button>
              <div className="inline-step-body">
                {toolLabel ? (
                  <span className="inline-tool-pill">
                    {hintIcon(step.tool_hint)}
                    {toolLabel}
                  </span>
                ) : null}
                {line ? <p>{line}</p> : null}
                {expanded && (
                  <div className="inline-step-details">
                    {step.detail ? <p>{step.detail}</p> : null}
                    {criteria.length > 0 && (
                      <div>
                        <small>Criterios</small>
                        {criteria.map((item, index) => (
                          <span key={`${step.id}-criteria-${index}`}>{item}</span>
                        ))}
                      </div>
                    )}
                    {evidence.length > 0 && (
                      <div>
                        <small>Evidencias</small>
                        {evidence.map((item, index) => (
                          <span key={`${step.id}-evidence-${index}`}>{item}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
