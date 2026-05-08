import { CheckCircle2, ChevronLeft, ChevronRight, Code2, Monitor, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

import { CollapsiblePanel } from "./CollapsiblePanel.jsx";
import { scaleIn } from "../animations/variants.js";

function isCodeAgentCommand(command) {
  let text = String(command || "").trim().replace(/^cd\s+[A-Za-z0-9_./-]+\s*&&\s*/, "");
  return text.split(/\s+/)[0] === "openclaude";
}

function publicText(value) {
  return String(value || "")
    .replace(/\bOpenClaude\b/g, "Vortax")
    .replace(/\bVertex CLI\b/g, "Vortax")
    .replace(/\bVertex\b/g, "Vortax")
    .replace(/\bopenclaude\b/g, "Vortax")
    .replace(/\bvertex\b/g, "Vortax");
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
  executing: "Executando Vortax",
  validating: "Abrindo no navegador",
  done: "Projeto pronto",
  error: "Correção necessária",
};

const stageDescriptions = {
  starting: "Preparando a pasta da conversa.",
  planning: "Estimando arquitetura, arquivos e próximos passos.",
  creating: "Gerando estrutura inicial e entradas principais.",
  writing_file: "Escrevendo código e recursos do projeto.",
  editing: "Refinando implementação antes dos testes.",
  installing: "Preparando dependências quando necessário.",
  reading_file: "Revisando arquivos gerados para decidir ajustes.",
  configuring: "Ajustando configurações, scripts ou integrações.",
  executing: "Rodando comandos internos e observando a saída.",
  validating: "Abrindo preview e revisando a entrega.",
  done: "Entrega finalizada e resultado consolidado.",
  error: "A revisão encontrou problemas que precisam ser corrigidos.",
};

const simulatedFiles = ["index.html", "style.css", "script.js", "assets", "revisão"];

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
  const message = publicText(payload.message || "Organizando arquivos e preparando a entrega.");
  const activeIndex = Math.max(0, Object.keys(stageLabels).indexOf(stage));
  const activeFile = payload.file;

  // Usa os arquivos reais enviados pelo backend ou os simulados como fallback
  const files = useMemo(() => {
    const realFiles = payload.files || [];
    if (realFiles.length > 0) {
      // Mostra ate 5 arquivos; se o arquivo ativo nao estiver no topo, garante que ele apareça
      const list = [...realFiles];
      if (activeFile && !list.slice(0, 5).includes(activeFile)) {
        return [activeFile, ...list.filter(f => f !== activeFile).slice(0, 4)];
      }
      return list.slice(0, 5);
    }
    return ["index.html", "style.css", "script.js", "assets", "revisão"];
  }, [payload.files, activeFile]);

  return (
    <div className="programming-stream" aria-label="Vortax programando">
      <div className="programming-stream-header">
        <span><Code2 size={15} /> Vortax programando</span>
        <small>{label}</small>
      </div>
      <div className="programming-stream-grid">
        <div className="programming-files">
          {files.map((file, index) => {
            const isCurrentlyActive = file === activeFile;
            const isStageActive = index <= activeIndex % files.length;
            const isActive = isCurrentlyActive || (isStageActive && !activeFile);

            return (
              <div className={`programming-file ${isActive ? "active" : ""}`} key={file}>
                <CheckCircle2 size={12} />
                <span>{file}</span>
              </div>
            );
          })}
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
        <p>{stageDescriptions[stage] || "A etapa é inferida pelos eventos do Vortax."}</p>
      </div>
    </div>
  );
}

export function ScreenView({ events, connectionState }) {
  const frames = useMemo(
    () => events.filter((event) => event.type === "screen_frame" && event.payload?.image_base64),
    [events],
  );
  const blockedFrame = [...events].reverse().find((event) => event.type === "screen_frame_blocked");
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
  const latestCodeAgentProgress = useMemo(
    () => latestEvent(events, (event) => event.type === "vertex_progress"),
    [events],
  );
  const lastCodeAgentCall = useMemo(
    () => latestEvent(
      events,
      (event) => event.type === "tool_call" && event.payload?.name === "shell_run" && isCodeAgentCommand(event.payload?.params?.command),
    ),
    [events],
  );
  const lastCodeAgentResult = useMemo(
    () => latestEvent(events, (event) => event.type === "tool_result" && event.payload?.name === "shell_run"),
    [events],
  );
  const codeAgentRunning = useMemo(() => {
    return Boolean(lastCodeAgentCall && (!lastCodeAgentResult || lastCodeAgentResult.created_at < lastCodeAgentCall.created_at));
  }, [lastCodeAgentCall, lastCodeAgentResult]);
  const image = selectedFrame?.payload?.image_base64;
  const imageAfterCodeAgent = Boolean(lastCodeAgentCall && selectedFrame?.created_at && selectedFrame.created_at > lastCodeAgentCall.created_at);
  const latestStage = latestCodeAgentProgress?.payload?.stage;
  const programmingMode = codeAgentRunning && !imageAfterCodeAgent && !["validating", "done"].includes(latestStage);
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
          <ProgrammingSimulation progress={latestCodeAgentProgress} />
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
        ) : blockedFrame ? (
          <div className="screen-placeholder sensitive">
            <Monitor size={34} />
            <p>{blockedFrame.payload?.caption || "Tela ocultada por conter dados sensíveis."}</p>
            <small>{blockedFrame.payload?.url}</small>
          </div>
        ) : (
          <div className="screen-placeholder">
            <Monitor size={34} />
            <p>{codeAgentRunning ? "Abrindo o navegador para testar o projeto." : "Os prints do stream aparecem aqui."}</p>
          </div>
        )}
      </div>

      <AnimatePresence>
        {isModalOpen && image && (
          <motion.div
            className="image-modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setIsModalOpen(false)}
          >
            <motion.button
              className="image-modal-close"
              variants={scaleIn}
              initial="hidden"
              animate="visible"
              exit="exit"
              onClick={() => setIsModalOpen(false)}
              title="Fechar"
              type="button"
            >
              <X size={18} />
            </motion.button>
            <motion.button
              className="image-modal-nav left"
              variants={scaleIn}
              initial="hidden"
              animate="visible"
              exit="exit"
              disabled={!canGoBack}
              onClick={(event) => { event.stopPropagation(); goPrevious(); }}
              title="Print anterior"
              type="button"
            >
              <ChevronLeft size={22} />
            </motion.button>
            <motion.img
              alt="Tela ampliada"
              className="image-modal-content"
              variants={scaleIn}
              initial="hidden"
              animate="visible"
              exit="exit"
              src={`data:image/jpeg;base64,${image}`}
              onClick={(event) => event.stopPropagation()}
            />
            <motion.button
              className="image-modal-nav right"
              variants={scaleIn}
              initial="hidden"
              animate="visible"
              exit="exit"
              disabled={!canGoForward}
              onClick={(event) => { event.stopPropagation(); goNext(); }}
              title="Proximo print"
              type="button"
            >
              <ChevronRight size={22} />
            </motion.button>
            <motion.div
              className="image-modal-counter"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
            >
              {selectedIndex + 1} / {frames.length}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </CollapsiblePanel>
  );
}
