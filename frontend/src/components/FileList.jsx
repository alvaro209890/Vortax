import { Download, FileArchive, Folder } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { API_BASE_URL } from "../lib/api.js";

function fileDownloadUrl(taskId, path) {
  const safeTaskId = encodeURIComponent(taskId || "");
  const safePath = String(path || "")
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `${API_BASE_URL}/api/files/task/${safeTaskId}/${safePath}`;
}

export function FileList({ error, files, loading, taskId }) {
  const downloadZipUrl = taskId ? `${API_BASE_URL}/api/tasks/${encodeURIComponent(taskId)}/download` : null;

  return (
    <CollapsiblePanel className="files-panel" count={files.length} storageKey="vortax.inspector.files.collapsed" title="Arquivos">
      {loading ? (
        <p className="panel-state">Carregando arquivos...</p>
      ) : error ? (
        <p className="panel-state error">Nao foi possivel carregar os arquivos.</p>
      ) : files.length === 0 ? (
        <p className="panel-state">Nenhum arquivo gerado.</p>
      ) : (
        <>
          {downloadZipUrl && (
            <a
              className="zip-download-btn"
              href={downloadZipUrl}
              download
              title="Baixar todos os arquivos em ZIP"
            >
              <FileArchive size={16} />
              <span>Baixar projeto (.zip)</span>
              <Download size={14} />
            </a>
          )}

          {files.map((file) => (
            <a className="file-item" href={fileDownloadUrl(taskId, file.path)} key={file.path}>
              <Folder size={15} />
              <span>{file.path}</span>
            </a>
          ))}
        </>
      )}
    </CollapsiblePanel>
  );
}
