import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowUp, FileArchive, FileSpreadsheet, FileText, Image, Lock, Mic, Monitor, Plus, Square, UploadCloud, X } from "lucide-react";

const ACCEPTED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const ACCEPTED_IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);
const ACCEPTED_DOCUMENT_EXTENSIONS = new Set([".xlsx", ".csv", ".docx", ".pdf", ".txt", ".md", ".json", ".zip"]);
const MAX_ATTACHMENTS = 8;

export const ACCEPTED_ATTACHMENTS = [
  "image/png",
  "image/jpeg",
  "image/webp",
  ".xlsx",
  ".csv",
  ".docx",
  ".pdf",
  ".txt",
  ".md",
  ".json",
  ".zip",
].join(",");

function isImageFile(file) {
  const type = String(file?.type || "").toLowerCase();
  const extension = fileExtension(file?.name);
  return ACCEPTED_IMAGE_TYPES.has(type) || ACCEPTED_IMAGE_EXTENSIONS.has(extension);
}

function fileExtension(name = "") {
  const match = String(name || "").toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? `.${match[1]}` : "";
}

function isAcceptedFile(file) {
  if (!file?.name) return false;
  if (isImageFile(file)) return true;
  return ACCEPTED_DOCUMENT_EXTENSIONS.has(fileExtension(file.name));
}

function fileKey(file) {
  return [file?.name || "", file?.size || 0, file?.lastModified || 0].join(":");
}

function AttachmentIcon({ file }) {
  const extension = fileExtension(file?.name);
  if (isImageFile(file)) return <Image size={18} />;
  if (extension === ".zip") return <FileArchive size={18} />;
  if (extension === ".xlsx" || extension === ".csv") return <FileSpreadsheet size={18} />;
  return <FileText size={18} />;
}

function hasDraggedFiles(event) {
  return Array.from(event?.dataTransfer?.types || []).includes("Files");
}

