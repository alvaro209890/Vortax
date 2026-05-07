import { useEffect, useState } from "react";

import { getAuthToken, WS_BASE_URL } from "../lib/api.js";

export function useWebSocket(taskId) {
  const [events, setEvents] = useState([]);
  const [connectionState, setConnectionState] = useState("idle");

  useEffect(() => {
    if (!taskId) {
      setEvents([]);
      setConnectionState("idle");
      return undefined;
    }

    let socket = null;
    let cancelled = false;
    let ping = null;
    setEvents([]);
    setConnectionState("connecting");

    getAuthToken().then((token) => {
      if (cancelled) return;
      const query = token ? `?token=${encodeURIComponent(token)}` : "";
      socket = new WebSocket(`${WS_BASE_URL}/ws/${taskId}${query}`);

      socket.addEventListener("open", () => setConnectionState("open"));
      socket.addEventListener("close", () => setConnectionState("closed"));
      socket.addEventListener("error", () => setConnectionState("error"));
      socket.addEventListener("message", (message) => {
        try {
          const event = JSON.parse(message.data);
          if (event.type !== "pong") {
            setEvents((current) => [...current, event]);
          }
        } catch {
          setEvents((current) => [
            ...current,
            {
              type: "error",
              task_id: taskId,
              created_at: new Date().toISOString(),
              payload: { message: "Evento WebSocket invalido" },
            },
          ]);
        }
      });

      ping = window.setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send("ping");
        }
      }, 30000);
    });

    return () => {
      cancelled = true;
      if (ping) window.clearInterval(ping);
      if (socket) socket.close();
    };
  }, [taskId]);

  return { events, connectionState };
}
