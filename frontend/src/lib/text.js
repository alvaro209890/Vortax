// Utilitários de texto compartilhados pela linha do tempo, pelo chat e pelo Computador.

// A interface pública mostra "Vortax" no lugar dos nomes internos do motor de código.
export function publicText(value) {
  return String(value ?? "")
    .replace(/\bOpenClaude\b/g, "Vortax")
    .replace(/\bVertex CLI\b/g, "Vortax")
    .replace(/\bVertex\b/g, "Vortax")
    .replace(/\bopenclaude\b/g, "Vortax")
    .replace(/\bvertex\b/g, "Vortax");
}

export function fileName(path = "") {
  return String(path || "").split(/[\\/]/).filter(Boolean).pop() || "";
}

// Encurta caminhos preservando o nome do arquivo: ".../components/App.jsx".
export function shortPath(path = "", max = 42) {
  const value = String(path || "").replace(/\\/g, "/");
  if (value.length <= max) return value;
  const parts = value.split("/");
  const name = parts.pop() || "";
  let kept = name;
  while (parts.length) {
    const candidate = `${parts[parts.length - 1]}/${kept}`;
    if (candidate.length + 2 > max) break;
    kept = candidate;
    parts.pop();
  }
  return kept.length >= value.length ? value : `…/${kept}`;
}

export function hostOf(url = "") {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function isHttpUrl(url = "") {
  return /^https?:\/\//i.test(String(url || ""));
}

// O preview interno é servido pelo backend em /api/files/preview/<tarefa>/; para a pessoa
// isso é "o preview do projeto", não um endereço local a ser copiado.
export function previewPathFromUrl(url = "") {
  const match = String(url || "").match(/\/api\/files\/preview\/[^/]+\/?(.*)$/);
  if (!match) return null;
  return decodeURIComponent(match[1].split("?")[0] || "index.html");
}

export function displayUrl(url = "") {
  const previewPath = previewPathFromUrl(url);
  if (previewPath !== null) return `Preview do projeto · ${previewPath}`;
  return String(url || "");
}

export function clip(value = "", max = 80) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function eventTime(event) {
  const value = event?.created_at ? Date.parse(event.created_at) : NaN;
  return Number.isFinite(value) ? value : 0;
}

export function formatClock(ms) {
  if (!ms) return "";
  return new Date(ms).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatAge(ms, now = Date.now()) {
  if (!ms) return "";
  const seconds = Math.max(0, Math.round((now - ms) / 1000));
  if (seconds < 5) return "agora";
  if (seconds < 60) return `há ${seconds} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  return formatClock(ms);
}

export function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export function formatBytes(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
