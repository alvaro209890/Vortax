import { memo, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Download, FileCode2, FileText, Folder, FolderOpen, Image as ImageIcon } from "lucide-react";

import { turnResults } from "../../lib/activity.js";
import { fileDownloadUrl } from "../../lib/api.js";
import { formatBytes, formatClock, shortPath } from "../../lib/text.js";
import {
  buildFileTree,
  compactDiff,
  contentAfterAction,
  contentBeforeAction,
  diffLines,
  fileKind,
  languageLabel,
} from "../../lib/workspace.js";
import { useFileContent } from "../../hooks/useFileContent.js";
import { StatusIndicator } from "../StatusIndicator.jsx";
import { CodeView, DiffView, parseNumberedRead } from "./CodeView.jsx";

function FileIcon({ path }) {
  const kind = fileKind(path);
  if (kind === "image") return <ImageIcon aria-hidden="true" size={13} />;
  if (/\.(md|txt|pdf|docx|csv|xlsx|pptx)$/i.test(path)) return <FileText aria-hidden="true" size={13} />;
  return <FileCode2 aria-hidden="true" size={13} />;
}

const TreeNode = memo(function TreeNode({ node, depth, activePath, changes, collapsed, onToggle, onSelect }) {
  if (node.type === "dir") {
    const open = !collapsed.has(node.path);
    return (
      <li>
        <button aria-expanded={open} className="vx-tree__row vx-tree__row--dir" onClick={() => onToggle(node.path)} style={{ "--depth": depth }} type="button">
          {open ? <ChevronDown aria-hidden="true" size={12} /> : <ChevronRight aria-hidden="true" size={12} />}
          {open ? <FolderOpen aria-hidden="true" size={13} /> : <Folder aria-hidden="true" size={13} />}
          <span>{node.name}</span>
        </button>
        {open ? (
          <ul>
            {node.children.map((child) => (
              <TreeNode activePath={activePath} changes={changes} collapsed={collapsed} depth={depth + 1} key={child.path} node={child} onSelect={onSelect} onToggle={onToggle} />
            ))}
          </ul>
        ) : null}
      </li>
    );
  }
  const change = changes.get(node.path);
  return (
    <li>
      <button
        aria-current={activePath === node.path ? "true" : undefined}
        className={`vx-tree__row ${activePath === node.path ? "is-active" : ""}`}
        onClick={() => onSelect(node.path)}
        style={{ "--depth": depth }}
        title={node.path}
        type="button"
      >
        <FileIcon path={node.path} />
        <span>{node.name}</span>
        {change ? <em className={`vx-tag vx-tag--${change}`}>{change === "created" ? "novo" : "editado"}</em> : null}
      </button>
    </li>
  );
});

function fileVersionKey(file) {
  return file?.content_hash || file?.modified_at || "";
}

// A versão atual do workspace ainda é a que a última ação registrou?
function currentMatchesAction(file, action) {
  if (!file || !action?.endedAt) return false;
  const modifiedMs = Number(file.modified_at) * 1000;
  return Number.isFinite(modifiedMs) && modifiedMs <= action.endedAt + 2500;
}

function editHunk(action) {
  const oldText = String(action.params?.old_string ?? "");
  const newText = String(action.params?.new_string ?? "");
  const start = action.result?.start_line || null;
  const lines = [];
  oldText.split("\n").forEach((text, index) => lines.push({ type: "del", text, oldNo: start ? start + index : null }));
  newText.split("\n").forEach((text, index) => lines.push({ type: "add", text, newNo: start ? start + index : null }));
  return lines;
}

