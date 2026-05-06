const statusClass = {
  online: "ok",
  done: "ok",
  running: "active",
  executing: "active",
  thinking: "active",
  queued: "active",
  paused: "warn",
  offline: "error",
  error: "error",
  stopped: "warn",
};

export function StatusBadge({ status, label }) {
  return <span className={`status-badge ${statusClass[status] || "idle"}`}>{label || status}</span>;
}
