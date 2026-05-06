import { useEffect, useMemo, useState } from "react";
import { MessageSquarePlus, Trash2 } from "lucide-react";

import { AgentActivity } from "./components/AgentActivity.jsx";
import { ChatShell } from "./components/ChatShell.jsx";
import { Composer } from "./components/Composer.jsx";
import { ConfirmDialog } from "./components/ConfirmDialog.jsx";
import { ContextIndicator } from "./components/ContextIndicator.jsx";
import { FileList } from "./components/FileList.jsx";
import { MessageList } from "./components/MessageList.jsx";
import { ScreenView } from "./components/ScreenView.jsx";
import { SourceList } from "./components/SourceList.jsx";
import { StatusBadge } from "./components/StatusBadge.jsx";
import { useWebSocket } from "./hooks/useWebSocket.js";
import {
  appendTaskMessage,
  appendTaskImages,
  confirmTask,
  createTask,
  createImageTask,
  deleteTask,
  getTask,
  healthcheck,
  listFiles,
  listProviders,
  listTasks,
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
  const [activeTask, setActiveTask] = useState(null);
  const [taskEvents, setTaskEvents] = useState([]);
  const [agentStatus, setAgentStatus] = useState("idle");
  const [tasks, setTasks] = useState([]);
  const [files, setFiles] = useState([]);
  const [sources, setSources] = useState([]);
  const [contextState, setContextState] = useState(null);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [pendingConfirmation, setPendingConfirmation] = useState(null);
  const { events, connectionState } = useWebSocket(activeTaskId);

  const currentEvents = events.length > 0 ? events : taskEvents;
  const messages = useMemo(() => buildMessages(activeTask, currentEvents), [activeTask, currentEvents]);
  const agentBusy = ["queued", "thinking", "executing", "running"].includes(agentStatus);

  useEffect(() => {
    healthcheck()
      .then(() => setBackendStatus("online"))
      .catch(() => setBackendStatus("offline"));
    listTasks()
      .then((data) => {
        const loadedTasks = data.tasks || [];
        setTasks(loadedTasks);
        if (loadedTasks.length > 0) {
          setActiveTaskId(loadedTasks[0].id);
        }
      })
      .catch(() => {});
    listFiles().then((data) => setFiles(data.files || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeTaskId) {
      setActiveTask(null);
      setTaskEvents([]);
      setSources([]);
      setContextState(null);
      setAgentStatus("idle");
      setPendingConfirmation(null);
      return;
    }

    getTask(activeTaskId)
      .then((data) => {
        const loadedTask = data.task || null;
        const loadedEvents = data.events || [];
        setActiveTask(loadedTask);
        setTaskEvents(loadedEvents);
        setSources(data.sources || []);
        setContextState(data.context || null);
        setAgentStatus(loadedTask?.status || "idle");

        const lastConfirmation = [...loadedEvents].reverse().find((event) => event.type === "confirmation_request");
        const lastConfirmationResult = [...loadedEvents].reverse().find((event) => event.type === "confirmation_result");
        setPendingConfirmation(lastConfirmation && !lastConfirmationResult ? lastConfirmation.payload : null);
      })
      .catch(() => {
        setActiveTask(null);
        setTaskEvents([]);
        setSources([]);
        setContextState(null);
        setAgentStatus("idle");
        setPendingConfirmation(null);
      });
  }, [activeTaskId]);

  useEffect(() => {
    if (!activeTaskId) return;

    const lastStatus = [...currentEvents].reverse().find((event) => event.type === "agent_status");
    if (lastStatus?.payload?.status) {
      const status = lastStatus.payload.status;
      setAgentStatus(status);
      setTasks((current) => current.map((task) => (task.id === activeTaskId ? { ...task, status } : task)));
      setActiveTask((current) => (current && current.id === activeTaskId ? { ...current, status } : current));
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

    if (currentEvents.some((event) => event.type === "tool_result" || event.type === "assistant_message_done" || event.type === "files_created")) {
      listFiles().then((data) => setFiles(data.files || [])).catch(() => {});
    }

    const lastFilesCreated = [...currentEvents].reverse().find((event) => event.type === "files_created");
    if (lastFilesCreated?.payload?.files) {
      setFiles((current) => {
        const byPath = new Map(current.map((f) => [f.path, f]));
        for (const f of lastFilesCreated.payload.files) {
          byPath.set(f.path, { ...(byPath.get(f.path) || {}), ...f });
        }
        return Array.from(byPath.values());
      });
    }
    const savedSources = currentEvents
      .filter((event) => event.type === "source_saved")
      .map((event) => event.payload);
    if (savedSources.length > 0) {
      setSources((current) => {
        const byUrl = new Map(current.map((source) => [source.url, source]));
        for (const source of savedSources) {
          byUrl.set(source.url, { ...(byUrl.get(source.url) || {}), ...source });
        }
        return Array.from(byUrl.values()).sort((a, b) => (b.quality_score || 0) - (a.quality_score || 0));
      });
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
      setSources([]);
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
    setSources([]);
    setContextState(null);
    setActiveTaskId(result.task_id);
  }

  async function handleConfirm(approved) {
    if (!activeTaskId) return;
    await confirmTask(activeTaskId, approved);
    setPendingConfirmation(null);
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
    setActiveTask(null);
    setTaskEvents([]);
    setSources([]);
    setContextState(null);
    setAgentStatus("idle");
    setPendingConfirmation(null);
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
            {tasks.length === 0 ? (
              <p className="muted">Nenhuma tarefa criada.</p>
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

          <SourceList sources={sources} />
          <FileList files={files} taskId={activeTaskId} hasFiles={files.length > 0} />
          <ConfirmDialog confirmation={pendingConfirmation} onAnswer={handleConfirm} />
        </>
      }
    />
  );
}