function SnapshotView({ action, actions }) {
  const [mode, setMode] = useState("changes");
  const path = action.target.value;
  const before = useMemo(() => (action.tool === "file_write" ? contentBeforeAction(actions, path, action.id) : null), [action, actions, path]);
  const after = useMemo(() => contentAfterAction(actions, path, action.id), [action, actions, path]);

  if (action.status === "failed") {
    return <p className="vx-pane-note vx-pane-note--error">{action.error || "A ação falhou e o arquivo não foi alterado por ela."}</p>;
  }
  if (["running", "paused"].includes(action.status)) {
    return <WaitingWrite action={action} />;
  }
  if (action.tool === "file_read") {
    const read = parseNumberedRead(action.result?.content || "");
    return <CodeView label={`Trecho lido de ${path}`} startLine={read.startLine} text={read.text} />;
  }
  if (action.tool === "file_edit") {
    const highlight = action.result?.start_line ? { from: action.result.start_line, to: action.result.end_line || action.result.start_line } : null;
    return (
      <>
        <ModeSwitch mode={mode} onChange={setMode} options={[["changes", "Alterações"], ...(after !== null ? [["file", "Arquivo após a edição"]] : [])]} />
        {mode === "file" && after !== null
          ? <CodeView highlight={highlight} label={`${path} após a edição`} text={after} />
          : <DiffView label={`Edição em ${path}`} lines={editHunk(action)} />}
        {after === null && mode === "file" ? <p className="vx-pane-note">Não há registro completo do arquivo antes desta edição.</p> : null}
      </>
    );
  }
  if (action.tool === "file_append") {
    return <DiffView label={`Acréscimo em ${path}`} lines={String(action.params?.content ?? "").split("\n").map((text) => ({ type: "add", text }))} />;
  }
  const content = String(action.params?.content ?? "");
  const diff = before !== null ? compactDiff(diffLines(before, content)) : null;
  return (
    <>
      <ModeSwitch mode={before !== null ? mode : "file"} onChange={setMode} options={before !== null ? [["changes", "Alterações"], ["file", "Arquivo"]] : [["file", "Arquivo novo"]]} />
      {before !== null && mode === "changes"
        ? <DiffView label={`Alterações em ${path}`} lines={diff} />
        : <CodeView label={`Conteúdo gravado em ${path}`} text={content} />}
    </>
  );
}

function WaitingWrite({ action }) {
  return (
    <div className="vx-pane-empty" role="status">
      <StatusIndicator size={20} status={action.status} />
      <strong>Aguardando gravação do arquivo</strong>
      <span>{action.title}. O conteúdo aparece assim que a ferramenta confirmar a gravação.</span>
    </div>
  );
}

function ModeSwitch({ mode, onChange, options }) {
  if (options.length < 2) return null;
  return (
    <div aria-label="Modo de exibição" className="vx-segmented" role="tablist">
      {options.map(([value, label]) => (
        <button aria-selected={mode === value} className={mode === value ? "is-active" : ""} key={value} onClick={() => onChange(value)} role="tab" type="button">{label}</button>
      ))}
    </div>
  );
}

function CurrentFileView({ taskId, file, lastAction, actions }) {
  const [mode, setMode] = useState("file");
  const content = useFileContent(taskId, file);
  const matches = currentMatchesAction(file, lastAction);
  const highlight = matches && lastAction?.tool === "file_edit" && lastAction.result?.start_line
    ? { from: lastAction.result.start_line, to: lastAction.result.end_line || lastAction.result.start_line }
    : null;
  const before = useMemo(
    () => (matches && lastAction?.tool === "file_write" ? contentBeforeAction(actions, file.path, lastAction.id) : null),
    [actions, file.path, lastAction, matches],
  );
  const kind = fileKind(file.path);

  if (kind === "image") {
    return <div className="vx-file-image"><img alt={file.path} src={fileDownloadUrl(taskId, file.path)} /></div>;
  }
  if (kind !== "text" || content.status === "binary" || content.status === "pdf") {
    return (
      <div className="vx-pane-empty">
        <FileText aria-hidden="true" size={24} />
        <strong>{kind === "pdf" ? "Documento PDF" : "Arquivo binário"}</strong>
        <span>Este formato não tem pré-visualização de texto aqui.</span>
        <a className="vx-btn" download href={fileDownloadUrl(taskId, file.path)}><Download size={14} /> Baixar {shortPath(file.path, 28)}</a>
      </div>
    );
  }
  if (content.status === "too_large") {
    return (
      <div className="vx-pane-empty">
        <strong>Arquivo grande ({formatBytes(file.size_bytes ?? file.size)})</strong>
        <span>Para não pesar a interface, baixe o arquivo para ler o conteúdo completo.</span>
        <a className="vx-btn" download href={fileDownloadUrl(taskId, file.path)}><Download size={14} /> Baixar</a>
      </div>
    );
  }
  if (content.status === "error") return <p className="vx-pane-note vx-pane-note--error">Não foi possível ler o arquivo atual ({content.error}).</p>;
  if (content.status === "loading" && !content.text) {
    return <div className="vx-pane-empty" role="status"><StatusIndicator size={18} status="running" /><span>Carregando o arquivo do workspace…</span></div>;
  }

  const options = [["file", "Arquivo"]];
  if (highlight) options.push(["changes", "Última edição"]);
  else if (before !== null) options.push(["changes", "Alterações da última gravação"]);
  return (
    <>
      <ModeSwitch mode={mode} onChange={setMode} options={options} />
      {mode === "changes" && highlight
        ? <DiffView label={`Última edição em ${file.path}`} lines={editHunk(lastAction)} />
        : mode === "changes" && before !== null
          ? <DiffView label={`Alterações em ${file.path}`} lines={compactDiff(diffLines(before, content.text))} />
          : <CodeView highlight={highlight} label={`Conteúdo atual de ${file.path}`} text={content.text} />}
    </>
  );
}

