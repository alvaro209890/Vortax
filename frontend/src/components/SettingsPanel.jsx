import { useEffect, useState } from "react";
import { Check, Edit3, Settings, X } from "lucide-react";
import { getUserSettings, updateUserSetting } from "../lib/api.js";

function groupByType(fields) {
  const groups = { personal: [], professional: [], preference: [] };
  for (const f of fields) {
    if (groups[f.type]) groups[f.type].push(f);
    else groups.preference.push(f);
  }
  return groups;
}

const typeLabels = {
  personal: "Pessoal",
  professional: "Profissional",
  preference: "Preferências da IA",
};

export default function SettingsPanel() {
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingKey, setEditingKey] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getUserSettings()
      .then((data) => {
        if (!cancelled) {
          setFields(data.fields || []);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError("Não foi possível carregar configurações.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  function startEdit(field) {
    setEditingKey(field.key);
    setEditValue(field.value || "");
  }

  function cancelEdit() {
    setEditingKey(null);
    setEditValue("");
  }

  async function saveEdit(field) {
    const value = editValue.trim();
    if (!value || value === field.value) {
      cancelEdit();
      return;
    }
    setSaving(true);
    try {
      await updateUserSetting(field.key, value, field.type);
      setFields((prev) => prev.map((f) =>
        f.key === field.key ? { ...f, value, is_set: true } : f
      ));
      cancelEdit();
    } catch {
      // keep editing on error
    } finally {
      setSaving(false);
    }
  }

  function handleKeyDown(e, field) {
    if (e.key === "Enter") saveEdit(field);
    if (e.key === "Escape") cancelEdit();
  }

  if (loading) {
    return (
      <div className="settings-panel">
        <div className="settings-header">
          <Settings size={15} />
          <span>Configurações</span>
        </div>
        <p className="panel-state">Carregando...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="settings-panel">
        <div className="settings-header">
          <Settings size={15} />
          <span>Configurações</span>
        </div>
        <p className="panel-state error">{error}</p>
      </div>
    );
  }

  const groups = groupByType(fields);

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <Settings size={15} />
        <span>Configurações</span>
      </div>
      <div className="settings-body">
        {Object.entries(groups).map(([type, items]) => {
          if (items.length === 0) return null;
          return (
            <div key={type} className="settings-group">
              <small className="settings-group-label">{typeLabels[type] || type}</small>
              {items.map((field) => (
                <div key={field.key} className="settings-row">
                  <span className="settings-key">{field.label}</span>
                  {editingKey === field.key ? (
                    <div className="settings-edit-inline">
                      <input
                        autoFocus
                        className="settings-input"
                        disabled={saving}
                        onKeyDown={(e) => handleKeyDown(e, field)}
                        onChange={(e) => setEditValue(e.target.value)}
                        placeholder={field.label}
                        type="text"
                        value={editValue}
                      />
                      <button
                        className="settings-btn save"
                        disabled={saving || !editValue.trim()}
                        onClick={() => saveEdit(field)}
                        title="Salvar"
                        type="button"
                      >
                        <Check size={14} />
                      </button>
                      <button
                        className="settings-btn cancel"
                        disabled={saving}
                        onClick={cancelEdit}
                        title="Cancelar"
                        type="button"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ) : (
                    <div className="settings-value-row">
                      <span className={`settings-value ${field.is_set ? "" : "empty"}`}>
                        {field.is_set ? field.value : "—"}
                      </span>
                      <button
                        className="settings-btn edit"
                        onClick={() => startEdit(field)}
                        title="Editar"
                        type="button"
                      >
                        <Edit3 size={13} />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
