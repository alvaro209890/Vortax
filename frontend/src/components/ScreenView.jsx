import { CheckCircle2, ChevronLeft, ChevronRight, Code2, Monitor, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";

function isVertexCommand(command) {
  let text = String(command || "").trim().replace(/^cd\s+[A-Za-z0-9_./-]+\s*&&\s*/, "");
  return text.split(/\s+/)[0] === "vertex";
}

const stageLabels = {
  starting: "Iniciando ambiente",
  planning: "Planejando estrutura",
  creating: "Criando projeto",
  writing_file: "Escrevendo arquivos",
  editing: "Ajustando interface",
  installing: "Preparando dependências",
  reading_file: "Lendo arquivos",
  configuring: "Configurando projeto",
  executing: "Executando Vertex",
  validating: "Abrindo no navegador",
  done: "Projeto pronto",
  error: "Correção necessária",
};

const stageDescriptions = {
  starting: "Abrindo Vertex e preparando a pasta da conversa.",
  planning: "Estimando arquitetura, arquivos e próximos passos.",
  creating: "Gerando estrutura inicial e entradas principais.",
  writing_file: "Escrevendo código e recursos do projeto.",
  editing: "Refinando implementação antes dos testes.",
  installing: "Preparando dependências quando necessário.",
  reading_file: "Revisando arquivos gerados para decidir ajustes.",
  configuring: "Ajustando configurações, scripts ou integrações.",
  executing: "Rodando comandos internos e observando a saída.",
  validating: "Abrindo preview e executando validação local.",
  done: "Entrega finalizada e resultado consolidado.",
  error: "A validação encontrou problemas que precisam ser corrigidos.",
};

const simulatedFiles = ["index.html", "style.css", "script.js", "assets", "validação"];

function latestEvent(events, predicate) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (predicate(events[index])) return events[index];
  }
  return null;
}

function ProgrammingSimulation({ progress }) {
  const payload = progress?.payload || {};
  const stage = payload.stage || "executing";
  const label = stageLabels[stage] || "Programando";
  const message = payload.message || "Organizando arquivos e preparando a entrega.";
  const activeIndex = Math.max(0, Object.keys(stageLabels).indexOf(stage));

  return (
    <div className="programming-stream" aria-label="Vertex programando">
      <div className="programming-stream-header">
        <span><Code2 size={15} /> Vertex programando</span>
        <small>{label}</small>
      </div>
      <div className="programming-stream-grid">
        <div className="programming-files">
          {simulatedFiles.map((file, index) => (
            <div className={`programming-file ${index <= activeIndex % simulatedFiles.length ? "active" : ""}`} key={file}>
              <CheckCircle2 size={12} />
              <span>{file}</span>
            </div>
          ))}
        </div>
        <div className="programming-code" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>
      <div className="programming-stream-footer">
        <strong>{label}</strong>
        <p>{message}</p>
      </div>
      <div className="programming-legend">
        <span>Leitura estimada</span>
        <p>{stageDescriptions[stage] || "A etapa é inferida pelos eventos emitidos pelo Vertex."}</p>
      </div>
    </div>
  );
}

export function ScreenView({ events, connectionState }) {
  const frames = useMemo(
    () => events.filter((event) => event.type === "screen_frame" && event.payload?.image_base64),
    [events],
  );
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    if (frames.length === 0) {
      setSelectedIndex(0);
      return;
    }
    setSelectedIndex((current) => (current >= frames.length - 1 ? frames.length - 1 : current));
  }, [frames.length]);

  useEffect(() => {
    if (frames.length > 0 && !isModalOpen) {
      setSelectedIndex(frames.length - 1);
    }
  }, [frames.length, isModalOpen]);

  const selectedFrame = frames[selectedIndex] || null;
  const latestVertexProgress = useMemo(
    () => latestEvent(events, (event) => event.type === "vertex_progress"),
    [events],
  );
  const lastVertexCall = useMemo(
    () => latestEvent(
      events,
      (event) => event.type === "tool_call" && event.payload?.name === "shell_run" && isVertexCommand(event.payload?.params?.command),
    ),
    [events],
  );
  const lastVertexResult = useMemo(
    () => latestEvent(events, (event) => event.type === "tool_result" && event.payload?.name === "shell_run"),
    [events],
  );
  const vertexRunning = useMemo(() => {
    return Boolean(lastVertexCall && (!lastVertexResult || lastVertexResult.created_at < lastVertexCall.created_at));
  }, [lastVertexCall, lastVertexResult]);
  const image = selectedFrame?.payload?.image_base64;
  const imageAfterVertex = Boolean(lastVertexCall && selectedFrame?.created_at && selectedFrame.created_at > lastVertexCall.created_at);
  const latestStage = latestVertexProgress?.payload?.stage;
  const programmingMode = vertexRunning && !imageAfterVertex && !["validating", "done"].includes(latestStage);
  const caption = selectedFrame?.payload?.caption || selectedFrame?.payload?.title || "Tela do navegador";
  const canGoBack = selectedIndex > 0;
  const canGoForward = selectedIndex < frames.length - 1;

  function goPrevious() {
    setSelectedIndex((current) => Math.max(current - 1, 0));
  }

  function goNext() {
    setSelectedIndex((current) => Math.min(current + 1, frames.length - 1));
  }

  return (
    <CollapsiblePanel
      className="screen-panel"
      count={frames.length > 0 ? `${selectedIndex + 1}/${frames.length}` : connectionState}
      storageKey="vortax.inspector.screen.collapsed"
      title="Tela"
    >
      <div className="screen-view">
        {programmingMode ? (
          <ProgrammingSimulation progress={latestVertexProgress} />
        ) : image ? (
          <>
            <button className="screen-nav left" disabled={!canGoBack} onClick={goPrevious} title="Print anterior" type="button">
              <ChevronLeft size={17} />
            </button>
            <img alt="Tela atual do PC" src={`data:image/jpeg;base64,${image}`} onClick={() => setIsModalOpen(true)} />
            <button className="screen-nav right" disabled={!canGoForward} onClick={goNext} title="Proximo print" type="button">
              <ChevronRight size={17} />
            </button>
            <div className="screen-caption">{caption}</div>
          </>
        ) : (
          <div className="screen-placeholder">
            <Monitor size={34} />
            <p>{vertexRunning ? "Abrindo o navegador para testar o projeto." : "Os prints do stream aparecem aqui."}</p>
          </div>
        )}
      </div>

      {isModalOpen && image && (
        <div className="image-modal-overlay" onClick={() => setIsModalOpen(false)}>
          <button className="image-modal-close" onClick={() => setIsModalOpen(false)} title="Fechar" type="button">
            <X size={18} />
          </button>
          <button className="image-modal-nav left" disabled={!canGoBack} onClick={(event) => { event.stopPropagation(); goPrevious(); }} title="Print anterior" type="button">
            <ChevronLeft size={22} />
          </button>
          <img
            alt="Tela ampliada"
            className="image-modal-content"
            src={`data:image/jpeg;base64,${image}`}
            onClick={(event) => event.stopPropagation()}
          />
          <button className="image-modal-nav right" disabled={!canGoForward} onClick={(event) => { event.stopPropagation(); goNext(); }} title="Proximo print" type="button">
            <ChevronRight size={22} />
          </button>
          <div className="image-modal-counter">
            {selectedIndex + 1} / {frames.length}
          </div>
        </div>
      )}
    </CollapsiblePanel>
  );
}
