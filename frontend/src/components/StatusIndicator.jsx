import { memo } from "react";
import { Check, Minus, Pause, Square, X } from "lucide-react";

import { STATUS_LABELS } from "../lib/activity.js";

// Indicador único de estado. "running" é um anel girando por CSS (transform), que só
// para quando o estado muda; o elemento fica estável entre renderizações, então a
// rotação não recomeça a cada evento. Com movimento reduzido o anel fica estático e
// o rótulo acessível continua descrevendo o estado.
export const StatusIndicator = memo(function StatusIndicator({ status = "pending", size = 16, label, className = "", showLabel = false }) {
  const text = label || STATUS_LABELS[status] || status;
  const iconSize = Math.max(8, Math.round(size * 0.62));
  let glyph = null;
  if (status === "done") glyph = <Check size={iconSize} strokeWidth={3} />;
  else if (status === "failed") glyph = <X size={iconSize} strokeWidth={3} />;
  else if (status === "paused") glyph = <Pause size={iconSize} strokeWidth={3} />;
  else if (status === "interrupted") glyph = <Square size={Math.max(6, iconSize - 3)} strokeWidth={3} />;
  else if (status === "unknown") glyph = <Minus size={iconSize} strokeWidth={3} />;
  else if (status === "waiting") glyph = <span className="vx-status__glyph-text">?</span>;

  return (
    <span className={`vx-status-wrap ${className}`}>
      <span
        aria-label={showLabel ? undefined : text}
        className={`vx-status vx-status--${status}`}
        data-status={status}
        role={showLabel ? undefined : "img"}
        style={{ "--vx-status-size": `${size}px` }}
        title={text}
      >
        {status === "running" ? <span aria-hidden="true" className="vx-status__ring" /> : null}
        {glyph ? <span aria-hidden="true" className="vx-status__glyph">{glyph}</span> : null}
      </span>
      {showLabel ? <span className="vx-status-label">{text}</span> : null}
    </span>
  );
});
