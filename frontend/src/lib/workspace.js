// Arquivos do workspace: árvore real, versões registradas nas ações e diferenças.

import { fileName } from "./text.js";

const TEXT_EXTENSIONS = new Set([
  "", ".txt", ".md", ".markdown", ".html", ".htm", ".css", ".scss", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
  ".json", ".py", ".sh", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".env", ".xml", ".svg", ".csv", ".sql", ".vue",
  ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".dart", ".lua", ".r",
]);
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp"]);
export const MAX_PREVIEW_BYTES = 400 * 1024;

export function extensionOf(path = "") {
  const name = fileName(path).toLowerCase();
  if (name.startsWith(".") && !name.slice(1).includes(".")) return name === ".env.example" ? ".env" : "";
  const match = name.match(/(\.[a-z0-9]+)$/);
  return match ? match[1] : "";
}

export function fileKind(path = "") {
  const extension = extensionOf(path);
  if (IMAGE_EXTENSIONS.has(extension)) return "image";
  if (extension === ".pdf") return "pdf";
  if (TEXT_EXTENSIONS.has(extension)) return "text";
  return "binary";
}

const LANGUAGES = {
  ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "SCSS", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
  ".jsx": "React JSX", ".ts": "TypeScript", ".tsx": "React TSX", ".json": "JSON", ".py": "Python", ".md": "Markdown",
  ".markdown": "Markdown", ".sh": "Shell", ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML", ".sql": "SQL", ".csv": "CSV",
  ".svg": "SVG", ".xml": "XML", ".txt": "Texto", ".vue": "Vue", ".go": "Go", ".rs": "Rust", ".java": "Java",
};

export function languageLabel(path = "") {
  return LANGUAGES[extensionOf(path)] || (fileKind(path) === "text" ? "Texto" : "Arquivo");
}

// Árvore com pastas antes de arquivos. Cada nó de arquivo guarda o registro original.
export function buildFileTree(files = []) {
  const root = { children: new Map(), name: "", path: "", type: "dir" };
  files.forEach((file) => {
    const path = String(file?.path || "").replace(/\\/g, "/");
    if (!path) return;
    const parts = path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      const childPath = parts.slice(0, index + 1).join("/");
      if (!node.children.has(part)) {
        node.children.set(part, isFile
          ? { file, name: part, path: childPath, type: "file" }
          : { children: new Map(), name: part, path: childPath, type: "dir" });
      }
      node = node.children.get(part);
    });
  });
  const toArray = (node) => {
    if (node.type === "file") return node;
    const children = [...node.children.values()]
      .map(toArray)
      .sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === "dir" ? -1 : 1));
    return { ...node, children };
  };
  return toArray(root).children;
}

// Versões de um arquivo que estão registradas nos eventos (conteúdo enviado por
// file_write, trechos de file_edit/file_append). Não reconstrói nada que não foi registrado.
export function fileVersions(actions = [], path) {
  const versions = [];
  actions.forEach((action) => {
    if (action.target?.type !== "file" || action.target.value !== path) return;
    if (!["file_write", "file_edit", "file_append", "file_read"].includes(action.tool)) return;
    versions.push({
      actionId: action.id,
      at: action.startedAt,
      content: action.tool === "file_write" ? String(action.params?.content ?? "") : null,
      endLine: action.result?.end_line || null,
      kind: action.tool,
      newString: action.tool === "file_edit" ? String(action.params?.new_string ?? "") : null,
      oldString: action.tool === "file_edit" ? String(action.params?.old_string ?? "") : null,
      appended: action.tool === "file_append" ? String(action.params?.content ?? "") : null,
      startLine: action.result?.start_line || null,
      status: action.status,
    });
  });
  return versions;
}

// Conteúdo do arquivo logo após a ação, quando ele pode ser reconstruído só com o registrado:
// a última gravação completa antes dela + edições/acréscimos posteriores aplicados em ordem.
export function contentAfterAction(actions = [], path, actionId) {
  const versions = fileVersions(actions, path).filter((version) => version.kind !== "file_read");
  const stop = versions.findIndex((version) => version.actionId === actionId);
  if (stop < 0) return null;
  let base = null;
  for (let index = stop; index >= 0; index -= 1) {
    if (versions[index].kind === "file_write" && versions[index].status === "done") {
      base = index;
      break;
    }
  }
  if (base === null) return null;
  let content = versions[base].content;
  for (let index = base + 1; index <= stop; index += 1) {
    const version = versions[index];
    if (version.status !== "done") continue;
    if (version.kind === "file_write") content = version.content;
    else if (version.kind === "file_append") content += version.appended;
    else if (version.kind === "file_edit") {
      if (!content.includes(version.oldString)) return null;
      content = content.replace(version.oldString, version.newString);
    }
  }
  return content;
}

