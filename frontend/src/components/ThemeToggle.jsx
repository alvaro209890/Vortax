import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "vortax-theme";

function readTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

// Escuro é o padrão do Vortax; o claro é opcional. O index.html aplica a escolha
// salva antes da primeira pintura, aqui só alternamos.
export function ThemeToggle() {
  const [theme, setTheme] = useState(readTheme);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "light") root.dataset.theme = "light";
    else delete root.dataset.theme;
    try {
      if (theme === "light") localStorage.setItem(STORAGE_KEY, "light");
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // sem storage o tema vale só nesta aba
    }
  }, [theme]);

  const isLight = theme === "light";
  const label = isLight ? "Mudar para tema escuro" : "Mudar para tema claro";

  return (
    <button
      aria-label={label}
      className="icon-ghost-btn theme-toggle"
      onClick={() => setTheme(isLight ? "dark" : "light")}
      title={label}
      type="button"
    >
      {isLight ? <Moon size={16} /> : <Sun size={16} />}
    </button>
  );
}
