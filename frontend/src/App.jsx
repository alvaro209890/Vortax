import { useEffect, useMemo, useState } from "react";
import { MessageSquarePlus, StopCircle, Trash2 } from "lucide-react";

import { AgentActivity } from "./components/AgentActivity.jsx";
import { ChatShell } from "./components/ChatShell.jsx";
import { Composer } from "./components/Composer.jsx";
import { ConfirmDialog } from "./components/ConfirmDialog.jsx";
import { ContextIndicator } from "./components/ContextIndicator.jsx";
import { FileList } from "./components/FileList.jsx";
import { MessageList } from "./components/MessageList.jsx";
import { PreviewPanel } from "./components/PreviewPanel.jsx";
import { ScreenView } from "./components/ScreenView.jsx";
import { SourceList } from "./components/SourceList.jsx";
import { StatusBadge } from "./components/StatusBadge.jsx";
import { ActionTimeline } from "./components/ActionTimeline.jsx";
import { useTaskData } from "./hooks/useTaskData.js";
import { useTaskEvents } from "./hooks/useTaskEvents.js";
import { useTaskFiles } from "./hooks/useTaskFiles.js";
import { useTaskSources } from "./hooks/useTaskSources.js";
import {
  appendTaskMessage,
  appendTaskImages,
  confirmTask,
  createTask,
  createImageTask,
  deleteTask,
  healthcheck,
  listProviders,
  listTasks,
  stopTask,
} from "./lib/api.js";

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  content: "Envie uma tarefa para validar o chat local e acompanhar o stream de execucao.",
};

function buildMessages(task, events) {
  if (!task) return [welcomeMessage];
  const messages = events
    .filter((event) => event.type === "user_message" || event.type === "assistant_message_delta" || event.type === "assistant_message_done")
    .map((event, index) => ({
      id: `${event.type}-${event.created_at}-${index}`,
      role: event.type === "user_message" ? "user" : "assistant",
      content: event.payload.content,
      images: event.payload.images || [],
    }));

  if (messages.length > 0) return messages;
  return [{ id: `user-${task.id}`, role: "user", content: task.description }];
}

