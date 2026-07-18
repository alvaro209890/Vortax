import { Download, FileArchive, FileText, Folder, Package, ScrollText } from "lucide-react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { fileDownloadUrl, taskDownloadZipUrl, taskExportSessionUrl } from "../lib/api.js";

export function FileList({ error, files, loading, taskId }) {
  const downloadZipUrl = taskId && files.length > 0 ? taskDownloadZipUrl(taskId) : null;
  const exportSessionUrl = taskId ? taskExportSessionUrl(taskId) : null;
  const projects = files.reduce((groups, file) => {
    const id = file.project_id || "root";
    if (!groups.has(id)) {
      groups.set(id, {
        id,
        name: file.project_name || "Projeto principal",
        root: file.project_root || "",
        type: file.project_type || "generic",
        files: [],
      });
    }
    groups.get(id).files.push(file);
    return groups;
  }, new Map());
  const groupedProjects = Array.from(projects.values());

  return (
    <CollapsiblePanel className="files-panel" count={files.length} storageKey="vortax.inspector.files.collapsed" title="Arquivos">
      {loading ? (
        <p className="panel-state">Carregando arquivos...</p>
      ) : error ? (
        <p className="panel-state error">Nao foi possivel carregar os arquivos.</p>
      ) : (
        <>
          <div className="file-actions-row" style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
            {exportSessionUrl && (
              <a
                className="zip-download-btn"
                href={exportSessionUrl}
                download
                title="Exportar sessão completa (eventos, plano, fontes, prints, arquivos)"
              >
                <ScrollText size={16} />
                <span>Exportar sessão (auditável)</span>
                <Download size={14} />
              </a>
            )}
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
          </div>

          {files.length === 0 ? (
            <p className="panel-state">Nenhum arquivo gerado.</p>
          ) : (
            <div className="project-file-groups">
              {groupedProjects.map((project) => (
                <section className="project-file-group" key={project.id}>
                  <div className="project-file-group-header">
                    <Package size={15} />
                    <div>
                      <strong>{project.name}</strong>
                      <span>{project.type.replace("_", " ")} · {project.files.length} arquivo(s){project.root ? ` · ${project.root}` : ""}</span>
                    </div>
                  </div>
                  {project.files.map((file) => (
                    <a className="file-item" href={fileDownloadUrl(taskId, file.path)} key={file.path}>
                      {file.file_type === "asset" ? <Folder size={15} /> : <FileText size={15} />}
                      <span>{file.path}</span>
                      {file.content_hash ? (
                        <small style={{ opacity: 0.55, marginLeft: 6 }} title={file.content_hash}>
                          {String(file.content_hash).slice(0, 8)}
                        </small>
                      ) : null}
                    </a>
                  ))}
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </CollapsiblePanel>
  );
}
