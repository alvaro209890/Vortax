import { useMemo } from "react";

import { useWebSocket } from "./useWebSocket.js";

export function useTaskEvents(activeTaskId, fallbackEvents) {
  const { events, connectionState } = useWebSocket(activeTaskId);
  const currentEvents = useMemo(
    () => (events.length > 0 ? events : fallbackEvents),
    [events, fallbackEvents],
  );

  return { connectionState, currentEvents };
}