export function contentBeforeAction(actions = [], path, actionId) {
  const versions = fileVersions(actions, path).filter((version) => version.kind !== "file_read" && version.status === "done");
  const position = versions.findIndex((version) => version.actionId === actionId);
  if (position <= 0) return null;
  return contentAfterAction(actions, path, versions[position - 1].actionId);
}

const MAX_DIFF_LINES = 2500;
const MAX_EDIT_DISTANCE = 1500;

// Diff de linhas (Myers, O((N+M)·D)); guarda só a faixa usada de cada passo, então a
// memória fica em O(D²). Retorna null quando os arquivos são grandes ou diferentes demais.
export function diffLines(before = "", after = "") {
  const a = String(before).split("\n");
  const b = String(after).split("\n");
  if (a.length > MAX_DIFF_LINES || b.length > MAX_DIFF_LINES) return null;
  const n = a.length;
  const m = b.length;
  const offset = n + m + 1;
  const v = new Int32Array(2 * offset + 2);
  const trace = [];
  let solved = false;
  for (let d = 0; d <= n + m && !solved; d += 1) {
    if (d > MAX_EDIT_DISTANCE) return null;
    trace.push({ start: offset - d - 1, data: v.slice(offset - d - 1, offset + d + 2) });
    for (let k = -d; k <= d; k += 2) {
      let x = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1]) ? v[offset + k + 1] : v[offset + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) {
        x += 1;
        y += 1;
      }
      v[offset + k] = x;
      if (x >= n && y >= m) {
        solved = true;
        break;
      }
    }
  }
  const at = (step, k) => step.data[offset + k - step.start];
  const lines = [];
  let x = n;
  let y = m;
  for (let d = trace.length - 1; d >= 0; d -= 1) {
    const step = trace[d];
    const k = x - y;
    const prevK = k === -d || (k !== d && at(step, k - 1) < at(step, k + 1)) ? k + 1 : k - 1;
    const prevX = at(step, prevK);
    const prevY = prevX - prevK;
    while (x > prevX && y > prevY) {
      lines.push({ type: "same", text: a[x - 1], oldNo: x, newNo: y });
      x -= 1;
      y -= 1;
    }
    if (d > 0) {
      if (x === prevX) lines.push({ type: "add", text: b[y - 1], newNo: y });
      else lines.push({ type: "del", text: a[x - 1], oldNo: x });
    }
    x = prevX;
    y = prevY;
  }
  return lines.reverse();
}

// Mostra só as linhas alteradas com contexto, para diffs longos ficarem legíveis.
export function compactDiff(lines, context = 3) {
  if (!lines) return null;
  const keep = new Array(lines.length).fill(false);
  lines.forEach((line, index) => {
    if (line.type === "same") return;
    for (let i = Math.max(0, index - context); i <= Math.min(lines.length - 1, index + context); i += 1) keep[i] = true;
  });
  const result = [];
  let skipped = 0;
  lines.forEach((line, index) => {
    if (keep[index]) {
      if (skipped) result.push({ type: "skip", count: skipped });
      skipped = 0;
      result.push(line);
    } else {
      skipped += 1;
    }
  });
  if (skipped) result.push({ type: "skip", count: skipped });
  return result;
}

export function diffStats(lines) {
  if (!lines) return { added: 0, removed: 0 };
  return lines.reduce((stats, line) => {
    if (line.type === "add") stats.added += 1;
    if (line.type === "del") stats.removed += 1;
    return stats;
  }, { added: 0, removed: 0 });
}

// index.html preferencial para o preview estático (raiz antes de subpastas).
export function previewEntry(files = []) {
  const candidates = files
    .map((file) => String(file?.path || ""))
    .filter((path) => /(^|\/)index\.html?$/i.test(path))
    .sort((a, b) => a.split("/").length - b.split("/").length || a.localeCompare(b));
  return candidates[0] || null;
}

// Assinatura dos arquivos que afetam o preview, para recarregar só quando eles mudam.
export function previewSignature(files = []) {
  return files
    .filter((file) => /\.(html?|css|js|mjs|json|svg|png|jpe?g|webp|gif)$/i.test(String(file?.path || "")))
    .map((file) => `${file.path}:${file.content_hash || file.modified_at || file.size || ""}`)
    .sort()
    .join("|");
}
