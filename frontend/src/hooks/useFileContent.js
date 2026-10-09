import { useEffect, useState } from "react";

import { fileDownloadUrl, getAuthToken } from "../lib/api.js";
import { fileKind, MAX_PREVIEW_BYTES } from "../lib/workspace.js";

// Cache pequeno por versão do arquivo (hash do backend): trocar de arquivo e voltar não
// refaz a requisição; uma versão nova (hash diferente) busca de novo.
const cache = new Map();
const CACHE_LIMIT = 24;

function remember(key, value) {
  cache.delete(key);
  cache.set(key, value);
  if (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
}

/** Conteúdo ATUAL de um arquivo do workspace da tarefa. */
export function useFileContent(taskId, file, enabled = true) {
  const path = file?.path || "";
  const version = file?.content_hash || file?.modified_at || file?.size || "";
  const size = Number(file?.size_bytes ?? file?.size ?? 0);
  const kind = fileKind(path);
  const key = `${taskId}:${path}:${version}`;
  const [state, setState] = useState({ status: "idle", text: "" });

  useEffect(() => {
    if (!enabled || !taskId || !path) {
      setState({ status: "idle", text: "" });
      return undefined;
    }
    if (kind !== "text") {
      setState({ status: kind, text: "" });
      return undefined;
    }
    if (size > MAX_PREVIEW_BYTES) {
      setState({ status: "too_large", text: "" });
      return undefined;
    }
    if (cache.has(key)) {
      setState({ status: "ready", text: cache.get(key) });
      return undefined;
    }
    const controller = new AbortController();
    setState((current) => ({ status: "loading", text: current.status === "ready" ? current.text : "" }));
    getAuthToken()
      .then(() => fetch(fileDownloadUrl(taskId, path), { signal: controller.signal }))
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then((text) => {
        remember(key, text);
        setState({ status: "ready", text });
      })
      .catch((error) => {
        if (error?.name === "AbortError") return;
        setState({ status: "error", text: "", error: error?.message || "erro" });
      });
    return () => controller.abort();
  }, [enabled, key, kind, path, size, taskId]);

  return state;
}
