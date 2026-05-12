import { useEffect, useMemo, useRef, useState } from "react";
import { LogOut, MessageSquarePlus, PanelRightOpen, Settings, Trash2 } from "lucide-react";

import { useAuth } from "./auth/AuthProvider.jsx";
import { AiExchangePanel } from "./components/AgentActivity.jsx";
import { AuthScreen } from "./components/AuthScreen.jsx";
import { ChatShell } from "./components/ChatShell.jsx";
import { Composer } from "./components/Composer.jsx";
import { AlertDialog } from "./components/AlertDialog.jsx";
import { ConfirmDialog } from "./components/ConfirmDialog.jsx";
import { ContextIndicator } from "./components/ContextIndicator.jsx";
import { DocumentationPanel } from "./components/DocumentationPanel.jsx";
import { FileList } from "./components/FileList.jsx";
import { MessageList } from "./components/MessageList.jsx";
import { SecureCredentialsDialog } from "./components/SecureCredentialsDialog.jsx";
import { SourceList } from "./components/SourceList.jsx";
import { StatusBadge } from "./components/StatusBadge.jsx";
import { ActionTimeline } from "./components/ActionTimeline.jsx";
import { TaskDetailDrawer } from "./components/TaskDetailDrawer.jsx";
import { VortaxComputerDock } from "./components/VortaxComputerDock.jsx";
import { OnboardingScreen } from "./components/OnboardingScreen.jsx";
import { SettingsPanel, loadUserProfile } from "./components/SettingsPanel.jsx";
import { useTaskData } from "./hooks/useTaskData.js";
import { useTaskEvents } from "./hooks/useTaskEvents.js";
import { useTaskFiles } from "./hooks/useTaskFiles.js";
import { buildLiveTaskPlan, useLiveTaskPlan } from "./hooks/useLiveTaskPlan.js";
import { useTaskSources } from "./hooks/useTaskSources.js";
import {
  appendTaskMessage,
  appendTaskImages,
  confirmTask,
  createTask,
  createAuthorizedTask,
  authorizeTask,
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

function normalizeMessageContent(content = "") {
  return String(content || "").replace(/\s+/g, " ").trim();
}

function messageTimestamp(message) {
  const value = message?.createdAt ? new Date(message.createdAt).getTime() : NaN;
  return Number.isFinite(value) ? value : null;
}

function eventTimestamp(event) {
  const value = event?.created_at ? new Date(event.created_at).getTime() : NaN;
  return Number.isFinite(value) ? value : null;
}

function hasEventIndex(message) {
  return Number.isFinite(message?.eventIndex);
}

function isOptimisticMessage(message) {
  return String(message?.id || "").startsWith("optimistic-user-");
}

function isFallbackUserMessage(message) {
  return message?.role === "user"
    && !hasEventIndex(message)
    && String(message?.id || "").startsWith("user-");
}

function isDuplicateUserMessage(candidate, existing) {
  if (candidate?.role !== "user" || existing?.role !== "user") return false;
  const candidateClientId = String(candidate.clientMessageId || "").trim();
  const existingClientId = String(existing.clientMessageId || "").trim();
  if (candidateClientId && existingClientId) return candidateClientId === existingClientId;
  if (candidateClientId || existingClientId) return false;

  const candidateContent = normalizeMessageContent(candidate.content);
  const existingContent = normalizeMessageContent(existing.content);
  if (!candidateContent || candidateContent !== existingContent) return false;

  const candidateTask = candidate.taskId;
  const existingTask = existing.taskId;
  if (candidateTask && existingTask && candidateTask !== existingTask && candidateTask !== "new" && existingTask !== "new") {
    return false;
  }

  const candidateTime = messageTimestamp(candidate);
  const existingTime = messageTimestamp(existing);
  if (candidateTime !== null && existingTime !== null) {
    return Math.abs(candidateTime - existingTime) < 20000;
  }

  return String(candidate.id || "").startsWith("optimistic-user-")
    || String(existing.id || "").startsWith("optimistic-user-")
    || String(candidate.id || "").startsWith("user-")
    || String(existing.id || "").startsWith("user-");
}

function shouldPreferDuplicate(candidate, existing) {
  if (hasEventIndex(candidate) && !hasEventIndex(existing)) return true;
  if (isOptimisticMessage(existing) && !isOptimisticMessage(candidate)) return true;
  if (isFallbackUserMessage(existing) && isOptimisticMessage(candidate)) return true;
  if (isFallbackUserMessage(candidate) && !isFallbackUserMessage(existing)) return false;
  return false;
}

function dedupeMessagesForDisplay(messages = []) {
  return messages.reduce((visible, message) => {
    let duplicateIndex = -1;
    for (let index = visible.length - 1; index >= 0; index -= 1) {
      if (isDuplicateUserMessage(message, visible[index])) {
        duplicateIndex = index;
        break;
      }
    }

    if (duplicateIndex < 0) return [...visible, message];

    const previous = visible[duplicateIndex];
    if (!shouldPreferDuplicate(message, previous)) return visible;

    const next = [...visible];
    next[duplicateIndex] = message;
    return next;
  }, []);
}

function buildMessages(task, events, responseReady = true, options = {}) {
  if (!task) return [welcomeMessage];
  const includeFallback = options.includeFallback !== false;

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
    .map((event, eventIndex) => ({ event, eventIndex }))
    .filter(({ event, eventIndex }) => assistantOk(event, eventIndex))
    .map(({ event, eventIndex }) => ({
      id: `${event.type}-${event.created_at}-${eventIndex}`,
      eventIndex,
      role: event.type === "user_message" ? "user" : "assistant",
      content: event.payload.content,
      createdAt: event.created_at,
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
      clientMessageId: event.payload.client_message_id || "",
  }));

  if (messages.length > 0) return dedupeMessagesForDisplay(messages);
  if (!includeFallback) return [];
  return [{ id: `user-${task.id}`, role: "user", content: task.description, taskId: task.id }];
}

function taskPromptForEvent(events, eventIndex) {
  for (let index = eventIndex; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type === "user_message") return event.payload?.content || "";
  }
  return "";
}

