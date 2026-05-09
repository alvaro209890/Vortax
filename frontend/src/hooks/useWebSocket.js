import { useCallback, useEffect, useRef, useState } from "react";

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
  const taskRef = useRef(taskId);
  taskRef.current = taskId;

  const connect = useCallback(
    async function connect(cancelledRef, stateRef) {
      if (cancelledRef.current) return;

      const { clearPing, scheduleReconnect, queueEvent, setFlush } = stateRef;

      clearPing();
      const currentState = stateRef.connectionState;
      stateRef.setConnectionState(
        currentState === "reconnecting" ? currentState : "connecting",
      );

      const token = await getAuthToken();
      if (cancelledRef.current) return;

      const socketRef = stateRef.socketRef;
      if (
        socketRef.current?.readyState === WebSocket.CONNECTING ||
        socketRef.current?.readyState === WebSocket.OPEN
      ) {
        socketRef.current.close();
      }

      const query = token ? `?token=${encodeURIComponent(token)}` : "";
      const ws = new WebSocket(`${WS_BASE_URL}/ws/${taskRef.current}${query}`);
      socketRef.current = ws;

      ws.addEventListener("open", () => {
        stateRef.reconnectDelay = INITIAL_RECONNECT_DELAY;
        stateRef.setConnectionState("open");
        clearPing();
        stateRef.ping = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 30000);
      });

      ws.addEventListener("close", () => {
        clearPing();
        if (cancelledRef.current) {
          stateRef.setConnectionState("closed");
          return;
        }
        // Pausa reconexao se a aba estiver escondida
        if (document.visibilityState === "hidden") {
          stateRef.setConnectionState("paused");
          stateRef._closeWasHidden = true;
          return;
        }
        scheduleReconnect(cancelledRef, stateRef);
      });

      ws.addEventListener("error", () => {
        if (!cancelledRef.current) stateRef.setConnectionState("error");
      });

      ws.addEventListener("message", (message) => {
        const event = parseSocketEvent(message.data, taskRef.current);
        if (event) queueEvent(event, stateRef, setFlush);
      });
    },
    [],
  );

  useEffect(() => {
    if (!taskId) {
      setEvents([]);
      setConnectionState("idle");
      return undefined;
    }

    const cancelledRef = { current: false };
    const socketRef = { current: null };
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
      if (!nextEvents.length || cancelledRef.current) return;
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

    function setFlush() {
      scheduleFlush();
    }

    function queueEvent(event, state, setFlushFn) {
      const key = eventKey(event);
      const seen = state?.seenEventKeys || seenEventKeys;
      if (seen.has(key)) return;
      seen.add(key);
      const pending = state?.pendingEvents || pendingEvents;
      pending.push(event);
      if (setFlushFn) {
        setFlushFn();
      } else {
        scheduleFlush();
      }
    }

    function scheduleReconnect(cancelled, state) {
      if (cancelled.current || state.reconnectTimer) return;
      // Nao reconectar se offline ou aba escondida
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        state.setConnectionState("offline");
        return;
      }
      if (document.visibilityState === "hidden") {
        state.setConnectionState("paused");
        return;
      }
      state.setConnectionState("reconnecting");
      const delay = state.reconnectDelay;
      state.reconnectDelay = Math.min(state.reconnectDelay * 2, MAX_RECONNECT_DELAY);
      state.reconnectTimer = window.setTimeout(() => {
        state.reconnectTimer = null;
        connect(cancelled, state);
      }, delay);
    }

    // State bag compartilhado com connect()
    const stateRef = {
      clearPing,
      setConnectionState,
      connectionState,
      reconnectDelay,
      reconnectTimer,
      pendingEvents,
      seenEventKeys,
      socketRef,
      ping,
      scheduleFlush,
      setFlush,
      queueEvent,
      scheduleReconnect,
    };

    // Handler de visibilidade da pagina
    function handleVisibilityChange() {
      if (document.visibilityState === "visible" && stateRef._closeWasHidden) {
        stateRef._closeWasHidden = false;
        // Reconectar imediatamente ao voltar
        if (
          cancelledRef.current ||
          socketRef.current?.readyState === WebSocket.OPEN
        )
          return;
        stateRef.reconnectDelay = INITIAL_RECONNECT_DELAY;
        connect(cancelledRef, stateRef);
      }
    }

    // Handler de status da rede
    function handleOnline() {
      if (cancelledRef.current) return;
      if (
        socketRef.current?.readyState === WebSocket.OPEN ||
        socketRef.current?.readyState === WebSocket.CONNECTING
      )
        return;
      stateRef.reconnectDelay = INITIAL_RECONNECT_DELAY;
      connect(cancelledRef, stateRef);
    }

    function handleOffline() {
      stateRef.setConnectionState("offline");
      clearPing();
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    setEvents([]);
    seenEventKeys.clear();
    setConnectionState("connecting");
    connect(cancelledRef, stateRef);

    return () => {
      cancelledRef.current = true;
      clearPing();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (flushHandle !== null) {
        if (
          flushWithAnimationFrame &&
          typeof window.cancelAnimationFrame === "function"
        ) {
          window.cancelAnimationFrame(flushHandle);
        } else {
          window.clearTimeout(flushHandle);
        }
      }
      if (socketRef.current) socketRef.current.close();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [taskId, connect]);

  return { events, connectionState };
}
