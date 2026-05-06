import { Folder } from "lucide-react";

export function FileList({ files }) {
  return (
    <section className="panel files-panel">
      <div className="panel-title">
        <span>Arquivos</span>
        <small>{files.length}</small>
      </div>
      {files.length === 0 ? (
        <p className="muted">Nenhum arquivo gerado.</p>
      ) : (
        files.map((file) => (
          <a className="file-item" href={`/api/files/${file.path}`} key={file.path}>
            <Folder size={15} />
            <span>{file.path}</span>
          </a>
        ))
      )}
    </section>
  );
}