function buildPlanSegments(events, initialPlan, livePlan, agentBusy, latestUserText, shouldShowPlanGeneration) {
  const planIndexes = events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => event.type === "task_plan_created" || event.type === "task_plan_replanned");

  const segments = planIndexes.map(({ index }, segmentIndex) => {
    const nextIndex = planIndexes[segmentIndex + 1]?.index ?? events.length;
    const scopedEvents = events.slice(index, nextIndex);
    const plan = segmentIndex === planIndexes.length - 1
      ? livePlan
      : buildLiveTaskPlan({ steps: [] }, scopedEvents);
    return {
      anchorEventIndex: index,
      id: `plan-${events[index]?.created_at || index}`,
      plan,
    };
  }).filter((segment) => segment.plan.hasSteps && !segment.plan.isDirect);

  const latestPlanIndex = planIndexes[planIndexes.length - 1]?.index ?? -1;
  const latestUserIndex = latestEventIndex(events, (event) => event.type === "user_message");
  if (agentBusy && latestUserIndex > latestPlanIndex && shouldShowPlanGeneration) {
    segments.push({
      anchorEventIndex: latestUserIndex,
      id: `pending-${events[latestUserIndex]?.created_at || latestUserIndex}`,
      plan: buildPendingPlan(latestUserText),
    });
  }
  return segments;
}

function buildMessagesWithPlanAnchors(task, events, responseReady, planSegments = [], options = {}) {
  const messages = buildMessages(task, events, responseReady, options);
  if (!messages.length || !planSegments.length) return messages;
  return messages.map((message) => {
    if (message.role !== "assistant") return message;
    const anchor = planSegments
      .filter((segment) => segment.anchorEventIndex < message.eventIndex)
      .at(-1);
    if (!anchor) return message;
    return { ...message, planSegmentId: anchor.id };
  });
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
  return /(pesquis|busc|procure|not[ií]cia|crie|criar|construa|monte|gere|gerar|desenvolv|implemente|program|c[oó]digo|fa[cç]a|calcule|analise|compare|investigue|verifique|colete|acesse|site|app|dashboard|relat[oó]rio|arquivo|imagem|pdf|planilha|documento|automatize|corrija|edite|altere|melhore|otimize|publique|execute|rode|instale)/i.test(value);
}

