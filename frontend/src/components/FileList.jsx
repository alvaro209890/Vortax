import { useState } from "react";
import { ChevronDown, ChevronRight, Download, FileArchive, Folder } from "lucide-react";

function fileDownloadUrl(taskId, path) {
  const safeTaskId = encodeURIComponent(taskId || "");
  const safePath = String(path || "")
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `/api/files/task/${safeTaskId}/${safePath}`;
}

export function FileList({ files, taskId, hasFiles }) {
  const [collapsed, setCollapsed] = useState(false);
  const downloadZipUrl = taskId ? `/api/tasks/${taskId}/download` : null;

  return (
    <section className={`panel files-panel ${collapsed ? "collapsed" : ""}`}>
      <button
        aria-expanded={!collapsed}
        className="files-toggle"
        onClick={() => setCollapsed((current) => !current)}
        type="button"
      >
        <span>Arquivos</span>
        <small>{files.length}</small>
        {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
      </button>

      <div className="files-content">
        {files.length === 0 ? (
          <p className="muted">Nenhum arquivo gerado.</p>
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
      </div>
    </section>
  );
}
