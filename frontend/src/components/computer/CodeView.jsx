import { memo, useEffect, useMemo, useRef } from "react";

const MAX_RENDERED_LINES = 4000;

/** Texto com números de linha reais; destaca um intervalo quando ele é conhecido. */
export const CodeView = memo(function CodeView({ text = "", startLine = 1, highlight = null, label }) {
  const containerRef = useRef(null);
  const lines = useMemo(() => {
    const all = String(text).replace(/\n$/, "").split("\n");
    return { rendered: all.slice(0, MAX_RENDERED_LINES), total: all.length };
  }, [text]);

  useEffect(() => {
    if (!highlight || !containerRef.current) return;
    const row = containerRef.current.querySelector(`[data-line="${highlight.from}"]`);
    row?.scrollIntoView({ block: "center" });
  }, [highlight?.from, text]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div aria-label={label} className="vx-code" ref={containerRef} role="region" tabIndex={0}>
      <pre>
        {lines.rendered.map((line, index) => {
          const number = startLine + index;
          const marked = highlight && number >= highlight.from && number <= highlight.to;
          return (
            <div className={`vx-code__row ${marked ? "is-marked" : ""}`} data-line={number} key={number}>
              <span aria-hidden="true" className="vx-code__ln">{number}</span>
              <span className="vx-code__text">{line || " "}</span>
            </div>
          );
        })}
      </pre>
      {lines.total > MAX_RENDERED_LINES ? (
        <p className="vx-code__more">Mostrando {MAX_RENDERED_LINES} de {lines.total} linhas. Baixe o arquivo para ver o restante.</p>
      ) : null}
    </div>
  );
});

/** Diferença de linhas já calculada (compactDiff); "skip" representa trechos iguais omitidos. */
export const DiffView = memo(function DiffView({ lines, label }) {
  if (!lines) {
    return <p className="vx-pane-note">As versões são grandes ou diferentes demais para comparar aqui.</p>;
  }
  if (!lines.some((line) => line.type === "add" || line.type === "del")) {
    return <p className="vx-pane-note">Sem diferenças entre as versões registradas.</p>;
  }
  return (
    <div aria-label={label} className="vx-code vx-code--diff" role="region" tabIndex={0}>
      <pre>
        {lines.map((line, index) => {
          if (line.type === "skip") {
            return <div className="vx-code__skip" key={`skip-${index}`}>⋯ {line.count} {line.count === 1 ? "linha igual" : "linhas iguais"}</div>;
          }
          const sign = line.type === "add" ? "+" : line.type === "del" ? "−" : " ";
          return (
            <div className={`vx-code__row vx-code__row--${line.type}`} key={`${line.type}-${line.oldNo ?? ""}-${line.newNo ?? ""}-${index}`}>
              <span aria-hidden="true" className="vx-code__ln">{line.oldNo ?? ""}</span>
              <span aria-hidden="true" className="vx-code__ln">{line.newNo ?? ""}</span>
              <span className="vx-code__sign" aria-label={line.type === "add" ? "adicionada" : line.type === "del" ? "removida" : undefined}>{sign}</span>
              <span className="vx-code__text">{line.text || " "}</span>
            </div>
          );
        })}
      </pre>
    </div>
  );
});

// Converte o retorno de file_read ("     1|conteúdo") em texto + número inicial.
export function parseNumberedRead(content = "") {
  const rows = String(content).split("\n");
  const parsed = rows.map((row) => row.match(/^\s*(\d+)\|(.*)$/));
  if (!parsed.length || parsed.some((match) => !match)) return { startLine: 1, text: String(content) };
  return { startLine: Number(parsed[0][1]), text: parsed.map((match) => match[2]).join("\n") };
}
