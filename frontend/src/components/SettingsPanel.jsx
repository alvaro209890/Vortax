import { useState, useEffect } from "react";
import { CheckCircle2, User, Briefcase, MessageSquare, Sliders, Brain, Trash2 } from "lucide-react";
import { listUserMemories, deleteUserMemory } from "../lib/api.js";

const STORAGE_KEY = "vortax_user_profile";

const DEFAULT_PROFILE = {
  name: "",
  profession: "",
  about: "",
  response_style: "",
};

export function loadUserProfile() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const filled = Object.values(parsed).some((v) => String(v || "").trim());
    return filled ? parsed : null;
  } catch {
    return null;
  }
}

export function SettingsPanel() {
  const [profile, setProfile] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? { ...DEFAULT_PROFILE, ...JSON.parse(raw) } : { ...DEFAULT_PROFILE };
    } catch {
      return { ...DEFAULT_PROFILE };
    }
  });
  const [saved, setSaved] = useState(false);

  function handleChange(field, value) {
    setProfile((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  }

  function handleSave() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch {
      // localStorage can fail in private mode
    }
  }

  const anyFilled = Object.values(profile).some((v) => String(v || "").trim());
  const [memories, setMemories] = useState([]);
  const [memoriesLoaded, setMemoriesLoaded] = useState(false);

  useEffect(() => {
    listUserMemories()
      .then((data) => setMemories(data.memories || []))
      .catch(() => {})
      .finally(() => setMemoriesLoaded(true));
  }, []);

  function handleDeleteMemory(memoryId) {
    deleteUserMemory(memoryId)
      .then(() => setMemories((prev) => prev.filter((m) => m.id !== memoryId)))
      .catch(() => {});
  }

  const typeLabels = {
    preference: "Preferência",
    fact: "Fato",
    context: "Contexto",
    feedback: "Feedback",
  };

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <span className="panel-label">Personalize o Vortax</span>
        <p className="settings-subtitle">
          O Vortax usa essas informações para personalizar respostas ao seu perfil.
        </p>
      </div>

      <div className="settings-fields">
        <div className="settings-field">
          <label className="settings-label">
            <User size={13} />
            Como devo te chamar?
          </label>
          <input
            className="settings-input"
            type="text"
            placeholder="Seu nome ou apelido"
            value={profile.name}
            onChange={(e) => handleChange("name", e.target.value)}
            maxLength={120}
          />
        </div>

        <div className="settings-field">
          <label className="settings-label">
            <Briefcase size={13} />
            Qual sua profissão ou área?
          </label>
          <input
            className="settings-input"
            type="text"
            placeholder="Ex: desenvolvedor, designer, estudante de direito..."
            value={profile.profession}
            onChange={(e) => handleChange("profession", e.target.value)}
            maxLength={200}
          />
        </div>

        <div className="settings-field">
          <label className="settings-label">
            <MessageSquare size={13} />
            O que o Vortax deve saber sobre você?
          </label>
          <textarea
            className="settings-textarea"
            placeholder="Seu nível de experiência, interesses, projetos em andamento, contexto importante..."
            value={profile.about}
            onChange={(e) => handleChange("about", e.target.value)}
            maxLength={1000}
            rows={4}
          />
          <span className="settings-char-count">{profile.about.length}/1000</span>
        </div>

        <div className="settings-field">
          <label className="settings-label">
            <Sliders size={13} />
            Como prefere que o Vortax responda?
          </label>
          <textarea
            className="settings-textarea"
            placeholder="Ex: seja direto e use exemplos de código, responda em português formal, prefiro respostas curtas com bullet points..."
            value={profile.response_style}
            onChange={(e) => handleChange("response_style", e.target.value)}
            maxLength={500}
            rows={3}
          />
          <span className="settings-char-count">{profile.response_style.length}/500</span>
        </div>
      </div>

      <div className="settings-footer">
        {!anyFilled && (
          <p className="settings-hint">
            Preencha pelo menos um campo para que o Vortax personalize as respostas.
          </p>
        )}
        <button
          className={`settings-save-btn ${saved ? "saved" : ""}`}
          onClick={handleSave}
          type="button"
        >
          {saved ? (
            <>
              <CheckCircle2 size={15} />
              Salvo
            </>
          ) : (
            "Salvar preferências"
          )}
        </button>
      </div>

      {/* Secao de memorias salvas */}
      <div className="settings-memories">
        <div className="settings-memories-header">
          <Brain size={15} />
          <span>Memórias salvas entre conversas</span>
        </div>
        <p className="settings-memories-hint">
          Use <code>/remember chave: valor</code> no chat para salvar. O Vortax detecta preferências automaticamente.
        </p>
        {!memoriesLoaded && <p className="settings-memories-loading">Carregando...</p>}
        {memoriesLoaded && memories.length === 0 && (
          <p className="settings-memories-empty">Nenhuma memória salva ainda.</p>
        )}
        {memories.length > 0 && (
          <ul className="settings-memories-list">
            {memories.map((mem) => (
              <li key={mem.id} className="settings-memory-item">
                <div className="settings-memory-info">
                  <span className={`settings-memory-type type-${mem.memory_type}`}>
                    {typeLabels[mem.memory_type] || mem.memory_type}
                  </span>
                  <span className="settings-memory-key">{mem.key}</span>
                </div>
                <button
                  className="settings-memory-delete"
                  title="Remover memória"
                  onClick={() => handleDeleteMemory(mem.id)}
                >
                  <Trash2 size={13} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
