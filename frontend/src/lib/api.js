const explicitBaseUrl = import.meta.env.VITE_API_BASE_URL;
const defaultBaseUrl = `${window.location.protocol}//${window.location.hostname}:8010`;

export const API_BASE_URL = explicitBaseUrl || defaultBaseUrl;
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Erro HTTP ${response.status}`);
  }

  return response.json();
}

export function createTask(description) {
  return request("/api/tasks/", {
    method: "POST",
    body: JSON.stringify({ description }),
  });
}

export function listTasks() {
  return request("/api/tasks/");
}

export function getTask(taskId) {
  return request(`/api/tasks/${taskId}`);
}

export function deleteTask(taskId) {
  return request(`/api/tasks/${taskId}`, { method: "DELETE" });
}

export function appendTaskMessage(taskId, content) {
  return request(`/api/tasks/${taskId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function controlTask(taskId, action) {
  return request(`/api/control/${taskId}/${action}`, { method: "POST" });
}

export function listFiles() {
  return request("/api/files/");
}

export function healthcheck() {
  return request("/health");
}

export function listProviders() {
  return request("/api/providers/");
}
