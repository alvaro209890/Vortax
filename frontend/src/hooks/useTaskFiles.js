import { useCallback, useEffect, useRef, useState } from "react";

import { listFiles } from "../lib/api.js";

const DEBOUNCE_MS = 2000;

function eventKey(event, index) {
  if (event.event_id) return `id:${event.event_id}`;
  if (event.id) return `id:${event.id}`;
  return `${index}:${event.type || "event"}:${event.created_at || ""}`;
}

function latestRelevantEvent(events) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type === "files_created" || event.type === "tool_result") {
      return { event, key: eventKey(event, index) };
    }
  }
  return null;
}

function mergeFiles(current, incoming) {
  const byPath = new Map(current.map((file) => [file.path, file]));
  for (const file of incoming) {
    byPath.set(file.path, { ...(byPath.get(file.path) || {}), ...file });
  }
  return Array.from(byPath.values());
}

export function useTaskFiles(activeTaskId, currentEvents, initialFiles) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const processedEventKeyRef = useRef("");
  const pendingRequestRef = useRef(null);
  const lastFetchRef = useRef(0);
  const debounceTimerRef = useRef(null);

  useEffect(() => {
    processedEventKeyRef.current = "";
    setFiles(initialFiles || []);
    setError(null);
    lastFetchRef.current = 0;
  }, [activeTaskId, initialFiles]);

  const fetchFiles = useCallback(
    function fetchFiles(taskId, cancelledRef) {
      if (cancelledRef.current) return;

      // Cancela request pendente anterior
      if (pendingRequestRef.current) {
        pendingRequestRef.current.cancelled = true;
        pendingRequestRef.current = null;
      }

      const requestCtx = { cancelled: false };
      pendingRequestRef.current = requestCtx;

      setLoading(true);
      lastFetchRef.current = Date.now();

      listFiles(taskId)
        .then((data) => {
          if (!cancelledRef.current && !requestCtx.cancelled) {
            setFiles(data.files || []);
            setError(null);
          }
        })
        .catch((reason) => {
          if (!cancelledRef.current && !requestCtx.cancelled) {
            setError(reason);
          }
        })
        .finally(() => {
          if (!cancelledRef.current && !requestCtx.cancelled) {
            setLoading(false);
          }
          if (pendingRequestRef.current === requestCtx) {
            pendingRequestRef.current = null;
          }
        });
    },
    [],
  );

  useEffect(() => {
    if (!activeTaskId) {
      processedEventKeyRef.current = "";
      setFiles([]);
      setLoading(false);
      setError(null);
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      return undefined;
    }

    const relevantEvent = latestRelevantEvent(currentEvents);
    if (
      !relevantEvent ||
      relevantEvent.key === processedEventKeyRef.current
    )
      return undefined;

    processedEventKeyRef.current = relevantEvent.key;

    // Eventos files_created ja trazem os arquivos no payload - merge imediato
    if (
      relevantEvent.event.type === "files_created" &&
      relevantEvent.event.payload?.files?.length
    ) {
      setFiles((current) =>
        mergeFiles(current, relevantEvent.event.payload.files),
      );
      setError(null);
      return undefined;
    }

    // Para tool_result, aplica debounce para evitar excesso de chamadas a API
    const now = Date.now();
    const timeSinceLastFetch = now - lastFetchRef.current;

    if (timeSinceLastFetch < DEBOUNCE_MS) {
      // Agenda fetch para depois do periodo de debounce
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      const cancelledRef = { current: false };
      debounceTimerRef.current = setTimeout(() => {
        debounceTimerRef.current = null;
        if (!cancelledRef.current) {
          fetchFiles(activeTaskId, cancelledRef);
        }
      }, DEBOUNCE_MS - timeSinceLastFetch);

      return () => {
        cancelledRef.current = true;
      };
    }

    // Fora do periodo de debounce, busca imediatamente
    const cancelledRef = { current: false };
    fetchFiles(activeTaskId, cancelledRef);

    return () => {
      cancelledRef.current = true;
      // Cancela o debounce pendente se o efeito for limpo
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
  }, [activeTaskId, currentEvents, fetchFiles]);

  return { error, files, loading, setFiles };
}
