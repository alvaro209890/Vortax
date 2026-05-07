import { useEffect, useMemo, useState } from "react";
import { MessageSquarePlus, StopCircle, Trash2 } from "lucide-react";

import { AgentActivity, AiExchangePanel, VertexProgressPanel } from "./components/AgentActivity.jsx";
import { ChatShell } from "./components/ChatShell.jsx";
import { Composer } from "./components/Composer.jsx";
import { ConfirmDialog } from "./components/ConfirmDialog.jsx";
import { ContextIndicator } from "./components/ContextIndicator.jsx";
import { DocumentationPanel } from "./components/DocumentationPanel.jsx";
import { FileList } from "./components/FileList.jsx";
import { MessageList } from "./components/MessageList.jsx";
import { ScreenView } from "./components/ScreenView.jsx";
import { SourceList } from "./components/SourceList.jsx";
import { StatusBadge } from "./components/StatusBadge.jsx";
import { ActionTimeline } from "./components/ActionTimeline.jsx";
import { TaskPlanPanel } from "./components/TaskPlanPanel.jsx";
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
  content: "Descreva uma tarefa e acompanhe o Vortax pesquisar, criar, revisar e entregar o resultado.",
};

function buildMessages(task, events) {
  if (!task) return [welcomeMessage];

  // So mostra mensagens do assistant apos o agente comecar a executar de fato
  // (evita resposta vazia aparecer antes das tasks carregarem)
  const firstProgressIndex = events.findIndex(
    (e) => e.type === "agent_progress" || e.type === "tool_call",
  );

  const assistantOk = (event, index) => {
    if (event.type === "user_message") return true;
    if (event.type === "assistant_message_done" || event.type === "assistant_message_delta") {
      // So mostra se veio depois do agente comecar a trabalhar
      return firstProgressIndex >= 0 && index > firstProgressIndex;
    }
    return false;
  };

  const messages = events
    .filter((event, index) => assistantOk(event, index))
    .map((event, index) => ({
      id: `${event.type}-${event.created_at}-${index}`,
      role: event.type === "user_message" ? "user" : "assistant",
      content: event.payload.content,
      downloads: event.payload.downloads || [],
      documentation: event.payload.documentation || null,
      images: event.payload.images || [],
      taskId: event.task_id || task.id,
    }));

  if (messages.length > 0) return messages;
  return [{ id: `user-${task.id}`, role: "user", content: task.description }];
}

function shouldShowTyping(task, events, agentBusy) {
  if (!task || !agentBusy) return false;
  if (events.length === 0) return true;

  let lastUserIndex = -1;
  let lastAssistantDoneIndex = -1;
  events.forEach((event, index) => {
    if (event.type === "user_message") lastUserIndex = index;
    if (event.type === "assistant_message_done") lastAssistantDoneIndex = index;
  });

  return lastUserIndex === -1 || lastAssistantDoneIndex < lastUserIndex;
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
    initialPlan,
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
  const showTyping = useMemo(
    () => shouldShowTyping(activeTask, currentEvents, agentBusy),
    [activeTask, agentBusy, currentEvents],
  );

  const activeSearch = useMemo(() => {
    const reversed = [...currentEvents].reverse();
    const lastSearchCall = reversed.find(e => e.type === "tool_call" && e.payload?.name === "browser_google_search");
    if (!lastSearchCall) return null;
    const lastSearchResult = reversed.find(e => e.type === "tool_result" && e.payload?.name === "browser_google_search");
    if (!lastSearchResult || lastSearchResult.created_at < lastSearchCall.created_at) {
      return {
        query: lastSearchCall.payload?.params?.query || "Buscando informações...",
      };
    }
    return null;
  }, [currentEvents]);

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
        const now = new Date().toISOString();
        setTaskEvents((current) => [
          ...current,
          {
            type: "user_message",
            task_id: activeTaskId,
            created_at: now,
            payload: {
              content: description || "Analise esta imagem.",
              images: files.map((file) => ({
                filename: file.name,
                content_type: file.type,
                image_base64: "",
              })),
            },
          },
        ]);
        const result = await appendTaskImages(activeTaskId, description, files);
        setTaskEvents((current) => [
          ...current.filter((event) => !(event.type === "user_message" && event.created_at === now)),
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
    <>
      <ChatShell
      sidebar={
        <>
          <div className="brand">
            <img className="brand-logo" src="/vortax-logo.png" alt="Vortax" />
            <div>
              <strong>Vortax</strong>
              <span>Agente autonomo</span>
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
            <div className="chat-header-left">
              <div className="chat-header-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" opacity="0.2" fill="currentColor"/>
                  <path d="M12 2a10 10 0 0 1 7 17.3M12 2a10 10 0 0 0-7 17.3M12 2v20M12 22a10 10 0 0 1-7-17.3M12 22a10 10 0 0 0 7-17.3"/>
                  <circle cx="12" cy="12" r="3"/>
                  <path d="M12 9v6M9 12h6"/>
                </svg>
              </div>
              <div className="chat-header-text">
                <span className="chat-header-badge">Agente IA</span>
                <h1>Crie, pesquise e <mark>execute</mark> tarefas com IA</h1>
              </div>
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
          <MessageList isTyping={showTyping} messages={messages} activeSearch={activeSearch} />
          <AgentActivity events={currentEvents} status={agentStatus} taskDescription={activeTask?.description} />
          <Composer disabled={backendStatus !== "online" || agentBusy} onSubmit={handleSubmit} />
        </>
      }
      inspector={
        <>
          <ScreenView events={currentEvents} connectionState={connectionState} />
          <DocumentationPanel files={files} taskId={activeTaskId} />
          <AiExchangePanel events={currentEvents} />
          <TaskPlanPanel events={currentEvents} initialPlan={initialPlan} />
          <ActionTimeline events={currentEvents} />
          <SourceList error={taskError} loading={taskLoading} sources={sources} />
          <FileList error={filesError} files={files} loading={taskLoading || filesLoading} taskId={activeTaskId} />
          <ConfirmDialog confirmation={pendingConfirmation} onAnswer={handleConfirm} />
        </>
      }
      />
      <VertexProgressPanel events={currentEvents} taskDescription={activeTask?.description} />
    </>
  );
}
