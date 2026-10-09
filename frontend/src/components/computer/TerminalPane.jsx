import { memo, useMemo } from "react";
import { ArrowDown, SquareTerminal } from "lucide-react";

import { STATUS_LABELS } from "../../lib/activity.js";
import { clip, formatClock, formatDuration, publicText } from "../../lib/text.js";
import { useStickToBottom } from "../../hooks/useStickToBottom.js";
import { StatusIndicator } from "../StatusIndicator.jsx";

const MAX_LINES = 1500;

// Linhas exibidas: a saída transmitida linha a linha; se não houve transmissão (sessão
// em segundo plano, conversas antigas), a saída que veio no resultado da ferramenta.
function outputLines(action) {
  if (action.output.length) return { lines: action.output.slice(-MAX_LINES), origin: "stream", total: action.output.length };
  const result = action.result || {};
  const lines = [];
  String(result.stdout || result.output || "").split("\n").filter(Boolean).forEach((text) => lines.push({ stream: "stdout", text: publicText(text) }));
  String(result.stderr || "").split("\n").filter(Boolean).forEach((text) => lines.push({ stream: "stderr", text: publicText(text) }));
  return { lines: lines.slice(-MAX_LINES), origin: lines.length ? "result" : "none", total: lines.length };
}

function ValidationDetails({ action }) {
  const result = action.result || {};
  const steps = action.validation.filter((item) => item.type.endsWith("_step"));
  const checks = Array.isArray(result.checks) ? result.checks : [];
  const bugs = Array.isArray(result.bugs) ? result.bugs : [];
  return (
    <div className="vx-term__checks">
      {steps.map((step) => (
        <div className="vx-term__check" key={step.index}>
          <span aria-hidden="true" className="vx-term__bullet" />
          <span>{publicText(step.payload.label || "Etapa da validação")}{step.payload.detail ? ` — ${publicText(step.payload.detail)}` : ""}</span>
        </div>
      ))}
      {checks.map((check, index) => {
        const passed = check.passed ?? check.returncode === 0;
        return (
          <div className="vx-term__check" key={`check-${index}`}>
            <StatusIndicator size={12} status={passed ? "done" : "failed"} />
            <code>{publicText(check.command || "verificação")}</code>
            {Number.isFinite(check.returncode) ? <em>código {check.returncode}</em> : null}
            {check.stdout || check.stderr ? <pre>{publicText(clip(`${check.stdout || ""}\n${check.stderr || ""}`.trim(), 600))}</pre> : null}
          </div>
        );
      })}
      {bugs.map((bug, index) => (
        <div className="vx-term__check" key={`bug-${index}`}>
          <StatusIndicator size={12} status="failed" />
          <span>{publicText(typeof bug === "string" ? bug : bug.message || bug.description || JSON.stringify(bug))}</span>
        </div>
      ))}
      {!steps.length && !checks.length && !bugs.length && action.status !== "running" ? (
        <p className="vx-pane-note">{publicText(result.reason || result.summary || "A validação não registrou verificações detalhadas.")}</p>
      ) : null}
    </div>
  );
}

const TerminalOutput = memo(function TerminalOutput({ action }) {
  const { lines, origin, total } = useMemo(() => outputLines(action), [action]);
  const { ref, scrollToBottom, stuck, unseen } = useStickToBottom(lines.length, { resetKey: action.id });
  const running = ["running", "paused"].includes(action.status);
  return (
    <div className="vx-term__output-wrap">
      <div aria-label="Saída do comando" aria-live={running ? "polite" : "off"} className="vx-term__output" ref={ref} role="log" tabIndex={0}>
        <div>
          {origin === "result" ? <div className="vx-term__note">Saída registrada no resultado do comando</div> : null}
          {total > lines.length ? <div className="vx-term__note">… {total - lines.length} linhas anteriores omitidas</div> : null}
          {lines.map((line, index) => (
            <div className={`vx-term__line ${line.stream === "stderr" ? "is-stderr" : ""}`} key={line.index ?? `r-${index}`}>{line.text || " "}</div>
          ))}
          {!lines.length ? (
            <div className="vx-term__note">{running ? "Aguardando saída do comando…" : "O comando não produziu saída."}</div>
          ) : null}
        </div>
      </div>
      {!stuck ? (
        <button className="vx-jump" onClick={() => scrollToBottom()} type="button">
          <ArrowDown size={14} /> {unseen ? `Ir para o fim · ${unseen} novas` : "Ir para o fim"}
        </button>
      ) : null}
      {!stuck && running ? <span className="vx-term__paused">Rolagem automática pausada</span> : null}
    </div>
  );
});

export const TerminalPane = memo(function TerminalPane({ computer }) {
  const { action, entries } = computer.terminal;
  if (!entries.length || !action) {
    return (
      <div className="vx-pane-empty">
        <SquareTerminal aria-hidden="true" size={24} />
        <strong>Nenhum comando nesta tarefa</strong>
        <span>Comandos executados pelo Vortax aparecem aqui com a saída real e o código de saída.</span>
      </div>
    );
  }
  const command = action.target?.type === "command" ? action.target.value : action.title;
  const isValidation = action.family === "validation";
  return (
    <div className="vx-term">
      <nav aria-label="Comandos executados" className="vx-term__list">
        <label className="vx-term__select">
          <span className="vx-sr-only">Escolher comando</span>
          <select onChange={(event) => computer.selectTerminal(event.target.value)} value={action.id}>
            {entries.map((entry, index) => (
              <option key={entry.id} value={entry.id}>{index + 1}. {clip(entry.target?.value || entry.title, 60)} — {STATUS_LABELS[entry.status]}</option>
            ))}
          </select>
        </label>
        <ul>
          {entries.map((entry) => (
            <li key={entry.id}>
              <button aria-current={entry.id === action.id ? "true" : undefined} className={entry.id === action.id ? "is-active" : ""} onClick={() => computer.selectTerminal(entry.id)} type="button">
                <StatusIndicator size={12} status={entry.status} />
                <span>{clip(entry.target?.type === "command" ? entry.target.value : entry.title, 48)}</span>
                <time>{formatClock(entry.startedAt)}</time>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <section className="vx-term__main">
        <header className="vx-term__head">
          <code className="vx-term__cmd">{isValidation ? action.title : <><span aria-hidden="true">$ </span>{command}</>}</code>
          <div className="vx-term__meta">
            <StatusIndicator showLabel size={13} status={action.status} />
            {Number.isFinite(action.result?.returncode) ? <span>código {action.result.returncode}</span> : null}
            {action.durationMs ? <span>{formatDuration(action.durationMs)}</span> : null}
            <span>{formatClock(action.startedAt)}</span>
          </div>
          {action.error ? <p className="vx-pane-note vx-pane-note--error">{action.error}</p> : null}
          {action.progress.length ? (
            <ul className="vx-term__progress">
              {action.progress.slice(-4).map((item) => <li key={item.index}>{item.message}</li>)}
            </ul>
          ) : null}
        </header>
        {isValidation || action.tool === "validate_project" ? <ValidationDetails action={action} /> : <TerminalOutput action={action} key={action.id} />}
      </section>
    </div>
  );
});
