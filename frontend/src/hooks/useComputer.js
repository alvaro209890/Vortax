import { useCallback, useEffect, useMemo, useState } from "react";

import { browserScene } from "../lib/browserScenes.js";
import { turnHeadline } from "../lib/activity.js";
import { previewEntry } from "../lib/workspace.js";

const PANES = ["browser", "files", "terminal", "preview"];

function latestWithPane(actions, pane) {
  for (let index = actions.length - 1; index >= 0; index -= 1) {
    if (!pane ? actions[index].pane : actions[index].pane === pane) return actions[index];
  }
  return null;
}

/**
 * Estado único do Computador do Vortax, compartilhado pelo dock e pelo painel.
 *
 * - "Ao vivo": a aba e o conteúdo seguem a ação mais recente do agente.
 * - Escolhas manuais (aba ou arquivo) são preservadas até "Seguir o agente".
 * - "Histórico": uma ação ou captura antiga escolhida no chat ou na linha do tempo;
 *   fica identificada como histórico até "Voltar à atividade atual".
 */
export function useComputer({ activity, agentStatus, events, files, taskId }) {
  const [selection, setSelection] = useState(null);
  const [userPane, setUserPane] = useState(null);
  const [userPath, setUserPath] = useState(null);
  const [userTerminalId, setUserTerminalId] = useState(null);

  useEffect(() => {
    setSelection(null);
    setUserPane(null);
    setUserPath(null);
    setUserTerminalId(null);
  }, [taskId]);

  const { actions, byId, frames: frameRefs, turns } = activity;
  const latestTurn = turns[turns.length - 1] || null;
  const headline = useMemo(() => turnHeadline(latestTurn), [latestTurn]);

  // Capturas e leituras do navegador da tarefa inteira (histórico navegável).
  const frames = useMemo(
    () => frameRefs.map((ref, frameIndex) => ({ ...browserScene(events[ref.eventIndex], frameIndex, ref.eventIndex), actionId: ref.actionId, turnIndex: ref.turnIndex })),
    [events, frameRefs],
  );

  const liveAction = useMemo(() => {
    const turnActions = latestTurn?.actions || [];
    const running = [...turnActions].reverse().find((action) => action.pane && ["running", "paused"].includes(action.status));
    return running || latestWithPane(turnActions) || latestWithPane(actions);
  }, [actions, latestTurn]);

  const selectedAction = selection?.actionId ? byId.get(selection.actionId) || null : null;
  const autoPane = liveAction?.pane || (frames.length ? "browser" : files.length ? "files" : "browser");
  const pane = selection?.pane || userPane || autoPane;
  const isHistory = Boolean(selection);
  const following = !selection && !userPane && !userPath && !userTerminalId;

  // ── Navegador ──
  const browser = useMemo(() => {
    let frameIndex = null;
    if (selection?.frameIndex !== undefined && selection?.frameIndex !== null) {
      frameIndex = selection.frameIndex;
    } else if (selectedAction && selectedAction.frames.length) {
      const lastEventIndex = selectedAction.frames[selectedAction.frames.length - 1];
      frameIndex = frames.findIndex((frame) => frame.eventIndex === lastEventIndex);
    } else if (selectedAction) {
      // Ação sem captura própria: mostra a última captura anterior a ela, identificada assim.
      const before = frames.filter((frame) => frame.eventIndex < selectedAction.startIndex);
      frameIndex = before.length ? before[before.length - 1].frameIndex : null;
    }
    const latestIndex = frames.length ? frames.length - 1 : null;
    const index = frameIndex ?? latestIndex;
    const scene = index === null ? null : frames[index];
    const owner = scene?.actionId ? byId.get(scene.actionId) : null;
    const liveBrowserAction = liveAction?.pane === "browser" ? liveAction : null;
    const active = !isHistory && Boolean(liveBrowserAction && ["running", "paused"].includes(liveBrowserAction.status));
    return {
      active,
      frameCount: frames.length,
      frameIndex: index,
      frames,
      owner,
      // Captura mais recente, mas o agente já está em outra ferramenta.
      stale: !isHistory && Boolean(scene) && !active && liveAction && liveAction.pane !== "browser",
      scene,
      waitingAction: active && liveBrowserAction && !liveBrowserAction.frames.length ? liveBrowserAction : null,
    };
  }, [byId, frames, isHistory, liveAction, selectedAction, selection]);

  // ── Arquivos ──
  const fileScene = useMemo(() => {
    const fileActions = actions.filter((action) => action.target?.type === "file");
    const liveFileAction = [...(latestTurn?.actions || [])].reverse().find((action) => action.target?.type === "file") || fileActions[fileActions.length - 1] || null;
    let path = null;
    let snapshotAction = null;
    if (selectedAction?.target?.type === "file") {
      path = selectedAction.target.value;
      snapshotAction = selectedAction;
    } else if (selection?.path) {
      path = selection.path;
    } else if (userPath) {
      path = userPath;
    } else if (liveFileAction) {
      path = liveFileAction.target.value;
    } else if (files.length) {
      path = files[0].path;
    }
    // Enquanto uma gravação está rodando, o arquivo ainda não tem o conteúdo novo.
    const pendingAction = !isHistory && !userPath && liveFileAction && liveFileAction.target.value === path && ["running", "paused"].includes(liveFileAction.status) && liveFileAction.family === "file"
      ? liveFileAction
      : null;
    const lastFileAction = [...fileActions].reverse().find((action) => action.target.value === path && action.family === "file" && action.status === "done") || null;
    return {
      followingAgent: !userPath && !selection?.path && !snapshotAction,
      lastFileAction,
      path,
      pendingAction,
      snapshotAction,
    };
  }, [actions, files, isHistory, latestTurn, selectedAction, selection, userPath]);

  // ── Terminal ──
  const terminal = useMemo(() => {
    const entries = actions.filter((action) => action.pane === "terminal");
    let actionId = null;
    if (selectedAction?.pane === "terminal") actionId = selectedAction.id;
    else if (userTerminalId && byId.has(userTerminalId)) actionId = userTerminalId;
    else if (entries.length) actionId = entries[entries.length - 1].id;
    return { action: actionId ? byId.get(actionId) : null, entries };
  }, [actions, byId, selectedAction, userTerminalId]);

  const preview = useMemo(() => ({ entry: previewEntry(files) }), [files]);

  const selectAction = useCallback((actionId) => {
    const action = byId.get(actionId);
    if (!action) return;
    setSelection({ actionId, pane: action.pane || "browser" });
  }, [byId]);

  const selectFrame = useCallback((frameIndex) => {
    if (frameIndex === null || frameIndex >= frames.length - 1) {
      setSelection((current) => (current?.frameIndex !== undefined || current?.pane === "browser" ? null : current));
      return;
    }
    setSelection({ frameIndex: Math.max(0, frameIndex), pane: "browser" });
  }, [frames.length]);

  const selectPane = useCallback((nextPane) => {
    if (!PANES.includes(nextPane)) return;
    setUserPane(nextPane === autoPane && !selection ? null : nextPane);
    setSelection((current) => (current && current.pane !== nextPane ? null : current));
  }, [autoPane, selection]);

  const selectFile = useCallback((path) => {
    setSelection((current) => (current?.pane === "files" ? null : current));
    setUserPath(path);
    setUserPane("files");
  }, []);

  const selectTerminal = useCallback((actionId) => {
    setSelection((current) => (current?.pane === "terminal" ? null : current));
    setUserTerminalId(actionId);
    setUserPane("terminal");
  }, []);

  const goLive = useCallback(() => {
    setSelection(null);
    setUserPane(null);
    setUserPath(null);
    setUserTerminalId(null);
  }, []);

  return {
    agentStatus,
    browser,
    files: fileScene,
    following,
    goLive,
    headline,
    isHistory,
    latestTurn,
    liveAction,
    pane,
    preview,
    selectAction,
    selectedAction,
    selectFile,
    selectFrame,
    selectPane,
    selectTerminal,
    selection,
    terminal,
  };
}
