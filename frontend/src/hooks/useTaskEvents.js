import { useMemo } from "react";

import { useWebSocket } from "./useWebSocket.js";

function eventKey(event) {
  if (event?.event_id !== undefined && event?.event_id !== null) {
    return `id:${event.event_id}`;
  }
  return [
    "fallback",
    event?.type || "",
    event?.created_at || "",
    JSON.stringify(event?.payload || {}),
  ].join(":");
}

function eventTime(event) {
  const value = event?.created_at ? new Date(event.created_at).getTime() : 0;
  return Number.isFinite(value) ? value : 0;
}

function eventBelongsToTask(event, taskId) {
  return !taskId || !event?.task_id || event.task_id === taskId;
}

function mergeEvents(taskId, fallbackEvents = [], websocketEvents = []) {
  const byKey = new Map();
  [...fallbackEvents, ...websocketEvents].forEach((event, index) => {
    if (!event) return;
    if (!eventBelongsToTask(event, taskId)) return;
    byKey.set(eventKey(event), { event, index });
  });

  return [...byKey.values()]
    .sort((a, b) => eventTime(a.event) - eventTime(b.event) || a.index - b.index)
    .map(({ event }) => event);
}

export function useTaskEvents(activeTaskId, fallbackEvents) {
  const { events, connectionState } = useWebSocket(activeTaskId);
  const currentEvents = useMemo(
    () => mergeEvents(activeTaskId, fallbackEvents, events),
    [activeTaskId, events, fallbackEvents],
  );

  return { connectionState, currentEvents };
}
