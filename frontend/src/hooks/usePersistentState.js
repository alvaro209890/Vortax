import { useEffect, useState } from "react";

export function usePersistentState(key, defaultValue) {
  const [value, setValue] = useState(() => {
    if (typeof window === "undefined") return defaultValue;
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? defaultValue : JSON.parse(stored);
    } catch {
      return defaultValue;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Local storage is optional UI state; ignore blocked/private mode writes.
    }
  }, [key, value]);

  return [value, setValue];
}
