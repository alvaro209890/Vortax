import { useEffect, useState } from "react";

import { WS_BASE_URL } from "../lib/api.js";

export function useWebSocket(taskId) {
  const [events, setEvents] = useState([]);
  const [connectionState, setConnectionState] = useState("idle");

  useEffect(() => {
    if (!taskId) {
      setEvents([]);
      setConnectionState("idle");
      return undefined;
    }

    const socket = new WebSocket(`${WS_BASE_URL}/ws/${taskId}`);
    setConnectionState("connecting");
    setEvents([]);

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

    const ping = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("ping");
      }
    }, 30000);

    return () => {
      window.clearInterval(ping);
      socket.close();
    };
  }, [taskId]);

  return { events, connectionState };
}
