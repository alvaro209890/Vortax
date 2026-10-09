import { memo, useMemo, useState } from "react";
import { ChevronDown, FileCode2, Globe2, Info, SquareTerminal } from "lucide-react";

import { groupActions, STATUS_LABELS, turnHeadline, turnResults } from "../lib/activity.js";
import { clip, displayUrl, fileName, formatClock, formatDuration, hostOf, isHttpUrl, publicText, shortPath } from "../lib/text.js";
import { StatusIndicator } from "./StatusIndicator.jsx";

function TargetChip({ target }) {
  if (!target?.value) return null;
  if (target.type === "file") return <code className="vx-target" title={target.value}><FileCode2 aria-hidden="true" size={11} />{shortPath(target.value, 34)}</code>;
  if (target.type === "url") return <span className="vx-target" title={target.value}><Globe2 aria-hidden="true" size={11} />{clip(hostOf(target.value) || displayUrl(target.value), 32)}</span>;
  if (target.type === "command") return <code className="vx-target vx-target--cmd" title={target.value}><SquareTerminal aria-hidden="true" size={11} />{clip(target.value, 40)}</code>;
  if (target.type === "query") return null;
  return <span className="vx-target" title={target.value}>{clip(target.value, 36)}</span>;
}

function summarizeParams(action) {
  const params = action.params || {};
  const entries = Object.entries(params).map(([key, value]) => {
    if (typeof value === "string" && (key === "content" || key === "new_string" || key === "old_string")) {
      const lines = value.split("\n").length;
      return [key, `${lines} ${lines === 1 ? "linha" : "linhas"} (${value.length} caracteres)`];
    }
    if (typeof value === "string") return [key, clip(publicText(value), 160)];
    return [key, clip(JSON.stringify(value), 160)];
  });
  return entries;
}

function TechnicalDetails({ action }) {
  return (
    <dl className="vx-action__details">
      <dt>Ferramenta</dt><dd><code>{action.tool}</code></dd>
      {action.callId ? <><dt>Chamada</dt><dd><code>{action.callId}</code></dd></> : null}
      <dt>Início</dt><dd>{formatClock(action.startedAt)}{action.durationMs ? ` · ${formatDuration(action.durationMs)}` : ""}</dd>
      <dt>Estado</dt><dd>{STATUS_LABELS[action.status]}</dd>
      {summarizeParams(action).map(([key, value]) => (
        <span className="vx-action__param" key={key}><dt>{key}</dt><dd>{value}</dd></span>
      ))}
      {action.warnings.length ? <><dt>Avisos</dt><dd>{action.warnings.map((item) => clip(item, 140)).join(" · ")}</dd></> : null}
    </dl>
  );
}

const ActionRow = memo(function ActionRow({ action, repeats = 1, onFocus }) {
  const [details, setDetails] = useState(false);
  return (
    <li className={`vx-action vx-action--${action.status}`}>
      <div className="vx-action__line">
        <button className="vx-action__main" onClick={() => onFocus?.(action.id)} title={action.pane ? "Ver esta ação no Computador do Vortax" : undefined} type="button">
          <StatusIndicator size={14} status={action.status} />
          <span className="vx-action__title">{action.title}{repeats > 1 ? <em> ×{repeats}</em> : null}</span>
          <TargetChip target={action.target} />
          {action.meta ? <span className="vx-action__meta">{action.meta}</span> : null}
        </button>
        <button aria-expanded={details} aria-label="Detalhes técnicos da ação" className="vx-icon-btn vx-action__info" onClick={() => setDetails((value) => !value)} title="Detalhes técnicos" type="button">
          <Info size={13} />
        </button>
      </div>
      {action.error ? <p className="vx-action__error">{clip(action.error, 280)}</p> : null}
      {details ? <TechnicalDetails action={action} /> : null}
    </li>
  );
});

