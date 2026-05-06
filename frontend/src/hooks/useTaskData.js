import { useCallback, useEffect, useState } from "react";

import { getTask } from "../lib/api.js";

const emptyTaskData = {
  activeTask: null,
  contextState: null,
  files: [],
  pendingConfirmation: null,
  sources: [],
  taskEvents: [],
};

function pendingConfirmationFrom(events) {
  const lastConfirmation = [...events].reverse().find((event) => event.type === "confirmation_request");
  const lastConfirmationResult = [...events].reverse().find((event) => event.type === "confirmation_result");
  return lastConfirmation && !lastConfirmationResult ? lastConfirmation.payload : null;
}

export function useTaskData(activeTaskId) {
  const [activeTask, setActiveTask] = useState(emptyTaskData.activeTask);
  const [taskEvents, setTaskEvents] = useState(emptyTaskData.taskEvents);
  const [files, setInitialFiles] = useState(emptyTaskData.files);
  const [sources, setInitialSources] = useState(emptyTaskData.sources);
  const [contextState, setContextState] = useState(emptyTaskData.contextState);
  const [pendingConfirmation, setPendingConfirmation] = useState(emptyTaskData.pendingConfirmation);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const resetTaskData = useCallback(() => {
    setActiveTask(emptyTaskData.activeTask);
    setTaskEvents(emptyTaskData.taskEvents);
    setInitialFiles(emptyTaskData.files);
    setInitialSources(emptyTaskData.sources);
    setContextState(emptyTaskData.contextState);
    setPendingConfirmation(emptyTaskData.pendingConfirmation);
    setLoading(false);
    setError(null);
  }, []);

  useEffect(() => {
    if (!activeTaskId) {
      resetTaskData();
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setActiveTask(null);
    setTaskEvents([]);
    setInitialFiles([]);
    setInitialSources([]);
    setContextState(null);
    setPendingConfirmation(null);

    getTask(activeTaskId)
      .then((data) => {
        if (cancelled) return;
        const loadedEvents = data.events || [];
        setActiveTask(data.task || null);
        setTaskEvents(loadedEvents);
        setInitialFiles(data.files || []);
        setInitialSources(data.sources || []);
        setContextState(data.context || null);
        setPendingConfirmation(pendingConfirmationFrom(loadedEvents));
      })
      .catch((reason) => {
        if (cancelled) return;
        setActiveTask(null);
        setTaskEvents([]);
        setInitialFiles([]);
        setInitialSources([]);
        setContextState(null);
        setPendingConfirmation(null);
        setError(reason);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeTaskId, resetTaskData]);

  return {
    activeTask,
    contextState,
    error,
    initialFiles: files,
    initialSources: sources,
    loading,
    pendingConfirmation,
    resetTaskData,
    setActiveTask,
    setContextState,
    setPendingConfirmation,
    setTaskEvents,
    taskEvents,
  };
}
