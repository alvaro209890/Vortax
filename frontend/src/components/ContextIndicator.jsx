import { motion } from "framer-motion";

function contextLabel(status, compactionCount) {
  if (!status || status === "empty") return "Contexto vazio";
  if (status === "full") return "Contexto cheio";
  if (status === "warning") return "Quase cheio";
  if (compactionCount > 0) return "Contexto compactado";
  return "Contexto ok";
}

function contextTone(status) {
  if (status === "full") return "full";
  if (status === "warning") return "warning";
  if (status === "empty") return "empty";
  return "ok";
}

function formatTokens(value) {
  const number = Number(value || 0);
  if (number >= 1000) return `${(number / 1000).toFixed(1)}k`;
  return String(number);
}

export function ContextIndicator({ context }) {
  const status = context?.status || "empty";
  const percent = Math.max(0, Math.min(100, Number(context?.percent || 0)));
  const compactionCount = Number(context?.compaction_count || 0);
  const label = contextLabel(status, compactionCount);
  const title = `${label}: ${formatTokens(context?.estimated_tokens)} / ${formatTokens(context?.token_limit)} tokens estimados`;

  return (
    <div className={`context-indicator ${contextTone(status)}`} title={title}>
      <motion.span
        className="context-dot"
        style={{ "--context-percent": `${percent}%` }}
        animate={
          status === "full"
            ? { scale: [1, 1.12, 1] }
            : {}
        }
        transition={
          status === "full"
            ? { duration: 1.2, repeat: Infinity, ease: "easeInOut" }
            : {}
        }
      />
      <div>
        <strong>{label}</strong>
        <span>{percent}%</span>
      </div>
    </div>
  );
}
