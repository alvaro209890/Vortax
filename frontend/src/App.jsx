import { useEffect, useMemo, useState } from "react";
import { LogOut, MessageSquarePlus, PanelRightOpen, Trash2 } from "lucide-react";

import { useAuth } from "./auth/AuthProvider.jsx";
import { AiExchangePanel } from "./components/AgentActivity.jsx";
import { AuthScreen } from "./components/AuthScreen.jsx";
import { ChatShell } from "./components/ChatShell.jsx";
import { Composer } from "./components/Composer.jsx";
import { ConfirmDialog } from "./components/ConfirmDialog.jsx";
import { ContextIndicator } from "./components/ContextIndicator.jsx";
import { DocumentationPanel } from "./components/DocumentationPanel.jsx";
import { FileList } from "./components/FileList.jsx";
import { InlineTaskTimeline } from "./components/InlineTaskTimeline.jsx";
import { MessageList } from "./components/MessageList.jsx";
import { SourceList } from "./components/SourceList.jsx";
import { StatusBadge } from "./components/StatusBadge.jsx";
import { ActionTimeline } from "./components/ActionTimeline.jsx";
import { TaskDetailDrawer } from "./components/TaskDetailDrawer.jsx";
import { VortaxComputerDock } from "./components/VortaxComputerDock.jsx";
import { useTaskData } from "./hooks/useTaskData.js";
import { useTaskEvents } from "./hooks/useTaskEvents.js";
import { useTaskFiles } from "./hooks/useTaskFiles.js";
import { useLiveTaskPlan } from "./hooks/useLiveTaskPlan.js";
import { useTaskSources } from "./hooks/useTaskSources.js";
import {
  appendTaskMessage,
  appendTaskImages,
  confirmTask,
  createTask,
  createImageTask,
  deleteTask,
  healthcheck,
  listTasks,
  stopTask,
} from "./lib/api.js";

const welcomeMessage = {
  id: "welcome",
  role: "assistant",
  content: "Descreva uma tarefa e acompanhe o Vortax pesquisar, criar, revisar e entregar o resultado.",
};