function formatBytes(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function Composer({ disabled, isBusy = false, onSecureLogin, onStop, onSubmit, stopping = false }) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [dropActive, setDropActive] = useState(false);
  const [attachmentNotice, setAttachmentNotice] = useState("");
  const textareaRef = useRef(null);
  const dragDepthRef = useRef(0);
  const filesRef = useRef([]);

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  useEffect(() => {
    const nextPreviews = files.map((file) => (isImageFile(file) ? URL.createObjectURL(file) : ""));
    setPreviews(nextPreviews);
    return () => {
      for (const preview of nextPreviews) {
        if (preview) URL.revokeObjectURL(preview);
      }
    };
  }, [files]);

  useEffect(() => {
    if (!attachmentNotice) return undefined;
    const timeout = window.setTimeout(() => setAttachmentNotice(""), 4200);
    return () => window.clearTimeout(timeout);
  }, [attachmentNotice]);

  function addFiles(nextFiles) {
    const selected = Array.from(nextFiles || []);
    if (selected.length === 0) return;

    const accepted = selected.filter(isAcceptedFile);
    const rejected = selected.length - accepted.length;
    let ignoredByLimit = 0;
    let ignoredDuplicates = 0;

    const current = filesRef.current;
    const existing = new Set(current.map(fileKey));
    const merged = [...current];
    for (const file of accepted) {
      if (existing.has(fileKey(file))) {
        ignoredDuplicates += 1;
        continue;
      }
      if (merged.length >= MAX_ATTACHMENTS) {
        ignoredByLimit += 1;
        continue;
      }
      existing.add(fileKey(file));
      merged.push(file);
    }
    filesRef.current = merged;
    setFiles(merged);

    const notices = [];
    if (rejected > 0) notices.push(`${rejected} arquivo(s) ignorado(s): formato nao aceito.`);
    if (ignoredByLimit > 0) notices.push(`Limite de ${MAX_ATTACHMENTS} anexos por envio atingido.`);
    if (ignoredDuplicates > 0) notices.push(`${ignoredDuplicates} anexo(s) duplicado(s) ignorado(s).`);
    if (notices.length > 0) setAttachmentNotice(notices.join(" "));
    else setAttachmentNotice("");

    textareaRef.current?.focus();
  }

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
  }, [value]);

  async function submit() {
    const description = value.trim();
    if ((!description && files.length === 0) || disabled || isBusy) return;
    setValue("");
    const selectedFiles = files;
    filesRef.current = [];
    setFiles([]);
    await onSubmit(description, selectedFiles);
  }

  function handleFiles(event) {
    addFiles(event.target.files);
    event.target.value = "";
  }

  useEffect(() => {
    function resetDragState() {
      dragDepthRef.current = 0;
      setDropActive(false);
    }

    function handleDragEnter(event) {
      if (!hasDraggedFiles(event)) return;
      event.preventDefault();
      dragDepthRef.current += 1;
      if (!disabled && !isBusy) setDropActive(true);
    }

    function handleDragOver(event) {
      if (!hasDraggedFiles(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = disabled || isBusy ? "none" : "copy";
      if (!disabled && !isBusy) setDropActive(true);
    }

    function handleDragLeave(event) {
      if (!hasDraggedFiles(event)) return;
      event.preventDefault();
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      if (dragDepthRef.current === 0) setDropActive(false);
    }

    function handleDrop(event) {
      if (!hasDraggedFiles(event)) return;
      event.preventDefault();
      const droppedFiles = event.dataTransfer?.files || [];
      resetDragState();
      if (disabled || isBusy) return;
      addFiles(droppedFiles);
    }

    window.addEventListener("dragenter", handleDragEnter);
    window.addEventListener("dragover", handleDragOver);
    window.addEventListener("dragleave", handleDragLeave);
    window.addEventListener("drop", handleDrop);
    window.addEventListener("blur", resetDragState);

    return () => {
      window.removeEventListener("dragenter", handleDragEnter);
      window.removeEventListener("dragover", handleDragOver);
      window.removeEventListener("dragleave", handleDragLeave);
      window.removeEventListener("drop", handleDrop);
      window.removeEventListener("blur", resetDragState);
    };
  }, [disabled, isBusy]);

  function removeFile(indexToRemove) {
    const nextFiles = filesRef.current.filter((_, index) => index !== indexToRemove);
    filesRef.current = nextFiles;
    setFiles(nextFiles);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const canSend = !disabled && !isBusy && (value.trim() || files.length > 0);
  const inputDisabled = disabled || isBusy;

  return (
    <div className="composer-wrapper">
      <AnimatePresence>
        {dropActive && (
          <motion.div
            className="composer-drop-target"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="composer-drop-target-inner">
              <UploadCloud size={26} />
              <strong>Solte para anexar</strong>
              <span>Imagens, ZIPs, Excel, Word, PDF, CSV, JSON, TXT e Markdown</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <div className={`composer-container ${disabled ? "disabled" : ""} ${isBusy ? "busy" : ""} ${dropActive ? "drag-active" : ""}`}>
        <AnimatePresence>
          {files.length > 0 && (
            <motion.div
              className="composer-attachments"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <AnimatePresence mode="popLayout">
                {files.map((file, index) => (
                  <motion.div
                    className="composer-attachment"
                    key={`${file.name}-${file.size}-${index}`}
                    layout
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={{ type: "spring", stiffness: 300, damping: 22 }}
                  >
                    {isImageFile(file) ? (
                      <img alt="" src={previews[index]} />
                    ) : (
                      <div className="composer-file-preview">
                        <AttachmentIcon file={file} />
                        <span>{file.name}</span>
                        <small>{formatBytes(file.size)}</small>
                      </div>
                    )}
                    <button onClick={() => removeFile(index)} title="Remover anexo" type="button">
                      <X size={12} />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
        <AnimatePresence>
          {attachmentNotice && (
            <motion.div
              className="composer-attachment-notice"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
            >
              {attachmentNotice}
            </motion.div>
          )}
        </AnimatePresence>
        <div className="composer-row">
          <label className="composer-icon-btn" title="Anexar imagem ou arquivo">
            <Plus size={20} />
            <input accept={ACCEPTED_ATTACHMENTS} disabled={inputDisabled} multiple onChange={handleFiles} type="file" />
          </label>
          <textarea
            ref={textareaRef}
            aria-label="Mensagem"
            disabled={inputDisabled}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "Backend indisponível..." : isBusy ? "Vortax esta trabalhando..." : "Enviar mensagem para Vortax"}
            rows={1}
            value={value}
          />
          <button className="composer-icon-btn" disabled={inputDisabled || !onSecureLogin} onClick={onSecureLogin} title="Login seguro" type="button">
            <Lock size={18} />
          </button>
          <span className="composer-computer-pill">
            <Monitor size={14} />
            Computador do Vortax
          </span>
          <button className="composer-voice-btn" disabled={inputDisabled} title="Voz" type="button">
            <Mic size={17} />
          </button>
          <motion.button
            className={`composer-send-btn ${canSend || isBusy ? "active" : ""} ${isBusy ? "stop-mode" : ""}`}
            whileHover={canSend || isBusy ? { scale: 1.08 } : {}}
            whileTap={canSend || isBusy ? { scale: 0.95 } : {}}
            transition={{ type: "spring", stiffness: 400, damping: 15 }}
            disabled={isBusy ? stopping || !onStop : !canSend}
            onClick={isBusy ? onStop : submit}
            title={isBusy ? "Interromper tarefa" : "Enviar"}
            type="button"
          >
            {isBusy ? <Square size={15} /> : <ArrowUp size={18} />}
          </motion.button>
        </div>
      </div>
    </div>
  );
}