function isProgressHandoffEvent(event) {
  return event?.type === "agent_activity"
    || event?.type === "agent_progress"
    || event?.type === "tool_call"
    || event?.type === "tool_result"
    || event?.type === "source_saved"
    || event?.type === "screen_frame"
    || event?.type === "vertex_progress"
    || event?.type === "files_created"
    || event?.type?.startsWith("task_step_");
}

function matchingUserEventIndex(events, pendingPreparation) {
  if (!pendingPreparation?.content) return -1;
  const pendingContent = normalizeMessageContent(pendingPreparation.content);
  const pendingClientId = String(pendingPreparation.clientMessageId || "").trim();
  const pendingTime = messageTimestamp(pendingPreparation);
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event?.type !== "user_message") continue;
    const eventClientId = String(event.payload?.client_message_id || "").trim();
    if (pendingClientId && eventClientId) {
      if (pendingClientId === eventClientId) return index;
      continue;
    }
    const currentTime = eventTimestamp(event);
    if (pendingTime !== null && currentTime !== null && currentTime < pendingTime - 2000) {
      continue;
    }
    if (
      pendingPreparation.taskId
      && pendingPreparation.taskId !== "new"
      && event.task_id
      && event.task_id !== pendingPreparation.taskId
    ) {
      continue;
    }
    const eventContent = normalizeMessageContent(event.payload?.content);
    if (eventContent === pendingContent) return index;
  }
  return -1;
}

