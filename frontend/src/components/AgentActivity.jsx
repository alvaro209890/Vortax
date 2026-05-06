import { Loader2 } from "lucide-react";

export function AgentActivity({ events, status }) {
  const active = ["queued", "thinking", "executing", "running"].includes(status);
  if (!active) return null;

  const progress = [...events].reverse().find((event) => event.type === "agent_progress");
  const label = progress?.payload?.label || "Trabalhando";
  const detail = progress?.payload?.detail;

  return (
    <div className="agent-activity">
      <Loader2 size={16} />
      <div>
        <strong>{label}</strong>
        {detail ? <span>{detail}</span> : null}
      </div>
    </div>
  );
}
