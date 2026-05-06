import { Download, FileArchive, Folder } from "lucide-react";

export function FileList({ files, taskId, hasFiles }) {
  const downloadZipUrl = taskId ? `/api/tasks/${taskId}/download` : null;

  return (
    <section className="panel files-panel">
      <div className="panel-title">
        <span>Arquivos</span>
        <small>{files.length}</small>
      </div>

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
            <a className="file-item" href={`/api/files/${file.path}`} key={file.path}>
              <Folder size={15} />
              <span>{file.path}</span>
            </a>
          ))}
        </>
      )}
    </section>
  );
}
