import { useEffect, useState } from "react";

import { getAuthToken, WS_BASE_URL } from "../lib/api.js";

const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 15000;

function eventKey(event) {
  if (event.event_id) return `id:${event.event_id}`;
  if (event.id) return `id:${event.id}`;
  return [
    event.type || "event",
    event.task_id || "",
    event.created_at || "",
    JSON.stringify(event.payload || {}),
  ].join("|");
}

function parseSocketEvent(rawData, taskId) {
  try {
    const event = JSON.parse(rawData);
    if (!event || event.type === "pong") return null;
    return event;
  } catch {
    return {
      type: "error",
      task_id: taskId,
      created_at: new Date().toISOString(),
      payload: { message: "Evento WebSocket invalido" },
    };
  }
}

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
    let reconnectTimer = null;
    let reconnectDelay = INITIAL_RECONNECT_DELAY;
    let flushHandle = null;
    let flushWithAnimationFrame = false;
    const pendingEvents = [];
    const seenEventKeys = new Set();

    function clearPing() {
      if (ping) {
        window.clearInterval(ping);
        ping = null;
      }
    }

    function flushEvents() {
      flushHandle = null;
      const nextEvents = pendingEvents.splice(0, pendingEvents.length);
      if (!nextEvents.length || cancelled) return;
      setEvents((current) => [...current, ...nextEvents]);
    }

    function scheduleFlush() {
      if (flushHandle !== null) return;
      if (typeof window.requestAnimationFrame === "function") {
        flushWithAnimationFrame = true;
        flushHandle = window.requestAnimationFrame(flushEvents);
      } else {
        flushWithAnimationFrame = false;
        flushHandle = window.setTimeout(flushEvents, 50);
      }
    }

    function queueEvent(event) {
      const key = eventKey(event);
      if (seenEventKeys.has(key)) return;
      seenEventKeys.add(key);
      pendingEvents.push(event);
      scheduleFlush();
    }

    function scheduleReconnect() {
      if (cancelled || reconnectTimer) return;
      setConnectionState("reconnecting");
      const delay = reconnectDelay;
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    }

    async function connect() {
      if (cancelled) return;
      clearPing();
      setConnectionState((current) => (current === "reconnecting" ? current : "connecting"));

      const token = await getAuthToken();
      if (cancelled) return;
      if (socket?.readyState === WebSocket.CONNECTING || socket?.readyState === WebSocket.OPEN) {
        socket.close();
      }

      const query = token ? `?token=${encodeURIComponent(token)}` : "";
      socket = new WebSocket(`${WS_BASE_URL}/ws/${taskId}${query}`);

      socket.addEventListener("open", () => {
        reconnectDelay = INITIAL_RECONNECT_DELAY;
        setConnectionState("open");
        clearPing();
        ping = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send("ping");
          }
        }, 30000);
      });

      socket.addEventListener("close", () => {
        clearPing();
        if (cancelled) {
          setConnectionState("closed");
          return;
        }
        scheduleReconnect();
      });

      socket.addEventListener("error", () => {
        if (!cancelled) setConnectionState("error");
      });

      socket.addEventListener("message", (message) => {
        const event = parseSocketEvent(message.data, taskId);
        if (event) queueEvent(event);
      });
    }

    setEvents([]);
    seenEventKeys.clear();
    setConnectionState("connecting");
    connect();

    return () => {
      cancelled = true;
      clearPing();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (flushHandle !== null) {
        if (flushWithAnimationFrame && typeof window.cancelAnimationFrame === "function") {
          window.cancelAnimationFrame(flushHandle);
        } else {
          window.clearTimeout(flushHandle);
        }
      }
      if (socket) socket.close();
    };
  }, [taskId]);

  return { events, connectionState };
}