function eventMatchesOptimisticMessage(event, message) {
  if (event?.type !== "user_message") return false;
  const eventClientId = String(event.payload?.client_message_id || "").trim();
  const messageClientId = String(message?.clientMessageId || "").trim();
  if (eventClientId && messageClientId) return eventClientId === messageClientId;
  if (eventClientId || messageClientId) return false;
  if (normalizeMessageContent(event.payload?.content) !== normalizeMessageContent(message?.content)) return false;
  if (
    message?.taskId
    && message.taskId !== "new"
    && event.task_id
    && event.task_id !== message.taskId
  ) {
    return false;
  }

  const messageTime = messageTimestamp(message);
  const currentTime = eventTimestamp(event);
  return !(messageTime !== null && currentTime !== null && currentTime < messageTime - 2000);
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
  const [sidebarTab, setSidebarTab] = useState("chats");
  const [backendStatus, setBackendStatus] = useState("checking");
  const [tasksLoading, setTasksLoading] = useState(true);
  const [tasksError, setTasksError] = useState(null);
  const [stopping, setStopping] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [secureLoginOpen, setSecureLoginOpen] = useState(false);
  const [computerFocusRequest, setComputerFocusRequest] = useState(null);
  const [optimisticMessages, setOptimisticMessages] = useState([]);
  const [pendingPreparation, setPendingPreparation] = useState(null);
  const [taskToDelete, setTaskToDelete] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const prevAgentStatusRef = useRef(null);
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
  const planSegments = useMemo(
    () => buildPlanSegments(currentEvents, initialPlan, livePlan, agentBusy, latestUserText, shouldShowPlanGeneration),
    [agentBusy, currentEvents, initialPlan, latestUserText, livePlan, shouldShowPlanGeneration],
  );

  const displayPlan = useMemo(
    () => {
      const latestPromptSegments = planSegments.filter((segment) => (
        lastUserIndex < 0 || segment.anchorEventIndex >= lastUserIndex
      ));
      return latestPromptSegments.length > 0
        ? latestPromptSegments[latestPromptSegments.length - 1].plan
        : emptyDisplayPlan;
    },
    [lastUserIndex, planSegments],
  );

  const filteredTasks = useMemo(() => {
    if (!searchQuery.trim()) return tasks;
    const q = searchQuery.toLowerCase();
    return tasks.filter((task) => (task.title || task.description || "").toLowerCase().includes(q));
  }, [tasks, searchQuery]);

  const messages = useMemo(() => {
    const pendingMessages = optimisticMessages.filter(
      (message) => !activeTaskId || message.taskId === activeTaskId || message.taskId === "new",
    );
    if (taskLoading) {
      return pendingMessages.length > 0
        ? dedupeMessagesForDisplay(pendingMessages)
        : [{ id: "task-loading", role: "assistant", content: "Carregando conversa..." }];
    }
    if (taskError) {
      return [{ id: "task-error", role: "assistant", content: "Nao foi possivel carregar esta conversa." }];
    }
    const responseReady = !agentBusy || displayPlan.percent >= 100 || displayPlan.isTerminal;
    const builtMessages = buildMessagesWithPlanAnchors(
      activeTask,
      currentEvents,
      responseReady,
      planSegments,
      { includeFallback: pendingMessages.length === 0 },
    );
    if (pendingMessages.length === 0) return dedupeMessagesForDisplay(builtMessages);
    const eventBackedMessages = builtMessages.filter((message) => hasEventIndex(message));
    const visibleBuiltMessages = builtMessages
      .filter((message) => message.id !== "welcome")
      .filter((message) => !pendingMessages.some((pending) => (
        isDuplicateUserMessage(pending, message) && !hasEventIndex(message)
      )));
    const pendingNotRepresented = pendingMessages.filter((pending) => !eventBackedMessages.some((message) => (
      isDuplicateUserMessage(pending, message)
    )));
    const mergedMessages = visibleBuiltMessages
      .concat(pendingNotRepresented);
    return dedupeMessagesForDisplay(mergedMessages);
  }, [activeTask, activeTaskId, agentBusy, currentEvents, displayPlan.isTerminal, displayPlan.percent, optimisticMessages, planSegments, taskError, taskLoading]);
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
    setPendingPreparation(null);
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
    if (!pendingPreparation) return;
    const userIndex = matchingUserEventIndex(currentEvents, pendingPreparation);
    if (userIndex < 0) return;
    const pendingTime = messageTimestamp(pendingPreparation);

    const hasRealProgress = currentEvents.some((event, index) => (
      index > userIndex
      && isProgressHandoffEvent(event)
      && (
        pendingTime === null
        || eventTimestamp(event) === null
        || eventTimestamp(event) >= pendingTime - 1000
      )
    ));
    const hasFinished = currentEvents.some((event, index) => (
      index > userIndex
      && event?.type === "assistant_message_done"
      && (
        pendingTime === null
        || eventTimestamp(event) === null
        || eventTimestamp(event) >= pendingTime - 1000
      )
    ));

    if (hasRealProgress || hasFinished) {
      setPendingPreparation(null);
    }
  }, [currentEvents, pendingPreparation]);

  useEffect(() => {
    if (!activeTaskId) return;

    const lastStatusIdx = latestEventIndex(currentEvents, (e) => e.type === "agent_status");
    if (lastStatusIdx >= 0) {
      const status = currentEvents[lastStatusIdx].payload?.status;
      if (status) {
        const isTerminal = ["done", "error", "stopped", "idle"].includes(status);
        const lastUserMsgIdx = latestEventIndex(currentEvents, (e) => e.type === "user_message");
        // Nunca rebaixa para status terminal se chegou uma mensagem nova depois do último status
        if (!isTerminal || lastUserMsgIdx <= lastStatusIdx) {
          setAgentStatus(status);
          setTasks((current) => current.map((task) => (task.id === activeTaskId ? { ...task, status } : task)));
          setActiveTask((current) => (current && current.id === activeTaskId ? { ...current, status } : current));
          if (isTerminal) setStopping(false);
        }
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

    const titleEvent = [...currentEvents].reverse().find((e) => e.type === "task_title_updated");
    if (titleEvent?.payload?.title) {
      setTasks((current) => current.map((task) => (
        task.id === activeTaskId ? { ...task, title: titleEvent.payload.title } : task
      )));
    }

  }, [activeTaskId, currentEvents]);

  useEffect(() => {
    if (!activeTaskId || optimisticMessages.length === 0 || currentEvents.length === 0) return;
    setOptimisticMessages((current) => current.filter((message) => {
      if (message.taskId !== activeTaskId) return true;
      return !currentEvents.some((event) => eventMatchesOptimisticMessage(event, message));
    }));
  }, [activeTaskId, currentEvents, optimisticMessages.length]);

  useEffect(() => {
    if (prevAgentStatusRef.current !== "done" && agentStatus === "done" && activeTaskId) {
      if (document.hidden && "Notification" in window) {
        Notification.requestPermission().then((permission) => {
          if (permission === "granted") {
            const task = tasks.find((t) => t.id === activeTaskId);
            new Notification("Vortax — Tarefa concluída", {
              body: task?.title || task?.description || "A tarefa foi concluída.",
              icon: "/vortax-logo.png",
            });
          }
        });
      }
    }
    prevAgentStatusRef.current = agentStatus;
  }, [agentStatus, activeTaskId, tasks]);

  async function handleSubmit(description, files = []) {
    setSubmitError(null);
    setAgentStatus("queued");
    const now = new Date().toISOString();
    const optimisticId = `optimistic-user-${now}`;
    const optimisticTaskId = activeTaskId || "new";
    const optimisticContent = description || (files.length > 0 ? "Analise esta imagem." : "");
    const shouldPrepareEnvironment = Boolean(optimisticContent) && (files.length > 0 || likelyTaskPrompt(optimisticContent));
    if (optimisticContent) {
      setOptimisticMessages((current) => [
        ...current,
        {
          id: optimisticId,
          role: "user",
          content: optimisticContent,
          createdAt: now,
          taskId: optimisticTaskId,
          clientMessageId: optimisticId,
        },
      ]);
    }
    setPendingPreparation(shouldPrepareEnvironment ? {
      content: optimisticContent,
      createdAt: now,
      id: optimisticId,
      taskId: optimisticTaskId,
      clientMessageId: optimisticId,
    } : null);
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
        setPendingPreparation(null);
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
      setPendingPreparation(null);
      return;
    }

    try {
      if (activeTaskId) {
        await appendTaskMessage(activeTaskId, description, optimisticId, loadUserProfile());
        return;
      }

      const result = await createTask(description, optimisticId, loadUserProfile());
      setOptimisticMessages((current) => current.map((message) => (
        message.id === optimisticId ? { ...message, taskId: result.task_id } : message
      )));
      setPendingPreparation((current) => (
        current?.id === optimisticId ? { ...current, taskId: result.task_id } : current
      ));
      setTasks((current) => [result.task, ...current]);
      setActiveTask(result.task);
      setTaskEvents([]);
      setContextState(null);
      setActiveTaskId(result.task_id);
    } catch {
      setOptimisticMessages((current) => current.filter((message) => message.id !== optimisticId));
      setPendingPreparation((current) => (current?.id === optimisticId ? null : current));
      setAgentStatus("idle");
      setSubmitError("Falha ao enviar. Verifique a conexão e tente novamente.");
      setTimeout(() => setSubmitError(null), 5000);
    }
  }

  async function handleSecureLogin(payload) {
    setAgentStatus("queued");
    if (activeTaskId) {
      await authorizeTask(activeTaskId, payload);
      setTaskEvents((current) => [
        ...current,
        {
          type: "agent_progress",
          task_id: activeTaskId,
          created_at: new Date().toISOString(),
          payload: {
            label: "Login seguro autorizado",
            detail: `Credenciais enviadas por fluxo seguro para ${payload.url}.`,
          },
        },
      ]);
      return;
    }
    const result = await createAuthorizedTask(payload);
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

  function handleDeleteTask(taskId) {
    setTaskToDelete(taskId);
  }

  async function confirmDeleteTask() {
    const taskId = taskToDelete;
    setTaskToDelete(null);
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
    setPendingPreparation(null);
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

            <div className="sidebar-tabs">
              <button
                className={`sidebar-tab ${sidebarTab === "chats" ? "active" : ""}`}
                onClick={() => setSidebarTab("chats")}
                type="button"
              >
                <MessageSquarePlus size={14} />
                Conversas
              </button>
              <button
                className={`sidebar-tab ${sidebarTab === "settings" ? "active" : ""}`}
                onClick={() => setSidebarTab("settings")}
                type="button"
              >
                <Settings size={14} />
                Configurações
              </button>
            </div>

            {sidebarTab === "chats" ? (
              <div className="task-list">
                <div className="task-list-header">
                  <span className="panel-label">Conversas</span>
                  <button onClick={handleNewChat} title="Novo chat" type="button">
                    <MessageSquarePlus size={15} />
                  </button>
                </div>
                {!tasksLoading && !tasksError && tasks.length > 0 && (
                  <input
                    className="task-search"
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Buscar conversas..."
                    type="search"
                    value={searchQuery}
                  />
                )}
                {tasksLoading ? (
                  <p className="panel-state">Carregando conversas...</p>
                ) : tasksError ? (
                  <p className="panel-state error">Nao foi possivel carregar conversas.</p>
                ) : tasks.length === 0 ? (
                  <p className="panel-state">Nenhuma conversa criada.</p>
                ) : filteredTasks.length === 0 ? (
                  <p className="panel-state">Nenhuma conversa encontrada.</p>
                ) : (
                  filteredTasks.map((task) => (
                    <div
                      className={`task-item ${task.id === activeTaskId ? "active" : ""}`}
                      key={task.id}
                      onClick={() => setActiveTaskId(task.id)}
                    >
                      <div className="task-content">
                        <span>{task.title || task.description}</span>
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
            ) : (
              <SettingsPanel />
            )}
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
            {!activeTaskId && !taskLoading ? (
              <OnboardingScreen onSubmit={handleSubmit} />
            ) : (
              <MessageList
                activeSearch={activeSearch}
                agentBusy={agentBusy || Boolean(pendingPreparation)}
                events={currentEvents}
                isTyping={showTyping}
                livePlan={displayPlan}
                messages={messages}
                onComputerFocus={(request) => setComputerFocusRequest({
                  ...request,
                  requestId: `${Date.now()}-${request?.eventIndex ?? "synthetic"}`,
                })}
                pendingPreparation={pendingPreparation}
              />
            )}
            <VortaxComputerDock
              activeTask={activeTask}
              agentStatus={agentStatus}
              connectionState={connectionState}
              events={currentEvents}
              focusRequest={computerFocusRequest}
              livePlan={displayPlan}
              onOpenDetails={() => setDetailsOpen(true)}
            />
            {submitError && (
              <div className="submit-error">{submitError}</div>
            )}
            <Composer
              disabled={backendStatus !== "online"}
              isBusy={agentBusy}
              onSecureLogin={() => setSecureLoginOpen(true)}
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
      <SecureCredentialsDialog
        activeTaskId={activeTaskId}
        disabled={backendStatus !== "online" || agentBusy}
        onClose={() => setSecureLoginOpen(false)}
        onSubmit={handleSecureLogin}
        open={secureLoginOpen}
      />
      <ConfirmDialog confirmation={pendingConfirmation} onAnswer={handleConfirm} />
      <AlertDialog
        cancelLabel="Cancelar"
        confirmLabel="Excluir"
        danger
        message="O histórico salvo no banco de dados será apagado permanentemente."
        onCancel={() => setTaskToDelete(null)}
        onConfirm={confirmDeleteTask}
        open={Boolean(taskToDelete)}
        title="Excluir conversa?"
      />
    </>
  );
}
