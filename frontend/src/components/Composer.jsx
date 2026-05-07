import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowUp, ImagePlus, X } from "lucide-react";

export function Composer({ disabled, onSubmit }) {
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
    if ((!description && files.length === 0) || disabled) return;
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

  const canSend = !disabled && (value.trim() || files.length > 0);

  return (
    <div className="composer-wrapper">
      <div className={`composer-container ${disabled ? "disabled" : ""}`}>
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
            <ImagePlus size={20} />
            <input accept="image/png,image/jpeg,image/webp" disabled={disabled} multiple onChange={handleFiles} type="file" />
          </label>
          <textarea
            ref={textareaRef}
            aria-label="Mensagem"
            disabled={disabled}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "Backend indisponível..." : "O que você quer que eu faça?"}
            rows={1}
            value={value}
          />
          <motion.button
            className={`composer-send-btn ${canSend ? "active" : ""}`}
            whileHover={canSend ? { scale: 1.08 } : {}}
            whileTap={canSend ? { scale: 0.95 } : {}}
            transition={{ type: "spring", stiffness: 400, damping: 15 }}
            disabled={!canSend}
            onClick={submit}
            title="Enviar"
            type="button"
          >
            <ArrowUp size={18} />
          </motion.button>
        </div>
      </div>
      <motion.span
        className="composer-hint"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4, duration: 0.3 }}
      >
        Pressione Enter para enviar · Shift+Enter para nova linha
      </motion.span>
    </div>
  );
}
