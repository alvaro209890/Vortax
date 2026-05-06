import { useEffect, useRef, useState } from "react";
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
        {files.length > 0 && (
          <div className="composer-attachments">
            {files.map((file, index) => (
              <div className="composer-attachment" key={`${file.name}-${file.size}-${index}`}>
                <img alt="" src={previews[index]} />
                <button onClick={() => removeFile(index)} title="Remover imagem" type="button">
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
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
          <button
            className={`composer-send-btn ${canSend ? "active" : ""}`}
            disabled={!canSend}
            onClick={submit}
            title="Enviar"
            type="button"
          >
            <ArrowUp size={18} />
          </button>
        </div>
      </div>
      <span className="composer-hint">Pressione Enter para enviar · Shift+Enter para nova linha</span>
    </div>
  );
}
