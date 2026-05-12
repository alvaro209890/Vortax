const explicitBaseUrl = import.meta.env.VITE_API_BASE_URL;
const defaultBaseUrl = `${window.location.protocol}//${window.location.hostname}:8010`;

export const API_BASE_URL = explicitBaseUrl || defaultBaseUrl;
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

let authTokenProvider = null;
let cachedAuthToken = "";

export function setAuthTokenProvider(provider) {
  authTokenProvider = provider;
}

export function setCachedAuthToken(token) {
  cachedAuthToken = token || "";
}

export async function getAuthToken(forceRefresh = false) {
  if (!authTokenProvider) return cachedAuthToken;
  try {
    const token = await authTokenProvider(forceRefresh);
    cachedAuthToken = token || "";
    return cachedAuthToken;
  } catch {
    return cachedAuthToken;
  }
}

export function fileDownloadUrl(taskId, path) {
  const safeTaskId = encodeURIComponent(taskId || "");
  const safePath = String(path || "")
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  const token = cachedAuthToken ? `?token=${encodeURIComponent(cachedAuthToken)}` : "";
  return `${API_BASE_URL}/api/files/task/${safeTaskId}/${safePath}${token}`;
}

export function taskDownloadZipUrl(taskId) {
  const token = cachedAuthToken ? `?token=${encodeURIComponent(cachedAuthToken)}` : "";
  return `${API_BASE_URL}/api/tasks/${encodeURIComponent(taskId || "")}/download${token}`;
}

export function taskPreviewUrl(taskId, path = "") {
  const encodedPath = String(path || "")
    .split("/")
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join("/");
  const suffix = encodedPath ? `/${encodedPath}` : "/";
  const token = cachedAuthToken ? `?token=${encodeURIComponent(cachedAuthToken)}` : "";
  return `${API_BASE_URL}/api/files/preview/${encodeURIComponent(taskId || "")}${suffix}${token}`;
}

async function parseErrorMessage(response) {
  const text = await response.text();
  if (!text) return `Erro HTTP ${response.status}`;
  try {
    const data = JSON.parse(text);
    return data.detail || data.message || text;
  } catch {
    return text;
  }
}

async function request(path, options = {}, retryingAfterAuthRefresh = false) {
  const token = await getAuthToken(retryingAfterAuthRefresh);
  const headers = options.body instanceof FormData
    ? {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      }
    : {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      };
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers,
    ...options,
  });

  if (!response.ok) {
    if (response.status === 401 && !retryingAfterAuthRefresh && authTokenProvider) {
      return request(path, options, true);
    }
    const message = await parseErrorMessage(response);
    throw new Error(message || `Erro HTTP ${response.status}`);
  }

  return response.json();
}

export function createTask(description, clientMessageId = "", userProfile = null) {
  return request("/api/tasks/", {
    method: "POST",
    body: JSON.stringify({
      description,
      client_message_id: clientMessageId,
      user_profile: userProfile || undefined,
    }),
  });
}

export function createAuthorizedTask(payload) {
  return request("/api/tasks/authorized", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function authorizeTask(taskId, payload) {
  return request(`/api/tasks/${taskId}/authorization`, {
    method: "POST",
    body: JSON.stringify(payload),
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

export function appendTaskMessage(taskId, content, clientMessageId = "", userProfile = null) {
  return request(`/api/tasks/${taskId}/messages`, {
    method: "POST",
    body: JSON.stringify({
      content,
      client_message_id: clientMessageId,
      user_profile: userProfile || undefined,
    }),
  });
}

function imageFormData(question, files) {
  const formData = new FormData();
  formData.append("question", question);
  for (const file of files) {
    formData.append("files", file);
  }
  return formData;
}

export function createImageTask(question, files) {
  return request("/api/tasks/images", {
    method: "POST",
    body: imageFormData(question, files),
  });
}

export function appendTaskImages(taskId, question, files) {
  return request(`/api/tasks/${taskId}/images`, {
    method: "POST",
    body: imageFormData(question, files),
  });
}

export function confirmTask(taskId, approved) {
  return request(`/api/control/${taskId}/confirm?approved=${approved}`, { method: "POST" });
}

export function listFiles(taskId) {
  if (!taskId) return Promise.resolve({ files: [] });
  return request(`/api/files/task/${taskId}`);
}

export function healthcheck() {
  return request("/health");
}

export function stopTask(taskId) {
  return request(`/api/control/${taskId}/stop`, { method: "POST" });
}

export function listProviders() {
  return request("/api/providers/");
}

export function getTaskPlan(description) {
  return request("/api/tasks/plan", {
    method: "POST",
    body: JSON.stringify({ description }),
  });
}

export function listUserMemories(memoryType = null) {
  const qs = memoryType ? `?memory_type=${encodeURIComponent(memoryType)}` : "";
  return request(`/api/tasks/memories/${qs}`);
}

export function addUserMemory(memoryType, key, content, priority = 5) {
  return request("/api/tasks/memories/", {
    method: "POST",
    body: JSON.stringify({
      memory_type: memoryType,
      key,
      content,
      priority,
    }),
  });
}

export function updateUserMemory(memoryId, content, priority = null) {
  return request(`/api/tasks/memories/${memoryId}`, {
    method: "PUT",
    body: JSON.stringify({ content, ...(priority !== null ? { priority } : {}) }),
  });
}

export function deleteUserMemory(memoryId) {
  return request(`/api/tasks/memories/${memoryId}`, { method: "DELETE" });
}
