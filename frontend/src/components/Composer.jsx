import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowUp, Lock, Mic, Monitor, Plus, Square, X } from "lucide-react";

export function Composer({ disabled, isBusy = false, onSecureLogin, onStop, onSubmit, stopping = false }) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const textareaRef = useRef(null);

  useEffect(() => {
    const nextPreviews = files.map((file) => URL.createObjectURL(file));
    setPreviews(nextPreviews);
    return () => {
      for (const preview of nextPreviews) {
        URL.revokeObjectURL(preview);
      }
    };
  }, [files]);

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
    setFiles([]);
    await onSubmit(description, selectedFiles);
  }

  function handleFiles(event) {
    const selected = Array.from(event.target.files || []);
    setFiles((current) => [...current, ...selected].slice(0, 4));
    event.target.value = "";
  }

  function removeFile(indexToRemove) {
    setFiles((current) => current.filter((_, index) => index !== indexToRemove));
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
      <div className={`composer-container ${disabled ? "disabled" : ""} ${isBusy ? "busy" : ""}`}>
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
                    <img alt="" src={previews[index]} />
                    <button onClick={() => removeFile(index)} title="Remover imagem" type="button">
                      <X size={12} />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="composer-row">
          <label className="composer-icon-btn" title="Anexar imagem">
            <Plus size={20} />
            <input accept="image/png,image/jpeg,image/webp" disabled={inputDisabled} multiple onChange={handleFiles} type="file" />
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