export default function App() {
  const [activeTaskId, setActiveTaskId] = useState(null);
  const [agentStatus, setAgentStatus] = useState("idle");
  const [tasks, setTasks] = useState([]);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [tasksLoading, setTasksLoading] = useState(true);
  const [tasksError, setTasksError] = useState(null);
  const [stopping, setStopping] = useState(false);
  const {
    activeTask,
    contextState,
    error: taskError,
    initialFiles,
    initialSources,
    loading: taskLoading,
    pendingConfirmation,
    resetTaskData,
    setActiveTask,
    setContextState,
    setPendingConfirmation,
    setTaskEvents,
    taskEvents,
  } = useTaskData(activeTaskId);
  const { connectionState, currentEvents } = useTaskEvents(activeTaskId, taskEvents);
  const { error: filesError, files, loading: filesLoading } = useTaskFiles(activeTaskId, currentEvents, initialFiles);
  const { sources } = useTaskSources(activeTaskId, currentEvents, initialSources);

  const messages = useMemo(() => {
    if (taskLoading) {
      return [{ id: "task-loading", role: "assistant", content: "Carregando conversa..." }];
    }
    if (taskError) {
      return [{ id: "task-error", role: "assistant", content: "Nao foi possivel carregar esta conversa." }];
    }
    return buildMessages(activeTask, currentEvents);
  }, [activeTask, currentEvents, taskError, taskLoading]);
  const agentBusy = ["queued", "thinking", "executing", "running"].includes(agentStatus);

  useEffect(() => {
    healthcheck()
      .then(() => setBackendStatus("online"))
      .catch(() => setBackendStatus("offline"));
    listTasks()
      .then((data) => {
        const loadedTasks = data.tasks || [];
        setTasks(loadedTasks);
        setTasksError(null);
        if (loadedTasks.length > 0) {
          setActiveTaskId(loadedTasks[0].id);
        }
      })
      .catch((error) => setTasksError(error))
      .finally(() => setTasksLoading(false));
  }, []);

  useEffect(() => {
    if (!activeTaskId) {
      resetTaskData();
      setAgentStatus("idle");
    } else if (activeTask?.status) {
      setAgentStatus(activeTask.status);
    }
  }, [activeTaskId, activeTask?.status, resetTaskData]);

  useEffect(() => {
    if (!activeTaskId) return;

    const lastStatus = [...currentEvents].reverse().find((event) => event.type === "agent_status");
    if (lastStatus?.payload?.status) {
      const status = lastStatus.payload.status;
      setAgentStatus(status);
      setTasks((current) => current.map((task) => (task.id === activeTaskId ? { ...task, status } : task)));
      setActiveTask((current) => (current && current.id === activeTaskId ? { ...current, status } : current));
      if (status === "stopped" || status === "done" || status === "error" || status === "idle") {
        setStopping(false);
      }
    }

    const lastConfirmation = [...currentEvents].reverse().find((event) => event.type === "confirmation_request");
    const lastConfirmationResult = [...currentEvents].reverse().find((event) => event.type === "confirmation_result");
    setPendingConfirmation(lastConfirmation && !lastConfirmationResult ? lastConfirmation.payload : null);

    const lastContext = [...currentEvents]
      .reverse()
      .find((event) => event.type === "context_status" || event.type === "context_compacted");
    if (lastContext?.payload) {
      setContextState(lastContext.payload);
    }

  }, [activeTaskId, currentEvents]);

  async function handleSubmit(description, files = []) {
    setAgentStatus("queued");
    if (files.length > 0) {
      if (activeTaskId) {
        const result = await appendTaskImages(activeTaskId, description, files);
        const now = new Date().toISOString();
        setTaskEvents((current) => [
          ...current,
          {
            type: "user_message",
            task_id: activeTaskId,
            created_at: now,
            payload: {
              content: description || "Analise esta imagem.",
              images: result.images?.map((image) => ({
                filename: image.filename,
                content_type: image.content_type,
                image_base64: image.image_base64,
              })) || [],
            },
          },
          {
            type: "assistant_message_done",
            task_id: activeTaskId,
            created_at: new Date().toISOString(),
            payload: { content: result.answer },
          },
        ]);
        setAgentStatus("done");
        return;
      }

      const result = await createImageTask(description, files);
      setTasks((current) => [result.task, ...current]);
      setActiveTask(result.task);
      setTaskEvents([]);
      setContextState(null);
      setActiveTaskId(result.task_id);
      setAgentStatus("done");
      return;
    }

    if (activeTaskId) {
      await appendTaskMessage(activeTaskId, description);
      setTaskEvents((current) => [
        ...current,
        {
          type: "user_message",
          task_id: activeTaskId,
          created_at: new Date().toISOString(),
          payload: { content: description },
        },
      ]);
      return;
    }

    const result = await createTask(description);
    setTasks((current) => [result.task, ...current]);
    setActiveTask(result.task);
    setTaskEvents([]);
    setContextState(null);
    setActiveTaskId(result.task_id);
  }

  async function handleConfirm(approved) {
    if (!activeTaskId) return;
    await confirmTask(activeTaskId, approved);
    setPendingConfirmation(null);
  }

  async function handleStop() {
    if (!activeTaskId) return;
    setStopping(true);
    try {
      await stopTask(activeTaskId);
    } catch {
      setStopping(false);
    }
  }

  async function handleDeleteTask(taskId) {
    if (!window.confirm("Excluir este chat e apagar o historico salvo no banco de dados?")) return;

    await deleteTask(taskId);

    setTasks((current) => {
      const remaining = current.filter((task) => task.id !== taskId);
      if (activeTaskId === taskId) {
        setActiveTaskId(remaining[0]?.id || null);
      }
      return remaining;
    });
  }

  function handleNewChat() {
    setActiveTaskId(null);
    resetTaskData();
    setAgentStatus("idle");
  }

  return (
    <ChatShell
      sidebar={
        <>
          <div className="brand">
            <div className="brand-mark">V</div>
            <div>
              <strong>Vortax</strong>
              <span>LAN MVP</span>
            </div>
          </div>
          <StatusBadge status={backendStatus} label={`Backend ${backendStatus}`} />

          <div className="task-list">
            <div className="task-list-header">
              <span className="panel-label">Conversas</span>
              <button onClick={handleNewChat} title="Novo chat" type="button">
                <MessageSquarePlus size={15} />
              </button>
            </div>
            {tasksLoading ? (
              <p className="panel-state">Carregando conversas...</p>
            ) : tasksError ? (
              <p className="panel-state error">Nao foi possivel carregar conversas.</p>
            ) : tasks.length === 0 ? (
              <p className="panel-state">Nenhuma conversa criada.</p>
            ) : (
              tasks.map((task) => (
                <div
                  className={`task-item ${task.id === activeTaskId ? "active" : ""}`}
                  key={task.id}
                  onClick={() => setActiveTaskId(task.id)}
                >
                  <div className="task-content">
                    <span>{task.description}</span>
                    <small>{task.status}</small>
                  </div>
                  <button
                    className="task-delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteTask(task.id);
                    }}
                    title="Excluir chat"
                    type="button"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))
            )}
          </div>
        </>
      }
      main={
        <>
          <header className="chat-header">
            <div>
              <span className="panel-label">Chat local</span>
              <h1>Controle este PC pela rede local</h1>
            </div>
            <div className="chat-header-actions">
              {agentBusy && (
                <button
                  className="stop-btn"
                  onClick={handleStop}
                  disabled={stopping}
                  title="Interromper tarefa"
                  type="button"
                >
                  <StopCircle size={16} />
                  <span>{stopping ? "Parando..." : "Parar"}</span>
                </button>
              )}
              <ContextIndicator context={contextState} />
              <StatusBadge status={agentStatus} label={agentStatus} />
            </div>
          </header>
          <MessageList messages={messages} />
          <AgentActivity events={currentEvents} status={agentStatus} taskDescription={activeTask?.description} />
          <Composer disabled={backendStatus !== "online" || agentBusy} onSubmit={handleSubmit} />
        </>
      }
      inspector={
        <>
          <ScreenView events={currentEvents} connectionState={connectionState} />
          <ActionTimeline events={currentEvents} />
          <PreviewPanel files={files} events={currentEvents} taskId={activeTaskId} />
          <SourceList error={taskError} loading={taskLoading} sources={sources} />
          <FileList error={filesError} files={files} loading={taskLoading || filesLoading} taskId={activeTaskId} />
          <ConfirmDialog confirmation={pendingConfirmation} onAnswer={handleConfirm} />
        </>
      }
    />
  );
}
