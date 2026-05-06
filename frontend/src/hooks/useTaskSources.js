import { useEffect, useState } from "react";

export function useTaskSources(activeTaskId, currentEvents, initialSources) {
  const [sources, setSources] = useState([]);

  useEffect(() => {
    setSources(initialSources || []);
  }, [activeTaskId, initialSources]);

  useEffect(() => {
    const savedSources = currentEvents
      .filter((event) => event.type === "source_saved")
      .map((event) => event.payload);
    if (savedSources.length === 0) return;

    setSources((current) => {
      const byUrl = new Map(current.map((source) => [source.url, source]));
      for (const source of savedSources) {
        byUrl.set(source.url, { ...(byUrl.get(source.url) || {}), ...source });
      }
      return Array.from(byUrl.values()).sort((a, b) => (b.quality_score || 0) - (a.quality_score || 0));
    });
  }, [currentEvents]);

  return { setSources, sources };
}