function buildMessages(task, events, responseReady = true) {
  if (!task) return [welcomeMessage];

  // Durante uma nova execucao, preserva respostas anteriores da IA e esconde
  // apenas deltas/respostas gerados depois da ultima mensagem do usuario.
  const firstProgressIndex = events.findIndex(
    (e) => e.type === "agent_progress" || e.type === "tool_call",
  );
  const lastUserIndex = events.reduce(
    (latest, event, index) => (event.type === "user_message" ? index : latest),
    -1,
  );

  const assistantOk = (event, index) => {
    if (event.type === "user_message") return true;
    if (event.type === "assistant_message_done" || event.type === "assistant_message_delta") {
      if (!responseReady && index > lastUserIndex) return false;
      // So mostra se veio depois do agente comecar a trabalhar; conversas antigas
      // sem eventos de progresso continuam exibindo a resposta normalmente.
      return firstProgressIndex < 0 || index > firstProgressIndex;
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
      documents: event.payload.documents || (event.payload.documentation ? [{
        ...event.payload.documentation,
        kind: "markdown",
        previewable: true,
        primary: true,
        source: "documentation",
      }] : []),
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

function isAuthError(error) {
  return /autenticacao obrigatoria|token firebase|unauthorized|401/i.test(error?.message || "");
}

function agentStatusLabel(status) {
  const labels = {
    done: "Pronto",
    error: "Erro",
    executing: "Executando",
    idle: "Parado",
    paused: "Pausado",
    queued: "Na fila",
    running: "Rodando",
    stopped: "Pausado",
    thinking: "Pensando",
  };
  return labels[status] || status;
}

function latestEventIndex(events, predicate) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (predicate(events[index])) return index;
  }
  return -1;
}

const emptyDisplayPlan = {
  currentStep: null,
  doneCount: 0,
  failedCount: 0,
  hasSteps: false,
  isDirect: true,
  isTerminal: false,
  latestProgress: "",
  percent: 0,
  planKey: "empty",
  screenCount: 0,
  sourceCount: 0,
  steps: [],
  totalCount: 0,
  visibleSteps: [],
};

function likelyTaskPrompt(prompt = "") {
  const value = String(prompt || "").trim().toLowerCase();
  if (value.length >= 28) return true;
  return /(pesquis|busc|procure|not[ií]cia|crie|criar|gere|gerar|desenvolva|implemente|fa[cç]a|calcule|analise|compare|site|app|dashboard|relat[oó]rio|arquivo|imagem|pdf)/i.test(value);
}

function buildPendingPlan(prompt = "") {
  const now = new Date().toISOString();
  const detail = String(prompt || "").trim();
  return {
    currentStep: null,
    doneCount: 0,
    failedCount: 0,
    hasSteps: true,
    isGeneratingPlan: true,
    isDirect: false,
    isTerminal: false,
    latestProgress: "Criando plano de tarefas",
    percent: 0,
    planKey: `pending:${now}:${detail}`,
    screenCount: 0,
    sourceCount: 0,
    steps: [],
    totalCount: 0,
    visibleSteps: [],
  };
}

export default function App() {
  const { loading: authLoading, signOut, user } = useAuth();
  const [activeTaskId, setActiveTaskId] = useState(null);
  const [agentStatus, setAgentStatus] = useState("idle");
  const [tasks, setTasks] = useState([]);
  const [backendStatus, setBackendStatus] = useState("checking");
  const [tasksLoading, setTasksLoading] = useState(true);
  const [tasksError, setTasksError] = useState(null);
  const [stopping, setStopping] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [optimisticMessages, setOptimisticMessages] = useState([]);
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
  const livePlan = useLiveTaskPlan(initialPlan, currentEvents);
  const agentBusy = ["queued", "thinking", "executing", "running"].includes(agentStatus);
  const lastUserIndex = useMemo(
    () => latestEventIndex(currentEvents, (event) => event.type === "user_message"),
    [currentEvents],
  );
  const lastPlanIndex = useMemo(
    () => latestEventIndex(currentEvents, (event) => event.type === "task_plan_created" || event.type === "task_plan_replanned"),
    [currentEvents],
  );
  const latestUserEvent = lastUserIndex >= 0 ? currentEvents[lastUserIndex] : null;
  const hasPendingPlanForLatestUser = agentBusy && lastUserIndex > lastPlanIndex;
  const latestUserText = latestUserEvent?.payload?.content || "";
  const shouldShowPlanGeneration = hasPendingPlanForLatestUser && likelyTaskPrompt(latestUserText);
  const displayPlan = useMemo(
    () => (
      hasPendingPlanForLatestUser
        ? shouldShowPlanGeneration
          ? buildPendingPlan(latestUserText)
          : emptyDisplayPlan
        : livePlan
    ),
    [hasPendingPlanForLatestUser, latestUserText, livePlan, shouldShowPlanGeneration],
  );

  const messages = useMemo(() => {
    const pendingMessages = optimisticMessages.filter(
      (message) => !activeTaskId || message.taskId === activeTaskId || message.taskId === "new",
    );
    if (taskLoading) {
      return pendingMessages.length > 0
        ? pendingMessages
        : [{ id: "task-loading", role: "assistant", content: "Carregando conversa..." }];
    }
    if (taskError) {
      return [{ id: "task-error", role: "assistant", content: "Nao foi possivel carregar esta conversa." }];
    }
    const responseReady = !agentBusy || displayPlan.percent >= 100 || displayPlan.isTerminal;
    const builtMessages = buildMessages(activeTask, currentEvents, responseReady);
    if (pendingMessages.length === 0) return builtMessages;
    return builtMessages
      .filter((message) => message.id !== "welcome")
      .concat(pendingMessages.filter((pending) => !builtMessages.some((message) => (
        message.role === "user" && message.content === pending.content
      ))));
  }, [activeTask, activeTaskId, agentBusy, currentEvents, displayPlan.isTerminal, displayPlan.percent, optimisticMessages, taskError, taskLoading]);
  const showTyping = useMemo(
    () => shouldShowTyping(activeTask, currentEvents, agentBusy),
    [activeTask, agentBusy, currentEvents],
  );

  const activeSearch = useMemo(() => {
    const scopedEvents = lastUserIndex >= 0 ? currentEvents.slice(lastUserIndex + 1) : currentEvents;
    const reversed = [...scopedEvents].reverse();
    const lastSearchCall = reversed.find((e) => e.type === "tool_call" && e.payload?.name === "browser_google_search");
    if (!lastSearchCall) return null;
    const lastSearchResult = reversed.find((e) => e.type === "tool_result" && e.payload?.name === "browser_google_search");
    if (!lastSearchResult || lastSearchResult.created_at < lastSearchCall.created_at) {
      return {
        query: lastSearchCall.payload?.params?.query || "Buscando informações...",
      };
    }
    return null;
  }, [currentEvents, lastUserIndex]);

  useEffect(() => {
    if (authLoading || !user) return undefined;
    let cancelled = false;
    setTasksLoading(true);
    setTasksError(null);
    healthcheck()
      .then(() => {
        if (!cancelled) setBackendStatus("online");
      })
      .catch(() => {
        if (!cancelled) setBackendStatus("offline");
      });
    listTasks()
      .then((data) => {
        if (cancelled) return;
        setBackendStatus("online");
        const loadedTasks = data.tasks || [];
        setTasks(loadedTasks);
        setTasksError(null);
        if (loadedTasks.length > 0) {
          setActiveTaskId(loadedTasks[0].id);
        } else {
          setActiveTaskId(null);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          if (isAuthError(error)) {
            setBackendStatus("online");
            signOut();
          }
          setTasksError(error);
        }
      })
      .finally(() => {
        if (!cancelled) setTasksLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, signOut, user]);

  useEffect(() => {
    if (user) return;
    setActiveTaskId(null);
    setTasks([]);
    setTasksLoading(true);
    setTasksError(null);
    setBackendStatus("checking");
    resetTaskData();
    setAgentStatus("idle");
  }, [resetTaskData, user]);

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

  useEffect(() => {
    if (!activeTaskId || optimisticMessages.length === 0 || currentEvents.length === 0) return;
    setOptimisticMessages((current) => current.filter((message) => {
      if (message.taskId !== activeTaskId) return true;
      return !currentEvents.some((event) => (
        event.type === "user_message" && event.payload?.content === message.content
      ));
    }));
  }, [activeTaskId, currentEvents, optimisticMessages.length]);

  async function handleSubmit(description, files = []) {
    setAgentStatus("queued");
    const now = new Date().toISOString();
    const optimisticId = `optimistic-user-${now}`;
    const optimisticTaskId = activeTaskId || "new";
    const optimisticContent = description || (files.length > 0 ? "Analise esta imagem." : "");
    if (optimisticContent) {
      setOptimisticMessages((current) => [
        ...current,
        {
          id: optimisticId,
          role: "user",
          content: optimisticContent,
          taskId: optimisticTaskId,
        },
      ]);
    }
    if (files.length > 0) {
      if (activeTaskId) {
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
        setOptimisticMessages((current) => current.filter((message) => message.id !== optimisticId));
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
      setOptimisticMessages((current) => current.filter((message) => message.id !== optimisticId));
      setTasks((current) => [result.task, ...current]);
      setActiveTask(result.task);
      setTaskEvents([]);
      setContextState(null);
      setActiveTaskId(result.task_id);
      setAgentStatus("done");
      return;
    }

    if (activeTaskId) {
      setTaskEvents((current) => [
        ...current,
        {
          type: "user_message",
          task_id: activeTaskId,
          created_at: new Date().toISOString(),
          payload: { content: description },
        },
      ]);
      try {
        await appendTaskMessage(activeTaskId, description);
      } finally {
        setOptimisticMessages((current) => current.filter((message) => message.id !== optimisticId));
      }
      return;
    }

    const result = await createTask(description);
    setOptimisticMessages((current) => current.map((message) => (
      message.id === optimisticId ? { ...message, taskId: result.task_id } : message
    )));
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

  if (authLoading) {
    return (
      <main className="auth-page auth-loading">
        <div className="auth-loading-card">
          <img src="/vortax-logo.png" alt="Vortax" />
          <span>Carregando acesso...</span>
        </div>
      </main>
    );
  }

  if (!user) return <AuthScreen />;

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
                <div className="chat-brand-mark">
                  <img className="chat-brand-logo" src="/vortax-logo.png" alt="Vortax" />
                </div>
                <div className="chat-header-text">
                  <div className="chat-brand-line">
                    <strong>Vortax</strong>
                    <span>Lite</span>
                  </div>
                  <small>{activeTask?.description || "Agente autonomo para pesquisar, criar e validar tarefas"}</small>
                </div>
              </div>
              <div className="chat-header-actions">
                <button
                  className="detail-open-btn"
                  onClick={() => setDetailsOpen(true)}
                  title="Abrir detalhes"
                  type="button"
                >
                  <PanelRightOpen size={16} />
                  <span>Detalhes</span>
                </button>
                <div className="chat-health-group">
                  <ContextIndicator context={contextState} />
                  <StatusBadge status={agentStatus} label={agentStatusLabel(agentStatus)} />
                </div>
                <button className="user-menu-btn" onClick={signOut} title="Sair" type="button">
                  <span>{user.displayName || user.email || "Usuario"}</span>
                  <LogOut size={15} />
                </button>
              </div>
            </header>
            <MessageList
              activeSearch={activeSearch}
              activity={displayPlan.hasSteps && !displayPlan.isDirect ? (
                <InlineTaskTimeline
                  livePlan={displayPlan}
                  showEmpty={false}
                />
              ) : null}
              activityVersion={displayPlan.planKey}
              isTyping={showTyping}
              messages={messages}
            />
            <VortaxComputerDock
              activeTask={activeTask}
              agentStatus={agentStatus}
              connectionState={connectionState}
              events={currentEvents}
              livePlan={displayPlan}
              onOpenDetails={() => setDetailsOpen(true)}
            />
            <Composer
              disabled={backendStatus !== "online"}
              isBusy={agentBusy}
              onStop={handleStop}
              onSubmit={handleSubmit}
              stopping={stopping}
            />
          </>
        }
      />
      <TaskDetailDrawer open={detailsOpen} onClose={() => setDetailsOpen(false)}>
        <DocumentationPanel files={files} taskId={activeTaskId} />
        <AiExchangePanel events={currentEvents} />
        <ActionTimeline events={currentEvents} />
        <SourceList error={taskError} loading={taskLoading} sources={sources} />
        <FileList error={filesError} files={files} loading={taskLoading || filesLoading} taskId={activeTaskId} />
      </TaskDetailDrawer>
      <ConfirmDialog confirmation={pendingConfirmation} onAnswer={handleConfirm} />
    </>
  );
}
