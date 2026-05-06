import { useEffect, useRef } from "react";
import { Terminal } from "lucide-react";

export function ShellOutput({ events }) {
  const endRef = useRef(null);

  const shellLines = events
    .filter((event) => event.type === "shell_stdout" || event.type === "shell_stderr")
    .slice(-200);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [shellLines.length]);

  if (shellLines.length === 0) return null;

  return (
    <div className="shell-output">
      <div className="shell-output-header">
        <Terminal size={14} />
        <span>Terminal</span>
        <small>{shellLines.length} linhas</small>
      </div>
      <pre className="shell-output-lines">
        {shellLines.map((event, i) => (
          <span
            className={event.type === "shell_stderr" ? "stderr" : ""}
            key={`${event.created_at}-${i}`}
          >
            {event.payload?.line || ""}
          </span>
        ))}
      </pre>
      <div ref={endRef} />
    </div>
  );
}
