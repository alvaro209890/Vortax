import { useMemo, useState } from "react";
import { CheckCircle2, ChevronDown, Circle, ClipboardList, Loader2, XCircle } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";

const PLAN_EVENTS = new Set([
  "task_plan_created",
  "task_plan_replanned",
  "task_step_started",
  "task_step_updated",
  "task_step_completed",
  "task_step_failed",
]);

function applyPlanEvents(initialPlan, events) {
  const byId = new Map();
  const loadSteps = (steps = []) => {
    steps.forEach((step) => {
      if (step?.id) byId.set(step.id, { ...step });
    });
  };

  loadSteps(initialPlan?.steps || []);
  events.filter((event) => PLAN_EVENTS.has(event.type)).forEach((event) => {
    const payload = event.payload || {};
    if (Array.isArray(payload.steps)) {
      byId.clear();
      loadSteps(payload.steps);
    }
    if (payload.step?.id) {
      byId.set(payload.step.id, { ...payload.step });
    }
  });

  return [...byId.values()].sort((a, b) => (a.position || 0) - (b.position || 0));
}

function iconForStatus(status) {
  if (status === "passed") return <CheckCircle2 size={15} />;
  if (status === "failed") return <XCircle size={15} />;
  if (status === "running") return <Loader2 size={15} className="spinner" />;
  return <Circle size={15} />;
}

function stepState(status) {
  if (status === "passed") return "done";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  if (status === "skipped") return "skipped";
  return "pending";
}

function compactEvidence(evidence = []) {
  if (!Array.isArray(evidence) || evidence.length === 0) return [];
  return evidence.slice(-3).map((item) => item?.summary || item?.status || "Evidencia registrada").filter(Boolean);
}

export function TaskPlanPanel({ events, initialPlan }) {
  const [expandedId, setExpandedId] = useState(null);
  const steps = useMemo(() => applyPlanEvents(initialPlan, events), [events, initialPlan]);
  const doneCount = steps.filter((step) => ["passed", "skipped"].includes(step.status)).length;
  const percent = steps.length ? Math.round((doneCount / steps.length) * 100) : 0;
  const current = steps.find((step) => step.status === "running") || steps.find((step) => step.status === "pending");

  return (
    <CollapsiblePanel
      className="task-plan-panel"
      count={steps.length}
      storageKey="vortax.inspector.live_plan.collapsed"
      title="Plano Vivo"
    >
      {steps.length === 0 ? (
        <p className="panel-state">O plano aparece aqui.</p>
      ) : (
        <>
          <div className="live-plan-summary">
            <div className="live-plan-mark">
              <ClipboardList size={16} />
            </div>
            <div>
              <strong>{current ? current.label : "Plano concluido"}</strong>
              <span>{doneCount}/{steps.length} etapas · {percent}%</span>
            </div>
          </div>
          <div className="live-plan-progress" aria-hidden="true">
            <span style={{ width: `${percent}%` }} />
          </div>
          <div className="live-plan-steps">
            {steps.map((step) => {
              const expanded = expandedId === step.id;
              const criteria = Array.isArray(step.acceptance_criteria) ? step.acceptance_criteria : [];
              const evidences = compactEvidence(step.evidence);
              return (
                <button
                  className={`live-plan-step ${stepState(step.status)} ${expanded ? "expanded" : ""}`}
                  key={step.id}
                  onClick={() => setExpandedId((currentId) => (currentId === step.id ? null : step.id))}
                  type="button"
                >
                  <div className="live-plan-step-main">
                    <span className="live-plan-step-icon">{iconForStatus(step.status)}</span>
                    <div>
                      <strong>{step.label}</strong>
                      <p>{step.detail}</p>
                    </div>
                    <ChevronDown size={14} />
                  </div>
                  {expanded && (
                    <div className="live-plan-details">
                      {criteria.length > 0 && (
                        <div>
                          <small>Criterios</small>
                          {criteria.map((item, index) => <span key={`${step.id}-c-${index}`}>{item}</span>)}
                        </div>
                      )}
                      {evidences.length > 0 && (
                        <div>
                          <small>Evidencias</small>
                          {evidences.map((item, index) => <span key={`${step.id}-e-${index}`}>{item}</span>)}
                        </div>
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </CollapsiblePanel>
  );
}
