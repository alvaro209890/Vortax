import { useEffect, useRef, useState } from "react";

import { listFiles } from "../lib/api.js";

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

  useEffect(() => {
    processedEventKeyRef.current = "";
    setFiles(initialFiles || []);
    setError(null);
  }, [activeTaskId, initialFiles]);

  useEffect(() => {
    if (!activeTaskId) {
      processedEventKeyRef.current = "";
      setFiles([]);
      setLoading(false);
      setError(null);
      return undefined;
    }

    const relevantEvent = latestRelevantEvent(currentEvents);
    if (!relevantEvent || relevantEvent.key === processedEventKeyRef.current) return undefined;

    processedEventKeyRef.current = relevantEvent.key;

    if (relevantEvent.event.type === "files_created" && relevantEvent.event.payload?.files?.length) {
      setFiles((current) => mergeFiles(current, relevantEvent.event.payload.files));
      setError(null);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    listFiles(activeTaskId)
      .then((data) => {
        if (!cancelled) {
          setFiles(data.files || []);
          setError(null);
        }
      })
      .catch((reason) => {
        if (!cancelled) setError(reason);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeTaskId, currentEvents]);

  return { error, files, loading, setFiles };
}
