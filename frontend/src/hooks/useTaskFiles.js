import { useEffect, useState } from "react";

import { listFiles } from "../lib/api.js";

export function useTaskFiles(activeTaskId, currentEvents, initialFiles) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setFiles(initialFiles || []);
    setError(null);
  }, [activeTaskId, initialFiles]);

  useEffect(() => {
    if (!activeTaskId) {
      setFiles([]);
      setLoading(false);
      setError(null);
      return;
    }

    const shouldReload = currentEvents.some((event) =>
      event.type === "tool_result" || event.type === "assistant_message_done" || event.type === "files_created"
    );
    if (!shouldReload) return;

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

  useEffect(() => {
    const lastFilesCreated = [...currentEvents].reverse().find((event) => event.type === "files_created");
    if (!lastFilesCreated?.payload?.files) return;

    setFiles((current) => {
      const byPath = new Map(current.map((file) => [file.path, file]));
      for (const file of lastFilesCreated.payload.files) {
        byPath.set(file.path, { ...(byPath.get(file.path) || {}), ...file });
      }
      return Array.from(byPath.values());
    });
  }, [currentEvents]);

  return { error, files, loading, setFiles };
}