export const FilesPane = memo(function FilesPane({ actions, computer, files, latestTurn, taskId }) {
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [treeOpen, setTreeOpen] = useState(false);
  const tree = useMemo(() => buildFileTree(files), [files]);
  const changes = useMemo(() => {
    const map = new Map();
    turnResults(latestTurn).files.forEach((file) => map.set(file.path, file.change));
    return map;
  }, [latestTurn]);
  const { path, pendingAction, snapshotAction, lastFileAction, followingAgent } = computer.files;
  const file = files.find((item) => item.path === path) || null;

  const toggleDir = (dirPath) => setCollapsed((current) => {
    const next = new Set(current);
    if (next.has(dirPath)) next.delete(dirPath);
    else next.add(dirPath);
    return next;
  });

  let header = null;
  let body = null;
  if (snapshotAction) {
    header = (
      <span className="vx-chip vx-chip--history">Registro da ação · {formatClock(snapshotAction.startedAt)}</span>
    );
    body = <SnapshotView action={snapshotAction} actions={actions} key={snapshotAction.id} />;
  } else if (pendingAction) {
    header = <span className="vx-chip vx-chip--live">{pendingAction.title}</span>;
    body = <WaitingWrite action={pendingAction} />;
  } else if (file) {
    header = (
      <span className="vx-chip">
        Versão atual do workspace{file.modified_at ? ` · modificado ${formatClock(Number(file.modified_at) * 1000)}` : ""}
      </span>
    );
    body = <CurrentFileView actions={actions} file={file} key={`${file.path}:${fileVersionKey(file)}`} lastAction={lastFileAction} taskId={taskId} />;
  } else if (path) {
    body = <p className="vx-pane-note">{path} não está no workspace atual desta tarefa.</p>;
  } else {
    body = (
      <div className="vx-pane-empty">
        <Folder aria-hidden="true" size={24} />
        <strong>Nenhum arquivo nesta tarefa</strong>
        <span>Arquivos criados ou editados pelo Vortax aparecem aqui com o conteúdo real.</span>
      </div>
    );
  }

  return (
    <div className={`vx-files ${treeOpen ? "tree-open" : ""}`}>
      <nav aria-label="Arquivos do workspace" className="vx-tree">
        <button aria-expanded={treeOpen} className="vx-tree__toggle" onClick={() => setTreeOpen((value) => !value)} type="button">
          <Folder aria-hidden="true" size={13} /> Arquivos ({files.length})
          {treeOpen ? <ChevronDown aria-hidden="true" size={13} /> : <ChevronRight aria-hidden="true" size={13} />}
        </button>
        <ul className="vx-tree__list">
          {tree.map((node) => (
            <TreeNode activePath={path} changes={changes} collapsed={collapsed} depth={0} key={node.path} node={node} onSelect={(next) => { computer.selectFile(next); setTreeOpen(false); }} onToggle={toggleDir} />
          ))}
        </ul>
      </nav>
      <section className="vx-file-view">
        {path ? (
          <header className="vx-file-view__head">
            <div>
              <strong title={path}>{shortPath(path, 56)}</strong>
              <span>{languageLabel(path)}{file?.size_bytes ?? file?.size ? ` · ${formatBytes(file.size_bytes ?? file.size)}` : ""}</span>
            </div>
            <div className="vx-file-view__meta">
              {header}
              {!followingAgent && !snapshotAction ? <span className="vx-chip">Escolhido por você</span> : null}
              {file ? (
                <a aria-label={`Baixar ${path}`} className="vx-icon-btn" download href={fileDownloadUrl(taskId, path)} title="Baixar arquivo"><Download size={15} /></a>
              ) : null}
            </div>
          </header>
        ) : null}
        <div className="vx-file-view__body">{body}</div>
      </section>
    </div>
  );
});

