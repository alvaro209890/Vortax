import { useMemo } from "react";

const PLAN_EVENTS = new Set([
  "task_plan_created",
  "task_plan_replanned",
  "task_step_started",
  "task_step_updated",
  "task_step_completed",
  "task_step_failed",
]);

function normalizeEvidence(evidence = []) {
  if (!Array.isArray(evidence)) return [];
  return evidence
    .map((item) => {
      if (!item) return null;
      if (typeof item === "string") return { summary: item };
      return item;
    })
    .filter(Boolean);
}

function normalizeStep(step) {
  const evidence = normalizeEvidence(step?.evidence);
  const criteria = Array.isArray(step?.acceptance_criteria) ? step.acceptance_criteria : [];
  return {
    ...step,
    acceptance_criteria: criteria,
    evidence,
    evidence_summary: evidence
      .slice(-3)
      .map((item) => item.summary || item.status || item.reason || item.detail || item.message || "Evidencia registrada")
      .filter(Boolean),
  };
}

export function applyLivePlanEvents(initialPlan, events) {
  const byId = new Map();
  const loadSteps = (steps = []) => {
    steps.forEach((step) => {
      if (step?.id) byId.set(step.id, normalizeStep(step));
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
      byId.set(payload.step.id, normalizeStep(payload.step));
    }
  });

  return [...byId.values()].sort((a, b) => (a.position || 0) - (b.position || 0));
}

function stepState(status) {
  if (status === "passed") return "done";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  if (status === "skipped") return "skipped";
  return "pending";
}

function latestEvent(events, predicate) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (predicate(events[index])) return events[index];
  }
  return null;
}

function latestProgressLabel(events) {
  const progress = latestEvent(events, (event) => event.type === "agent_progress");
  return progress?.payload?.label || progress?.payload?.detail || "";
}

function latestPlanMeta(events, steps) {
  const planEvent = latestEvent(events, (event) => event.type === "task_plan_created" || event.type === "task_plan_replanned");
  const direct = Boolean(planEvent?.payload?.direct)
    || (steps.length === 1 && steps[0]?.tool_hint === "deliver" && /responder/i.test(steps[0]?.label || ""));
  return {
    direct,
    fallback: Boolean(planEvent?.payload?.fallback),
  };
}

function progressiveSteps(steps, terminal) {
  if (terminal) return steps;
  let lastRevealedIndex = steps.findIndex((step) => step.status === "running");
  steps.forEach((step, index) => {
    if (step.status && step.status !== "pending") {
      lastRevealedIndex = Math.max(lastRevealedIndex, index);
    }
  });
  if (lastRevealedIndex < 0) return steps.slice(0, 1);
  return steps.slice(0, Math.min(steps.length, lastRevealedIndex + 2));
}

export function buildLiveTaskPlan(initialPlan, events) {
  const steps = applyLivePlanEvents(initialPlan, events).map((step) => ({
    ...step,
    state: stepState(step.status),
  }));
  const doneCount = steps.filter((step) => ["passed", "skipped"].includes(step.status)).length;
  const failedCount = steps.filter((step) => step.status === "failed").length;
  const runningStep = steps.find((step) => step.status === "running");
  const pendingStep = steps.find((step) => step.status === "pending");
  const latestStatus = latestEvent(events, (event) => event.type === "agent_status")?.payload?.status || "";
  const terminal = ["done", "stopped", "error", "idle"].includes(latestStatus);
  const meta = latestPlanMeta(events, steps);
  const currentStep = terminal && steps.length
    ? steps[steps.length - 1]
    : runningStep || pendingStep || steps[steps.length - 1] || null;
  const percent = steps.length ? Math.round((doneCount / steps.length) * 100) : 0;
  const sourceCount = events.filter((event) => event.type === "source_saved").length;
  const screenCount = events.filter((event) => event.type === "screen_frame").length;
  const latestProgress = latestProgressLabel(events);
  const planKey = steps
    .map((step) => `${step.id}:${step.status}:${step.updated_at || ""}:${step.evidence?.length || 0}`)
    .join("|");

  return {
    currentStep,
    doneCount,
    failedCount,
    hasSteps: steps.length > 0,
    isDirect: meta.direct,
    isTerminal: terminal,
    latestProgress,
    percent,
    planKey,
    screenCount,
    sourceCount,
    steps,
    totalCount: steps.length,
    visibleSteps: meta.direct ? steps : progressiveSteps(steps, terminal),
  };
}

export function useLiveTaskPlan(initialPlan, events) {
  return useMemo(() => buildLiveTaskPlan(initialPlan, events), [initialPlan, events]);
}