const GroupRow = memo(function GroupRow({ group, onFocus }) {
  const [open, setOpen] = useState(false);
  if (group.single) return <ActionRow action={group.item.action} onFocus={onFocus} repeats={group.item.repeats.length} />;
  return (
    <li className={`vx-group vx-action--${group.status}`}>
      <button aria-expanded={open} className="vx-group__head" onClick={() => setOpen((value) => !value)} type="button">
        <StatusIndicator size={14} status={group.status} />
        <span className="vx-action__title">{group.title}</span>
        {group.failures ? <span className="vx-tag vx-tag--failed">{group.failures} com falha</span> : null}
        <ChevronDown aria-hidden="true" className="vx-group__chevron" size={14} />
      </button>
      {open ? (
        <ol className="vx-group__items">
          {group.items.map((item) => <ActionRow action={item.action} key={item.action.id} onFocus={onFocus} repeats={item.repeats.length} />)}
        </ol>
      ) : null}
    </li>
  );
});

function TurnResults({ turn, onFocus }) {
  const { files, sources } = useMemo(() => turnResults(turn), [turn]);
  if (!files.length && !sources.length) return null;
  return (
    <div className="vx-turn__results">
      {files.length ? (
        <div>
          <span>Arquivos</span>
          {files.map((file) => (
            <button className="vx-result" key={file.path} onClick={() => onFocus?.(file.actionId)} title={`Ver ${file.path} no Computador`} type="button">
              <FileCode2 aria-hidden="true" size={12} />{fileName(file.path)}<em>{file.change === "created" ? "novo" : "editado"}</em>
            </button>
          ))}
        </div>
      ) : null}
      {sources.length ? (
        <div>
          <span>Fontes</span>
          {sources.slice(0, 8).map((source) => (
            <a className="vx-result" href={isHttpUrl(source.url) ? source.url : undefined} key={source.url} rel="noopener noreferrer" target="_blank" title={source.url}>
              <Globe2 aria-hidden="true" size={12} />{clip(source.title || hostOf(source.url), 34)}
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Atividade de um turno: resumo do que acontece agora, grupos de ações e resultados. */
export const TurnActivity = memo(function TurnActivity({ turn, onFocus, defaultOpen }) {
  const headline = turnHeadline(turn);
  const groups = useMemo(() => groupActions(turn.actions), [turn.actions]);
  const live = ["running", "paused", "waiting"].includes(turn.status);
  const [openState, setOpenState] = useState(null);
  const open = openState ?? (defaultOpen ?? live);
  const failures = turn.actions.filter((action) => action.status === "failed").length;
  const count = turn.actions.length;

  return (
    <article aria-label="Atividade do Vortax" className={`vx-turn vx-turn--${turn.status}`}>
      <button aria-expanded={open} className="vx-turn__summary" onClick={() => setOpenState(!open)} type="button">
        <StatusIndicator size={16} status={headline.status} />
        <span className="vx-turn__headline">{headline.title}</span>
        {count ? <span className="vx-turn__count">{count} {count === 1 ? "ação" : "ações"}{failures ? ` · ${failures} com falha` : ""}</span> : null}
        <ChevronDown aria-hidden="true" className="vx-turn__chevron" size={15} />
      </button>
      {headline.detail ? <p className="vx-turn__question">{headline.detail}</p> : null}
      {open && groups.length ? (
        <ol className="vx-turn__groups">
          {groups.map((group) => <GroupRow group={group} key={group.id} onFocus={onFocus} />)}
        </ol>
      ) : null}
      {turn.errors.length ? (
        <div className="vx-turn__errors" role="status">
          {turn.errors.slice(-2).map((error) => <p key={error.index}>{clip(error.message, 240)}</p>)}
        </div>
      ) : null}
      {!live ? <TurnResults onFocus={onFocus} turn={turn} /> : null}
    </article>
  );
});

// Turno ainda sem eventos (a mensagem acabou de ser enviada).
export function PreparingTurn() {
  return (
    <article aria-label="Atividade do Vortax" className="vx-turn vx-turn--running">
      <div className="vx-turn__summary is-static">
        <StatusIndicator size={16} status="running" />
        <span className="vx-turn__headline">Preparando a tarefa</span>
      </div>
    </article>
  );
}
