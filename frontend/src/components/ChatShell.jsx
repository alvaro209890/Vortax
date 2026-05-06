import { useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

export function ChatShell({ sidebar, main, inspector }) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  return (
    <div className={`app-shell ${isSidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
      <aside className="sidebar">
        <div className="sidebar-toggle-container">
          <button 
            className="sidebar-toggle-btn" 
            onClick={() => setIsSidebarOpen(false)}
            title="Recolher menu"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
        {sidebar}
      </aside>
      <main className="chat-panel">
        {!isSidebarOpen && (
          <button 
            className="sidebar-open-btn" 
            onClick={() => setIsSidebarOpen(true)}
            title="Expandir menu"
          >
            <PanelLeftOpen size={18} />
          </button>
        )}
        {main}
      </main>
      <aside className="inspector">{inspector}</aside>
    </div>
  );
}
